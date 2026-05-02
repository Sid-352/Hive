import os
import logging
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

logger = logging.getLogger("hive.security")

DEFAULT_ROOM_PIN = "0000"


class SecurityManager:
    def __init__(self, room_pin: str) -> None:
        self._room_pin = room_pin
        self._key = self._derive_key(room_pin)
        self._aes = AESGCM(self._key)

    def _derive_key(self, pin: str) -> bytes:
        kdf = Argon2id(
            salt=b"hive_fixed_salt_2026",
            length=32,
            iterations=2,
            lanes=4,
            memory_cost=65536)
        return kdf.derive(pin.encode())

    def encrypt(self, data: bytes, aad: bytes = None) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aes.encrypt(nonce, data, aad)

    def decrypt(self, token: bytes, aad: bytes = None) -> bytes:
        nonce = token[:12]
        ciphertext = token[12:]
        return self._aes.decrypt(nonce, ciphertext, aad)
