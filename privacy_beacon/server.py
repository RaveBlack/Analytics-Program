#!/usr/bin/env python3
"""
Privacy Beacon Analytics (stdlib-only).

Hard privacy guarantees:
- Never reads, stores, or hashes client IP addresses (no remote_addr, no XFF).
- Never stores Cookie / Set-Cookie / Authorization headers.
- No user identifiers, no fingerprinting, no cookies/localStorage.

This is an old-school "beacon hit counter + environment telemetry" system:
- 1x1 PNG beacon (BBCode-friendly)
- Symbol/text beacon
- JS beacon (collects optional client metadata via a second image request)
- Server-side endpoint for curl/backend testing

Run:
  python3 privacy_beacon/server.py run

Create a new beacon ID + embed snippets:
  python3 privacy_beacon/server.py create
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_DIR / "config.json"


# 1x1 transparent PNG (base64). This is a real valid PNG response for BBCode [img].
PIXEL_PNG_BYTES = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+tmfQAAAAASUVORK5CYII="
)


def utc_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def now_ts() -> int:
    return int(time.time())


def clamp_int(v: Any, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except Exception:
        return lo
    return max(lo, min(hi, n))


def json_response(handler: BaseHTTPRequestHandler, obj: Any, *, status: int = 200) -> None:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def text_response(handler: BaseHTTPRequestHandler, text: str, *, status: int = 200, content_type: str = "text/plain") -> None:
    data = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def bytes_response(
    handler: BaseHTTPRequestHandler,
    body: bytes,
    *,
    status: int = 200,
    content_type: str,
    extra_headers: Optional[Dict[str, str]] = None,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    handler.send_header("Content-Length", str(len(body)))
    if extra_headers:
        for k, v in extra_headers.items():
            handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler, *, max_bytes: int = 64_000) -> Any:
    length = handler.headers.get("Content-Length", "")
    n = clamp_int(length, 0, max_bytes)
    raw = handler.rfile.read(n) if n else b""
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def safe_header_subset(headers: Any) -> Dict[str, str]:
    """
    Keep a safe, non-identifying subset of request headers.

    Never record cookies, auth, or proxy/ip-related headers.
    """

    allow = {
        "User-Agent",
        "Accept",
        "Accept-Language",
        "Accept-Encoding",
        "DNT",
        "Sec-Fetch-Site",
        "Sec-Fetch-Mode",
        "Sec-Fetch-Dest",
        "Sec-Ch-Ua",
        "Sec-Ch-Ua-Mobile",
        "Sec-Ch-Ua-Platform",
        "Origin",
        "Referer",
    }

    out: Dict[str, str] = {}
    for k in allow:
        v = headers.get(k)
        if v is None:
            continue
        vv = str(v)
        # Avoid accidentally storing extremely long headers.
        if len(vv) > 2048:
            vv = vv[:2048] + "…"
        out[k] = vv
    return out


def normalize_url_for_storage(url: str, *, store_full: bool) -> str:
    """
    Privacy guardrail: by default store only scheme://host/path (no query/fragment),
    which avoids collecting emails/tokens frequently present in query strings.
    """

    url = (url or "").strip()
    if not url:
        return ""
    try:
        u = urlparse(url)
    except Exception:
        return ""
    if not u.scheme or not u.netloc:
        return ""
    if store_full:
        # Still drop username/password if present (rare but possible).
        netloc = u.hostname or u.netloc
        if u.port:
            netloc = f"{netloc}:{u.port}"
        return f"{u.scheme}://{netloc}{u.path or ''}{('?' + u.query) if u.query else ''}"
    return f"{u.scheme}://{u.netloc}{u.path or ''}"


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    storage_path: str
    public_base_url: str
    store_full_urls: bool
    require_registered_beacons: bool


def load_config(path: Path) -> Config:
    raw: Dict[str, Any] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))

    host = str(raw.get("host") or os.getenv("PB_HOST") or "127.0.0.1")
    port = clamp_int(raw.get("port") or os.getenv("PB_PORT") or 8080, 1, 65535)
    storage_path = str(raw.get("storage_path") or os.getenv("PB_STORAGE_PATH") or str(APP_DIR / "storage" / "beacon.db"))
    public_base_url = str(raw.get("public_base_url") or os.getenv("PB_PUBLIC_BASE_URL") or "").rstrip("/")
    store_full_urls = bool(raw.get("store_full_urls") or False)
    require_registered_beacons = bool(raw.get("require_registered_beacons") or False)

    return Config(
        host=host,
        port=port,
        storage_path=storage_path,
        public_base_url=public_base_url,
        store_full_urls=store_full_urls,
        require_registered_beacons=require_registered_beacons,
    )


def connect_db(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=15.0)
    con.row_factory = sqlite3.Row
    return con


def init_db(db_path: str) -> None:
    with connect_db(db_path) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS beacons (
              beacon_id TEXT PRIMARY KEY,
              label TEXT NOT NULL DEFAULT '',
              created_ts INTEGER NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS hits (
              hit_id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL,
              beacon_id TEXT NOT NULL,
              hit_type TEXT NOT NULL,
              origin_type TEXT NOT NULL,         -- client | server | unknown
              user_agent TEXT NOT NULL,
              referrer TEXT NOT NULL,            -- header or client-provided (normalized)
              page_url TEXT NOT NULL,            -- client-provided (normalized)
              screen_w INTEGER,
              screen_h INTEGER,
              headers_json TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_hits_ts ON hits(ts)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_hits_beacon_ts ON hits(beacon_id, ts)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_hits_type_ts ON hits(hit_type, ts)")


def beacon_exists(db_path: str, beacon_id: str) -> bool:
    with connect_db(db_path) as con:
        row = con.execute("SELECT 1 FROM beacons WHERE beacon_id = ? LIMIT 1", (beacon_id,)).fetchone()
    return row is not None


def ensure_beacon(db_path: str, beacon_id: str) -> None:
    with connect_db(db_path) as con:
        con.execute(
            "INSERT OR IGNORE INTO beacons(beacon_id, label, created_ts) VALUES (?, '', ?)",
            (beacon_id, now_ts()),
        )


def create_beacon(db_path: str, *, label: str = "") -> str:
    bid = secrets.token_urlsafe(9).rstrip("=")  # short, URL-safe
    with connect_db(db_path) as con:
        con.execute(
            "INSERT INTO beacons(beacon_id, label, created_ts) VALUES (?, ?, ?)",
            (bid, (label or "")[:120], now_ts()),
        )
    return bid


def log_hit(
    *,
    db_path: str,
    cfg: Config,
    beacon_id: str,
    hit_type: str,
    origin_type: str,
    user_agent: str,
    referrer: str,
    page_url: str,
    screen_w: Optional[int],
    screen_h: Optional[int],
    headers_subset: Dict[str, str],
) -> None:
    ts = now_ts()
    if cfg.require_registered_beacons and not beacon_exists(db_path, beacon_id):
        return

    # Keep the system usable without an explicit "create" step.
    ensure_beacon(db_path, beacon_id)

    referrer_n = normalize_url_for_storage(referrer, store_full=cfg.store_full_urls)
    page_n = normalize_url_for_storage(page_url, store_full=cfg.store_full_urls)
    ua = (user_agent or "")[:1024]
    headers_json = json.dumps(headers_subset, ensure_ascii=False, separators=(",", ":"))

    with connect_db(db_path) as con:
        con.execute(
            """
            INSERT INTO hits(
              ts, beacon_id, hit_type, origin_type,
              user_agent, referrer, page_url,
              screen_w, screen_h, headers_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                beacon_id,
                hit_type[:32],
                origin_type[:16],
                ua,
                referrer_n,
                page_n,
                screen_w,
                screen_h,
                headers_json,
            ),
        )


def query_stats(db_path: str) -> Dict[str, Any]:
    with connect_db(db_path) as con:
        total = int(con.execute("SELECT COUNT(*) AS n FROM hits").fetchone()["n"])
        beacons = int(con.execute("SELECT COUNT(*) AS n FROM beacons").fetchone()["n"])
        last_ts_row = con.execute("SELECT MAX(ts) AS ts FROM hits").fetchone()
        last_ts = last_ts_row["ts"]
        per_beacon_rows = con.execute(
            "SELECT beacon_id, COUNT(*) AS n FROM hits GROUP BY beacon_id ORDER BY n DESC, beacon_id ASC"
        ).fetchall()
        per_type_rows = con.execute(
            "SELECT hit_type, COUNT(*) AS n FROM hits GROUP BY hit_type ORDER BY n DESC, hit_type ASC"
        ).fetchall()
    return {
        "total_hits": total,
        "beacon_count": beacons,
        "last_hit_ts": int(last_ts) if last_ts is not None else None,
        "last_hit_ts_iso": utc_iso(int(last_ts)) if last_ts is not None else None,
        "hits_per_beacon": {r["beacon_id"]: int(r["n"]) for r in per_beacon_rows},
        "hits_per_type": {r["hit_type"]: int(r["n"]) for r in per_type_rows},
    }


def query_beacons(db_path: str) -> List[Dict[str, Any]]:
    with connect_db(db_path) as con:
        rows = con.execute(
            """
            SELECT
              b.beacon_id,
              b.label,
              b.created_ts,
              (SELECT COUNT(*) FROM hits h WHERE h.beacon_id = b.beacon_id) AS hit_count
            FROM beacons b
            ORDER BY hit_count DESC, b.created_ts DESC
            """
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "beacon_id": r["beacon_id"],
                "label": r["label"],
                "created_ts": int(r["created_ts"]),
                "created_ts_iso": utc_iso(int(r["created_ts"])),
                "hit_count": int(r["hit_count"]),
            }
        )
    return out


def query_hits(db_path: str, *, beacon_id: str, limit: int, offset: int) -> List[Dict[str, Any]]:
    limit = clamp_int(limit, 1, 2000)
    offset = clamp_int(offset, 0, 2_000_000)
    params: List[Any] = []
    where = ""
    if beacon_id and beacon_id != "all":
        where = "WHERE beacon_id = ?"
        params.append(beacon_id)
    params.extend([limit, offset])
    sql = (
        "SELECT hit_id, ts, beacon_id, hit_type, origin_type, user_agent, referrer, page_url, screen_w, screen_h, headers_json "
        "FROM hits "
        f"{where} "
        "ORDER BY ts DESC, hit_id DESC "
        "LIMIT ? OFFSET ?"
    )
    with connect_db(db_path) as con:
        rows = con.execute(sql, params).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        ts = int(r["ts"])
        out.append(
            {
                "hit_id": int(r["hit_id"]),
                "ts": ts,
                "ts_iso": utc_iso(ts),
                "beacon_id": r["beacon_id"],
                "hit_type": r["hit_type"],
                "origin_type": r["origin_type"],
                "user_agent": r["user_agent"],
                "referrer": r["referrer"],
                "page_url": r["page_url"],
                "screen_w": r["screen_w"],
                "screen_h": r["screen_h"],
                "headers": json.loads(r["headers_json"] or "{}"),
            }
        )
    return out


def query_timeline(db_path: str, *, beacon_id: str, bucket: str, buckets: int) -> List[Dict[str, Any]]:
    """
    Returns time-series counts for the last N buckets.
    bucket: "hour" or "day"
    """
    bucket = bucket if bucket in ("hour", "day") else "hour"
    buckets = clamp_int(buckets, 1, 24 * 31)
    now = now_ts()
    seconds = 3600 if bucket == "hour" else 86400
    start = now - (buckets - 1) * seconds

    where = "WHERE ts >= ?"
    params: List[Any] = [start]
    if beacon_id and beacon_id != "all":
        where += " AND beacon_id = ?"
        params.append(beacon_id)

    # Group by floored timestamp bucket.
    with connect_db(db_path) as con:
        rows = con.execute(
            f"""
            SELECT (ts / ?) * ? AS bucket_ts, COUNT(*) AS n
            FROM hits
            {where}
            GROUP BY bucket_ts
            ORDER BY bucket_ts ASC
            """,
            (seconds, seconds, *params),
        ).fetchall()

    counts = {int(r["bucket_ts"]): int(r["n"]) for r in rows}
    out: List[Dict[str, Any]] = []
    for i in range(buckets):
        ts = ((start // seconds) * seconds) + i * seconds
        out.append({"bucket_ts": ts, "bucket_ts_iso": utc_iso(ts), "count": counts.get(ts, 0)})
    return out


def build_embed_examples(base_url: str, beacon_id: str) -> Dict[str, str]:
    base = base_url.rstrip("/")
    return {
        "image_html": f'<img src="{base}/b/{beacon_id}.png" width="1" height="1" alt="" />',
        "image_bbcode": f"[img]{base}/b/{beacon_id}.png[/img]",
        "script_html": f'<script src="{base}/b/{beacon_id}.js"></script>',
        "endpoint_curl": f"curl -i {base}/b/{beacon_id}",
        "symbol_url": f"{base}/b/{beacon_id}.txt",
    }


def dashboard_html() -> str:
    # Loaded via /dashboard/app.js and /dashboard/styles.css
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Privacy Beacon Analytics</title>
    <link rel="stylesheet" href="/dashboard/styles.css" />
  </head>
  <body>
    <header class="top">
      <div>
        <div class="title">Privacy Beacon Analytics</div>
        <div class="sub">No IPs • No cookies • No fingerprinting • Self-hosted</div>
      </div>
      <div class="actions">
        <button id="createBeaconBtn">Create beacon</button>
        <a class="btn" href="/export.csv?beacon=all" download>Export CSV</a>
      </div>
    </header>

    <main class="grid">
      <section class="card">
        <div class="cardTitle">Totals</div>
        <div class="kpis">
          <div class="kpi"><div class="k">Total hits</div><div class="v" id="kTotal">…</div></div>
          <div class="kpi"><div class="k">Beacons</div><div class="v" id="kBeacons">…</div></div>
          <div class="kpi"><div class="k">Last hit (UTC)</div><div class="v" id="kLast">…</div></div>
        </div>
        <div class="row">
          <label>Beacon</label>
          <select id="beaconSelect"></select>
          <label>Bucket</label>
          <select id="bucketSelect">
            <option value="hour">Hour</option>
            <option value="day">Day</option>
          </select>
          <label>Count</label>
          <select id="bucketCount">
            <option value="48">48</option>
            <option value="168" selected>168</option>
            <option value="720">720</option>
          </select>
        </div>
        <canvas id="timeline" height="120"></canvas>
        <div class="muted" id="timelineHint"></div>
      </section>

      <section class="card">
        <div class="cardTitle">Embed examples</div>
        <div class="muted">Select a beacon to get BBCode/HTML/script/curl snippets.</div>
        <div class="snips">
          <div class="snip"><div class="snipK">1×1 image (HTML)</div><pre id="snipImgHtml">…</pre></div>
          <div class="snip"><div class="snipK">1×1 image (BBCode)</div><pre id="snipImgBb">…</pre></div>
          <div class="snip"><div class="snipK">JS beacon</div><pre id="snipJs">…</pre></div>
          <div class="snip"><div class="snipK">Server-side endpoint (curl)</div><pre id="snipCurl">…</pre></div>
          <div class="snip"><div class="snipK">Symbol URL</div><pre id="snipSymbol">…</pre></div>
        </div>
      </section>

      <section class="card span2">
        <div class="cardTitle">Raw hit log</div>
        <div class="row">
          <label>Limit</label>
          <select id="hitsLimit">
            <option value="100">100</option>
            <option value="250" selected>250</option>
            <option value="500">500</option>
            <option value="1000">1000</option>
          </select>
          <button id="refreshBtn">Refresh</button>
          <a class="btn" id="exportFiltered" href="/export.csv?beacon=all" download>Export current beacon CSV</a>
        </div>
        <div class="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Time (UTC)</th>
                <th>Beacon</th>
                <th>Type</th>
                <th>Origin</th>
                <th>Page URL</th>
                <th>Referrer</th>
                <th>Screen</th>
                <th>User-Agent</th>
              </tr>
            </thead>
            <tbody id="hitsBody"></tbody>
          </table>
        </div>
      </section>
    </main>

    <dialog id="createDialog">
      <form method="dialog" class="dlg">
        <div class="dlgTitle">Create beacon</div>
        <label>Label (optional)</label>
        <input id="newLabel" maxlength="120" placeholder="e.g. forum-thread-123" />
        <div class="dlgRow">
          <button value="cancel">Cancel</button>
          <button id="createConfirm" value="ok">Create</button>
        </div>
        <div class="muted">A random beacon ID will be generated. No personal identifiers required.</div>
      </form>
    </dialog>

    <script src="/dashboard/app.js"></script>
  </body>
</html>
"""


def dashboard_js() -> str:
    return """(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');

  async function getJson(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  }

  async function postJson(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
      cache: 'no-store',
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  }

  function currentBeacon() {
    return $('beaconSelect').value || 'all';
  }

  function setSnips(ex) {
    $('snipImgHtml').textContent = ex.image_html || '';
    $('snipImgBb').textContent = ex.image_bbcode || '';
    $('snipJs').textContent = ex.script_html || '';
    $('snipCurl').textContent = ex.endpoint_curl || '';
    $('snipSymbol').textContent = ex.symbol_url || '';
  }

  function drawTimeline(series) {
    const c = $('timeline');
    const ctx = c.getContext('2d');
    const w = c.width = c.clientWidth * devicePixelRatio;
    const h = c.height = c.clientHeight * devicePixelRatio;
    ctx.clearRect(0,0,w,h);

    const pad = 10 * devicePixelRatio;
    const innerW = w - pad*2;
    const innerH = h - pad*2;
    const max = Math.max(1, ...series.map(s => s.count));

    // Axes baseline
    ctx.strokeStyle = 'rgba(127,127,127,.35)';
    ctx.lineWidth = 1 * devicePixelRatio;
    ctx.beginPath();
    ctx.moveTo(pad, pad + innerH);
    ctx.lineTo(pad + innerW, pad + innerH);
    ctx.stroke();

    const n = series.length;
    const barW = innerW / Math.max(1, n);
    ctx.fillStyle = 'rgba(80,160,255,.75)';
    for (let i=0; i<n; i++) {
      const v = series[i].count;
      const bh = (v / max) * (innerH - 2*devicePixelRatio);
      const x = pad + i * barW;
      const y = pad + innerH - bh;
      ctx.fillRect(x, y, Math.max(1, barW - 1*devicePixelRatio), bh);
    }

    const total = series.reduce((a,b)=>a+(b.count||0),0);
    $('timelineHint').textContent = `Buckets: ${n} • Total in window: ${total} • Max bucket: ${max}`;
  }

  async function refresh() {
    const stats = await getJson('/api/stats');
    $('kTotal').textContent = String(stats.total_hits ?? 0);
    $('kBeacons').textContent = String(stats.beacon_count ?? 0);
    $('kLast').textContent = String(stats.last_hit_ts_iso ?? '—');

    const beacons = await getJson('/api/beacons');
    const sel = $('beaconSelect');
    const cur = currentBeacon();
    sel.innerHTML = '';
    const optAll = document.createElement('option');
    optAll.value = 'all';
    optAll.textContent = 'all beacons';
    sel.appendChild(optAll);
    for (const b of (beacons.beacons || [])) {
      const o = document.createElement('option');
      o.value = b.beacon_id;
      o.textContent = b.label ? `${b.beacon_id} — ${b.label}` : b.beacon_id;
      sel.appendChild(o);
    }
    sel.value = cur && Array.from(sel.options).some(o => o.value === cur) ? cur : 'all';

    const emb = await getJson(`/api/embed?beacon=${encodeURIComponent(currentBeacon())}`);
    setSnips(emb.examples || {});

    $('exportFiltered').href = `/export.csv?beacon=${encodeURIComponent(currentBeacon())}`;

    const bucket = $('bucketSelect').value;
    const count = $('bucketCount').value;
    const tl = await getJson(`/api/timeline?beacon=${encodeURIComponent(currentBeacon())}&bucket=${encodeURIComponent(bucket)}&buckets=${encodeURIComponent(count)}`);
    drawTimeline(tl.series || []);

    const limit = $('hitsLimit').value;
    const hits = await getJson(`/api/hits?beacon=${encodeURIComponent(currentBeacon())}&limit=${encodeURIComponent(limit)}&offset=0`);
    const body = $('hitsBody');
    body.innerHTML = '';
    for (const h of (hits.hits || [])) {
      const tr = document.createElement('tr');
      const screen = (h.screen_w && h.screen_h) ? `${h.screen_w}×${h.screen_h}` : '';
      tr.innerHTML =
        `<td>${esc(h.ts_iso)}</td>` +
        `<td><code>${esc(h.beacon_id)}</code></td>` +
        `<td>${esc(h.hit_type)}</td>` +
        `<td>${esc(h.origin_type)}</td>` +
        `<td class="wrap">${esc(h.page_url || '')}</td>` +
        `<td class="wrap">${esc(h.referrer || '')}</td>` +
        `<td>${esc(screen)}</td>` +
        `<td class="wrap">${esc(h.user_agent || '')}</td>`;
      body.appendChild(tr);
    }
  }

  async function createBeacon(label) {
    const r = await postJson('/api/beacons', { label: label || '' });
    // switch selection to new beacon and refresh
    await refresh();
    $('beaconSelect').value = r.beacon_id;
    const emb = await getJson(`/api/embed?beacon=${encodeURIComponent(r.beacon_id)}`);
    setSnips(emb.examples || {});
  }

  $('refreshBtn').addEventListener('click', () => refresh().catch(console.error));
  $('beaconSelect').addEventListener('change', () => refresh().catch(console.error));
  $('bucketSelect').addEventListener('change', () => refresh().catch(console.error));
  $('bucketCount').addEventListener('change', () => refresh().catch(console.error));
  $('hitsLimit').addEventListener('change', () => refresh().catch(console.error));

  const dlg = $('createDialog');
  $('createBeaconBtn').addEventListener('click', () => { $('newLabel').value = ''; dlg.showModal(); });
  $('createConfirm').addEventListener('click', async (e) => {
    e.preventDefault();
    dlg.close();
    try { await createBeacon($('newLabel').value.trim()); } catch (err) { console.error(err); }
  });

  refresh().catch(console.error);
  setInterval(() => refresh().catch(() => {}), 5000);
})();"""


def dashboard_css() -> str:
    return """:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;max-width:1200px;margin-inline:auto}
.top{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:16px}
.title{font-weight:700;font-size:18px}
.sub{opacity:.75;font-size:13px}
.actions{display:flex;gap:10px;align-items:center}
button,.btn{font:inherit;padding:8px 10px;border-radius:10px;border:1px solid rgba(127,127,127,.35);background:Canvas;color:CanvasText;text-decoration:none;cursor:pointer}
button:hover,.btn:hover{border-color:rgba(80,160,255,.8)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{border:1px solid rgba(127,127,127,.35);border-radius:14px;padding:12px;background:rgba(127,127,127,.06)}
.cardTitle{font-weight:700;margin-bottom:10px}
.span2{grid-column:1 / span 2}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px}
.kpi{min-width:160px}
.k{opacity:.75;font-size:12px}
.v{font-size:22px;font-weight:800}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
label{opacity:.75;font-size:12px}
select,input{font:inherit;padding:7px 8px;border-radius:10px;border:1px solid rgba(127,127,127,.35);background:Canvas;color:CanvasText}
canvas{width:100%;border:1px solid rgba(127,127,127,.25);border-radius:12px;background:Canvas}
.muted{opacity:.75;font-size:12px;margin-top:8px}
.snips{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px}
.snipK{opacity:.75;font-size:12px;margin-bottom:4px}
pre{margin:0;padding:10px;border-radius:12px;border:1px solid rgba(127,127,127,.25);background:Canvas;overflow:auto;white-space:pre-wrap;word-break:break-word}
.tableWrap{overflow:auto;max-height:520px;border-radius:12px;border:1px solid rgba(127,127,127,.25);background:Canvas}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:8px;border-bottom:1px solid rgba(127,127,127,.15);vertical-align:top}
th{position:sticky;top:0;background:Canvas;font-weight:700}
.wrap{max-width:360px;word-break:break-word}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
dialog{border:1px solid rgba(127,127,127,.35);border-radius:14px;padding:0}
.dlg{padding:14px;min-width:min(420px,92vw)}
.dlgTitle{font-weight:800;margin-bottom:10px}
.dlgRow{display:flex;gap:10px;justify-content:flex-end;margin-top:12px}
"""


def js_beacon_payload() -> str:
    # Returned by /b/<id>.js
    # It triggers a single extra 1x1 PNG request to /c/<id>.png with client metadata.
    return r"""(() => {
  try {
    const cs = document.currentScript;
    if (!cs || !cs.src) return;
    const src = new URL(cs.src);
    const file = src.pathname.split('/').pop() || '';
    const beaconId = decodeURIComponent(file.replace(/\.js$/,''));

    const pageUrl = (typeof location !== 'undefined' && location.href) ? location.href : '';
    const ref = (typeof document !== 'undefined' && document.referrer) ? document.referrer : '';
    const sw = (typeof screen !== 'undefined' && Number.isFinite(screen.width)) ? String(screen.width) : '';
    const sh = (typeof screen !== 'undefined' && Number.isFinite(screen.height)) ? String(screen.height) : '';

    const u = new URL(`/c/${encodeURIComponent(beaconId)}.png`, src.origin);
    u.searchParams.set('ht', 'js');
    u.searchParams.set('ot', 'client');
    if (pageUrl) u.searchParams.set('u', pageUrl);
    if (ref) u.searchParams.set('r', ref);
    if (sw) u.searchParams.set('sw', sw);
    if (sh) u.searchParams.set('sh', sh);
    u.searchParams.set('_', String(Date.now()));

    const img = new Image();
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer-when-downgrade';
    img.src = u.toString();
  } catch (_) {
    // Intentionally no-op.
  }
})();"""


class PrivacyBeaconHandler(BaseHTTPRequestHandler):
    server_version = "PrivacyBeacon/1.0"

    @property
    def cfg(self) -> Config:
        return getattr(self.server, "cfg")  # type: ignore[no-any-return]

    @property
    def db_path(self) -> str:
        return getattr(self.server, "db_path")  # type: ignore[no-any-return]

    def log_message(self, format: str, *args: Any) -> None:
        # Hard privacy rule: do not log client IPs to stdout/stderr.
        return

    def _base_url(self) -> str:
        # Prefer explicitly configured public URL; otherwise infer from request host.
        if self.cfg.public_base_url:
            return self.cfg.public_base_url
        host = self.headers.get("Host") or f"{self.cfg.host}:{self.cfg.port}"
        scheme = "http"
        return f"{scheme}://{host}"

    def _route(self) -> Tuple[str, Dict[str, List[str]]]:
        u = urlparse(self.path)
        return u.path, parse_qs(u.query or "", keep_blank_values=True)

    def _send_404(self) -> None:
        text_response(self, "Not found\n", status=404)

    def _send_405(self) -> None:
        text_response(self, "Method not allowed\n", status=405)

    def _handle_beacon_image(self, beacon_id: str, qs: Dict[str, List[str]], *, hit_type: str, origin_default: str) -> None:
        ua = self.headers.get("User-Agent", "") or ""
        ref_h = self.headers.get("Referer", "") or ""
        ref_q = (qs.get("r") or [""])[0]
        page_q = (qs.get("u") or [""])[0]
        sw = (qs.get("sw") or [""])[0]
        sh = (qs.get("sh") or [""])[0]
        origin_type = (qs.get("ot") or [origin_default])[0] or origin_default
        origin_type = origin_type if origin_type in ("client", "server", "unknown") else origin_default
        ht = (qs.get("ht") or [hit_type])[0] or hit_type

        screen_w = int(sw) if sw.isdigit() else None
        screen_h = int(sh) if sh.isdigit() else None

        headers_subset = safe_header_subset(self.headers)
        # Prefer client-provided referrer (document.referrer) if present; otherwise header.
        referrer = ref_q or ref_h

        log_hit(
            db_path=self.db_path,
            cfg=self.cfg,
            beacon_id=beacon_id,
            hit_type=ht,
            origin_type=origin_type,
            user_agent=ua,
            referrer=referrer,
            page_url=page_q,
            screen_w=screen_w,
            screen_h=screen_h,
            headers_subset=headers_subset,
        )

        bytes_response(self, PIXEL_PNG_BYTES, content_type="image/png")

    def do_GET(self) -> None:  # noqa: N802
        path, qs = self._route()

        # Dashboard + static assets
        if path == "/" or path == "/dashboard":
            text_response(self, dashboard_html(), content_type="text/html", status=200)
            return
        if path == "/dashboard/app.js":
            text_response(self, dashboard_js(), content_type="application/javascript", status=200)
            return
        if path == "/dashboard/styles.css":
            text_response(self, dashboard_css(), content_type="text/css", status=200)
            return

        # API
        if path == "/api/stats":
            json_response(self, query_stats(self.db_path))
            return
        if path == "/api/beacons":
            json_response(self, {"beacons": query_beacons(self.db_path)})
            return
        if path == "/api/hits":
            beacon_id = (qs.get("beacon") or ["all"])[0]
            limit = clamp_int((qs.get("limit") or ["250"])[0], 1, 2000)
            offset = clamp_int((qs.get("offset") or ["0"])[0], 0, 2_000_000)
            json_response(self, {"hits": query_hits(self.db_path, beacon_id=beacon_id, limit=limit, offset=offset)})
            return
        if path == "/api/timeline":
            beacon_id = (qs.get("beacon") or ["all"])[0]
            bucket = (qs.get("bucket") or ["hour"])[0]
            buckets = clamp_int((qs.get("buckets") or ["168"])[0], 1, 24 * 31)
            json_response(self, {"series": query_timeline(self.db_path, beacon_id=beacon_id, bucket=bucket, buckets=buckets)})
            return
        if path == "/api/embed":
            beacon_id = (qs.get("beacon") or ["all"])[0]
            if not beacon_id or beacon_id == "all":
                # Try to pick top beacon; otherwise create one.
                beacons = query_beacons(self.db_path)
                if beacons:
                    beacon_id = beacons[0]["beacon_id"]
                else:
                    beacon_id = create_beacon(self.db_path, label="")
            json_response(self, {"beacon_id": beacon_id, "examples": build_embed_examples(self._base_url(), beacon_id)})
            return

        if path == "/export.csv":
            beacon_id = (qs.get("beacon") or ["all"])[0]
            hits = query_hits(self.db_path, beacon_id=beacon_id, limit=2000, offset=0)
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(
                [
                    "hit_id",
                    "ts_iso",
                    "beacon_id",
                    "hit_type",
                    "origin_type",
                    "page_url",
                    "referrer",
                    "screen_w",
                    "screen_h",
                    "user_agent",
                    "headers_json",
                ]
            )
            for h in hits:
                w.writerow(
                    [
                        h["hit_id"],
                        h["ts_iso"],
                        h["beacon_id"],
                        h["hit_type"],
                        h["origin_type"],
                        h["page_url"],
                        h["referrer"],
                        h["screen_w"] if h["screen_w"] is not None else "",
                        h["screen_h"] if h["screen_h"] is not None else "",
                        h["user_agent"],
                        json.dumps(h["headers"], ensure_ascii=False, separators=(",", ":")),
                    ]
                )
            data = buf.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f'attachment; filename="privacy_beacon_hits_{beacon_id}.csv"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # Beacons
        if path.startswith("/b/") and path.endswith(".png"):
            beacon_id = unquote(path[len("/b/") : -len(".png")]).strip()
            if beacon_id:
                self._handle_beacon_image(beacon_id, qs, hit_type="image", origin_default="unknown")
                return
            self._send_404()
            return

        if path.startswith("/c/") and path.endswith(".png"):
            beacon_id = unquote(path[len("/c/") : -len(".png")]).strip()
            if beacon_id:
                self._handle_beacon_image(beacon_id, qs, hit_type="js", origin_default="client")
                return
            self._send_404()
            return

        if path.startswith("/b/") and path.endswith(".txt"):
            beacon_id = unquote(path[len("/b/") : -len(".txt")]).strip()
            if beacon_id:
                ua = self.headers.get("User-Agent", "") or ""
                headers_subset = safe_header_subset(self.headers)
                log_hit(
                    db_path=self.db_path,
                    cfg=self.cfg,
                    beacon_id=beacon_id,
                    hit_type="symbol",
                    origin_type="unknown",
                    user_agent=ua,
                    referrer=self.headers.get("Referer", "") or "",
                    page_url="",
                    screen_w=None,
                    screen_h=None,
                    headers_subset=headers_subset,
                )
                text_response(self, "H", content_type="text/plain", status=200)
                return
            self._send_404()
            return

        if path.startswith("/b/") and path.endswith(".js"):
            beacon_id = unquote(path[len("/b/") : -len(".js")]).strip()
            if not beacon_id:
                self._send_404()
                return
            # JS file itself does not count as a hit; it triggers a single metadata image hit.
            body = js_beacon_payload()
            text_response(self, body, content_type="application/javascript", status=200)
            return

        if path.startswith("/b/") and path.count("/") == 2 and not path.endswith((".png", ".js", ".txt")):
            # Server-side endpoint: /b/<id>
            beacon_id = unquote(path[len("/b/") :]).strip()
            if beacon_id:
                ua = self.headers.get("User-Agent", "") or ""
                headers_subset = safe_header_subset(self.headers)
                log_hit(
                    db_path=self.db_path,
                    cfg=self.cfg,
                    beacon_id=beacon_id,
                    hit_type="endpoint",
                    origin_type="server",
                    user_agent=ua,
                    referrer=self.headers.get("Referer", "") or "",
                    page_url="",
                    screen_w=None,
                    screen_h=None,
                    headers_subset=headers_subset,
                )
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self._send_404()
            return

        self._send_404()

    def do_POST(self) -> None:  # noqa: N802
        path, _qs = self._route()
        if path == "/api/beacons":
            try:
                body = read_json_body(self)
            except Exception:
                json_response(self, {"error": "invalid_json"}, status=400)
                return
            label = ""
            if isinstance(body, dict):
                label = str(body.get("label") or "")
            bid = create_beacon(self.db_path, label=label)
            json_response(self, {"beacon_id": bid, "examples": build_embed_examples(self._base_url(), bid)}, status=201)
            return
        self._send_405()


class _Server(ThreadingHTTPServer):
    def __init__(self, server_address: Tuple[str, int], handler_cls: type[PrivacyBeaconHandler], *, cfg: Config) -> None:
        super().__init__(server_address, handler_cls)
        self.cfg = cfg
        self.db_path = cfg.storage_path


def run_server(cfg: Config) -> None:
    init_db(cfg.storage_path)
    httpd: ThreadingHTTPServer = _Server((cfg.host, cfg.port), PrivacyBeaconHandler, cfg=cfg)
    base = cfg.public_base_url or f"http://{cfg.host}:{cfg.port}"
    print(f"Privacy Beacon Analytics running at {base}/")
    print("Dashboard: /")
    print("Create beacon: POST /api/beacons  (or run: python3 privacy_beacon/server.py create)")
    httpd.serve_forever()


def cmd_create(cfg: Config, *, label: str) -> int:
    init_db(cfg.storage_path)
    bid = create_beacon(cfg.storage_path, label=label)
    base = cfg.public_base_url or f"http://{cfg.host}:{cfg.port}"
    ex = build_embed_examples(base, bid)
    print("Beacon created")
    print(f"- beacon_id: {bid}")
    if label:
        print(f"- label: {label}")
    print("")
    print("Embed examples:")
    print(ex["image_html"])
    print(ex["image_bbcode"])
    print(ex["script_html"])
    print(ex["endpoint_curl"])
    print(ex["symbol_url"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Privacy Beacon Analytics (stdlib-only)")
    ap.add_argument("--config", default=os.getenv("PRIVACY_BEACON_CONFIG", str(DEFAULT_CONFIG_PATH)), help="Path to config.json")
    sub = ap.add_subparsers(dest="cmd", required=False)

    runp = sub.add_parser("run", help="Run the server")
    runp.add_argument("--host", default=None)
    runp.add_argument("--port", default=None)

    createp = sub.add_parser("create", help="Create a new beacon and print embed snippets")
    createp.add_argument("--label", default="", help="Optional label for dashboard display")

    args = ap.parse_args()
    cfg = load_config(Path(args.config))

    cmd = args.cmd or "run"
    if cmd == "run":
        host = args.host if getattr(args, "host", None) else cfg.host
        port = clamp_int(args.port if getattr(args, "port", None) else cfg.port, 1, 65535)
        cfg2 = Config(
            host=host,
            port=port,
            storage_path=cfg.storage_path,
            public_base_url=cfg.public_base_url,
            store_full_urls=cfg.store_full_urls,
            require_registered_beacons=cfg.require_registered_beacons,
        )
        run_server(cfg2)
        return 0
    if cmd == "create":
        return cmd_create(cfg, label=str(getattr(args, "label", "") or ""))
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

