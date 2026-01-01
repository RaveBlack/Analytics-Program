from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class DatabaseConfig:
    sqlite_path: str


def _dict_factory(cursor: sqlite3.Cursor, row: Tuple[Any, ...]) -> Dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class Database:
    def __init__(self, cfg: DatabaseConfig):
        self.cfg = cfg
        self._ensure_parent_dir()
        self._init_schema()

    def _ensure_parent_dir(self) -> None:
        path = os.path.abspath(self.cfg.sqlite_path)
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.cfg.sqlite_path, check_same_thread=False)
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  token_hash TEXT NOT NULL UNIQUE,
                  created_at INTEGER NOT NULL,
                  expires_at INTEGER NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS pixels (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  pixel_id TEXT NOT NULL UNIQUE,
                  label TEXT,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS hits (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  pixel_id TEXT NOT NULL,
                  tag_raw TEXT,
                  tag_hash TEXT,
                  ip_raw TEXT,
                  ip_hash TEXT,
                  ua_raw TEXT,
                  ua_hash TEXT,
                  ref_raw TEXT,
                  ref_hash TEXT,
                  visitor_raw TEXT,
                  visitor_hash TEXT,
                  ts INTEGER NOT NULL,
                  FOREIGN KEY(pixel_id) REFERENCES pixels(pixel_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_hits_pixel_ts ON hits(pixel_id, ts);
                CREATE INDEX IF NOT EXISTS idx_hits_ts ON hits(ts);
                CREATE INDEX IF NOT EXISTS idx_hits_visitor ON hits(visitor_hash);
                """
            )
            # Lightweight migrations for existing databases (older schema without *_raw columns).
            for col in ("tag_raw", "ip_raw", "ua_raw", "ref_raw", "visitor_raw"):
                try:
                    conn.execute(f"ALTER TABLE hits ADD COLUMN {col} TEXT;")
                except sqlite3.OperationalError:
                    # column already exists
                    pass
            conn.commit()
        finally:
            conn.close()

    # -------- users / sessions --------
    def user_count(self) -> int:
        conn = self.connect()
        try:
            row = conn.execute("SELECT COUNT(1) AS c FROM users").fetchone()
            return int(row["c"])
        finally:
            conn.close()

    def create_user(self, *, username: str, password_hash: str) -> int:
        now = int(time.time())
        conn = self.connect()
        try:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, now),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        try:
            return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        finally:
            conn.close()

    def create_session(self, *, user_id: int, token_hash: str, ttl_seconds: int) -> None:
        now = int(time.time())
        expires_at = now + ttl_seconds
        conn = self.connect()
        try:
            conn.execute(
                "INSERT INTO sessions(user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (user_id, token_hash, now, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_session(self, *, token_hash: str) -> None:
        conn = self.connect()
        try:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            conn.commit()
        finally:
            conn.close()

    def get_session(self, *, token_hash: str) -> Optional[Dict[str, Any]]:
        now = int(time.time())
        conn = self.connect()
        try:
            return conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ? AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
        finally:
            conn.close()

    # -------- pixels / hits --------
    def ensure_pixel(self, *, pixel_id: str, label: Optional[str] = None) -> None:
        now = int(time.time())
        conn = self.connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO pixels(pixel_id, label, created_at) VALUES (?, ?, ?)",
                (pixel_id, label, now),
            )
            conn.commit()
        finally:
            conn.close()

    def create_pixel(self, *, pixel_id: str, label: Optional[str]) -> None:
        now = int(time.time())
        conn = self.connect()
        try:
            conn.execute(
                "INSERT INTO pixels(pixel_id, label, created_at) VALUES (?, ?, ?)",
                (pixel_id, label, now),
            )
            conn.commit()
        finally:
            conn.close()

    def list_pixels(self) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            return list(conn.execute("SELECT * FROM pixels ORDER BY created_at DESC").fetchall())
        finally:
            conn.close()

    def insert_hit(
        self,
        *,
        pixel_id: str,
        tag_raw: Optional[str],
        tag_hash: Optional[str],
        ip_raw: Optional[str],
        ip_hash: Optional[str],
        ua_raw: Optional[str],
        ua_hash: Optional[str],
        ref_raw: Optional[str],
        ref_hash: Optional[str],
        visitor_raw: Optional[str],
        visitor_hash: Optional[str],
        ts: int,
    ) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO hits(
                  pixel_id,
                  tag_raw, tag_hash,
                  ip_raw, ip_hash,
                  ua_raw, ua_hash,
                  ref_raw, ref_hash,
                  visitor_raw, visitor_hash,
                  ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pixel_id,
                    tag_raw,
                    tag_hash,
                    ip_raw,
                    ip_hash,
                    ua_raw,
                    ua_hash,
                    ref_raw,
                    ref_hash,
                    visitor_raw,
                    visitor_hash,
                    ts,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def recent_hits(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            return list(
                conn.execute(
                    """
                    SELECT
                      id, pixel_id,
                      tag_raw, tag_hash,
                      ip_raw, ip_hash,
                      ua_raw, ua_hash,
                      ref_raw, ref_hash,
                      visitor_raw, visitor_hash,
                      ts
                    FROM hits
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            )
        finally:
            conn.close()

    def totals(self) -> Dict[str, int]:
        conn = self.connect()
        try:
            total_hits = int(conn.execute("SELECT COUNT(1) AS c FROM hits").fetchone()["c"])
            unique_visitors = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT COALESCE(visitor_hash, visitor_raw)) AS c FROM hits WHERE COALESCE(visitor_hash, visitor_raw) IS NOT NULL"
                ).fetchone()["c"]
            )
            pixel_count = int(conn.execute("SELECT COUNT(1) AS c FROM pixels").fetchone()["c"])
            return {"total_hits": total_hits, "unique_visitors": unique_visitors, "pixel_count": pixel_count}
        finally:
            conn.close()

    def hits_per_pixel(self) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            return list(
                conn.execute(
                    """
                    SELECT p.pixel_id,
                           COALESCE(p.label, '') AS label,
                           COUNT(h.id) AS hits,
                           COUNT(DISTINCT COALESCE(h.visitor_hash, h.visitor_raw)) AS unique_visitors
                    FROM pixels p
                    LEFT JOIN hits h ON h.pixel_id = p.pixel_id
                    GROUP BY p.pixel_id
                    ORDER BY hits DESC, p.created_at DESC
                    """
                ).fetchall()
            )
        finally:
            conn.close()

    def time_series(self, *, bucket: str, since_ts: int) -> List[Dict[str, Any]]:
        """
        bucket: 'hour' or 'day'
        Returns: [{t: <bucket_start_ts>, hits: <int>, unique_visitors: <int>}]
        """
        if bucket not in ("hour", "day"):
            raise ValueError("bucket must be 'hour' or 'day'")
        seconds = 3600 if bucket == "hour" else 86400
        conn = self.connect()
        try:
            return list(
                conn.execute(
                    f"""
                    SELECT (ts / {seconds}) * {seconds} AS t,
                           COUNT(1) AS hits,
                           COUNT(DISTINCT COALESCE(visitor_hash, visitor_raw)) AS unique_visitors
                    FROM hits
                    WHERE ts >= ?
                    GROUP BY t
                    ORDER BY t ASC
                    """,
                    (since_ts,),
                ).fetchall()
            )
        finally:
            conn.close()
