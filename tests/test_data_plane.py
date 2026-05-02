import hashlib
import struct
import asyncio
import io
import os
import pytest

from app.core.data_plane import DataPlane


class MockSecurity:
    def encrypt(self, data: bytes, aad: bytes = None) -> bytes:
        return b"ENC:" + data
    def decrypt(self, data: bytes, aad: bytes = None) -> bytes:
        if data.startswith(b"ENC:"):
            return data[4:]
        return data

class MockReader:
    def __init__(self, data: bytes):
        self.stream = io.BytesIO(data)
    async def readexactly(self, n: int) -> bytes:
        res = self.stream.read(n)
        if len(res) < n:
            raise asyncio.IncompleteReadError(res, n)
        return res

class MockWriter:
    def __init__(self):
        self.data = b""
    def write(self, data: bytes):
        self.data += data
    async def drain(self):
        pass

def test_get_resume_offset_existing_file(tmp_path):
    target = tmp_path / "movie.mp4"
    target.write_bytes(b"x" * 123)
    assert DataPlane.get_resume_offset(str(target)) == 123

def test_get_resume_offset_missing_file(tmp_path):
    target = tmp_path / "missing.bin"
    assert DataPlane.get_resume_offset(str(target)) == 0

def test_compute_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "data.bin"
    content = b"hive test data"
    path.write_bytes(content)
    assert DataPlane.compute_sha256(str(path)) == hashlib.sha256(content).hexdigest()

def test_send_file_framed(tmp_path):
    path = tmp_path / "send.bin"
    content = b"hello world"
    path.write_bytes(content)
    
    sec = MockSecurity()
    dp = DataPlane(sec)
    dp._connected = True
    writer = MockWriter()
    dp._writer = writer
    
    asyncio.run(dp.send_file(str(path)))
    
    # Check framing: [4 bytes length] [ENC:payload]
    # Encrypted payload is b"ENC:hello world" (4 + 11 = 15 bytes)
    expected_payload = b"ENC:hello world"
    expected_len = len(expected_payload)
    assert len(writer.data) == 4 + expected_len
    length = struct.unpack(">I", writer.data[:4])[0]
    assert length == expected_len
    assert writer.data[4:] == expected_payload

def test_receive_file_framed(tmp_path):
    dest = tmp_path / "recv.bin"
    content = b"secret data"
    encrypted = b"ENC:" + content
    payload = struct.pack(">I", len(encrypted)) + encrypted
    
    sec = MockSecurity()
    dp = DataPlane(sec)
    dp._connected = True
    reader = MockReader(payload)
    dp._reader = reader
    
    asyncio.run(dp.receive_file(str(dest), len(content)))
    
    assert dest.read_bytes() == content

def test_send_file_requires_connection(tmp_path):
    path = tmp_path / "send.bin"
    path.write_bytes(b"data")
    dp = DataPlane(MockSecurity())
    with pytest.raises(RuntimeError, match="DataPlane not connected"):
        asyncio.run(dp.send_file(str(path)))

def test_receive_file_requires_connection(tmp_path):
    dp = DataPlane(MockSecurity())
    with pytest.raises(RuntimeError, match="DataPlane not connected"):
        asyncio.run(dp.receive_file(str(tmp_path / "recv.bin"), 1))

def test_send_file_rejects_invalid_resume_offset(tmp_path):
    path = tmp_path / "send.bin"
    path.write_bytes(b"data")
    dp = DataPlane(MockSecurity())
    dp._connected = True
    with pytest.raises(ValueError, match="Invalid resume offset"):
        asyncio.run(dp.send_file(str(path), resume_offset=-1))

def test_receive_file_rejects_negative_total_size(tmp_path):
    dp = DataPlane(MockSecurity())
    dp._connected = True
    with pytest.raises(ValueError, match="Invalid total size"):
        asyncio.run(dp.receive_file(str(tmp_path / "recv.bin"), -1))

