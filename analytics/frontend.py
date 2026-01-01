"""
Tiny terminal "frontend" for the local analytics backend.

This is optional (the main UI is served by backend.py at http://127.0.0.1:5000/),
but it satisfies a simple "local frontend" requirement without extra deps.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request


def fetch_json(url: str, timeout: float = 2.5) -> dict:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - localhost tool
        data = resp.read().decode("utf-8")
    return json.loads(data)


def clear_screen() -> None:
    # ANSI clear + home
    print("\033[2J\033[H", end="")


def main() -> int:
    ap = argparse.ArgumentParser(description="Local analytics terminal viewer")
    ap.add_argument("--base-url", default="http://127.0.0.1:5000", help="Backend base URL")
    ap.add_argument("--id", default="", help="Filter by tracking ID (optional)")
    ap.add_argument("--interval", type=float, default=2.0, help="Refresh interval (seconds)")
    ap.add_argument("--limit", type=int, default=10, help="How many recent hits to show")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    filt = args.id.strip()

    while True:
        try:
            stats = fetch_json(f"{base}/api/stats")
            qs = {"limit": str(max(1, min(args.limit, 200)))}
            if filt:
                qs["id"] = filt
            hits = fetch_json(f"{base}/api/hits?{urllib.parse.urlencode(qs)}").get("hits", [])

            clear_screen()
            print(f"Local Analytics Viewer  ({base})")
            print("-" * 72)
            print(f"Total hits : {stats.get('total_hits')}")
            print(f"Unique IDs : {stats.get('unique_ids')}")
            print(f"Last hit   : {stats.get('last_hit_ts_iso')}")
            if filt:
                print(f"Filter ID  : {filt}")
            print("-" * 72)
            for h in hits:
                print(f"{h.get('ts_iso')}  id={h.get('id')}  ip={h.get('ip')}")
                ua = h.get("user_agent", "")
                ref = h.get("referer", "")
                if ua:
                    print(f"  UA: {ua}")
                if ref:
                    print(f"  Ref: {ref}")
            if not hits:
                print("(no hits yet)")
            print("-" * 72)
            print("Tip: open the web UI at " + base + "/")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            clear_screen()
            print("Local Analytics Viewer")
            print("-" * 72)
            print("Backend not reachable yet.")
            print(f"Error: {e}")
            print("")
            print("Start it with:")
            print("  python3 analytics/backend.py")

        time.sleep(max(0.25, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())

