## Privacy Beacon Analytics (production-ready, stdlib-only)

Self-hosted web analytics beacon system (classic “tracking pixel” style) that logs **hits + non-identifying technical metadata only**.

### Hard privacy rules (enforced)

- **No IP addresses**: never reads `remote_addr`, never reads `X-Forwarded-For`, never stores or hashes IPs, and the HTTP server does **not** print access logs containing IPs.
- **No cookies / storage**: no cookies, no `localStorage`, no sessions.
- **No fingerprinting**: no stable identifiers, no cross-request linking.
- **No external services**: no third-party analytics.
- **No auth/passwords**: nothing to hash or store.

### What gets recorded (allowed)

- Timestamp
- Beacon ID
- User-Agent
- Referrer (header or client-provided from JS)
- Safe subset of headers (allowlist)
- Screen resolution (JS beacon only)
- Page URL (JS beacon only)
- Origin type (`client` / `server` / `unknown`)
- Hit type (`image`, `symbol`, `js`, `endpoint`, etc.)

**Important privacy guardrail**: by default `store_full_urls=false`, so `page_url` and `referrer` are stored as **scheme://host/path only** (query strings are dropped) to avoid collecting tokens/emails commonly present in URLs.

---

## Run (no dependencies)

```bash
python3 privacy_beacon/server.py run
```

Open:

- Dashboard: `http://127.0.0.1:8080/`

### Configuration

Edit `privacy_beacon/config.json`:

- `port`: server port
- `storage_path`: SQLite DB file path
- `public_base_url`: used when generating embed snippets (set to your public domain, e.g. `https://domain.com`)
- `store_full_urls`: store full URL incl query if you explicitly want it
- `require_registered_beacons`: if `true`, unknown beacon IDs will be ignored (no auto-create on first hit)

You can also override:

- `PB_HOST`, `PB_PORT`, `PB_STORAGE_PATH`, `PB_PUBLIC_BASE_URL`

---

## Create a beacon ID (auto-generated)

From CLI:

```bash
python3 privacy_beacon/server.py create --label "forum-thread-123"
```

Or in the dashboard, click **Create beacon**.

---

## Embed examples (BBCode + HTML + JS + curl)

Assuming beacon ID `abc123` and base URL `https://domain.com`:

### 1×1 image beacon (works in forums / BBCode `[img]`)

```html
<img src="https://domain.com/b/abc123.png" width="1" height="1" alt="" />
```

```text
[img]https://domain.com/b/abc123.png[/img]
```

### Symbol / letter beacon (visible)

```text
https://domain.com/b/abc123.txt
```

### JS beacon (optional client metadata)

```html
<script src="https://domain.com/b/abc123.js"></script>
```

This will trigger a single background hit to:

- `/c/abc123.png?ht=js&ot=client&u=<page>&r=<ref>&sw=<w>&sh=<h>`

### Server-side endpoint (curl / backend calls)

```bash
curl -i https://domain.com/b/abc123
```

---

## Storage (SQLite)

Database path is `storage_path` (default: `privacy_beacon/storage/beacon.db`).

### Schema

Canonical schema file: `privacy_beacon/schema.sql`

Table `beacons`

- `beacon_id` (TEXT, PK)
- `label` (TEXT)
- `created_ts` (INTEGER unix seconds)

Table `hits`

- `hit_id` (INTEGER, PK autoincrement)
- `ts` (INTEGER unix seconds)
- `beacon_id` (TEXT)
- `hit_type` (TEXT)
- `origin_type` (TEXT: `client` / `server` / `unknown`)
- `user_agent` (TEXT)
- `referrer` (TEXT, normalized)
- `page_url` (TEXT, normalized)
- `screen_w` / `screen_h` (INTEGER nullable)
- `headers_json` (TEXT JSON, allowlisted subset)

### Export

- CSV export: `GET /export.csv?beacon=all` or `GET /export.csv?beacon=<id>`

---

## Bundling notes

### PyInstaller (one-file)

This project is stdlib-only and can be bundled directly:

```bash
pyinstaller --onefile privacy_beacon/server.py
```

The dashboard assets are embedded as strings, so no extra `--add-data` is required.

### Node `pkg` (architecture note)

If you port this to Node, you’ll need a SQLite binding or use JSON/CSV storage. The design here keeps strict separation between:

- **Beacon endpoints** (`/b/*`, `/c/*`)
- **Collector logic** (the `log_hit(...)` function)
- **Storage layer** (SQLite via `sqlite3`)
- **Viewer/dashboard** (`/` + `/api/*`)

