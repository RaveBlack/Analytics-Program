import os
import platform
import socket
import subprocess
import sys
import time
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

    # Linux/macOS (best-effort)
    # systemctl is preferred; fallback to shutdown
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
    shared_key = os.getenv("AGENT_SHARED_KEY", "").strip()

    sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=1)

    @sio.event(namespace="/agent")
    def connect():
        payload = {
            "agent_id": agent_id,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "local_ips": _local_ips(),
            "shared_key": shared_key,
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

