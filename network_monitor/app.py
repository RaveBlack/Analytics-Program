import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from scapy.all import sniff, IP, TCP, UDP, Raw
import ipaddress
import os
import platform
import re
import shutil
import subprocess
import time
import json
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TrafficMonitor")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Global control variables
sniffing = True
# Simple string filter for IP presence (source or dest)
target_ip_filter = "" 

# Wireshark CLI (tshark) capture management (safe, local-only tooling)
CAPTURE_DIR = (Path(__file__).resolve().parent / "captures")
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

# capture_id -> process info
_tshark_processes: Dict[str, Dict[str, Any]] = {}


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}[A-Za-z0-9]$|^\[[0-9A-Fa-f:]+\]$")


def _validate_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        raise ValueError("Host is required.")
    # Allow IP literals or simple hostnames. No spaces, no shell metacharacters.
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if not _HOST_RE.match(host):
        raise ValueError("Invalid host. Use an IP or hostname.")
    return host


def _run_command(args: List[str], timeout_s: int = 15) -> Tuple[int, str]:
    """
    Runs a command safely (no shell). Returns (exit_code, combined_output).
    """
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_s,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired as e:
        out = ""
        if getattr(e, "stdout", None):
            out += e.stdout
        if getattr(e, "stderr", None):
            out += e.stderr
        return 124, (out or "") + "\n[timeout]\n"
    except FileNotFoundError:
        return 127, f"[not found] {args[0]}\n"


def _list_interfaces() -> List[Dict[str, str]]:
    sysname = platform.system().lower()
    if sysname == "windows":
        # netsh interface show interface
        rc, out = _run_command(["netsh", "interface", "show", "interface"], timeout_s=10)
        if rc != 0:
            return []
        interfaces: List[Dict[str, str]] = []
        # Typical lines:
        # Admin State    State          Type             Interface Name
        # Enabled        Connected      Dedicated        Ethernet
        for line in out.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("admin state") or line.startswith("-"):
                continue
            parts = re.split(r"\s{2,}", line)
            if len(parts) >= 4:
                interfaces.append(
                    {
                        "name": parts[3],
                        "state": parts[1],
                        "type": parts[2],
                    }
                )
        return interfaces

    # Linux/macOS: prefer "ip link", fallback to ifconfig
    if _which("ip"):
        rc, out = _run_command(["ip", "-o", "link", "show"], timeout_s=10)
        if rc != 0:
            return []
        interfaces = []
        # Example: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> ..."
        for line in out.splitlines():
            m = re.match(r"^\d+:\s+([^:]+):\s+<([^>]*)>", line)
            if not m:
                continue
            name = m.group(1)
            flags = m.group(2)
            state = "UP" if "UP" in flags.split(",") else "DOWN"
            interfaces.append({"name": name, "state": state, "type": "link"})
        return interfaces

    return []


def _list_neighbor_devices() -> List[Dict[str, str]]:
    """
    Passive device list from OS neighbor/ARP cache (no scanning).
    """
    sysname = platform.system().lower()
    devices: List[Dict[str, str]] = []
    if sysname == "windows":
        rc, out = _run_command(["arp", "-a"], timeout_s=10)
        if rc != 0:
            return []
        # Lines like: "  192.168.1.1          aa-bb-cc-dd-ee-ff     dynamic"
        for line in out.splitlines():
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F\-]{17})\s+(\w+)", line)
            if m:
                devices.append({"ip": m.group(1), "mac": m.group(2), "state": m.group(3)})
        return devices

    # Linux/macOS: "ip neigh"
    if _which("ip"):
        rc, out = _run_command(["ip", "neigh"], timeout_s=10)
        if rc != 0:
            return []
        # Example: "192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE"
        for line in out.splitlines():
            m = re.match(
                r"^(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+dev\s+(?P<dev>\S+)(?:\s+lladdr\s+(?P<mac>[0-9a-fA-F:]{17}))?\s+(?P<state>\S+)",
                line.strip(),
            )
            if m:
                devices.append(
                    {
                        "ip": m.group("ip"),
                        "mac": m.group("mac") or "",
                        "iface": m.group("dev"),
                        "state": m.group("state"),
                    }
                )
        return devices

    return devices

def packet_callback(packet):
    global target_ip_filter, sniffing
    
    if not sniffing:
        return

    if IP in packet:
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        
        # Filter logic: if filter is set, one of the IPs must match
        if target_ip_filter and (target_ip_filter != src_ip and target_ip_filter != dst_ip):
            return

        proto_num = packet[IP].proto
        protocol = "OTHER"
        if proto_num == 6:
            protocol = "TCP"
        elif proto_num == 17:
            protocol = "UDP"
        elif proto_num == 1:
            protocol = "ICMP"

        payload = ""
        is_plain_text = False
        raw_bytes = b""
        
        # Extract L7 payload
        if Raw in packet:
            raw_bytes = packet[Raw].load
            try:
                # Try to decode as UTF-8 for "plain text"
                payload = raw_bytes.decode('utf-8')
                is_plain_text = True
            except UnicodeDecodeError:
                # If binary, we encode it as base64 so it can be sent to JSON
                # The frontend can then decide to show it as Hex or try other decodings
                payload = base64.b64encode(raw_bytes).decode('utf-8')
                is_plain_text = False
        
        pkt_data = {
            'timestamp': time.strftime('%H:%M:%S', time.localtime()),
            'src': src_ip,
            'dst': dst_ip,
            'protocol': protocol,
            'length': len(packet),
            'payload': payload,
            'is_plain_text': is_plain_text,
            'summary': packet.summary()
        }
        
        socketio.emit('new_packet', pkt_data)
        eventlet.sleep(0) # Yield to eventlet loop

def start_sniffing():
    logger.info("Starting packet sniffer...")
    # store=0 prevents memory buildup
    # filter="ip" ensures we only look at IP packets (IPv4)
    sniff(prn=packet_callback, filter="ip", store=0)

sniffer_thread = None
_sniffer_started = False


def _ensure_sniffer_started() -> None:
    """
    Start packet sniffing lazily so importing this module does not require
    elevated privileges (and so API-only usage is possible).
    """
    global sniffer_thread, _sniffer_started
    if _sniffer_started:
        return
    if os.getenv("DISABLE_SNIFFER", "").strip() == "1":
        logger.info("Sniffer disabled via DISABLE_SNIFFER=1")
        _sniffer_started = True
        return
    # Note: eventlet.spawn is preferred under eventlet async mode
    sniffer_thread = eventlet.spawn(start_sniffing)
    _sniffer_started = True

@app.route('/')
def index():
    _ensure_sniffer_started()
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify(
        {
            "ok": True,
            "time": datetime.utcnow().isoformat() + "Z",
            "tshark_available": bool(_which("tshark")),
            "platform": platform.platform(),
        }
    )


@app.route('/api/interfaces')
def api_interfaces():
    return jsonify({"interfaces": _list_interfaces()})


@app.route('/api/devices')
def api_devices():
    return jsonify({"devices": _list_neighbor_devices()})


@app.route('/api/ping', methods=['POST'])
def api_ping():
    data = request.get_json(silent=True) or {}
    host = _validate_host(str(data.get("host", "")))
    count = int(data.get("count", 4) or 4)
    count = max(1, min(count, 10))

    sysname = platform.system().lower()
    if sysname == "windows":
        args = ["ping", "-n", str(count), host]
    else:
        args = ["ping", "-c", str(count), "-n", host]

    rc, out = _run_command(args, timeout_s=20)
    return jsonify({"host": host, "exit_code": rc, "output": out})


@app.route('/api/traceroute', methods=['POST'])
def api_traceroute():
    data = request.get_json(silent=True) or {}
    host = _validate_host(str(data.get("host", "")))
    max_hops = int(data.get("max_hops", 20) or 20)
    max_hops = max(1, min(max_hops, 30))

    sysname = platform.system().lower()
    if sysname == "windows":
        args = ["tracert", "-h", str(max_hops), host]
    else:
        cmd = "traceroute" if _which("traceroute") else "tracepath"
        if cmd == "traceroute":
            args = ["traceroute", "-n", "-m", str(max_hops), host]
        else:
            # tracepath doesn't support max hops consistently; keep it simple
            args = ["tracepath", "-n", host]

    rc, out = _run_command(args, timeout_s=45)
    return jsonify({"host": host, "exit_code": rc, "output": out})


def _safe_capture_filename(prefix: str = "capture") -> Tuple[str, Path]:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    # short random-ish suffix without importing uuid (keep deterministic-ish)
    suffix = str(int(time.time() * 1000))[-6:]
    name = f"{prefix}_{stamp}_{suffix}.pcapng"
    path = (CAPTURE_DIR / name).resolve()
    # ensure it stays under CAPTURE_DIR
    if CAPTURE_DIR not in path.parents:
        raise ValueError("Invalid capture path.")
    return name, path


@app.route('/api/capture/start', methods=['POST'])
def api_capture_start():
    """
    Starts a tshark capture to a file.
    Safe defaults: duration-limited, local interface only, no custom filters by default.
    """
    if not _which("tshark"):
        return jsonify({"ok": False, "error": "tshark not found. Install Wireshark/tshark and ensure it is in PATH."}), 400

    data = request.get_json(silent=True) or {}
    iface = str(data.get("interface", "")).strip()
    duration = int(data.get("duration_seconds", 30) or 30)
    duration = max(5, min(duration, 300))

    # Validate interface name against discovered interfaces (best-effort)
    interfaces = {i.get("name") for i in _list_interfaces()}
    if iface and interfaces and iface not in interfaces:
        return jsonify({"ok": False, "error": f"Unknown interface: {iface}"}), 400

    filename, path = _safe_capture_filename()
    capture_id = filename.rsplit(".", 1)[0]

    args = ["tshark"]
    if iface:
        args += ["-i", iface]
    # Write to file
    args += ["-w", str(path)]
    # Duration limit (prevents runaway captures)
    args += ["-a", f"duration:{duration}"]

    # Start process (no shell). Keep stdout for basic status.
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to start tshark: {e}"}), 500

    _tshark_processes[capture_id] = {
        "pid": proc.pid,
        "interface": iface,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "duration_seconds": duration,
        "filename": filename,
        "path": str(path),
        "proc": proc,
    }

    return jsonify({"ok": True, "capture_id": capture_id, "filename": filename})


@app.route('/api/capture/stop', methods=['POST'])
def api_capture_stop():
    data = request.get_json(silent=True) or {}
    capture_id = str(data.get("capture_id", "")).strip()
    info = _tshark_processes.get(capture_id)
    if not info:
        return jsonify({"ok": False, "error": "Unknown capture_id"}), 404

    proc = info.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route('/api/capture/list')
def api_capture_list():
    items = []
    for p in sorted(CAPTURE_DIR.glob("*.pcap*"), key=lambda x: x.stat().st_mtime, reverse=True):
        items.append(
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "modified_at": datetime.utcfromtimestamp(p.stat().st_mtime).isoformat() + "Z",
            }
        )
    return jsonify({"captures": items})


@app.route('/api/capture/download/<path:filename>')
def api_capture_download(filename: str):
    # Only allow files in CAPTURE_DIR
    safe_name = os.path.basename(filename)
    return send_from_directory(str(CAPTURE_DIR), safe_name, as_attachment=True)


@socketio.on('connect')
def test_connect():
    _ensure_sniffer_started()
    emit('status', {'msg': 'Connected to Traffic Monitor'})

@socketio.on('set_filter')
def handle_filter(data):
    global target_ip_filter
    target_ip_filter = data.get('ip', '').strip()
    emit('status', {'msg': f'Filter set to: {target_ip_filter if target_ip_filter else "None"}'})

@socketio.on('toggle_sniffing')
def handle_toggle(data):
    global sniffing
    sniffing = data.get('state', True)
    status = "Resumed" if sniffing else "Paused"
    emit('status', {'msg': f'Sniffing {status}'})

if __name__ == '__main__':
    # We must run with sudo for scapy to sniff on Linux
    print("Starting Web Server on http://0.0.0.0:5000")
    print("NOTE: You must run this script with sudo privileges to capture packets.")
    socketio.run(app, host='0.0.0.0', port=5000)
