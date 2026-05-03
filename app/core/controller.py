import asyncio
import logging
import os
import socket
import sys
import threading
import time
import json
import uuid as _uuid_mod
from typing import Optional

from app.core.agent import AsyncHardwareAgent
from app.core.data_plane import DataPlane
from app.core.events import HiveEvent, HiveEventBus
from app.core.network import NetworkManager, P2P_PORT
from app.core.recovery_controller import RecoveryController
from app.core.security import DEFAULT_ROOM_PIN, SecurityManager
from app.core.session_controller import SessionController
from app.core.session import SessionContext
from app.core.transfer_controller import TransferController

logger = logging.getLogger("hive.controller")

def _runtime_base_dir() -> str:
    if getattr(sys, "frozen", False): return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class LogBridgeHandler(logging.Handler):
    _local = threading.local()
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-7s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
    def emit(self, record):
        if getattr(self._local, 'emitting', False): return
        self._local.emitting = True
        try:
            msg = self.format(record)
            self.bus.publish(HiveEvent.LOG_MESSAGE, msg, no_log=True)
        except Exception: self.handleError(record)
        finally: self._local.emitting = False

class AppController:
    def __init__(self, room_pin: str, agent_override: Optional[str], debug: bool) -> None:
        self._room_pin, self._agent_override, self._debug = room_pin, agent_override, debug
        self._ui, self._running, self._leaving_session = None, False, False
        self._intended_state, self._connection_mode = "IDLE", "IDLE"
        self._target_uuid, self._target_peer_uuid = "", ""
        self._transfer_lock, self._leave_lock = asyncio.Lock(), asyncio.Lock()
        self._recovery_task, self._ip_poll_task, self._watchdog_task = None, None, None
        self._active_transfer_task, self._dispatcher_task = None, None
        self._dispatcher_generation = 0
        self._last_telemetry_time, self._last_telemetry = time.time(), {}
        self._pending_send = None

        self.my_uuid = str(_uuid_mod.UUID(int=_uuid_mod.getnode(), version=1))
        self.my_name = socket.gethostname()[:32]

        base_dir = _runtime_base_dir()
        self.session = SessionContext(
            room_pin=room_pin, node_uuid=self.my_uuid, node_name=self.my_name,
            runtime_dir=base_dir, config_file=os.path.join(base_dir, ".hive_config.json"),
            download_dir=base_dir, security=SecurityManager(room_pin=room_pin)
        )
        self.download_dir = self.session.download_dir
        self.security = self.session.security
        self.agent = AsyncHardwareAgent(executable_path=agent_override)
        self.network, self.dp = None, None
        self._loop = asyncio.new_event_loop()
        self._loop_thread = None
        self.bus = HiveEventBus(self._loop, ui=None)

        log_handler = LogBridgeHandler(self.bus)
        logging.getLogger("hive").addHandler(log_handler)
        if debug: logging.getLogger("hive").setLevel(logging.DEBUG)

        self.session_controller = SessionController(self)
        self.transfer_controller = TransferController(self)
        self.recovery_controller = RecoveryController(self)
        self._load_config()

    def _load_config(self) -> None:
        if os.path.exists(self.session.config_file):
            try:
                with open(self.session.config_file, "r") as f:
                    data = json.load(f)
                    d_dir = data.get("download_dir")
                    if isinstance(d_dir, str) and os.path.isdir(d_dir): self.download_dir = d_dir
                    self.my_name = data.get("my_name", self.my_name)
                    self.session.node_name, self.session.download_dir = self.my_name, self.download_dir
            except Exception as e: logger.warning("Config load failed: %s", e)

    def _save_config(self) -> None:
        try:
            with open(self.session.config_file, "w") as f:
                json.dump({"download_dir": self.download_dir, "my_name": self.my_name}, f)
        except Exception as e: logger.warning("Config save failed: %s", e)

    def update_settings(self, name: str, pin: str, download_dir: str) -> None:
        self.my_name, self.download_dir = name, download_dir
        self.session.node_name, self.session.download_dir = name, download_dir
        if pin != self._room_pin:
            self._room_pin = pin
            self.security = SecurityManager(room_pin=pin)
            self.session.security, self.session.room_pin = self.security, pin
            if self.network: self.network.pin, self.network.security = pin, self.security
            if self.dp: self.dp.security = self.security
        if self.network: self.network.node_name = name
        self._save_config()

    def bind_ui(self, ui) -> None: self._ui = ui; self.bus.ui = ui
    def cancel_transfer(self) -> None:
        if self._active_transfer_task and not self._active_transfer_task.done():
            self._active_transfer_task.cancel()
            self.bus.publish(HiveEvent.TRANSFER_ERROR, "Transfer stopped")
            self._submit(self._reset_data_plane())

    def start(self) -> None:
        if self._running: return
        self._running = True
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="hive-async")
        self._loop_thread.start()
        self._submit(self._async_start())

    def shutdown(self) -> None:
        if not self._running: return
        self.cancel_transfer()
        try: asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop).result(timeout=4)
        except Exception as e: logger.warning("Shutdown timeout: %s", e)
        self._running = False
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread: self._loop_thread.join(timeout=2)
        proc = getattr(self.agent, "_process", None)
        if proc:
            try:
                if os.name == 'nt': import subprocess; subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=1)
                else: proc.terminate()
            except Exception: pass

    async def _async_start(self) -> None:
        try:
            await self.agent.start()
            self.bus.publish(HiveEvent.STATUS_CHANGED, "AGENT READY")
            self._dispatcher_generation += 1
            self._dispatcher_task = asyncio.create_task(self._dispatch_agent_events(self._dispatcher_generation))
            self._last_telemetry_time = time.time()
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            await self._send_agent_command({"type": "GET_TELEMETRY"})
        except Exception as e:
            logger.error("Startup failed: %s", e)
            self.bus.publish(HiveEvent.STATUS_CHANGED, f"ERROR: {e}")

    async def _async_stop(self) -> None:
        for t in [self._recovery_task, self._ip_poll_task, self._watchdog_task, self._dispatcher_task]:
            if t and not t.done(): t.cancel()
        if self.dp: await self.dp.disconnect(); self.dp = None
        if self.network: await self.network.stop(); self.network = None
        await self.agent.stop()

    async def _dispatch_agent_events(self, generation: int) -> None:
        while self._running and self._dispatcher_generation == generation:
            try:
                event = await asyncio.wait_for(self.agent.response_queue.get(), timeout=1.0)
                if self._dispatcher_generation == generation: await self._handle_agent_event(event)
            except asyncio.TimeoutError:
                if not self.agent.running: return
            except Exception as e: logger.error("Event error: %s", e)

    async def _handle_agent_event(self, event: dict) -> None:
        t = event.get("type")
        if t == "STATUS":
            state = event.get("state", "READY")
            if not (self._intended_state in ("HOST", "CLIENT") and state == "READY"):
                self.bus.publish(HiveEvent.STATUS_CHANGED, state)
        elif t == "TELEMETRY": self._on_telemetry(event)
        elif t == "SCAN_RESULT": self.bus.publish(HiveEvent.DISCOVERY_GROUPS_UPDATED, event.get("groups", []))
        elif t == "CONNECTED": await self._on_connected(event); self._refresh_ui()
        elif t == "GROUP_CREATED": await self._on_group_created(event); self._refresh_ui()
        elif t == "DATA_PLANE_STARTED": await self._on_data_plane_started(event)
        elif t == "DISCONNECTED": await self._on_disconnected()
        elif t == "ERROR": logger.error("Agent error: %s", event)

    def _on_telemetry(self, event: dict) -> None:
        self._last_telemetry_time = time.time()
        score = event.get("vitality_score", 0)
        if event != self._last_telemetry:
            self._last_telemetry = event
            self.bus.publish(HiveEvent.TELEMETRY_UPDATED, event)
        if self.network: self.network.update_vitality(score); return
        self.network = NetworkManager(self.my_uuid, self.my_name, score, self._room_pin, self.security, bus=self.bus)
        self.network.on_peer_joined = lambda _: self._refresh_ui()
        self.network.on_peer_left = lambda _: self._refresh_ui()
        self.network.on_host_elected = self._on_host_elected
        self.bus.subscribe(HiveEvent.PEER_DISCOVERED, lambda e,d: self._refresh_ui())
        self.bus.subscribe(HiveEvent.PEER_LEFT, lambda e,d: self._refresh_ui())
        self.bus.subscribe(HiveEvent.HOST_ELECTED, lambda e,d: self.session_controller.on_host_elected(d))
        self.network.on_transfer_req = self._on_transfer_req
        self.network.on_transfer_permit = self._on_transfer_permit
        self.network.on_p2p_handshake = self._on_p2p_handshake
        self.network.on_p2p_done = self._on_p2p_done
        self.network.on_host_lost = self.session_controller.on_host_lost
        self.dp = DataPlane(self.security)

    async def _on_data_plane_started(self, event: dict) -> None:
        if not self.dp: return
        target = event.get("bridge_port") or event.get("pipe_path") or event.get("socket_path")
        if target is None: return
        try:
            await self.dp.connect(str(target))
            self.bus.publish(HiveEvent.DATA_PLANE_STATE_CHANGED, True)
        except Exception as e: logger.error("DP Connect failed: %s", e)

    def scan_groups(self, duration=10): self.session_controller.scan_groups(duration)
    def host_group(self, ruthless=False): self.session_controller.host_group(ruthless)
    def join_group(self, u): self.session_controller.join_group(u)
    def leave_session(self): self.session_controller.leave_session()
    def send_file(self, p, t): self.transfer_controller.send_file(p, t)
    async def _on_connected(self, e): await self.session_controller.on_connected(e)
    async def _on_group_created(self, e): await self.session_controller.on_group_created(e)
    async def _on_disconnected(self): await self.session_controller.on_disconnected()
    async def _watchdog_loop(self): await self.recovery_controller.watchdog_loop()
    async def _recover_agent(self, trace_id="REC-AUTO"): await self.recovery_controller.recover_agent(trace_id)
    async def _poll_for_valid_ip(self, event): await self.session_controller.poll_for_valid_ip(event)
    async def _on_transfer_req(self, d, w): await self.transfer_controller.on_transfer_req(d, w)
    def _on_transfer_permit(self, d): self.transfer_controller.on_transfer_permit(d)
    async def _on_p2p_handshake(self, d, r, w): await self.transfer_controller.on_p2p_handshake(d, r, w)
    def _on_p2p_done(self, u, trace_id="TX-DONE"): self.transfer_controller.on_p2p_done(u, trace_id)
    def _refresh_ui(self): self.session_controller.refresh_ui()
    async def _reset_data_plane(self): await self.transfer_controller.reset_data_plane()
    async def _send_agent_command(self, c):
        if self.agent.running: await self.agent.send_command(c)
    def _submit(self, coro):
        if self._running: return asyncio.run_coroutine_threadsafe(coro, self._loop)
        if asyncio.iscoroutine(coro): coro.close()
    def _ui_call_with_future(self, fut, method, *args):
        if not self._ui: fut.set_result(False); return
        self._ui.after(0, lambda: self._loop.call_soon_threadsafe(lambda: fut.set_result(getattr(self._ui, method)(*args))))
    def _on_host_elected(self, uid: str): self.session_controller.on_host_elected(uid)
    async def _start_overlay(self, ip: str): await self.session_controller.start_overlay(ip)
    async def _leave_session_async(self): await self.session_controller.leave_session_async()
    async def _execute_p2p_receive(self, data: dict, reader, writer): await self.transfer_controller.execute_p2p_receive(data, reader, writer)
    async def _execute_p2p_send(self, ip: str, port: int, pending: dict, trace_id: str = "P2P-SEND"): await self.transfer_controller.execute_p2p_send(ip, port, pending, trace_id)
    async def _start_file_send(self, path: str, target: str): await self.transfer_controller.start_file_send(path, target)
    async def _clear_pending_send_after_timeout(self, pending_obj: dict): await self.transfer_controller.clear_pending_send_after_timeout(pending_obj)
    def _on_progress(self, current: int, total: int): self.transfer_controller.on_progress(current, total)
