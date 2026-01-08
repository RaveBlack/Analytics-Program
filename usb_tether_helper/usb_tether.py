#!/usr/bin/env python3
"""
Linux USB-tether helper (Android/iOS built-in tethering).

This does NOT "replace PDANet" on the phone. It simply:
  - detects the USB-tether network interface created by the kernel
  - brings the interface up
  - acquires an IP address via DHCP (dhclient or udhcpc)

Requires root (or capabilities for ip + DHCP client).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SYS_CLASS_NET = Path("/sys/class/net")


@dataclass(frozen=True)
class Candidate:
    name: str
    driver: str | None
    devtype: str | None


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def _require_root() -> None:
    if os.geteuid() != 0:
        print("This tool must run as root (try: sudo ...)", file=sys.stderr)
        raise SystemExit(2)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _iface_names() -> list[str]:
    try:
        return sorted(p.name for p in SYS_CLASS_NET.iterdir() if p.is_dir())
    except OSError:
        return []


def _is_loopback(name: str) -> bool:
    return name == "lo"


def _sysfs_driver_for_iface(name: str) -> str | None:
    # /sys/class/net/<iface>/device/driver -> .../<driver>
    driver_link = SYS_CLASS_NET / name / "device" / "driver"
    try:
        target = driver_link.resolve()
    except OSError:
        return None
    return target.name if target.name else None


def _sysfs_devtype_for_iface(name: str) -> str | None:
    # /sys/class/net/<iface>/uevent often contains DEVTYPE=...
    uevent = _read_text(SYS_CLASS_NET / name / "uevent")
    if not uevent:
        return None
    m = re.search(r"^DEVTYPE=(.+)$", uevent, flags=re.MULTILINE)
    return m.group(1).strip() if m else None


def _is_probable_usb_tether_iface(name: str, driver: str | None) -> bool:
    # Common USB tethering drivers: rndis_host (RNDIS), cdc_ether (ECM), cdc_ncm (NCM)
    if driver in {"rndis_host", "cdc_ether", "cdc_ncm"}:
        return True
    # Some systems show USB-tether as enx<mac> (still often cdc_* driver, but resolve might fail)
    if name.startswith("usb"):
        return True
    if name.startswith("enx"):
        return True
    if name.startswith("eth") and driver in {"cdc_ether"}:
        return True
    return False


def find_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for name in _iface_names():
        if _is_loopback(name):
            continue
        driver = _sysfs_driver_for_iface(name)
        devtype = _sysfs_devtype_for_iface(name)
        if _is_probable_usb_tether_iface(name, driver):
            out.append(Candidate(name=name, driver=driver, devtype=devtype))
    return out


def choose_iface(preferred: str | None) -> str:
    if preferred:
        if not (SYS_CLASS_NET / preferred).exists():
            raise SystemExit(f"Interface '{preferred}' not found in /sys/class/net.")
        return preferred
    cands = find_candidates()
    if not cands:
        raise SystemExit(
            "No probable USB-tether interface found.\n"
            "Make sure your phone has USB tethering enabled, then re-plug the USB cable."
        )
    # Prefer usb0 if present; otherwise first candidate.
    for c in cands:
        if c.name == "usb0":
            return "usb0"
    return cands[0].name


def iface_up(iface: str) -> None:
    _run(["ip", "link", "set", iface, "up"])


def dhcp(iface: str, *, timeout_s: int) -> None:
    # Try dhclient first (common on Debian/Ubuntu).
    if shutil.which("dhclient"):
        # -1: exit after one lease attempt; -v: verbose; -timeout: overall timeout seconds
        _run(["dhclient", "-v", "-1", "-timeout", str(timeout_s), iface])
        return
    # Try udhcpc (common in busybox / some minimal distros).
    if shutil.which("udhcpc"):
        # -q: quiet; -n: exit if no lease; -t: retries; -T: timeout per try
        # Approximate overall timeout using small per-try timeouts.
        per_try = max(1, min(5, timeout_s))
        tries = max(1, timeout_s // per_try)
        _run(["udhcpc", "-i", iface, "-n", "-T", str(per_try), "-t", str(tries)])
        return
    raise SystemExit("No DHCP client found. Install 'isc-dhcp-client' (dhclient) or 'udhcpc'.")


def show_status(iface: str) -> None:
    for cmd in (["ip", "-br", "link", "show", iface], ["ip", "-br", "addr", "show", iface], ["ip", "route", "show"]):
        try:
            cp = _run(cmd, check=False)
        except FileNotFoundError:
            continue
        if cp.stdout.strip():
            print(cp.stdout.rstrip())


def wait_for_iface(*, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if find_candidates():
            return
        time.sleep(0.5)
    raise SystemExit("Timed out waiting for a USB-tether interface. Enable USB tethering on the phone, then re-plug.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bring up phone USB tethering on Linux (DHCP + link up).")
    p.add_argument("--iface", help="Interface to use (e.g. usb0, enx...). If omitted, auto-detect.")
    p.add_argument("--list", action="store_true", help="List probable USB-tether interfaces and exit.")
    p.add_argument("--watch", action="store_true", help="Wait for USB-tether interface to appear before configuring.")
    p.add_argument("--watch-timeout", type=int, default=30, help="Seconds to wait in --watch mode (default: 30).")
    p.add_argument("--dhcp-timeout", type=int, default=20, help="Seconds for DHCP (default: 20).")
    p.add_argument("--status", action="store_true", help="Print interface and route status after configuring.")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.list:
        cands = find_candidates()
        if not cands:
            print("No probable USB-tether interfaces found.")
            return 1
        for c in cands:
            driver = c.driver or "?"
            devtype = c.devtype or "?"
            print(f"{c.name}\tdriver={driver}\tdevtype={devtype}")
        return 0

    _require_root()

    if args.watch:
        wait_for_iface(timeout_s=int(args.watch_timeout))

    iface = choose_iface(args.iface)
    iface_up(iface)
    dhcp(iface, timeout_s=int(args.dhcp_timeout))

    if args.status:
        show_status(iface)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

