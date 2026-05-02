from dataclasses import dataclass
from typing import Optional

from app.core.security import SecurityManager


@dataclass
class SessionContext:
    room_pin: str
    node_uuid: str
    node_name: str
    runtime_dir: str
    config_file: str
    download_dir: str
    security: SecurityManager
    role: str = "CLIENT"
    pending_send: Optional[dict] = None
    host_uuid: Optional[str] = None
