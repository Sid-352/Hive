import asyncio
import os
import struct

import pytest

from app.core.data_plane import DataPlane
from app.core.security import SecurityManager


class _MalformedChannel:
    def __init__(self, payloads):
        self._buf = bytearray(b"".join(payloads))

    async def readexactly(self, n: int) -> bytes:
        if len(self._buf) < n:
            partial = bytes(self._buf)
            self._buf.clear()
            raise asyncio.IncompleteReadError(partial=partial, expected=n)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


@pytest.mark.integration
def test_receiver_preserves_part_when_stream_truncates(tmp_path):
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run integration tests")

    sec = SecurityManager(room_pin="Pin12345")

    receiver = DataPlane(sec)

    expected_size = 65_536
    partial_plain = os.urandom(12_000)
    encrypted_partial = sec.encrypt(partial_plain)
    frame_header = struct.pack(">I", len(encrypted_partial))
    truncated = encrypted_partial[:-7]

    reader = _MalformedChannel([frame_header, truncated])

    # Wire in-memory reader directly — no agent TCP bridge needed
    receiver._reader = reader
    receiver._connected = True

    dest = tmp_path / "bad.bin"

    # DataPlane raises ConnectionError when stream truncates prematurely
    with pytest.raises(ConnectionError):
        asyncio.run(receiver.receive_file(str(dest), expected_size))
    assert dest.exists()
