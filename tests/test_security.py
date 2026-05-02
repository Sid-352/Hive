import pytest

from app.core.security import SecurityManager


def test_encrypt_decrypt_roundtrip_same_pin():
    sec = SecurityManager(room_pin="1234")
    payload = b"hive-secret"

    token = sec.encrypt(payload)

    assert sec.decrypt(token) == payload


def test_different_pin_cannot_decrypt():
    sender = SecurityManager(room_pin="1234")
    receiver = SecurityManager(room_pin="9999")

    token = sender.encrypt(b"secret")

    with pytest.raises(Exception):
        receiver.decrypt(token)


def test_decrypt_too_short_raises():
    sec = SecurityManager(room_pin="1234")

    with pytest.raises(Exception):
        sec.decrypt(b"short")
