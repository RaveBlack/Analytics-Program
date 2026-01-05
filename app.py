#!/usr/bin/env python3
"""
High-bandwidth *monitor* (safe): ping + local interface bandwidth.

This tool is intentionally rate-limited and does NOT implement traffic flooding.
It is meant for legitimate connectivity troubleshooting on your own network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


HISTORY_FILE_DEFAULT = ".hbping_history.json"

# User-requested bounds for the alert thresholds (Mbps).
ALERT_MIN_FLOOR_Mbps = 50.0
ALERT_MAX_CEIL_Mbps = 900.0

# Safety limits for ping cadence.
PING_INTERVAL_MIN_S = 0.2
PING_INTERVAL_MAX_S = 10.0


def _now_s() -> float:
    return time.time()


def _fmt_mbps(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:7.1f}"


def _fmt_ms(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:6.1f}"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def list_interfaces_linux() -> list[str]:
    """Return interface names from /proc/net/dev (Linux)."""
    ifaces: list[str] = []
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        for line in lines[2:]:
            if ":" not in line:
                continue
            name = line.split(":", 1)[0].strip()
            if name:
                ifaces.append(name)
    except OSError:
        pass
    return ifaces


def get_default_interface_linux() -> Optional[str]:
    """Try to detect the default-route interface on Linux."""
    ip = shutil.which("ip")
    if not ip:
        return None
    try:
        out = subprocess.check_output([ip, "route", "show", "default"], text=True)
    except Exception:
        return None
    # Example: "default via 192.168.1.1 dev wlan0 proto dhcp metric 600"
    m = re.search(r"\bdev\s+(\S+)", out)
    return m.group(1) if m else None


@dataclass
class NetDevSample:
    ts: float
    rx_bytes: int
    tx_bytes: int


def read_netdev_bytes_linux(iface: str) -> tuple[int, int]:
    """
    Read RX/TX bytes for an interface from /proc/net/dev.
    Returns (rx_bytes, tx_bytes).
    """
    with open("/proc/net/dev", "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    for line in lines[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name != iface:
            continue
        fields = rest.split()
        # /proc/net/dev: receive fields then transmit fields
        rx_bytes = int(fields[0])
        tx_bytes = int(fields[8])
        return rx_bytes, tx_bytes
    raise ValueError(f"Interface not found in /proc/net/dev: {iface!r}")


@dataclass
class PingStats:
    target: str
    sent: int = 0
    received: int = 0
    last_rtt_ms: Optional[float] = None
    rtt_sum_ms: float = 0.0
    rtt_min_ms: Optional[float] = None
    rtt_max_ms: Optional[float] = None
    last_line: str = ""
    error: Optional[str] = None
    started_at: float = field(default_factory=_now_s)

    def record_reply(self, rtt_ms: float) -> None:
        self.received += 1
        self.last_rtt_ms = rtt_ms
        self.rtt_sum_ms += rtt_ms
        self.rtt_min_ms = rtt_ms if self.rtt_min_ms is None else min(self.rtt_min_ms, rtt_ms)
        self.rtt_max_ms = rtt_ms if self.rtt_max_ms is None else max(self.rtt_max_ms, rtt_ms)

    @property
    def loss_pct(self) -> float:
        if self.sent <= 0:
            return 0.0
        return 100.0 * (self.sent - self.received) / self.sent

    @property
    def avg_rtt_ms(self) -> Optional[float]:
        if self.received <= 0:
            return None
        return self.rtt_sum_ms / self.received


class PingRunner:
    """
    Runs system ping and parses replies.

    Notes:
    - Uses system `ping` to avoid raw-socket permissions.
    - Intentionally does not support payload size changes or flood modes.
    """

    _time_re = re.compile(r"\btime[=<]([\d.]+)\s*ms\b")
    _seq_re = re.compile(r"\bicmp_seq=(\d+)\b")

    def __init__(self, target: str, interval_s: float, count: Optional[int] = None) -> None:
        self.target = target
        self.interval_s = interval_s
        self.count = count
        self.stats = PingStats(target=target)
        self._proc: Optional[subprocess.Popen[str]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        ping = shutil.which("ping")
        if not ping:
            raise RuntimeError("`ping` not found on PATH")

        # -n: numeric output; -i: interval; -c: count (optional).
        # Intentionally: no -f (flood) and no payload size options.
        cmd = [ping, "-n", "-i", f"{self.interval_s}"]
        if self.count is not None:
            cmd += ["-c", str(self.count)]
        cmd += [self.target]

        # Line-buffered text output.
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        self._thread = threading.Thread(target=self._read_loop, name="ping-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def is_done(self) -> bool:
        return self._proc is not None and self._proc.poll() is not None

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            line = line.rstrip("\n")
            self.stats.last_line = line

            # Common Linux capability/setuid failures in restricted environments/containers.
            if (
                "Operation not permitted" in line
                or "missing cap_net_raw" in line
                or "cap_net_raw" in line and "missing" in line
            ):
                self.stats.error = line
                self._stop.set()
                break

            # Count "sent" by looking for icmp_seq as it increases.
            mseq = self._seq_re.search(line)
            if mseq:
                seq = int(mseq.group(1))
                self.stats.sent = max(self.stats.sent, seq)

            # Parse RTT when present.
            mt = self._time_re.search(line)
            if mt:
                try:
                    rtt = float(mt.group(1))
                except ValueError:
                    continue
                self.stats.record_reply(rtt)


def load_history(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"runs": []}


def save_history(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def run_monitor(
    target: str,
    iface: str,
    interval_s: float,
    alert_min_mbps: float,
    alert_max_mbps: float,
    history_path: str,
    *,
    duration_s: Optional[float] = None,
    count: Optional[int] = None,
) -> int:
    alert_min_mbps = _clamp(alert_min_mbps, ALERT_MIN_FLOOR_Mbps, ALERT_MAX_CEIL_Mbps)
    alert_max_mbps = _clamp(alert_max_mbps, ALERT_MIN_FLOOR_Mbps, ALERT_MAX_CEIL_Mbps)
    if alert_min_mbps > alert_max_mbps:
        alert_min_mbps, alert_max_mbps = alert_max_mbps, alert_min_mbps

    interval_s = _clamp(interval_s, PING_INTERVAL_MIN_S, PING_INTERVAL_MAX_S)

    try:
        rx0, tx0 = read_netdev_bytes_linux(iface)
    except Exception as e:
        print(f"Error reading interface stats for {iface!r}: {e}", file=sys.stderr)
        return 2

    pr = PingRunner(target=target, interval_s=interval_s, count=count)
    try:
        pr.start()
    except Exception as e:
        print(f"Error starting ping: {e}", file=sys.stderr)
        return 2

    # Give ping a moment to fail fast with a permission/capability error.
    time.sleep(0.2)
    if pr.is_done() and pr.stats.error:
        print("Ping failed due to missing ICMP permissions/capabilities.", file=sys.stderr)
        print(f"ping output: {pr.stats.error}", file=sys.stderr)
        print(
            "Fix (Linux): install a normal ping (iputils-ping) or grant capability, e.g.\n"
            "  sudo setcap cap_net_raw+ep \"$(command -v ping)\"\n"
            "Then re-run this app.",
            file=sys.stderr,
        )
        return 2

    start_ts = _now_s()
    last = NetDevSample(ts=start_ts, rx_bytes=rx0, tx_bytes=tx0)
    max_rx_mbps: float = 0.0
    max_tx_mbps: float = 0.0

    banner = (
        f"Target: {target} | Interface: {iface} | ping interval: {interval_s}s | "
        f"alerts: {alert_min_mbps:.0f}-{alert_max_mbps:.0f} Mbps"
    )
    if count is not None:
        banner += f" | count: {count}"
    if duration_s is not None:
        banner += f" | duration: {duration_s}s"
    print(banner, flush=True)
    print("Press Ctrl+C to stop.\n", flush=True)

    try:
        while True:
            time.sleep(1.0)
            ts = _now_s()
            if duration_s is not None and (ts - start_ts) >= duration_s:
                break
            if pr.is_done():
                break
            rx, tx = read_netdev_bytes_linux(iface)
            dt = max(0.001, ts - last.ts)
            rx_mbps = ((rx - last.rx_bytes) * 8.0) / dt / 1_000_000.0
            tx_mbps = ((tx - last.tx_bytes) * 8.0) / dt / 1_000_000.0
            max_rx_mbps = max(max_rx_mbps, rx_mbps)
            max_tx_mbps = max(max_tx_mbps, tx_mbps)
            last = NetDevSample(ts=ts, rx_bytes=rx, tx_bytes=tx)

            bw_warn = ""
            if rx_mbps > alert_max_mbps or tx_mbps > alert_max_mbps:
                bw_warn = "  BW:HIGH"
            elif rx_mbps < alert_min_mbps and tx_mbps < alert_min_mbps:
                bw_warn = "  BW:LOW"

            st = pr.stats
            uptime = int(ts - start_ts)
            line = (
                f"t+{uptime:>4}s  "
                f"rtt last/avg/min/max(ms): {_fmt_ms(st.last_rtt_ms)}/{_fmt_ms(st.avg_rtt_ms)}/"
                f"{_fmt_ms(st.rtt_min_ms)}/{_fmt_ms(st.rtt_max_ms)}  "
                f"loss: {st.loss_pct:5.1f}% ({st.received}/{max(1, st.sent)})  "
                f"RX/TX(Mbps): {_fmt_mbps(rx_mbps)}/{_fmt_mbps(tx_mbps)}{bw_warn}"
            )
            # Update-in-place (keeps terminal readable).
            print("\r" + line + " " * 8, end="", flush=True)

    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        pr.stop()

    # Save history.
    st = pr.stats
    hist = load_history(history_path)
    hist.setdefault("runs", []).append(
        {
            "timestamp": int(start_ts),
            "target": target,
            "iface": iface,
            "ping_interval_s": interval_s,
            "sent": st.sent,
            "received": st.received,
            "loss_pct": round(st.loss_pct, 2),
            "rtt_ms": {
                "min": st.rtt_min_ms,
                "avg": st.avg_rtt_ms,
                "max": st.rtt_max_ms,
            },
            "max_iface_mbps": {"rx": round(max_rx_mbps, 2), "tx": round(max_tx_mbps, 2)},
            "alerts_mbps": {"min": alert_min_mbps, "max": alert_max_mbps},
        }
    )
    saved_ok = True
    try:
        save_history(history_path, hist)
    except Exception:
        saved_ok = False

    print(
        f"Summary: loss={st.loss_pct:.1f}% sent={st.sent} recv={st.received} "
        f"rtt avg={st.avg_rtt_ms if st.avg_rtt_ms is not None else 'n/a'} ms "
        f"max RX/TX={max_rx_mbps:.1f}/{max_tx_mbps:.1f} Mbps"
    )
    if saved_ok:
        print(f"History saved to: {history_path}")
    else:
        print(f"History not saved (write failed): {history_path}", file=sys.stderr)
    return 0


def interactive(args: argparse.Namespace) -> int:
    print("High-bandwidth ping monitor (safe). Type a target IP/host to start.\n")

    detected_iface = get_default_interface_linux() or "wlan0"
    ifaces = list_interfaces_linux()
    if detected_iface not in ifaces and ifaces:
        detected_iface = ifaces[0]

    while True:
        try:
            target = input("Target (ip/host) or 'q' to quit: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not target:
            continue
        if target.lower() in {"q", "quit", "exit"}:
            return 0

        iface = input(f"Interface [{detected_iface}]: ").strip() or detected_iface
        interval_s = args.interval

        try:
            amin = float(input(f"Alert MIN Mbps [{args.alert_min}]: ").strip() or str(args.alert_min))
            amax = float(input(f"Alert MAX Mbps [{args.alert_max}]: ").strip() or str(args.alert_max))
        except ValueError:
            print("Invalid alert number(s). Try again.\n")
            continue

        history_path = args.history
        print()
        return run_monitor(
            target=target,
            iface=iface,
            interval_s=interval_s,
            alert_min_mbps=amin,
            alert_max_mbps=amax,
            history_path=history_path,
            duration_s=args.duration,
            count=args.count,
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="app.py",
        description="Ping + local interface RX/TX Mbps monitor (rate-limited; not a flood tool).",
    )
    p.add_argument("--target", help="Target IP/hostname to ping. If omitted, runs interactive mode.")
    p.add_argument("--iface", help="Network interface to read (e.g. wlan0, eth0). Auto-detect if omitted.")
    p.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help=f"Ping interval seconds (clamped to {PING_INTERVAL_MIN_S}-{PING_INTERVAL_MAX_S}). Default: 1.0",
    )
    p.add_argument(
        "--alert-min",
        type=float,
        default=50.0,
        help=f"Low bandwidth alert threshold Mbps (clamped to {ALERT_MIN_FLOOR_Mbps}-{ALERT_MAX_CEIL_Mbps}).",
    )
    p.add_argument(
        "--alert-max",
        type=float,
        default=900.0,
        help=f"High bandwidth alert threshold Mbps (clamped to {ALERT_MIN_FLOOR_Mbps}-{ALERT_MAX_CEIL_Mbps}).",
    )
    p.add_argument(
        "--history",
        default=HISTORY_FILE_DEFAULT,
        help=f"Where to save run history JSON. Default: {HISTORY_FILE_DEFAULT}",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Stop automatically after N seconds (optional).",
    )
    p.add_argument(
        "--count",
        type=int,
        default=None,
        help="Send N pings then stop (optional).",
    )
    return p


def main(argv: list[str]) -> int:
    p = build_parser()
    args = p.parse_args(argv)

    # Basic protection against misuse: we won't accept extra ping arguments.
    # (If you need more, we can add safe options like count/timeout.)
    if args.target is None:
        return interactive(args)

    iface = args.iface or get_default_interface_linux()
    if not iface:
        ifaces = list_interfaces_linux()
        iface = next((i for i in ifaces if i != "lo"), None) or (ifaces[0] if ifaces else None)
    if not iface:
        print("Could not detect a network interface. Provide --iface.", file=sys.stderr)
        return 2

    return run_monitor(
        target=args.target,
        iface=iface,
        interval_s=args.interval,
        alert_min_mbps=args.alert_min,
        alert_max_mbps=args.alert_max,
        history_path=args.history,
        duration_s=args.duration,
        count=args.count,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

