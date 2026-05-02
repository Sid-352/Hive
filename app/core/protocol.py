import re
from dataclasses import dataclass
from typing import Any


class ProtocolValidationError(ValueError):
    pass


def is_valid_sha256_hex(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True)
class FileMeta:
    name: str
    size: int
    hash: str

    @property
    def sha256(self) -> str:
        return self.hash


@dataclass(frozen=True)
class TransferReq:
    target_uuid: str
    file_meta: FileMeta


@dataclass(frozen=True)
class TransferPermit:
    target_ip: str
    target_port: int


@dataclass(frozen=True)
class P2PHandshake:
    file_meta: FileMeta
    challenge_nonce: str


def _parse_file_meta(file_meta: Any) -> FileMeta:
    if not isinstance(file_meta, dict):
        raise ProtocolValidationError("file_meta must be an object")
    name = file_meta.get("name")
    size = file_meta.get("size")
    file_hash = file_meta.get("hash")
    if file_hash is None:
        file_hash = file_meta.get("sha256")
    if not isinstance(name, str) or name == "":
        raise ProtocolValidationError(
            "file_meta.name must be a non-empty string")
    if not isinstance(size, int) or size < 0:
        raise ProtocolValidationError(
            "file_meta.size must be a non-negative integer")
    if not is_valid_sha256_hex(file_hash):
        raise ProtocolValidationError(
            "file_meta.hash must be 64 lowercase hex chars")
    return FileMeta(name=name, size=size, hash=file_hash)


def parse_transfer_req(data: Any) -> TransferReq:
    if not isinstance(data, dict):
        raise ProtocolValidationError("TRANSFER_REQ payload must be an object")
    target_uuid = data.get("target_uuid")
    if not isinstance(target_uuid, str) or target_uuid == "":
        raise ProtocolValidationError("target_uuid must be a non-empty string")

    file_meta = data.get("file_meta")
    if isinstance(file_meta, dict):
        return TransferReq(
            target_uuid=target_uuid,
            file_meta=_parse_file_meta(file_meta))

    legacy_file_meta = {
        "name": data.get("filename"),
        "size": data.get("size"),
        "sha256": data.get("sha256") or data.get("hash"),
    }
    return TransferReq(target_uuid=target_uuid,
                       file_meta=_parse_file_meta(legacy_file_meta))


def parse_transfer_permit(data: Any) -> TransferPermit:
    if not isinstance(data, dict):
        raise ProtocolValidationError(
            "TRANSFER_PERMIT payload must be an object")
    target_ip = data.get("target_ip")
    target_port = data.get("target_port")
    if not isinstance(target_ip, str) or target_ip == "":
        raise ProtocolValidationError("target_ip must be a non-empty string")
    if not isinstance(target_port, int) or not (1 <= target_port <= 65535):
        raise ProtocolValidationError(
            "target_port must be an integer in [1, 65535]")
    return TransferPermit(target_ip=target_ip, target_port=target_port)


def parse_p2p_handshake(data: Any) -> P2PHandshake:
    if not isinstance(data, dict):
        raise ProtocolValidationError(
            "P2P_HANDSHAKE payload must be an object")
    nonce = data.get("challenge_nonce")
    if not isinstance(nonce, str) or len(nonce) < 8:
        raise ProtocolValidationError(
            "P2P_HANDSHAKE must include a challenge_nonce")
    return P2PHandshake(
        file_meta=_parse_file_meta(data.get("file_meta")),
        challenge_nonce=nonce
    )
