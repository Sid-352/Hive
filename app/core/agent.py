import asyncio
import json
import logging
import sys
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PASSPHRASE = "Hive12345678"
SERVICE_UUID = "00000001-4856-4147-454E-540000000001"
SSID_PREFIX = "DIRECT-HV-"


def _runtime_base_dir() -> str:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_executable(override: Optional[str]) -> str:
    base_dir = _runtime_base_dir()
    exe_dir = os.path.dirname(sys.executable)

    def _find_relative(rel_path: str) -> str:
        candidates = [
            os.path.join(base_dir, rel_path),
            os.path.join(exe_dir, rel_path),
            os.path.join(exe_dir, "_internal", rel_path),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return candidates[0]

    if override:
        path = override if os.path.isabs(
            override) else _find_relative(override)
    elif sys.platform == "win32":
        path = _find_relative(os.path.join("agents", "win32", "HiveAgent.exe"))
    else:
        path = _find_relative(os.path.join("agents", "linux", "HiveAgent"))

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Hardware Agent binary not found: '{path}'")
    return path


class AsyncHardwareAgent:
    def __init__(self, executable_path: Optional[str] = None):
        self._exe_path = executable_path
        self._process: Optional[asyncio.subprocess.Process] = None
        self._read_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._start_lock = asyncio.Lock()
        self.running = False
        self.version = "unknown"
        self.response_queue = asyncio.Queue()

    async def start(self) -> None:
        async with self._start_lock:
            if self.running:
                raise RuntimeError("AsyncHardwareAgent is already running.")

            exe = _resolve_executable(self._exe_path)
            logger.info("[Agent] Launching: %s", exe)

            try:
                self._process = await asyncio.create_subprocess_exec(
                    exe,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                logger.critical("[Agent] Failed to launch subprocess: %s", exc)
                raise

            self.running = True
            self._read_task = asyncio.create_task(self._read_loop())
            self._stderr_task = asyncio.create_task(self._log_stderr())

            try:
                boot = await asyncio.wait_for(self.response_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.critical("[Agent] Timed out waiting for READY signal.")
                await self.stop()
                raise

            if boot.get("type") != "STATUS" or boot.get("state") != "READY":
                logger.error("[Agent] Unexpected boot message: %s", boot)
                await self.response_queue.put(boot)
            else:
                self.version = boot.get("version", "UNKNOWN")
                logger.info("[Agent] READY (v%s)", self.version)

    async def stop(self) -> None:
        if not self.running:
            return

        logger.info("[Agent] Shutting down...")
        if self._process and self._process.returncode is None:
            try:
                line = json.dumps({"type": "SHUTDOWN"}) + "\n"
                self._process.stdin.write(line.encode())
                await self._process.stdin.drain()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
                logger.info("[Agent] Process exited cleanly.")
            except Exception as exc:
                logger.warning("[Agent] Graceful shutdown failed: %s", exc)
                if self._process:
                    self._process.kill()
                    await self._process.wait()

        self.running = False
        for task in (self._read_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._process = None
        self._read_task = None
        self._stderr_task = None

    async def send_command(self, command_dict: dict) -> None:
        if not self._process or not self.running:
            raise RuntimeError("Agent is not running.")
        if self._process.stdin.is_closing():
            raise OSError("Agent stdin is closed.")

        try:
            line = json.dumps(command_dict) + "\n"
            self._process.stdin.write(line.encode())
            await self._process.stdin.drain()
            if command_dict.get("type") != "GET_TELEMETRY":
                logger.debug("[Agent] → %s", command_dict)
        except (BrokenPipeError, ConnectionResetError) as exc:
            logger.error(
                "[Agent] Broken pipe while sending %s: %s",
                command_dict.get("type"),
                exc)
            self.running = False
            raise
        except Exception as exc:
            logger.error("[Agent] send_command failed: %s", exc)
            raise

    async def _read_loop(self) -> None:
        assert self._process is not None
        try:
            async for raw_line in self._process.stdout:
                line = raw_line.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    await self.response_queue.put(event)
                    if event.get("type") != "TELEMETRY":
                        logger.debug("[Agent] ← %s", event)
                except json.JSONDecodeError:
                    logger.warning("[Agent] Non-JSON line: %r", line)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("[Agent] Read loop error: %s", exc)
        finally:
            self.running = False

    async def _log_stderr(self) -> None:
        assert self._process is not None
        try:
            async for raw_line in self._process.stderr:
                line = raw_line.decode(errors="replace").strip()
                if line:
                    if "Telemetry:" in line:
                        continue
                    level = logging.WARNING if any(
                        k in line.upper() for k in (
                            "ERROR", "FAIL", "CRITICAL")) else logging.DEBUG
                    logger.log(level, "[Agent STDERR] %s", line)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
