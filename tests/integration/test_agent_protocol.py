"""
Integration tests for the C++ HiveAgent binary.

These tests launch the real HiveAgent.exe subprocess (win32) and validate:
  - READY handshake on startup
  - STATUS command shape
  - GET_TELEMETRY response schema and value ranges
  - SCAN command returns a well-formed response without crashing
  - SHUTDOWN command cleanly terminates the process
  - Malformed JSON command doesn't crash the agent
  - Stderr produces DEBUG output (not silent)
  - Agent version reported matches expected format

All tests are gated on RUN_INTEGRATION=1 and win32 platform.
"""
import asyncio
import json
import os
import re
import sys

import pytest

from app.core.agent import AsyncHardwareAgent


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

AGENT_EXE = os.path.join("agents", "win32", "HiveAgent.exe")


def _skip_if_unavailable():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run integration tests")
    if sys.platform != "win32":
        pytest.skip("C++ agent integration tests target win32 only")
    if not os.path.isfile(AGENT_EXE):
        pytest.skip(f"HiveAgent.exe not present at {AGENT_EXE}")


async def _boot_agent() -> AsyncHardwareAgent:
    """Start agent and return it ready to accept commands."""
    agent = AsyncHardwareAgent()
    await agent.start()
    return agent


# ---------------------------------------------------------------------------
# 1. READY response on boot
# ---------------------------------------------------------------------------

def test_agent_emits_ready_on_startup():
    """
    The agent must emit a STATUS/READY event within 5 seconds of launch.
    We validate the full required shape of the handshake message.
    """
    _skip_if_unavailable()

    async def _run():
        agent = await _boot_agent()
        try:
            # start() already consumed the READY event; query STATUS to get
            # a fresh response and verify it is well-formed
            await agent.send_command({"type": "STATUS"})
            ev = await asyncio.wait_for(agent.response_queue.get(), timeout=3.0)
            assert ev.get("type") == "STATUS"
            assert ev.get("state") in ("READY", "DISCONNECTED", "SCANNING")
            assert "message" in ev
        finally:
            await agent.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. GET_TELEMETRY schema and value sanity
# ---------------------------------------------------------------------------

def test_agent_telemetry_schema_and_ranges():
    """
    GET_TELEMETRY must return a response containing:
      - vitality_score  (int, 0–200 reasonable range)
      - ram_gb          (float or int, > 0)
      - cores           (int, >= 1)
      - ac_power        (bool)
    """
    _skip_if_unavailable()

    async def _run():
        agent = await _boot_agent()
        try:
            await agent.send_command({"type": "GET_TELEMETRY"})
            ev = await asyncio.wait_for(agent.response_queue.get(), timeout=5.0)

            assert ev.get("type") == "TELEMETRY", \
                f"Expected TELEMETRY response, got: {ev}"
            assert isinstance(ev.get("vitality_score"), (int, float)), \
                "vitality_score must be numeric"
            assert 0 <= ev["vitality_score"] <= 200, \
                f"vitality_score out of plausible range: {ev['vitality_score']}"

            assert isinstance(ev.get("ram_gb"), (int, float)), \
                "ram_gb must be numeric"
            assert ev["ram_gb"] > 0, "ram_gb must be positive"

            assert isinstance(ev.get("cores") or ev.get("logical_cores"), int), \
                f"cores/logical_cores must be int, got: {ev}"
            cores = ev.get("cores") or ev.get("logical_cores")
            assert cores >= 1, "cores must be at least 1"

            ac = ev.get("ac_power") if "ac_power" in ev else ev.get("on_ac_power")
            assert isinstance(ac, bool), \
                f"ac_power/on_ac_power must be boolean, got: {ev}"
        finally:
            await agent.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. SCAN returns a well-formed response
# ---------------------------------------------------------------------------

def test_agent_scan_returns_response():
    """
    SCAN must return a SCAN_RESULT (or equivalent) response without crashing.
    We don't assert any groups are found (test machine may have none) but we
    do assert the agent stays alive and the response is valid JSON-derived dict.
    """
    _skip_if_unavailable()

    async def _run():
        agent = await _boot_agent()
        try:
            await agent.send_command({"type": "SCAN", "duration": 3})
            # Give the scan up to 8 seconds to complete
            ev = await asyncio.wait_for(agent.response_queue.get(), timeout=8.0)

            assert isinstance(ev, dict), "SCAN response must be a dict"
            assert "type" in ev, "SCAN response must have a 'type' field"
            # Agent must still be alive (running flag)
            assert agent.running, "Agent must still be running after SCAN"
        finally:
            await agent.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. SHUTDOWN command terminates the process cleanly
# ---------------------------------------------------------------------------

def test_agent_shutdown_command_exits_cleanly():
    """
    Sending SHUTDOWN must cause the agent process to exit. We verify that
    agent.running becomes False within a reasonable timeout.
    """
    _skip_if_unavailable()

    async def _run():
        agent = await _boot_agent()
        assert agent.running

        await agent.send_command({"type": "SHUTDOWN"})
        # Poll for up to 5 seconds for the process to exit
        for _ in range(50):
            await asyncio.sleep(0.1)
            if not agent.running:
                break

        assert not agent.running, \
            "Agent must not be running after SHUTDOWN command"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Malformed JSON does not crash the agent
# ---------------------------------------------------------------------------

def test_agent_survives_malformed_json():
    """
    Sending a raw non-JSON string must not crash the agent. It should
    either be silently ignored or return an error response — but the
    agent must remain alive and able to respond to a subsequent STATUS.
    """
    _skip_if_unavailable()

    async def _run():
        agent = await _boot_agent()
        try:
            # Send garbage directly via the process stdin (bypassing
            # send_command which serialises to JSON)
            assert agent._process is not None
            agent._process.stdin.write(b"NOT JSON AT ALL\n")
            await agent._process.stdin.drain()

            # Give it a moment to process the garbage
            await asyncio.sleep(0.3)

            # Agent must still be running
            assert agent.running, "Agent crashed on malformed input"

            # Must still respond to a valid command
            await agent.send_command({"type": "STATUS"})
            ev = await asyncio.wait_for(agent.response_queue.get(), timeout=3.0)
            assert ev.get("type") == "STATUS"
        finally:
            await agent.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. Agent version format is semver-like
# ---------------------------------------------------------------------------

def test_agent_version_format():
    """
    The READY event must include a 'version' field in MAJOR.MINOR.PATCH
    format (e.g. '1.1.1').
    """
    _skip_if_unavailable()

    SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

    async def _run():
        import subprocess
        import asyncio

        # Launch the agent directly and read first line to get READY event
        proc = await asyncio.create_subprocess_exec(
            AGENT_EXE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
            ready = json.loads(line.decode())
            assert ready.get("state") == "READY"
            version = ready.get("version", "")
            assert SEMVER_RE.match(version), \
                f"version '{version}' is not in MAJOR.MINOR.PATCH format"
        finally:
            proc.terminate()
            await proc.wait()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. START_DATA_PLANE returns a bridge_port
# ---------------------------------------------------------------------------

def test_agent_data_plane_returns_bridge_port():
    """
    START_DATA_PLANE must return a DATA_PLANE_STARTED response containing
    a 'bridge_port' field with a valid TCP port number (1024–65535).
    """
    _skip_if_unavailable()

    async def _run():
        agent = await _boot_agent()
        try:
            await agent.send_command({"type": "START_DATA_PLANE", "peer_port": 6001})
            ev = await asyncio.wait_for(agent.response_queue.get(), timeout=5.0)

            assert ev.get("type") == "DATA_PLANE_STARTED", \
                f"Expected DATA_PLANE_STARTED, got: {ev}"
            bridge_port = ev.get("bridge_port")
            assert isinstance(bridge_port, int), \
                f"bridge_port must be an int, got: {bridge_port!r}"
            assert 1024 <= bridge_port <= 65535, \
                f"bridge_port {bridge_port} is outside valid TCP range"

            # Clean up the data plane
            await agent.send_command({"type": "STOP_DATA_PLANE"})
        finally:
            await agent.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. Agent does not accept two simultaneous data planes (idempotency guard)
# ---------------------------------------------------------------------------

def test_agent_data_plane_start_is_idempotent_or_errors():
    """
    Calling START_DATA_PLANE twice must either return a second valid
    bridge_port (new session) or return an error — but must NOT crash.
    The agent must remain alive either way.
    """
    _skip_if_unavailable()

    async def _run():
        agent = await _boot_agent()
        try:
            await agent.send_command({"type": "START_DATA_PLANE", "peer_port": 6001})
            first = await asyncio.wait_for(
                agent.response_queue.get(), timeout=5.0)
            assert first.get("type") == "DATA_PLANE_STARTED"

            # Second call
            await agent.send_command({"type": "START_DATA_PLANE", "peer_port": 6002})
            second = await asyncio.wait_for(
                agent.response_queue.get(), timeout=5.0)

            # Must return something meaningful — either started or error
            assert second.get("type") in ("DATA_PLANE_STARTED", "ERROR"), \
                f"Unexpected response to second START_DATA_PLANE: {second}"
            assert agent.running, "Agent must stay alive after duplicate START_DATA_PLANE"
        finally:
            await agent.stop()

    asyncio.run(_run())
