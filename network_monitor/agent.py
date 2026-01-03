import os
import platform
import socket
import subprocess
import sys
import time
import json
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from typing import List

import socketio


def _local_ips() -> List[str]:
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" in ip:
                continue
            if ip.startswith("127."):
                continue
            ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


TOKEN_FILE = Path.home() / ".network_monitor_agent_token"


def _load_token() -> str:
    # env overrides file
    env = os.getenv("AGENT_TOKEN", "").strip()
    if env:
        return env
    try:
        if TOKEN_FILE.exists():
            return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    return ""


def _save_token(token: str) -> None:
    try:
        TOKEN_FILE.write_text(token.strip() + "\n", encoding="utf-8")
    except Exception:
        return


def _http_post_json(url: str, payload: dict, timeout_s: int = 10) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw or "{}")
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        try:
            return json.loads(raw or "{}")
        except Exception:
            return {"ok": False, "error": f"http {e.code}"}
    except URLError as e:
        return {"ok": False, "error": str(e)}


def _pair_if_needed(server_url: str, agent_id: str) -> str:
    token = _load_token()
    if token:
        return token
    code = os.getenv("PAIR_CODE", "").strip()
    if not code:
        return ""
    claim_url = server_url.rstrip("/") + "/api/pairing/claim"
    resp = _http_post_json(
        claim_url,
        {
            "code": code,
            "agent_id": agent_id,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "local_ips": _local_ips(),
        },
        timeout_s=10,
    )
    if resp.get("ok") and resp.get("token"):
        token = str(resp["token"]).strip()
        _save_token(token)
        return token
    return ""


def _shutdown_now() -> None:
    """
    Shutdown ONLY when ENABLE_SHUTDOWN=1 on the agent.
    """
    if os.getenv("ENABLE_SHUTDOWN", "").strip() != "1":
        print("Refusing shutdown: set ENABLE_SHUTDOWN=1 on agent to allow.", flush=True)
        return

    sysname = platform.system().lower()
    if sysname == "windows":
        # Immediate shutdown
        subprocess.Popen(["shutdown", "/s", "/t", "0"])
        return

    if sysname == "darwin":
        # macOS: try AppleScript first (may require permissions), fallback to shutdown
        if _which("osascript"):
            subprocess.Popen(["osascript", "-e", 'tell application "System Events" to shut down'])
            return
        subprocess.Popen(["shutdown", "-h", "now"])
        return

    # Linux (best-effort)
    if _which("systemctl"):
        subprocess.Popen(["systemctl", "poweroff"])
        return
    subprocess.Popen(["shutdown", "-h", "now"])


def _which(cmd: str):
    try:
        import shutil
        return shutil.which(cmd)
    except Exception:
        return None


def main() -> int:
    server_url = os.getenv("SERVER_URL", "http://127.0.0.1:5000").strip()
    agent_id = os.getenv("AGENT_ID", socket.gethostname()).strip()
    # legacy support (server may still require shared key)
    shared_key = os.getenv("AGENT_SHARED_KEY", "").strip()
    token = _pair_if_needed(server_url, agent_id) or _load_token()

    sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=1)

    @sio.event(namespace="/agent")
    def connect():
        payload = {
            "agent_id": agent_id,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "local_ips": _local_ips(),
            "shared_key": shared_key,
            "token": token,
        }
        sio.emit("register", payload, namespace="/agent")

    @sio.on("agent_status", namespace="/agent")
    def on_status(data):
        print(f"[agent_status] {data}", flush=True)

    @sio.on("agent_command", namespace="/agent")
    def on_command(data):
        cmd = (data or {}).get("command")
        print(f"[agent_command] {data}", flush=True)
        if cmd == "shutdown":
            _shutdown_now()

    while True:
        try:
            sio.connect(server_url, namespaces=["/agent"])
            sio.wait()
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print(f"connect error: {e}", file=sys.stderr, flush=True)
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())

