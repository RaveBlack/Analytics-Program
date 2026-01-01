from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml
from flask import Flask, Response, jsonify, request

from .auth import (
    AuthConfig,
    create_session,
    delete_session,
    hash_password,
    validate_session,
    verify_password,
)
from .database import Database, DatabaseConfig
from .hashing import HashingConfig, protected_value, visitor_protected
from .pixel import glyph_png, transparent_pixel_png


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _client_ip(trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # Left-most is original client in standard practice.
            return xff.split(",")[0].strip()
    return request.remote_addr or ""


def _bearer_token() -> Optional[str]:
    authz = request.headers.get("Authorization", "")
    if authz.lower().startswith("bearer "):
        return authz.split(" ", 1)[1].strip()
    return None


def create_app() -> Flask:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg_path = os.environ.get("ANALYTICS_PIXEL_CONFIG", os.path.join(root, "config.yaml"))
    cfg = load_config(cfg_path)
    cfg_dir = os.path.dirname(os.path.abspath(cfg_path))

    def resolve_from_cfg_dir(p: str) -> str:
        # Treat relative paths in config as relative to the config file location.
        if os.path.isabs(p):
            return p
        return os.path.abspath(os.path.join(cfg_dir, p))

    mode = str(cfg.get("privacy", {}).get("identifiable_mode", "hash")).strip().lower()
    if mode not in ("hash", "plaintext", "both"):
        mode = "hash"
    hashing_cfg = HashingConfig(
        salt=str(cfg["security"]["hashing_salt"]),
        identifiable_mode=mode,  # type: ignore[arg-type]
    )
    auth_cfg = AuthConfig(auth_secret=str(cfg["security"]["auth_secret"]))
    db = Database(DatabaseConfig(sqlite_path=resolve_from_cfg_dir(str(cfg["database"]["sqlite_path"]))))
    trust_proxy_headers = bool(cfg.get("privacy", {}).get("trust_proxy_headers", False))

    app = Flask(__name__)

    def require_auth() -> Optional[int]:
        token = _bearer_token()
        return validate_session(db=db, hashing_cfg=hashing_cfg, token=token)

    @app.get("/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    # -------- tracking endpoints --------
    @app.get("/p/<pixel_id>.png")
    def pixel(pixel_id: str) -> Response:
        """
        Main tracking pixel endpoint. Works in browsers, emails, BBCode [img], etc.
        Optional query args:
          - tag: campaign name or custom label (hashed before storing)
        """
        tag = request.args.get("tag", default=None, type=str)
        ip = _client_ip(trust_proxy_headers)
        ua = request.headers.get("User-Agent", "")
        ref = request.headers.get("Referer", "")

        # Ensure pixel exists, then record hashed hit.
        db.ensure_pixel(pixel_id=pixel_id)
        ts = int(time.time())
        tag_raw, tag_hash = protected_value(hashing_cfg, label="tag", value=tag)
        ip_raw, ip_hash = protected_value(hashing_cfg, label="ip", value=ip)
        ua_raw, ua_hash = protected_value(hashing_cfg, label="ua", value=ua)
        ref_raw, ref_hash = protected_value(hashing_cfg, label="ref", value=ref)
        visitor_raw, visitor_hash = visitor_protected(hashing_cfg, ip=ip, user_agent=ua)
        db.insert_hit(
            pixel_id=pixel_id,
            tag_raw=tag_raw,
            tag_hash=tag_hash,
            ip_raw=ip_raw,
            ip_hash=ip_hash,
            ua_raw=ua_raw,
            ua_hash=ua_hash,
            ref_raw=ref_raw,
            ref_hash=ref_hash,
            visitor_raw=visitor_raw,
            visitor_hash=visitor_hash,
            ts=ts,
        )

        resp = Response(transparent_pixel_png(), mimetype="image/png")
        # Encourage clients to actually fetch again (analytics wants hits).
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    @app.get("/g/<pixel_id>.png")
    def glyph(pixel_id: str) -> Response:
        """
        Symbol/glyph fallback endpoint (still an image fetch, still counts as a hit).
        Useful in places that block 1×1 pixels but allow small icons.
        Query args:
          - text: glyph text, e.g. '•' or 'i'
          - tag: optional campaign/tag
        """
        text = request.args.get("text", default="•", type=str)
        # Reuse the same hit pipeline by internally calling pixel() logic.
        # We duplicate the minimal recording here to avoid internal request hacks.
        tag = request.args.get("tag", default=None, type=str)
        ip = _client_ip(trust_proxy_headers)
        ua = request.headers.get("User-Agent", "")
        ref = request.headers.get("Referer", "")

        db.ensure_pixel(pixel_id=pixel_id)
        ts = int(time.time())
        tag_raw, tag_hash = protected_value(hashing_cfg, label="tag", value=tag)
        ip_raw, ip_hash = protected_value(hashing_cfg, label="ip", value=ip)
        ua_raw, ua_hash = protected_value(hashing_cfg, label="ua", value=ua)
        ref_raw, ref_hash = protected_value(hashing_cfg, label="ref", value=ref)
        visitor_raw, visitor_hash = visitor_protected(hashing_cfg, ip=ip, user_agent=ua)
        db.insert_hit(
            pixel_id=pixel_id,
            tag_raw=tag_raw,
            tag_hash=tag_hash,
            ip_raw=ip_raw,
            ip_hash=ip_hash,
            ua_raw=ua_raw,
            ua_hash=ua_hash,
            ref_raw=ref_raw,
            ref_hash=ref_hash,
            visitor_raw=visitor_raw,
            visitor_hash=visitor_hash,
            ts=ts,
        )

        resp = Response(glyph_png(text=text), mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # -------- admin/auth endpoints --------
    @app.post("/api/setup")
    def setup() -> Response:
        """
        One-time local setup endpoint: creates the first admin user if none exists.
        Disabled once at least one user exists.
        """
        if db.user_count() > 0:
            return jsonify({"error": "setup_disabled"}), 403

        payload = request.get_json(force=True, silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not username or not password:
            return jsonify({"error": "username_and_password_required"}), 400

        uid = db.create_user(username=username, password_hash=hash_password(password))
        token = create_session(db=db, hashing_cfg=hashing_cfg, auth_cfg=auth_cfg, user_id=uid)
        return jsonify({"ok": True, "token": token})

    @app.post("/api/login")
    def login() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        user = db.get_user_by_username(username)
        if not user or not verify_password(str(user["password_hash"]), password):
            return jsonify({"error": "invalid_credentials"}), 401
        token = create_session(db=db, hashing_cfg=hashing_cfg, auth_cfg=auth_cfg, user_id=int(user["id"]))
        return jsonify({"ok": True, "token": token})

    @app.post("/api/logout")
    def logout() -> Response:
        token = _bearer_token()
        delete_session(db=db, hashing_cfg=hashing_cfg, token=token)
        return jsonify({"ok": True})

    # -------- analytics API (for pygame dashboard) --------
    @app.get("/api/stats/summary")
    def stats_summary() -> Response:
        if require_auth() is None:
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(db.totals())

    @app.get("/api/stats/pixels")
    def stats_pixels() -> Response:
        if require_auth() is None:
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"pixels": db.hits_per_pixel()})

    @app.get("/api/stats/timeseries")
    def stats_timeseries() -> Response:
        if require_auth() is None:
            return jsonify({"error": "unauthorized"}), 401
        bucket = request.args.get("bucket", default="hour", type=str)
        hours = int(request.args.get("hours", default=48, type=int))
        since_ts = int(time.time()) - max(1, hours) * 3600
        return jsonify({"bucket": bucket, "since_ts": since_ts, "series": db.time_series(bucket=bucket, since_ts=since_ts)})

    @app.get("/api/events/recent")
    def events_recent() -> Response:
        if require_auth() is None:
            return jsonify({"error": "unauthorized"}), 401
        limit = int(request.args.get("limit", default=200, type=int))
        limit = max(1, min(1000, limit))
        return jsonify({"events": db.recent_hits(limit=limit)})

    @app.post("/api/pixels/create")
    def pixels_create() -> Response:
        uid = require_auth()
        if uid is None:
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(force=True, silent=True) or {}
        pixel_id = str(payload.get("pixel_id", "")).strip()
        label = str(payload.get("label", "")).strip() or None
        if not pixel_id:
            return jsonify({"error": "pixel_id_required"}), 400

        db.create_pixel(pixel_id=pixel_id, label=label)

        base = request.host_url.rstrip("/")
        bb = f"[img]{base}/p/{pixel_id}.png[/img]"
        bb_tag = f"[img]{base}/p/{pixel_id}.png?tag=campaign[/img]"
        bb_glyph = f"[img]{base}/g/{pixel_id}.png?text=%E2%80%A2[/img]"
        return jsonify(
            {
                "ok": True,
                "pixel_id": pixel_id,
                "label": label,
                "embed": {
                    "pixel_url": f"{base}/p/{pixel_id}.png",
                    "glyph_url": f"{base}/g/{pixel_id}.png?text=%E2%80%A2",
                    "bbcode": bb,
                    "bbcode_with_tag": bb_tag,
                    "bbcode_glyph": bb_glyph,
                    "html_img": f'<img src="{base}/p/{pixel_id}.png" width="1" height="1" alt="" />',
                },
            }
        )

    return app


if __name__ == "__main__":
    app = create_app()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg_path = os.environ.get("ANALYTICS_PIXEL_CONFIG", os.path.join(root, "config.yaml"))
    cfg = load_config(cfg_path)
    host = str(cfg["server"]["host"])
    port = int(cfg["server"]["port"])
    app.run(host=host, port=port, debug=False)

