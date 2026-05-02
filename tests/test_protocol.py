import pytest

from app.core.protocol import (
    ProtocolValidationError,
    parse_p2p_handshake,
    parse_transfer_permit,
    parse_transfer_req,
)


def test_parse_transfer_req_nested_file_meta_valid():
    req = parse_transfer_req(
        {
            "target_uuid": "peer-1",
            "file_meta": {"name": "a.bin", "size": 1, "hash": "a" * 64},
        }
    )
    assert req.target_uuid == "peer-1"
    assert req.file_meta.name == "a.bin"


def test_parse_transfer_req_legacy_shape_valid():
    req = parse_transfer_req(
        {
            "target_uuid": "peer-1",
            "filename": "legacy.bin",
            "size": 5,
            "sha256": "b" * 64,
        }
    )
    assert req.file_meta.name == "legacy.bin"
    assert req.file_meta.size == 5
    assert req.file_meta.sha256 == "b" * 64


def test_parse_transfer_req_invalid_hash():
    with pytest.raises(ProtocolValidationError):
        parse_transfer_req(
            {
                "target_uuid": "peer-1",
                "file_meta": {"name": "a.bin", "size": 1, "hash": "zz"},
            }
        )


def test_parse_transfer_permit_invalid_port():
    with pytest.raises(ProtocolValidationError):
        parse_transfer_permit({"target_ip": "10.0.0.2", "target_port": 99999})


def test_parse_p2p_handshake_valid():
    hs = parse_p2p_handshake(
        {"file_meta": {"name": "a.bin", "size": 5, "hash": "b" * 64}, "challenge_nonce": "12345678"}
    )
    assert hs.file_meta.size == 5
