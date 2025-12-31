# Analytics Pixel (privacy-first, local control)

Classic tracking-pixel analytics — but **no third-party services** and **no plaintext identifiable data**.  
You run the server locally, embed pixels anywhere an external image is allowed (BBCode, HTML, emails), and view analytics in a local **Pygame** dashboard.

## What gets stored (and what doesn’t)

This project supports a configurable mode to **display identifiable data**:
- `privacy.identifiable_mode: "hash" | "plaintext" | "both"` in `config.yaml`

- **Stored**
  - **Timestamp** (unix seconds)
  - **Pixel ID**
  - **Hashed fields (salted, one-way)**:
    - IP address → SHA-256 + salt
    - User-Agent → SHA-256 + salt
    - Referrer → SHA-256 + salt
    - Optional tag/campaign → SHA-256 + salt
    - “Unique visitor” key → SHA-256 of (IP + UA) + salt
- **When `identifiable_mode: "plaintext"` or `"both"`**
  - The server will also store and the dashboard will display **raw** IP / User-Agent / Referrer / tag.

- **Never stored**
  - Plaintext passwords

## Install

Python 3.11+ required.

```bash
cd /workspace/analytics_pixel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure (IMPORTANT)

Edit `config.yaml` and replace:

- `security.hashing_salt`
- `security.auth_secret`

Use long random strings (32+ bytes). This salt is required for privacy-safe one-way hashing.

## Run the server

```bash
source .venv/bin/activate
python3 -m analytics_pixel.server.app
```

Server defaults to `http://127.0.0.1:5055`.

## First-time admin setup

The first admin user is created via a one-time local setup endpoint (disabled once a user exists):

```bash
curl -sS -X POST http://127.0.0.1:5055/api/setup \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"admin","password":"change_me"}'
```

Response includes a bearer token for API usage.

## Generate a pixel & embed it

### Create a pixel ID (via API)

Login to get a token:

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:5055/api/login \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"admin","password":"change_me"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
```

Create a pixel:

```bash
curl -sS -X POST http://127.0.0.1:5055/api/pixels/create \\
  -H "Authorization: Bearer $TOKEN" \\
  -H 'Content-Type: application/json' \\
  -d '{"pixel_id":"forum_sig_001","label":"Forum signature"}'
```

### BBCode embed (forums, signatures, messages)

1×1 tracking pixel:

```text
[img]http://127.0.0.1:5055/p/forum_sig_001.png[/img]
```

With a campaign/tag (still hashed):

```text
[img]http://127.0.0.1:5055/p/forum_sig_001.png?tag=summer_campaign[/img]
```

### HTML embed (webpages)

```html
<img src="http://127.0.0.1:5055/p/forum_sig_001.png" width="1" height="1" alt="" />
```

## Symbol / glyph fallback

Some platforms block “1×1 pixels” but allow small icons. Use:

```text
[img]http://127.0.0.1:5055/g/forum_sig_001.png?text=•[/img]
```

This still triggers the analytics hit and returns a tiny glyph PNG.

> Note: if a platform blocks *all* external images, no pixel-based method can record an automatic view (by definition). In those cases you can still use a **click tracking link** pattern later if you want (not included by default).

## Run the Pygame dashboard

```bash
source .venv/bin/activate
python3 -m analytics_pixel.dashboard.pygame_ui
```

Features:
- Dark UI, scrollable pixel table
- Total hits / unique visitors
- Hits-per-pixel
- Simple time-series chart
- Click pixel → copy BBCode / URL to clipboard
- Live refresh via polling

## API endpoints (overview)

- `GET /p/<pixel_id>.png` — tracking pixel (records hit; returns 1×1 PNG)
- `GET /g/<pixel_id>.png?text=•` — glyph fallback (records hit; returns tiny glyph PNG)
- `POST /api/setup` — one-time create first admin user (disabled once user exists)
- `POST /api/login` — returns bearer token
- `POST /api/pixels/create` — create a pixel id (auth required)
- `GET /api/stats/summary` — totals (auth required)
- `GET /api/stats/pixels` — hits per pixel (auth required)
- `GET /api/stats/timeseries?bucket=hour&hours=48` — time series (auth required)

## Privacy model (why this is “one-way”)

All sensitive fields are **salted** and hashed with SHA-256 *before disk write*.  
Because the salt is not stored alongside raw values, hashes cannot be reversed into the original IP/UA/referrer.

