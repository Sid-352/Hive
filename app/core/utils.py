import os
from typing import Optional


def sanitize_receive_filename(filename: Optional[str]) -> str:
    safe = os.path.basename((filename or "").replace("\\", "/"))
    if safe in ("", ".", ".."):
        return "received_file"
    return safe
