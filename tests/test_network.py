import asyncio
import json

from app.core.network import (
    CONTROL_PORT,
    MSG_DISCOVERY,
    MSG_P2P_ACK,
    MSG_P2P_HANDSHAKE,
    MSG_P2P_PERMIT,
    MSG_P2P_REQ,
    NetworkManager,
    P2P_PORT,
    _recv_packet,
    _send_packet,
)


class DummySecurity:
    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data


class DummyWriter:
    def __init__(self):
        self.buffer = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class DummyReader:
    def __init__(self, payload: bytes):
        self._payload = payload
        self._offset = 0

    async def readexactly(self, n: int) -> bytes:
        if self._offset + n > len(self._payload):
            raise asyncio.IncompleteReadError(partial=self._payload[self._offset :], expected=n)
        out = self._payload[self._offset : self._offset + n]
        self._offset += n
        return out


def test_process_discovery_adds_peer_and_elects_host():
    nm = NetworkManager("self", "node", 50, "1234", DummySecurity())
    elected = []
    nm.on_host_elected = lambda uid: elected.append(uid)

    nm._process_discovery({"uuid": "peer-a", "name": "Peer A", "score": 100}, "10.0.0.2")

    assert "peer-a" in nm.peers
    assert nm.peers["peer-a"]["ip"] == "10.0.0.2"
    assert nm.host_uuid == "peer-a"
    assert elected == ["peer-a"]


def test_process_discovery_ignores_self_and_missing_uuid():
    nm = NetworkManager("self", "node", 50, "1234", DummySecurity())

    nm._process_discovery({"uuid": "self", "name": "Self", "score": 10}, "10.0.0.2")
    nm._process_discovery({"name": "Missing", "score": 10}, "10.0.0.3")

    assert nm.peers == {}


def test_decrypt_payload_roundtrip_passthrough():
    nm = NetworkManager("self", "node", 50, "1234", DummySecurity())
    payload = b"hello"
    assert nm.decrypt_payload(payload) == payload


def test_send_and_recv_packet_roundtrip():
    writer = DummyWriter()
    msg_type = MSG_P2P_REQ
    payload = json.dumps({"k": "v"}).encode()

    asyncio.run(_send_packet(writer, msg_type, payload))

    reader = DummyReader(writer.buffer)
    recv_type, recv_payload = asyncio.run(_recv_packet(reader))

    assert recv_type == msg_type
    assert recv_payload == payload


def test_send_transfer_permit_and_ack_close_writer():
    nm = NetworkManager("self", "node", 50, "1234", DummySecurity())

    writer_permit = DummyWriter()
    asyncio.run(nm.send_transfer_permit(writer_permit, "10.0.0.2", 5000))
    assert writer_permit.closed is True

    writer_ack = DummyWriter()
    asyncio.run(nm.send_p2p_ack(writer_ack, 123, "valid_sig"))
    # Note: send_p2p_ack no longer closes the writer immediately to avoid race conditions.
    # The dispatcher's finally block or GC will handle it.
    assert writer_ack.closed is False


def test_message_constants_are_stable():
    assert CONTROL_PORT == 5000
    assert P2P_PORT == 5001
    assert MSG_DISCOVERY == 0x01
    assert MSG_P2P_REQ == 0x10
    assert MSG_P2P_PERMIT == 0x11
    assert MSG_P2P_HANDSHAKE == 0x20
    assert MSG_P2P_ACK == 0x21


def test_update_vitality_updates_score():
    nm = NetworkManager("self", "node", 50, "1234", DummySecurity())
    nm.update_vitality(123)
    assert nm.score == 123


def test_prune_stale_peers_removes_old_nodes():
    nm = NetworkManager("self", "node", 50, "1234", DummySecurity())
    removed = []
    nm.on_peer_left = lambda uid: removed.append(uid)
    nm.peers["old"] = {"name": "old", "score": 1, "ip": "10.0.0.2", "last_seen": 0}
    nm._rtt_samples["old"] = [10.0]
    nm._hb_miss_count["old"] = 5

    nm._prune_stale_peers()

    assert "old" not in nm.peers
    assert "old" not in nm._rtt_samples
    assert "old" not in nm._hb_miss_count
    assert removed == ["old"]
