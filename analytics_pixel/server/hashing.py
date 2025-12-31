from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HashingConfig:
    salt: str


def _to_bytes(s: str) -> bytes:
    return s.encode("utf-8", errors="replace")


def sha256_hex(cfg: HashingConfig, *, label: str, value: Optional[str]) -> Optional[str]:
    """
    One-way hash for sensitive fields. Never store raw values to disk.

    - Includes a required salt (cfg.salt)
    - Includes a label domain separator to prevent hash reuse across fields
    - Returns None if value is None/empty
    """
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None

    h = hashlib.sha256()
    h.update(_to_bytes("analytics_pixel:v1:"))
    h.update(_to_bytes(label))
    h.update(b":")
    h.update(_to_bytes(cfg.salt))
    h.update(b":")
    h.update(_to_bytes(v))
    return h.hexdigest()


def visitor_key_hex(cfg: HashingConfig, *, ip: Optional[str], user_agent: Optional[str]) -> Optional[str]:
    """
    Stable-ish "unique visitor" key derived from (IP + UA), still one-way hashed.
    """
    if (ip is None or not ip.strip()) and (user_agent is None or not user_agent.strip()):
        return None
    combined = f"{ip or ''}\n{user_agent or ''}"
    return sha256_hex(cfg, label="visitor", value=combined)
