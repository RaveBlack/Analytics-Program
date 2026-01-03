import base64
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Deque, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request
from scapy.all import AsyncSniffer, IP, Raw, conf  # type: ignore


@dataclass(frozen=True)
class PacketRow:
    id: int
    ts: float
    timestamp: str
    src: str
    dst: str
    protocol: str
    length: int
    summary: str
    payload: str
    is_plain_text: bool


class CaptureState:
    def __init__(self, max_packets: int = 2000) -> None:
        self._lock = threading.Lock()
        self._sniffer: Optional[AsyncSniffer] = None
        self._running = False
        self._filter_ip = ""
        self._iface: Optional[str] = None

        self._next_id = 1
        self._packets: Deque[PacketRow] = deque(maxlen=max_packets)
        self._stats: Dict[str, int] = {
            "packets_total": 0,
            "packets_in": 0,
            "packets_out": 0,
            "bytes_total": 0,
            "bytes_in": 0,
            "bytes_out": 0,
        }

    def get_status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "running": self._running,
                "filter_ip": self._filter_ip,
                "iface": self._iface,
                "buffer_len": len(self._packets),
                "last_id": (self._next_id - 1),
                "stats": dict(self._stats),
            }

    def get_packets(self, since_id: int = 0, limit: int = 200) -> List[Dict[str, object]]:
        with self._lock:
            rows = [p for p in self._packets if p.id > since_id]
            if limit > 0:
                rows = rows[-limit:]
            return [asdict(p) for p in rows]

    def set_filter(self, ip: str) -> None:
        with self._lock:
            self._filter_ip = (ip or "").strip()

    def _packet_ok(self, src: str, dst: str) -> bool:
        with self._lock:
            f = self._filter_ip
        if not f:
            return True
        return f == src or f == dst

    def _on_packet(self, pkt) -> None:
        if IP not in pkt:
            return
        src = pkt[IP].src
        dst = pkt[IP].dst
        if not self._packet_ok(src, dst):
            return

        proto_num = int(pkt[IP].proto)
        protocol = {6: "TCP", 17: "UDP", 1: "ICMP"}.get(proto_num, "OTHER")

        raw_bytes = b""
        payload = ""
        is_plain_text = False
        if Raw in pkt:
            raw_bytes = bytes(pkt[Raw].load)
            try:
                payload = raw_bytes.decode("utf-8", errors="strict")
                is_plain_text = True
            except UnicodeDecodeError:
                payload = base64.b64encode(raw_bytes).decode("utf-8")
                is_plain_text = False

        now = time.time()
        row = PacketRow(
            id=0,
            ts=now,
            timestamp=time.strftime("%H:%M:%S", time.localtime(now)),
            src=src,
            dst=dst,
            protocol=protocol,
            length=len(pkt),
            summary=pkt.summary(),
            payload=payload,
            is_plain_text=is_plain_text,
        )

        with self._lock:
            row = PacketRow(**{**asdict(row), "id": self._next_id})
            self._next_id += 1

            self._packets.append(row)
            self._stats["packets_total"] += 1
            self._stats["bytes_total"] += row.length

            f = self._filter_ip
            # If filter is set, treat direction relative to it.
            # Otherwise direction is unknown; keep it as "out" when src==host is hard to know.
            if f:
                if row.dst == f:
                    self._stats["packets_out"] += 1
                    self._stats["bytes_out"] += row.length
                elif row.src == f:
                    self._stats["packets_in"] += 1
                    self._stats["bytes_in"] += row.length

    def start(self, ip_filter: str = "", iface: Optional[str] = None) -> None:
        ip_filter = (ip_filter or "").strip()
        with self._lock:
            if self._running:
                # If already running, just update filter/iface
                self._filter_ip = ip_filter
                self._iface = iface
                return
            self._filter_ip = ip_filter
            self._iface = iface

            # Reset counters when starting fresh.
            for k in self._stats:
                self._stats[k] = 0

            self._sniffer = AsyncSniffer(
                prn=self._on_packet,
                store=False,
                filter="ip",
                iface=iface,
            )
            self._sniffer.start()
            self._running = True

    def stop(self) -> None:
        sniffer: Optional[AsyncSniffer]
        with self._lock:
            sniffer = self._sniffer
            self._sniffer = None
            self._running = False
        if sniffer is not None:
            try:
                sniffer.stop()
            except Exception:
                # Best-effort stop; sniffers can fail if permissions are missing.
                pass


def _ping_windows(ip: str, count: int = 4, timeout_ms: int = 1000) -> Tuple[int, List[str]]:
    # ping -n <count> -w <timeout_ms>
    cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), ip]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    return proc.returncode, lines


def _ping_unix(ip: str, count: int = 4, timeout_s: int = 1) -> Tuple[int, List[str]]:
    # ping -c <count> -W <timeout_s>
    cmd = ["ping", "-c", str(count), "-W", str(timeout_s), ip]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    return proc.returncode, lines


def create_app(state: CaptureState) -> Flask:
    app = Flask(__name__)

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/interfaces")
    def interfaces():
        # scapy's conf.ifaces is the most portable for Windows/Linux/macOS
        try:
            ifaces = []
            for _, iface in conf.ifaces.items():
                ifaces.append(
                    {
                        "name": getattr(iface, "name", str(iface)),
                        "description": getattr(iface, "description", ""),
                    }
                )
            return jsonify({"interfaces": ifaces})
        except Exception as e:
            return jsonify({"interfaces": [], "error": str(e)}), 500

    @app.get("/api/status")
    def status():
        return jsonify(state.get_status())

    @app.post("/api/filter")
    def set_filter():
        data = request.get_json(silent=True) or {}
        state.set_filter(str(data.get("ip", "")).strip())
        return jsonify(state.get_status())

    @app.post("/api/capture/start")
    def capture_start():
        data = request.get_json(silent=True) or {}
        ip = str(data.get("ip", "")).strip()
        iface = data.get("iface")
        iface = str(iface).strip() if iface else None
        try:
            state.start(ip_filter=ip, iface=iface)
            return jsonify(state.get_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/capture/stop")
    def capture_stop():
        state.stop()
        return jsonify(state.get_status())

    @app.get("/api/packets")
    def packets():
        since = request.args.get("since", "0")
        limit = request.args.get("limit", "200")
        try:
            since_id = int(since)
        except ValueError:
            since_id = 0
        try:
            limit_n = int(limit)
        except ValueError:
            limit_n = 200
        limit_n = max(1, min(limit_n, 2000))
        return jsonify({"packets": state.get_packets(since_id=since_id, limit=limit_n)})

    @app.get("/api/ping")
    def ping():
        ip = (request.args.get("ip") or "").strip()
        if not ip:
            return jsonify({"error": "Missing ip"}), 400

        count = request.args.get("count", "4")
        timeout = request.args.get("timeout_ms", "1000")
        try:
            count_n = max(1, min(int(count), 20))
        except ValueError:
            count_n = 4
        try:
            timeout_ms = max(200, min(int(timeout), 5000))
        except ValueError:
            timeout_ms = 1000

        if sys.platform.startswith("win"):
            rc, lines = _ping_windows(ip, count=count_n, timeout_ms=timeout_ms)
        else:
            rc, lines = _ping_unix(ip, count=count_n, timeout_s=max(1, timeout_ms // 1000))
        return jsonify({"ip": ip, "ok": rc == 0, "returncode": rc, "lines": lines})

    return app


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    state = CaptureState()
    app = create_app(state)
    # Threaded, no reloader: safe for embedding in a terminal app exe.
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    run_server()

