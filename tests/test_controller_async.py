"""
Async-focused tests for AppController.
"""
import asyncio
import os
import pytest
import json
from unittest.mock import MagicMock, AsyncMock

from app.core import controller as controller_module
from app.core.controller import AppController
from app.core.network import NetworkManager
from app.core.data_plane import DataPlane
from tests.conftest_utils import NetworkManagerMock, DataPlaneMock, SecurityManagerMock

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_controller(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    
    # Mock AsyncHardwareAgent
    mock_agent = MagicMock()
    mock_agent.start = AsyncMock()
    mock_agent.stop = AsyncMock()
    mock_agent.send_command = AsyncMock()
    mock_agent.running = True
    mock_agent.response_queue = asyncio.Queue()
    mock_agent._exe_path = "fake_path"
    
    monkeypatch.setattr("app.core.controller.AsyncHardwareAgent", lambda executable_path=None: mock_agent)
    monkeypatch.setattr("app.core.recovery_controller.AsyncHardwareAgent", lambda executable_path=None: mock_agent)
    
    c = AppController(room_pin="test", agent_override=None, debug=False)
    monkeypatch.setattr(c, "_send_agent_command", _async_noop)
    return c


async def _async_noop(*a, **kw):
    return None


# ---------------------------------------------------------------------------
# 1. Transfer lock serialises concurrent callers
# ---------------------------------------------------------------------------

def test_transfer_lock_serialises_concurrent_receive(tmp_path, monkeypatch):
    c = _make_controller(tmp_path, monkeypatch)
    order = []

    class MockNetwork(NetworkManagerMock):
        async def send_p2p_ack(self, writer, offset, sig, trace_id=None):
            order.append("ack")

    class MockDP(DataPlaneMock):
        def __init__(self, security=None):
            super().__init__(security)
            self._connected = True

        async def receive_file(self, path, size, resume_offset=0, progress_cb=None):
            order.append("recv_start")
            await asyncio.sleep(0)
            order.append("recv_end")

    c.network = MockNetwork()
    c.dp = MockDP()
    c.security = SecurityManagerMock()
    c.my_uuid = "me"
    monkeypatch.setattr(c, "_reset_data_plane", _async_noop)

    payload = {
        "file_meta": {"name": "file.bin", "size": 10, "hash": "a" * 64},
        "challenge_nonce": "12345678",
    }
    writer = object()

    async def run():
        await asyncio.gather(
            c._execute_p2p_receive(payload, None, writer),
            c._execute_p2p_receive(payload, None, writer),
        )

    asyncio.run(run())
    assert order == ["ack", "recv_start", "recv_end", "ack", "recv_start", "recv_end"]


def test_cancelled_error_propagates_from_receive(tmp_path, monkeypatch):
    c = _make_controller(tmp_path, monkeypatch)

    class MockDP(DataPlaneMock):
        def __init__(self, security=None):
            super().__init__(security)
            self._connected = True
        async def receive_file(self, path, size, resume_offset=0, progress_cb=None):
            await asyncio.sleep(60)

    c.network = NetworkManagerMock()
    c.dp = MockDP()
    c.security = SecurityManagerMock()
    c.my_uuid = "me"
    monkeypatch.setattr(c, "_reset_data_plane", _async_noop)

    payload = {
        "file_meta": {"name": "file.bin", "size": 10, "hash": "a" * 64},
        "challenge_nonce": "12345678",
    }

    async def run():
        task = asyncio.create_task(c._execute_p2p_receive(payload, None, None))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


def test_on_disconnected_nulls_network_and_dp(tmp_path, monkeypatch):
    c = _make_controller(tmp_path, monkeypatch)
    c.network = NetworkManagerMock()
    c.dp = DataPlaneMock()
    
    asyncio.run(c._on_disconnected())
    
    assert c.network is None
    assert c.dp is None
    assert c._connection_mode == "IDLE"


def test_leave_session_async_is_reentrant_safe(tmp_path, monkeypatch):
    c = _make_controller(tmp_path, monkeypatch)
    c._running = True
    call_count = []

    class MockNetwork(NetworkManagerMock):
        async def stop(self):
            call_count.append("stop")
            await asyncio.sleep(0)

    c.network = MockNetwork()
    c.dp = DataPlaneMock()

    async def run():
        await asyncio.gather(c._leave_session_async(), c._leave_session_async())

    asyncio.run(run())
    assert call_count == ["stop"]


def test_recover_agent_cancels_old_watchdog(tmp_path, monkeypatch):
    c = _make_controller(tmp_path, monkeypatch)
    c._running = True
    
    async def sentinel():
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            sentinel.cancelled = True
            raise

    async def run():
        sentinel.cancelled = False
        # Create and assign the task
        sentinel_task = asyncio.create_task(sentinel())
        c._dispatcher_task = sentinel_task
        
        await asyncio.sleep(0)
        
        # Recovery will cancel c._dispatcher_task and replace it
        await c._recover_agent()
        
        # We must await the SPECIFIC old task, not the newly replaced c._dispatcher_task
        with pytest.raises(asyncio.CancelledError):
            await sentinel_task
            
        assert sentinel.cancelled is True
        
        # Cleanup the new loop task created by recovery
        if c._dispatcher_task:
            c._dispatcher_task.cancel()

    asyncio.run(run())


def test_receive_file_raises_on_premature_disconnect(tmp_path):
    import struct as _struct
    dest = tmp_path / "out.bin"
    dp = DataPlane(SecurityManagerMock())
    dp._connected = True

    chunk = b"x" * 100
    frame = _struct.pack(">I", len(chunk)) + chunk

    class FakeReader:
        def __init__(self): self.step = 0
        async def readexactly(self, n):
            if self.step == 0:
                self.step = 1
                return frame[:4]
            if self.step == 1:
                self.step = 2
                return frame[4:]
            raise asyncio.IncompleteReadError(b"", n)

    dp._reader = FakeReader()
    with pytest.raises(ConnectionError) as exc:
        asyncio.run(dp.receive_file(str(dest), 200))
    assert "prematurely" in str(exc.value)


def test_elect_host_handles_none_score():
    nm = NetworkManager("local", "Local", 50, "pin", SecurityManagerMock())
    elected = []
    nm.on_host_elected = lambda uid: elected.append(uid)
    nm.peers["remote"] = {"name": "Remote", "ip": "1.1.1.1", "last_seen": 100}
    nm._elect_host()
    assert nm.host_uuid == "local"


def test_elect_host_promotes_high_score_peer():
    nm = NetworkManager("local", "Local", 30, "pin", SecurityManagerMock())
    elected = []
    nm.on_host_elected = lambda uid: elected.append(uid)
    nm.peers["remote"] = {"name": "Remote", "score": 100, "ip": "1.1.1.1", "last_seen": 100}
    nm._elect_host()
    assert nm.host_uuid == "remote"
    assert elected == ["remote"]


def test_on_telemetry_does_not_recreate_network(tmp_path, monkeypatch):
    c = _make_controller(tmp_path, monkeypatch)
    c._on_telemetry({"vitality_score": 10})
    first_nm = c.network
    c._on_telemetry({"vitality_score": 20})
    assert c.network is first_nm
    assert c.network.score == 20


def test_on_disconnected_schedules_auto_recovery(tmp_path, monkeypatch):
    c = _make_controller(tmp_path, monkeypatch)
    c._intended_state = "HOST"
    
    async def fake_recovery():
        await asyncio.sleep(60)
        
    monkeypatch.setattr(c.recovery_controller, "auto_recovery_loop", fake_recovery)
    
    asyncio.run(c._on_disconnected())
    assert c._recovery_task is not None
    # Cleanup
    c._recovery_task.cancel()
