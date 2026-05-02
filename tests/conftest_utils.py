import asyncio
from typing import Dict, Optional, Callable, List

class SecurityManagerMock:
    def __init__(self, room_pin="0000"):
        self._room_pin = room_pin
    def encrypt(self, data: bytes, aad: bytes = None) -> bytes:
        return data
    def decrypt(self, data: bytes, aad: bytes = None) -> bytes:
        return data

class NetworkManagerMock:
    def __init__(self, node_uuid="local", node_name="Local", score=0, pin="0000", security=None):
        self.node_uuid = node_uuid
        self.node_name = node_name
        self.score = score
        self.pin = pin
        self.security = security or SecurityManagerMock()
        self.local_ip = "0.0.0.0"
        self.control_port = 5000
        self.p2p_port = 5001
        self.peers: Dict[str, dict] = {}
        self.host_uuid: Optional[str] = None
        self.running = False

        self.on_peer_joined: Optional[Callable] = None
        self.on_peer_left: Optional[Callable] = None
        self.on_host_elected: Optional[Callable] = None
        self.on_transfer_req: Optional[Callable] = None
        self.on_transfer_permit: Optional[Callable] = None
        self.on_p2p_handshake: Optional[Callable] = None
        self.on_host_lost: Optional[Callable] = None

        # Tracking for tests
        self.acks = []  # list of (writer, resume_offset)
        self.permits = []  # list of (writer, target_ip, target_port)
        self.handshakes = []  # list of (writer, filename, size, sha, challenge_nonce)
        self.started_with = None

    async def start(self, local_ip: str) -> None:
        self.local_ip = local_ip
        self.started_with = local_ip
        self.running = True

    async def stop(self) -> None:
        self.running = False

    async def send_transfer_req(self, target_uuid, filename, size, sha, trace_id=None) -> None:
        pass

    async def send_transfer_permit(self, writer, target_ip, target_port, trace_id=None) -> None:
        self.permits.append((writer, target_ip, target_port))

    async def send_p2p_handshake(self, writer, filename, size, sha, challenge_nonce, trace_id=None) -> None:
        self.handshakes.append((writer, filename, size, sha, challenge_nonce))

    async def send_p2p_ack(self, writer, resume_offset, signature, trace_id=None) -> None:
        self.acks.append((writer, resume_offset))

    async def send_p2p_done(self, target_ip: str, target_port: int, trace_id=None) -> None:
        pass

    def update_vitality(self, score: int) -> None:
        self.score = score
        self._elect_host()

    def _elect_host(self, trace_id=None) -> None:
        all_nodes = [(self.node_uuid, self.score)] + [
            (u, p.get("score") or 0) for u, p in self.peers.items()
        ]
        if not all_nodes:
            self.host_uuid = None
            return
        # Handle None scores by defaulting to 0
        best_uid = max(all_nodes, key=lambda x: (x[1] if x[1] is not None else 0, x[0]))[0]
        if best_uid != self.host_uuid:
            self.host_uuid = best_uid
            if self.on_host_elected:
                self.on_host_elected(best_uid)

    async def broadcast_retirement(self) -> None:
        pass

    def decrypt_payload(self, payload: bytes) -> bytes:
        return self.security.decrypt(payload)

class DataPlaneMock:
    def __init__(self, security=None):
        self.security = security or SecurityManagerMock()
        self._connected = False
        # Tracking for tests
        self.received = []  # list of (path, size)
        self.sent = []  # list of (path, resume_offset)

    async def connect(self, path_or_port: str) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def send_file(self, path: str, resume_offset: int = 0, progress_cb=None) -> None:
        self.sent.append((path, resume_offset))
        if progress_cb:
            progress_cb(100, 100)

    async def receive_file(self, path: str, total_size: int, resume_offset: int = 0, progress_cb=None) -> None:
        self.received.append((path, total_size))
        if progress_cb:
            progress_cb(total_size, total_size)
