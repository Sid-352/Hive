import asyncio
import logging

from app.core import controller as controller_module
from app.core.controller import AppController
from app.core.data_plane import DataPlane
from tests.conftest_utils import NetworkManagerMock, DataPlaneMock, SecurityManagerMock


def test_controller_uses_runtime_base_dir_for_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(controller_module.os, "getcwd", lambda: "C:/unexpected-cwd")

    c = AppController(room_pin="pin", agent_override=None, debug=False)

    assert c.download_dir == str(tmp_path)
    assert c.session.config_file == str(tmp_path / ".hive_config.json")


def test_load_config_logs_warning_on_invalid_json(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    (tmp_path / ".hive_config.json").write_text("{broken", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="hive.controller"):
        AppController(room_pin="pin", agent_override=None, debug=False)

    assert "Config load failed" in caplog.text


def test_load_config_warns_and_falls_back_for_invalid_download_dir(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    bad_dir = str(tmp_path / "does-not-exist")
    (tmp_path / ".hive_config.json").write_text(
        '{"download_dir": "%s", "my_name": "NodeA"}' % bad_dir.replace("\\", "\\\\"),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="hive.controller"):
        c = AppController(room_pin="pin", agent_override=None, debug=False)

    assert c.download_dir == str(tmp_path)
    assert c.my_name == "NodeA"


def test_save_config_logs_warning_on_write_failure(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    c = AppController(room_pin="pin", agent_override=None, debug=False)
    # Point session.config_file at an unwritable path to force the warning
    c.session.config_file = str(tmp_path / "missing" / ".hive_config.json")

    with caplog.at_level(logging.WARNING, logger="hive.controller"):
        c._save_config()

    assert "Config save failed" in caplog.text


def test_on_telemetry_shares_single_security_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    c = AppController(room_pin="pin", agent_override=None, debug=False)

    c._on_telemetry({"vitality_score": 123})

    assert c.network is not None
    assert c.dp is not None
    assert c.network.security is c.security
    assert c.dp.security is c.security


def test_on_connected_starts_overlay_and_data_plane(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    c = AppController(room_pin="pin", agent_override=None, debug=False)

    c.network = NetworkManagerMock()

    sent_commands = []

    async def fake_send_agent_command(command):
        sent_commands.append(command)

    monkeypatch.setattr(c, "_send_agent_command", fake_send_agent_command)
    events = []
    monkeypatch.setattr(
        c.bus,
        "publish",
        lambda event, data=None, **kwargs: events.append((event, data)),
    )

    c._intended_state = "CLIENT"  # required: _on_connected guards on this
    asyncio.run(c._on_connected({"assigned_ip": "192.168.49.5"}))

    assert c.network.started_with == "192.168.49.5"
    assert any(c.get("type") == "START_DATA_PLANE" and c.get("peer_port") == controller_module.P2P_PORT for c in sent_commands)
    assert c._connection_mode == "CLIENT"
    assert (controller_module.HiveEvent.NETWORK_STATE_CHANGED, "CLIENT") in events
    assert (controller_module.HiveEvent.SHOW_SCREEN, "session") in events


def test_leave_session_uses_connection_mode_for_disconnect(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    c = AppController(room_pin="pin", agent_override=None, debug=False)
    c._running = True
    c._connection_mode = "HOST"

    sent = []

    async def fake_send_agent_command(command):
        sent.append(command)

    c.network = NetworkManagerMock()
    c.dp = DataPlaneMock()
    monkeypatch.setattr(c, "_send_agent_command", fake_send_agent_command)

    asyncio.run(c._leave_session_async())
    assert [c["type"] for c in sent] == ["STOP_DATA_PLANE", "STOP_GROUP"]
    assert all("trace_id" in c for c in sent)

    sent.clear()
    c._leaving_session = False  # reset gate for second call
    c._connection_mode = "CLIENT"
    asyncio.run(c._leave_session_async())
    assert [c["type"] for c in sent] == ["STOP_DATA_PLANE", "DISCONNECT"]
    assert all("trace_id" in c for c in sent)


def test_execute_p2p_receive_uses_resume_offset_and_sanitized_path(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    c = AppController(room_pin="pin", agent_override=None, debug=False)
    c.download_dir = str(tmp_path)

    c.network = NetworkManagerMock()
    c.dp = DataPlaneMock()
    c.dp._connected = True
    c.security = SecurityManagerMock()
    c.my_uuid = "12345"
    events = []
    ui_calls = []

    def fake_ui_call_with_future(fut, method, *args):
        ui_calls.append((method, args))
        fut.set_result(True)

    monkeypatch.setattr(
        c.bus,
        "publish",
        lambda event, data=None, **kwargs: events.append((event, data)),
    )
    monkeypatch.setattr(c, "_ui_call_with_future", fake_ui_call_with_future)
    
    import os
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    monkeypatch.setattr(os.path, "getsize", lambda p: 321)
    monkeypatch.setattr(DataPlane, "compute_sha256", staticmethod(lambda _: "a" * 64))

    payload = {
        "file_meta": {
            "name": "../danger.bin",
            "size": 1000,
            "hash": "a" * 64,
        },
        "challenge_nonce": "12345678"
    }
    class MockWriter:
        def get_extra_info(self, key):
            return ("127.0.0.1", 12345) if key == "peername" else None
    writer = MockWriter()

    asyncio.run(c._execute_p2p_receive(payload, None, writer))

    assert c.network.acks == [(writer, 321)]
    assert c.dp.received == [(str(tmp_path / "danger.bin"), 1000)]
    assert (controller_module.HiveEvent.RECEIVE_COMPLETE, None) in events


def test_transfer_req_permit_targets_requester_ip(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    c = AppController(room_pin="pin", agent_override=None, debug=False)

    class FakeWriter:
        def get_extra_info(self, key):
            if key == "peername":
                return ("192.168.137.199", 12345)
            return None

    c.network = NetworkManagerMock()
    submitted = []

    def fake_submit(coro):
        submitted.append(coro)
        return asyncio.run(coro)

    monkeypatch.setattr(c, "_submit", fake_submit)
    writer = FakeWriter()
    asyncio.run(c._on_transfer_req({}, writer))

    assert len(c.network.permits) == 1
    _, ip, port = c.network.permits[0]
    assert ip == "192.168.137.199"
    assert port == c.network.p2p_port


def test_leave_session_clears_pending_send(tmp_path, monkeypatch):
    monkeypatch.setattr(controller_module, "_runtime_base_dir", lambda: str(tmp_path))
    c = AppController(room_pin="pin", agent_override=None, debug=False)
    c._running = True
    c._pending_send = {"file_path": "x"}

    async def fake_send_agent_command(_):
        return None

    c.network = NetworkManagerMock()
    c.dp = DataPlaneMock()
    monkeypatch.setattr(c, "_send_agent_command", fake_send_agent_command)

    asyncio.run(c._leave_session_async())

    assert c._pending_send is None
