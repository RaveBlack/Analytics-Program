from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .database import Database
from .hashing import HashingConfig, sha256_hex


@dataclass(frozen=True)
class AuthConfig:
    auth_secret: str
    session_ttl_seconds: int = 60 * 60 * 24  # 24h


_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def issue_token() -> str:
    # Random bearer token returned to dashboard.
    return secrets.token_urlsafe(32)


def token_hash(cfg: HashingConfig, *, token: str) -> str:
    # Hash tokens before storing them in DB (defense-in-depth).
    return sha256_hex(cfg, label="session_token", value=token) or ""


def create_session(
    *,
    db: Database,
    hashing_cfg: HashingConfig,
    auth_cfg: AuthConfig,
    user_id: int,
) -> str:
    token = issue_token()
    th = token_hash(hashing_cfg, token=token)
    db.create_session(user_id=user_id, token_hash=th, ttl_seconds=auth_cfg.session_ttl_seconds)
    return token


def validate_session(
    *,
    db: Database,
    hashing_cfg: HashingConfig,
    token: Optional[str],
) -> Optional[int]:
    if token is None or not token.strip():
        return None
    th = token_hash(hashing_cfg, token=token)
    sess = db.get_session(token_hash=th)
    if not sess:
        return None
    return int(sess["user_id"])


def delete_session(*, db: Database, hashing_cfg: HashingConfig, token: Optional[str]) -> None:
    if token is None or not token.strip():
        return
    th = token_hash(hashing_cfg, token=token)
    db.delete_session(token_hash=th)
