import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from flask_socketio import SocketIO, emit
from scapy.all import sniff, AsyncSniffer, IP, TCP, UDP, Raw, ARP
from collections import deque
import ipaddress
import os
import platform
import re
import shutil
import subprocess
import time
import json
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

# Passive MITM-detection state (no interception, no spoofing)
_arp_sniffer: Optional[AsyncSniffer] = None
_arp_events: "deque[Dict[str, Any]]" = deque(maxlen=300)
_ip_to_macs: Dict[str, set] = {}
_gateway_ip_last: Optional[str] = None
_gateway_mac_last: Optional[str] = None

# Device discovery (controlled ping sweep -> populate ARP/neighbor cache)
_discover_job: Dict[str, Any] = {"running": False, "started_at": None, "finished_at": None}
_discover_results: List[Dict[str, Any]] = []
_router_leases: List[Dict[str, str]] = []

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

def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def _is_wifi_interface_name(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return False
    # Exclude explicitly
    if "ethernet" in n or n.startswith("eth") or n.startswith("en"):
        return False
    if "pdanet" in n:
        return False
    # Include common Wi-Fi markers
    return any(k in n for k in ("wi-fi", "wifi", "wireless", "wlan")) or n.startswith("wl")


def _windows_wifi_interface_names() -> List[str]:
    """
    Best-effort Wi-Fi interface names on Windows.
    """
    rc, out = _run_command(["netsh", "wlan", "show", "interfaces"], timeout_s=10)
    if rc != 0:
        return []
    names = []
    # Example: "    Name                   : Wi-Fi"
    for line in out.splitlines():
        m = re.match(r"^\s*Name\s*:\s*(.+)\s*$", line)
        if m:
            names.append(m.group(1).strip())
    return names


def _list_interfaces() -> List[Dict[str, str]]:
    sysname = platform.system().lower()
    if sysname == "windows":
        # netsh interface show interface
        rc, out = _run_command(["netsh", "interface", "show", "interface"], timeout_s=10)
        if rc != 0:
            return []
        wifi_names = set(_windows_wifi_interface_names())
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
                name = parts[3]
                # Keep Wi‑Fi only; exclude Ethernet/PDANet/etc.
                if wifi_names:
                    if name not in wifi_names:
                        continue
                else:
                    if not _is_wifi_interface_name(name):
                        continue
                interfaces.append({"name": name, "state": parts[1], "type": parts[2]})
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
            if not _is_wifi_interface_name(name):
                continue
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


def _is_private_v4(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.version == 4 and addr.is_private
    except ValueError:
        return False


def _get_local_ipv4_networks() -> List[Dict[str, str]]:
    """
    Best-effort detection of locally configured IPv4 networks.
    Returns items like: {"iface": "...", "cidr": "192.168.1.0/24", "ip": "192.168.1.10"}
    """
    sysname = platform.system().lower()
    nets: List[Dict[str, str]] = []

    if sysname == "windows":
        rc, out = _run_command(["ipconfig"], timeout_s=10)
        if rc != 0:
            return []
        current_iface = ""
        ip_val = ""
        mask_val = ""
        for line in out.splitlines():
            line = line.rstrip()
            # "Wireless LAN adapter Wi-Fi:" / "Ethernet adapter Ethernet:"
            m_iface = re.match(r"^[A-Za-z].*adapter\s+(.+):\s*$", line.strip())
            if m_iface:
                current_iface = m_iface.group(1).strip()
                ip_val = ""
                mask_val = ""
                continue
            m_ip = re.search(r"IPv4 Address[.\s]*:\s*(\d{1,3}(?:\.\d{1,3}){3})", line)
            if m_ip:
                ip_val = m_ip.group(1)
                continue
            m_mask = re.search(r"Subnet Mask[.\s]*:\s*(\d{1,3}(?:\.\d{1,3}){3})", line)
            if m_mask:
                mask_val = m_mask.group(1)
            if current_iface and ip_val and mask_val:
                try:
                    net = ipaddress.IPv4Network(f"{ip_val}/{mask_val}", strict=False)
                    nets.append({"iface": current_iface, "cidr": str(net), "ip": ip_val})
                except ValueError:
                    pass
                ip_val = ""
                mask_val = ""
        # Prefer private nets first
        nets.sort(key=lambda x: 0 if _is_private_v4(x["ip"]) else 1)
        return nets

    # Linux/macOS: ip -o -f inet addr show
    if _which("ip"):
        rc, out = _run_command(["ip", "-o", "-f", "inet", "addr", "show"], timeout_s=10)
        if rc != 0:
            return []
        # "2: eth0    inet 192.168.1.10/24 brd ... scope global eth0"
        for line in out.splitlines():
            m = re.match(r"^\d+:\s+(?P<iface>\S+)\s+inet\s+(?P<cidr>\d{1,3}(?:\.\d{1,3}){3}/\d+)\b", line.strip())
            if not m:
                continue
            iface = m.group("iface")
            cidr = m.group("cidr")
            try:
                net = ipaddress.IPv4Network(cidr, strict=False)
                ip = cidr.split("/", 1)[0]
                nets.append({"iface": iface, "cidr": str(net), "ip": ip})
            except ValueError:
                continue
        nets.sort(key=lambda x: 0 if _is_private_v4(x["ip"]) else 1)
        return nets

    return nets


def _ping_once(ip: str, timeout_ms: int = 350) -> Tuple[int, str]:
    sysname = platform.system().lower()
    if sysname == "windows":
        # -n 1 = one echo, -w timeout in ms
        return _run_command(["ping", "-n", "1", "-w", str(timeout_ms), ip], timeout_s=5)
    # Linux/macOS: -c 1 one packet; -W is seconds on Linux, -t on mac varies.
    # Use a short overall subprocess timeout and rely on it.
    return _run_command(["ping", "-c", "1", "-n", ip], timeout_s=2)


def _run_discovery(cidr: str, max_hosts: int) -> None:
    """
    Background job: ping a limited number of hosts in cidr to populate neighbor cache,
    then return neighbor/ARP table as "connected-ish" devices.
    """
    global _discover_job, _discover_results
    _discover_job = {"running": True, "started_at": datetime.utcnow().isoformat() + "Z", "finished_at": None, "cidr": cidr, "max_hosts": max_hosts}
    _discover_results = []

    try:
        net = ipaddress.IPv4Network(cidr, strict=False)
        count = 0
        for host in net.hosts():
            if count >= max_hosts:
                break
            ip = str(host)
            # Only touch private ranges (safety guard)
            if not _is_private_v4(ip):
                continue
            count += 1
            _ping_once(ip)
            if count % 16 == 0:
                socketio.emit("discover_status", {"running": True, "progress": count, "max_hosts": max_hosts})
                eventlet.sleep(0)

        # After pings, read neighbor cache
        devices = _list_neighbor_devices()
        # Deduplicate by IP
        seen = set()
        results = []
        for d in devices:
            ip = (d.get("ip") or "").strip()
            if not ip or ip in seen:
                continue
            seen.add(ip)
            results.append(d)
        _discover_results = results
        socketio.emit("discover_results", {"devices": results, "cidr": cidr})
    finally:
        _discover_job["running"] = False
        _discover_job["finished_at"] = datetime.utcnow().isoformat() + "Z"
        socketio.emit("discover_status", {"running": False, "finished_at": _discover_job["finished_at"]})



def _get_default_gateway_ip() -> Optional[str]:
    """
    Best-effort default gateway detection (no scanning).
    """
    sysname = platform.system().lower()
    if sysname == "windows":
        rc, out = _run_command(["ipconfig"], timeout_s=10)
        if rc != 0:
            return None
        # "Default Gateway . . . . . . . . . : 192.168.1.1"
        for line in out.splitlines():
            if "Default Gateway" in line:
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                if m:
                    return m.group(1)
        return None

    # Linux/macOS: "ip route show default"
    if _which("ip"):
        rc, out = _run_command(["ip", "route", "show", "default"], timeout_s=10)
        if rc != 0:
            return None
        # "default via 192.168.1.1 dev wlan0 ..."
        m = re.search(r"\bvia\s+(\d{1,3}(?:\.\d{1,3}){3})\b", out)
        if m:
            return m.group(1)
    return None


def _normalize_mac(mac: str) -> str:
    mac = (mac or "").strip().lower()
    return mac


def _neighbor_mac_for_ip(ip: str) -> str:
    for d in _list_neighbor_devices():
        if d.get("ip") == ip:
            return _normalize_mac(d.get("mac") or "")
    return ""


def _record_arp_event(kind: str, details: Dict[str, Any]) -> None:
    _arp_events.appendleft(
        {
            "time": datetime.utcnow().isoformat() + "Z",
            "kind": kind,
            **details,
        }
    )


def _arp_callback(pkt: Any) -> None:
    try:
        if ARP not in pkt:
            return
        arp = pkt[ARP]
        ip = str(getattr(arp, "psrc", "") or "").strip()
        mac = _normalize_mac(str(getattr(arp, "hwsrc", "") or ""))
        op = int(getattr(arp, "op", 0) or 0)  # 1=request, 2=reply
        if not ip or not mac:
            return

        seen = _ip_to_macs.setdefault(ip, set())
        if mac not in seen and len(seen) > 0:
            _record_arp_event(
                "ip_conflict_suspected",
                {"ip": ip, "new_mac": mac, "known_macs": sorted(seen), "op": op},
            )
        seen.add(mac)
    except Exception:
        # Never let packet parsing crash the server
        return


def _arp_monitor_running() -> bool:
    return bool(_arp_sniffer and getattr(_arp_sniffer, "running", False))


def _start_arp_monitor() -> None:
    global _arp_sniffer
    if os.getenv("DISABLE_ARP_MONITOR", "").strip() == "1":
        return
    if _arp_monitor_running():
        return
    _arp_sniffer = AsyncSniffer(filter="arp", prn=_arp_callback, store=False)
    _arp_sniffer.start()
    _record_arp_event("monitor_started", {})


def _stop_arp_monitor() -> None:
    global _arp_sniffer
    if not _arp_sniffer:
        return
    try:
        if getattr(_arp_sniffer, "running", False):
            _arp_sniffer.stop()
            _record_arp_event("monitor_stopped", {})
    finally:
        _arp_sniffer = None


def _compute_mitm_indicators() -> Dict[str, Any]:
    """
    Returns passive indicators only:
    - duplicate IP->MAC mapping changes
    - default gateway MAC change
    - recent ARP-based conflicts seen
    """
    global _gateway_ip_last, _gateway_mac_last
    indicators: List[Dict[str, Any]] = []

    # Duplicate IPs in neighbor cache (same IP, multiple MACs observed historically)
    conflicts = [
        {"ip": ip, "macs": sorted(list(macs))}
        for ip, macs in _ip_to_macs.items()
        if len(macs) > 1
    ]
    if conflicts:
        indicators.append({"type": "duplicate_ip_mapping", "severity": "medium", "details": conflicts})

    # Gateway change indicator
    gw_ip = _get_default_gateway_ip()
    gw_mac = _neighbor_mac_for_ip(gw_ip) if gw_ip else ""
    if gw_ip:
        if not gw_mac:
            indicators.append(
                {
                    "type": "gateway_mac_unknown",
                    "severity": "info",
                    "details": {"gateway_ip": gw_ip, "note": "Gateway MAC not in neighbor/ARP cache yet."},
                }
            )
        else:
            if _gateway_ip_last == gw_ip and _gateway_mac_last and _gateway_mac_last != gw_mac:
                indicators.append(
                    {
                        "type": "gateway_mac_changed",
                        "severity": "high",
                        "details": {"gateway_ip": gw_ip, "old_mac": _gateway_mac_last, "new_mac": gw_mac},
                    }
                )
            _gateway_ip_last = gw_ip
            _gateway_mac_last = gw_mac

    # Recent ARP conflict events (from passive monitor)
    recent = list(_arp_events)[:25]
    if any(e.get("kind") == "ip_conflict_suspected" for e in recent):
        indicators.append({"type": "arp_conflict_events", "severity": "medium", "details": recent[:10]})

    return {
        "gateway_ip": gw_ip or "",
        "gateway_mac": gw_mac or "",
        "arp_monitor_running": _arp_monitor_running(),
        "indicators": indicators,
        "recent_events": recent,
    }

def _parse_router_leases_text(text: str) -> List[Dict[str, str]]:
    """
    Parses a router DHCP lease export from:
    - CSV with headers (ip, mac, hostname) in any order (case-insensitive)
    - OpenWrt-style /tmp/dhcp.leases lines: "<expiry> <mac> <ip> <hostname> <clientid>"
    Returns list of {ip, mac, hostname, source}.
    """
    text = (text or "").strip()
    if not text:
        return []

    # Heuristic: OpenWrt dhcp.leases format
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    leases: List[Dict[str, str]] = []
    openwrt_hits = 0
    for ln in lines[:25]:
        parts = re.split(r"\s+", ln)
        if len(parts) >= 4 and parts[0].isdigit() and re.match(r"^[0-9a-fA-F:]{17}$", parts[1]):
            openwrt_hits += 1
    if openwrt_hits >= 2:
        for ln in lines:
            parts = re.split(r"\s+", ln)
            if len(parts) < 4:
                continue
            expiry, mac, ip, hostname = parts[0], parts[1], parts[2], parts[3]
            if not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", ip):
                continue
            leases.append(
                {
                    "ip": ip,
                    "mac": _normalize_mac(mac),
                    "hostname": hostname if hostname != "*" else "",
                    "source": "router_openwrt_dhcp_leases",
                }
            )
        return leases

    # CSV-ish parsing (simple, no extra dependency)
    # Accept comma or tab separated
    delim = "," if "," in lines[0] else ("\t" if "\t" in lines[0] else ",")
    header = [h.strip().lower() for h in lines[0].split(delim)]
    has_header = any(h in ("ip", "address", "ipv4", "mac", "hostname", "name") for h in header)

    def col_idx(*names: str) -> int:
        for n in names:
            if n in header:
                return header.index(n)
        return -1

    ip_i = col_idx("ip", "address", "ipv4")
    mac_i = col_idx("mac", "mac address", "mac_address")
    host_i = col_idx("hostname", "name", "device", "client")

    start = 1 if has_header else 0
    for ln in lines[start:]:
        cols = [c.strip() for c in ln.split(delim)]
        ip = cols[ip_i] if ip_i >= 0 and ip_i < len(cols) else ""
        mac = cols[mac_i] if mac_i >= 0 and mac_i < len(cols) else ""
        hostname = cols[host_i] if host_i >= 0 and host_i < len(cols) else ""
        # Fallback: try to find IP and MAC anywhere
        if not ip:
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", ln)
            ip = m.group(1) if m else ""
        if not mac:
            m = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", ln)
            mac = m.group(1) if m else ""
        if not ip and not mac:
            continue
        leases.append(
            {
                "ip": ip,
                "mac": _normalize_mac(mac),
                "hostname": hostname,
                "source": "router_csv",
            }
        )
    return leases


def _merge_devices(neigh: List[Dict[str, str]], leases: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Merge neighbor/ARP list with router leases by IP (and MAC if present).
    """
    merged_by_ip: Dict[str, Dict[str, str]] = {}
    for d in neigh:
        ip = (d.get("ip") or "").strip()
        if not ip:
            continue
        merged_by_ip[ip] = {
            "ip": ip,
            "mac": _normalize_mac(d.get("mac") or ""),
            "hostname": "",
            "iface": d.get("iface") or "",
            "state": d.get("state") or "",
            "sources": "neighbor",
        }
    for l in leases:
        ip = (l.get("ip") or "").strip()
        if not ip:
            continue
        cur = merged_by_ip.get(ip)
        if not cur:
            merged_by_ip[ip] = {
                "ip": ip,
                "mac": _normalize_mac(l.get("mac") or ""),
                "hostname": l.get("hostname") or "",
                "iface": "",
                "state": "",
                "sources": l.get("source") or "router",
            }
        else:
            # fill missing fields
            if not cur.get("mac") and l.get("mac"):
                cur["mac"] = _normalize_mac(l.get("mac") or "")
            if not cur.get("hostname") and l.get("hostname"):
                cur["hostname"] = l.get("hostname") or ""
            cur["sources"] = ",".join(sorted(set((cur.get("sources") or "").split(",") + [(l.get("source") or "router")]))).strip(",")

    # Sort private IPs first then numerically
    def ip_key(x: Dict[str, str]) -> Tuple[int, int]:
        ip = x.get("ip", "")
        try:
            addr = ipaddress.ip_address(ip)
            return (0 if getattr(addr, "is_private", False) else 1, int(addr))
        except ValueError:
            return (2, 0)

    return sorted(list(merged_by_ip.values()), key=ip_key)

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
        is_plain_text = True
        
        # Extract L7 payload (always plain text; no base64 encoding)
        if Raw in packet:
            raw_bytes = packet[Raw].load
            # Always decode into readable text; replace undecodable bytes.
            payload = raw_bytes.decode("utf-8", errors="replace")
        
        # Correct wording/format for UI display
        summary = packet.summary()
        if protocol == "TCP" and TCP in packet:
            sport = int(packet[TCP].sport)
            dport = int(packet[TCP].dport)
            ftp_kind = "FTP"
            if sport == 21 or dport == 21:
                ftp_kind = "FTP (control)"
            elif sport == 20 or dport == 20:
                ftp_kind = "FTP (data)"
            summary = f"{ftp_kind} {src_ip}:{sport} -> {dst_ip}:{dport}"

        pkt_data = {
            "timestamp": time.strftime("%H:%M:%S", time.localtime()),
            "src": src_ip,
            "dst": dst_ip,
            "protocol": protocol,
            "length": len(packet),
            "payload": payload,
            "is_plain_text": is_plain_text,
            "summary": summary,
        }
        
        socketio.emit('new_packet', pkt_data)
        eventlet.sleep(0) # Yield to eventlet loop

def start_sniffing():
    logger.info("Starting packet sniffer...")
    # store=0 prevents memory buildup
    # Keep only FTP control/data channels (TCP/21 and TCP/20).
    # This keeps the UI focused on FTP connections for IP tracking.
    sniff(prn=packet_callback, filter="tcp port 21 or tcp port 20", store=0)

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
            "time": _utc_now_iso(),
            "tshark_available": bool(_which("tshark")),
            "platform": platform.platform(),
        }
    )


@app.route('/api/interfaces')
def api_interfaces():
    return jsonify({"interfaces": _list_interfaces()})

@app.route('/api/network/info')
def api_network_info():
    nets = _get_local_ipv4_networks()
    return jsonify({"networks": nets, "default_gateway": _get_default_gateway_ip() or ""})


@app.route('/api/devices')
def api_devices():
    return jsonify({"devices": _list_neighbor_devices()})

@app.route('/api/router/leases/import', methods=['POST'])
def api_router_leases_import():
    """
    Import router DHCP leases export (CSV or dhcp.leases text).
    Accepts either:
    - multipart/form-data with file field "file"
    - application/json with {"text": "..."}
    """
    global _router_leases
    text = ""

    if request.files and "file" in request.files:
        f = request.files["file"]
        try:
            text = f.read().decode("utf-8", errors="replace")
        except Exception:
            return jsonify({"ok": False, "error": "Failed to read uploaded file"}), 400
    else:
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "") or "")

    leases = _parse_router_leases_text(text)
    if not leases:
        return jsonify({"ok": False, "error": "No leases parsed. Upload a CSV or dhcp.leases text."}), 400
    _router_leases = leases
    return jsonify({"ok": True, "count": len(leases)})


@app.route('/api/router/leases')
def api_router_leases():
    return jsonify({"leases": _router_leases})


@app.route('/api/devices/merged')
def api_devices_merged():
    neigh = _list_neighbor_devices()
    merged = _merge_devices(neigh, _router_leases)
    return jsonify({"devices": merged, "neighbor_count": len(neigh), "lease_count": len(_router_leases)})


@app.route('/api/devices/merged.csv')
def api_devices_merged_csv():
    neigh = _list_neighbor_devices()
    merged = _merge_devices(neigh, _router_leases)
    lines = ["ip,mac,hostname,iface,state,sources"]
    for d in merged:
        # very small csv escaping
        def esc(v: str) -> str:
            v = (v or "").replace('"', '""')
            return f"\"{v}\"" if ("," in v or "\n" in v) else v
        lines.append(
            ",".join(
                [
                    esc(d.get("ip", "")),
                    esc(d.get("mac", "")),
                    esc(d.get("hostname", "")),
                    esc(d.get("iface", "")),
                    esc(d.get("state", "")),
                    esc(d.get("sources", "")),
                ]
            )
        )
    body = "\n".join(lines) + "\n"
    return Response(body, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=devices_merged.csv"})

@app.route('/api/discover/start', methods=['POST'])
def api_discover_start():
    """
    Starts a controlled ping sweep on a private local subnet (defaults to first detected private network).
    This is NOT port scanning; it only tries ICMP echo to populate ARP/neighbor cache.
    """
    global _discover_job
    if _discover_job.get("running"):
        return jsonify({"ok": True, "running": True, "job": _discover_job})

    data = request.get_json(silent=True) or {}
    cidr = str(data.get("cidr", "") or "").strip()
    max_hosts = int(data.get("max_hosts", 128) or 128)
    max_hosts = max(16, min(max_hosts, 512))

    if not cidr:
        nets = _get_local_ipv4_networks()
        if not nets:
            return jsonify({"ok": False, "error": "Could not detect local networks. Provide cidr manually."}), 400
        cidr = nets[0]["cidr"]

    try:
        net = ipaddress.IPv4Network(cidr, strict=False)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid cidr. Example: 192.168.1.0/24"}), 400

    # Safety: only allow RFC1918 private networks and keep jobs bounded
    if not net.is_private:
        return jsonify({"ok": False, "error": "Only private (RFC1918) networks are allowed."}), 400

    # Spawn background job (non-blocking)
    eventlet.spawn_n(_run_discovery, str(net), max_hosts)
    return jsonify({"ok": True, "running": True, "cidr": str(net), "max_hosts": max_hosts})


@app.route('/api/discover/status')
def api_discover_status():
    return jsonify({"job": _discover_job})


@app.route('/api/discover/results')
def api_discover_results():
    return jsonify({"devices": _discover_results, "job": _discover_job})

@app.route('/api/mitm/summary')
def api_mitm_summary():
    # Build baseline from current neighbor cache too (helps even if ARP sniff isn't running)
    for d in _list_neighbor_devices():
        ip = (d.get("ip") or "").strip()
        mac = _normalize_mac(d.get("mac") or "")
        if ip and mac:
            _ip_to_macs.setdefault(ip, set()).add(mac)
    return jsonify(_compute_mitm_indicators())


@app.route('/api/mitm/monitor/start', methods=['POST'])
def api_mitm_monitor_start():
    try:
        _start_arp_monitor()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to start ARP monitor: {e}"}), 500
    return jsonify({"ok": True, "running": _arp_monitor_running()})


@app.route('/api/mitm/monitor/stop', methods=['POST'])
def api_mitm_monitor_stop():
    try:
        _stop_arp_monitor()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to stop ARP monitor: {e}"}), 500
    return jsonify({"ok": True, "running": _arp_monitor_running()})


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
