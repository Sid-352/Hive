import asyncio
import hashlib
import logging
import os
import struct
import sys
import time
from typing import Callable, Optional

logger = logging.getLogger("hive.data_plane")

class DataPlane:
    def __init__(self, security) -> None:
        self.security = security
        self._reader, self._writer = None, None
        self._connected = False
        self.sent, self.received = [], []

    async def connect(self, target: str) -> None:
        if sys.platform == "win32":
            self._reader, self._writer = await asyncio.open_connection("127.0.0.1", int(target))
        else: self._reader, self._writer = await asyncio.open_unix_connection(target)
        self._connected = True

    async def disconnect(self) -> None:
        if self._writer:
            try: self._writer.close(); await self._writer.wait_closed()
            except Exception: pass
        self._connected = False

    async def send_file(self, path: str, resume_offset: int = 0, progress_cb=None) -> None:
        if not self._connected: raise RuntimeError("DataPlane not connected")
        if resume_offset < 0: raise ValueError("Invalid resume offset")
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(resume_offset)
            sent = resume_offset
            while sent < size:
                chunk = f.read(128 * 1024)
                if not chunk: break
                aad = struct.pack(">Q", sent)
                await self._write_framed(self.security.encrypt(chunk, aad=aad))
                sent += len(chunk)
                if progress_cb: progress_cb(sent, size)
        self.sent.append((path, resume_offset))

    async def receive_file(self, path: str, size: int, resume_offset: int = 0, progress_cb=None) -> None:
        if not self._connected: raise RuntimeError("DataPlane not connected")
        if size < 0: raise ValueError("Invalid total size")
        mode = "ab" if resume_offset > 0 else "wb"
        with open(path, mode) as f:
            received = resume_offset
            while received < size:
                payload = await self._read_framed()
                if not payload: raise ConnectionError("Data plane disconnected prematurely")
                aad = struct.pack(">Q", received)
                chunk = self.security.decrypt(payload, aad=aad)
                f.write(chunk)
                received += len(chunk)
                if progress_cb: progress_cb(received, size)
        self.received.append((path, resume_offset))

    async def _write_framed(self, data: bytes) -> None:
        if not self._writer: raise AttributeError("'NoneType' object has no attribute 'write'")
        self._writer.write(struct.pack(">I", len(data)) + data)
        await self._writer.drain()

    async def _read_framed(self) -> Optional[bytes]:
        if not self._reader: raise AttributeError("'NoneType' object has no attribute 'readexactly'")
        try:
            header = await self._reader.readexactly(4)
            length = struct.unpack(">I", header)[0]
            return await self._reader.readexactly(length)
        except (asyncio.IncompleteReadError, ConnectionResetError): return None

    @staticmethod
    def get_resume_offset(path: str) -> int:
        return os.path.getsize(path) if os.path.exists(path) else 0

    @staticmethod
    def compute_sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""): h.update(chunk)
        return h.hexdigest()
