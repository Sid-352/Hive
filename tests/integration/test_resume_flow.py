import asyncio
import os

import pytest

from app.core.data_plane import DataPlane
from app.core.security import SecurityManager


class _InMemoryChannel:
    def __init__(self):
        self._buf = bytearray()
        self._ready = asyncio.Event()

    async def read(self, n: int) -> bytes:
        while len(self._buf) < n:
            self._ready.clear()
            await self._ready.wait()
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


class _ChannelWriter:
    def __init__(self, channel: _InMemoryChannel):
        self._channel = channel

    def write(self, data: bytes) -> None:
        self._channel._buf.extend(data)
        self._channel._ready.set()

    async def drain(self) -> None:
        await asyncio.sleep(0)


class _ChannelReader:
    def __init__(self, channel: _InMemoryChannel):
        self._channel = channel

    async def readexactly(self, n: int) -> bytes:
        return await self._channel.read(n)


@pytest.mark.integration
def test_data_plane_resume_end_to_end_with_in_memory_channel(tmp_path):
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run integration tests")

    host_sec = SecurityManager(room_pin="Pin12345")
    peer_sec = SecurityManager(room_pin="Pin12345")

    sender = DataPlane(host_sec)
    receiver = DataPlane(peer_sec)

    # Wire in-memory channel directly — no agent TCP bridge needed
    send_channel = _InMemoryChannel()
    recv_channel = _InMemoryChannel()

    # sender writes to send_channel; receiver reads from send_channel
    sender._writer = _ChannelWriter(send_channel)
    receiver._reader = _ChannelReader(send_channel)
    sender._connected = True
    receiver._connected = True

    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src_bytes = os.urandom(65_536 * 2 + 123)
    src.write_bytes(src_bytes)

    resume_offset = 65_536
    dst.write_bytes(src_bytes[:resume_offset])

    async def _run():
        recv_task = asyncio.create_task(
            receiver.receive_file(str(dst), len(src_bytes), resume_offset=resume_offset))
        send_task = asyncio.create_task(
            sender.send_file(str(src), resume_offset=resume_offset))
        await asyncio.gather(recv_task, send_task)

    asyncio.run(_run())

    assert dst.read_bytes() == src_bytes
