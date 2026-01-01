## Local Analytics (minimal tracking pixel)

Single-user, local-only analytics that logs **raw IP address**, User-Agent, Referer, timestamp, and a caller-provided tracking ID.

No hashing. No logins. No accounts. No cloud. No external APIs.

### Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r analytics/requirements.txt

python3 analytics/backend.py
```

Then open the local UI:

- `http://127.0.0.1:5000/`

Optional terminal viewer (polls the JSON API):

```bash
python3 analytics/frontend.py
```

### Tracking pixel (BBCode-compatible)

Use inside a forum post/message that supports `[img]`:

```text
[img]http://127.0.0.1:5000/t/pixel.png?id=THREAD_ID[/img]
```

- Replace `THREAD_ID` with any identifier you want (thread id, post id, campaign tag, etc.)
- When the image loads, the backend logs a hit to SQLite.

### Endpoints

- **Pixel**: `GET /t/pixel.png?id=TRACKING_ID`
- **Stats (JSON)**: `GET /api/stats`
- **Hits (JSON)**: `GET /api/hits?limit=200&id=OPTIONAL_ID`
- **BBCode helper (JSON)**: `GET /api/bbcode?id=THREAD_ID`
- **UI**: `GET /`

### Storage

SQLite database is stored at:

- `analytics/storage/analytics.db`

To wipe all analytics, stop the server and delete that file.

