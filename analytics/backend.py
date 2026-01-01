"""
Minimal local analytics backend (localhost-only).

What it does:
- Serves a BBCode-friendly 1x1 tracking image at /t/pixel.png?id=TRACKING_ID
- Logs each hit (timestamp, raw IP, user-agent, referer, tracking id) to SQLite
- Exposes a tiny JSON API and a simple local HTML UI at /

What it deliberately does NOT do:
- No hashing, no authentication, no passwords, no cloud, no external APIs.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, Response, jsonify, render_template_string, request, send_file


APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
STORAGE_DIR = APP_DIR / "storage"
DB_PATH = STORAGE_DIR / "analytics.db"
PIXEL_PATH = ASSETS_DIR / "pixel.png"


def utc_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def get_client_ip() -> str:
    """
    Best-effort IP capture.
    For local-only use, request.remote_addr is typically sufficient, but we also
    consider X-Forwarded-For in case the user puts a local reverse proxy in front.
    """
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # XFF can be a comma-separated list; first is the original client.
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS hits (
              id TEXT NOT NULL,
              ts INTEGER NOT NULL,
              ip TEXT NOT NULL,
              user_agent TEXT NOT NULL,
              referer TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_hits_ts ON hits(ts)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_hits_id_ts ON hits(id, ts)")


def log_hit(tracking_id: str) -> None:
    ts = int(time.time())
    ip = get_client_ip()
    ua = request.headers.get("User-Agent", "") or ""
    ref = request.headers.get("Referer", "") or ""

    with connect_db() as con:
        con.execute(
            "INSERT INTO hits(id, ts, ip, user_agent, referer) VALUES (?, ?, ?, ?, ?)",
            (tracking_id, ts, ip, ua, ref),
        )


def query_stats() -> Dict[str, Any]:
    with connect_db() as con:
        total = con.execute("SELECT COUNT(*) AS n FROM hits").fetchone()["n"]
        last_ts_row = con.execute("SELECT MAX(ts) AS ts FROM hits").fetchone()
        last_ts = last_ts_row["ts"]
        per_id_rows = con.execute(
            "SELECT id, COUNT(*) AS n FROM hits GROUP BY id ORDER BY n DESC, id ASC"
        ).fetchall()
        per_id = {r["id"]: r["n"] for r in per_id_rows}

    return {
        "total_hits": int(total),
        "unique_ids": int(len(per_id)),
        "last_hit_ts": int(last_ts) if last_ts is not None else None,
        "last_hit_ts_iso": utc_iso(int(last_ts)) if last_ts is not None else None,
        "hits_per_id": per_id,
    }


def query_hits(
    *,
    tracking_id: Optional[str],
    limit: int,
    since_ts: Optional[int],
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    params: List[Any] = []
    where: List[str] = []

    if tracking_id:
        where.append("id = ?")
        params.append(tracking_id)
    if since_ts is not None:
        where.append("ts >= ?")
        params.append(int(since_ts))

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT id, ts, ip, user_agent, referer "
        "FROM hits"
        f"{where_sql} "
        "ORDER BY ts DESC "
        "LIMIT ?"
    )
    params.append(limit)

    with connect_db() as con:
        rows = con.execute(sql, params).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        ts = int(r["ts"])
        out.append(
            {
                "id": r["id"],
                "ts": ts,
                "ts_iso": utc_iso(ts),
                "ip": r["ip"],
                "user_agent": r["user_agent"],
                "referer": r["referer"],
            }
        )
    return out


app = Flask(__name__)
init_db()


@app.get("/t/pixel.png")
def tracking_pixel() -> Response:
    tracking_id = (request.args.get("id") or "").strip() or "unknown"
    log_hit(tracking_id)

    # Important for forums: return a real image with correct content-type.
    resp = send_file(str(PIXEL_PATH), mimetype="image/png", conditional=False)
    # Avoid caching; analytics should reflect reloads.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/api/stats")
def api_stats() -> Response:
    return jsonify(query_stats())


@app.get("/api/hits")
def api_hits() -> Response:
    tracking_id = (request.args.get("id") or "").strip() or None
    limit = int(request.args.get("limit") or 200)
    since = request.args.get("since")
    since_ts = int(since) if since not in (None, "") else None
    return jsonify({"hits": query_hits(tracking_id=tracking_id, limit=limit, since_ts=since_ts)})


@app.get("/api/bbcode")
def api_bbcode() -> Response:
    tracking_id = (request.args.get("id") or "").strip() or "THREAD_ID"
    base = request.host_url.rstrip("/")
    url = f"{base}/t/pixel.png?id={tracking_id}"
    return jsonify({"bbcode": f"[img]{url}[/img]", "url": url, "id": tracking_id})


UI_HTML = """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Local Analytics</title>
    <style>
      :root { color-scheme: light dark; }
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 16px; }
      .row { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
      .card { border: 1px solid rgba(127,127,127,.35); border-radius: 10px; padding: 12px; min-width: 320px; }
      .muted { opacity: .75; }
      input, button { font: inherit; padding: 6px 8px; }
      table { width: 100%; border-collapse: collapse; }
      th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid rgba(127,127,127,.25); vertical-align: top; }
      th { position: sticky; top: 0; background: Canvas; }
      .scroll { max-height: 420px; overflow: auto; border: 1px solid rgba(127,127,127,.25); border-radius: 8px; }
      code { word-break: break-all; }
    </style>
  </head>
  <body>
    <h2 style="margin:0 0 8px 0;">Local Analytics (localhost-only)</h2>
    <div class="muted" style="margin-bottom:12px;">
      Pixel endpoint: <code>/t/pixel.png?id=THREAD_ID</code> • API: <code>/api/stats</code>, <code>/api/hits</code>
    </div>

    <div class="row">
      <div class="card">
        <div><b>Total hits:</b> <span id="totalHits">…</span></div>
        <div><b>Unique IDs:</b> <span id="uniqueIds">…</span></div>
        <div><b>Last hit:</b> <span id="lastHit">…</span></div>
        <div style="margin-top:10px;">
          <label><b>Filter by tracking ID:</b></label><br/>
          <input id="filterId" placeholder="(empty = all)" style="width: 220px;" />
          <button id="applyFilter">Apply</button>
        </div>
        <div style="margin-top:10px;">
          <label><b>BBCode snippet:</b></label><br/>
          <input id="bbcodeId" placeholder="THREAD_ID" style="width: 220px;" />
          <button id="makeBbcode">Generate</button>
          <div style="margin-top:8px;">
            <code id="bbcodeOut" class="muted"></code>
          </div>
          <div style="margin-top:8px;">
            <button id="copyBbcode" disabled>Copy</button>
            <span id="copyStatus" class="muted"></span>
          </div>
        </div>
      </div>

      <div class="card" style="min-width: 420px;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; gap:10px;">
          <div><b>Hits per ID</b></div>
          <div class="muted">Auto-refresh: <span id="refreshMs">2000</span>ms</div>
        </div>
        <div class="scroll" style="margin-top:8px;">
          <table>
            <thead><tr><th>ID</th><th>Hits</th></tr></thead>
            <tbody id="perIdBody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:16px;">
      <div style="display:flex; justify-content:space-between; align-items:baseline; gap:10px;">
        <div><b>Live view log</b> <span class="muted">(newest first)</span></div>
        <div class="muted">Showing <span id="shownCount">…</span></div>
      </div>
      <div class="scroll" style="margin-top:8px;">
        <table>
          <thead><tr><th>Time (UTC)</th><th>ID</th><th>IP</th><th>User-Agent</th><th>Referer</th></tr></thead>
          <tbody id="hitsBody"></tbody>
        </table>
      </div>
    </div>

    <script>
      const REFRESH_MS = 2000;
      document.getElementById('refreshMs').textContent = String(REFRESH_MS);

      function esc(s) {
        return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
      }

      async function getJson(url) {
        const r = await fetch(url, { cache: 'no-store' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return await r.json();
      }

      function currentFilter() {
        const v = document.getElementById('filterId').value.trim();
        return v ? v : null;
      }

      async function refresh() {
        try {
          const stats = await getJson('/api/stats');
          document.getElementById('totalHits').textContent = stats.total_hits;
          document.getElementById('uniqueIds').textContent = stats.unique_ids;
          document.getElementById('lastHit').textContent = stats.last_hit_ts_iso || '—';

          const perIdBody = document.getElementById('perIdBody');
          perIdBody.innerHTML = '';
          for (const [id, n] of Object.entries(stats.hits_per_id)) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${esc(id)}</td><td>${esc(n)}</td>`;
            perIdBody.appendChild(tr);
          }

          const id = currentFilter();
          const hitsUrl = id ? `/api/hits?id=${encodeURIComponent(id)}&limit=200` : '/api/hits?limit=200';
          const hitsResp = await getJson(hitsUrl);
          const hits = hitsResp.hits || [];

          const hitsBody = document.getElementById('hitsBody');
          hitsBody.innerHTML = '';
          for (const h of hits) {
            const tr = document.createElement('tr');
            tr.innerHTML =
              `<td>${esc(h.ts_iso)}</td>` +
              `<td>${esc(h.id)}</td>` +
              `<td>${esc(h.ip)}</td>` +
              `<td>${esc(h.user_agent)}</td>` +
              `<td>${esc(h.referer || '')}</td>`;
            hitsBody.appendChild(tr);
          }
          document.getElementById('shownCount').textContent = String(hits.length);
        } catch (e) {
          // Keep UI usable even if backend is restarting.
          document.getElementById('lastHit').textContent = 'Backend unavailable';
        }
      }

      async function generateBbcode() {
        const id = document.getElementById('bbcodeId').value.trim() || 'THREAD_ID';
        const data = await getJson(`/api/bbcode?id=${encodeURIComponent(id)}`);
        const bb = data.bbcode || '';
        const out = document.getElementById('bbcodeOut');
        out.textContent = bb;
        const copyBtn = document.getElementById('copyBbcode');
        copyBtn.disabled = !bb;
      }

      async function copyBbcode() {
        const bb = document.getElementById('bbcodeOut').textContent || '';
        const status = document.getElementById('copyStatus');
        status.textContent = '';
        if (!bb) return;
        try {
          await navigator.clipboard.writeText(bb);
          status.textContent = 'Copied.';
        } catch {
          // Fallback for older browsers.
          const tmp = document.createElement('textarea');
          tmp.value = bb;
          document.body.appendChild(tmp);
          tmp.select();
          document.execCommand('copy');
          document.body.removeChild(tmp);
          status.textContent = 'Copied.';
        }
        setTimeout(() => { status.textContent = ''; }, 1500);
      }

      document.getElementById('applyFilter').addEventListener('click', refresh);
      document.getElementById('filterId').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') refresh();
      });
      document.getElementById('makeBbcode').addEventListener('click', generateBbcode);
      document.getElementById('copyBbcode').addEventListener('click', copyBbcode);

      // Initial load + auto-refresh
      refresh();
      setInterval(refresh, REFRESH_MS);
    </script>
  </body>
</html>
"""


@app.get("/")
def ui() -> Response:
    return Response(render_template_string(UI_HTML), mimetype="text/html; charset=utf-8")


def main() -> None:
    if not PIXEL_PATH.exists():
        raise SystemExit(f"Missing asset: {PIXEL_PATH} (expected 1x1 PNG)")
    # Localhost-only by design:
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)


if __name__ == "__main__":
    main()

