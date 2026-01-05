#!/usr/bin/env python3
"""
Repo launcher script.

This provides one place to run the projects in this workspace:
- GovCode AI (Next.js): dev/build/start/lint
- Privacy Beacon (Python): run/create/other CLI commands
- Network Monitor (Python): run (needs sudo/root for packet capture)

Examples:
  python3 app.py govcode-ai dev
  python3 app.py govcode-ai build
  python3 app.py govcode-ai start --port 3000

  python3 app.py privacy-beacon run
  python3 app.py privacy-beacon create --label "my-beacon"

  sudo python3 app.py network-monitor run

  python3 app.py all
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


ROOT = Path(__file__).resolve().parent
GOVCODE_DIR = ROOT / "govcode-ai"
PRIVACY_BEACON_DIR = ROOT / "privacy_beacon"
NETWORK_MONITOR_DIR = ROOT / "network_monitor"


def _which_or_die(bin_name: str) -> str:
    p = shutil.which(bin_name)
    if not p:
        raise SystemExit(f"Missing required executable: {bin_name}")
    return p


def _run(cmd: list[str], *, cwd: Optional[Path] = None, env: Optional[dict[str, str]] = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=True)


def _popen(cmd: list[str], *, cwd: Optional[Path] = None, env: Optional[dict[str, str]] = None) -> subprocess.Popen:
    return subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env)


def _ensure_dir_exists(p: Path, label: str) -> None:
    if not p.exists():
        raise SystemExit(f"Missing {label} directory: {p}")


def _npm_install_if_needed(project_dir: Path) -> None:
    node_modules = project_dir / "node_modules"
    if node_modules.exists():
        return
    _which_or_die("npm")
    print("[govcode-ai] Installing dependencies (first run)...", file=sys.stderr)
    # Prefer "npm install" (works everywhere). If you want CI-reproducible installs, swap to "npm ci".
    _run(["npm", "install"], cwd=project_dir)


def cmd_govcode_ai(args: argparse.Namespace) -> None:
    _ensure_dir_exists(GOVCODE_DIR, "govcode-ai")
    _which_or_die("node")
    _which_or_die("npm")

    if args.action in {"dev", "build", "start", "lint"}:
        _npm_install_if_needed(GOVCODE_DIR)

    if args.action == "dev":
        env = os.environ.copy()
        if args.port:
            env["PORT"] = str(args.port)
        cmd = ["npm", "run", "dev"]
        if args.port:
            cmd = ["npm", "run", "dev", "--", "--port", str(args.port)]
        _run(cmd, cwd=GOVCODE_DIR, env=env)
        return

    if args.action == "build":
        _run(["npm", "run", "build"], cwd=GOVCODE_DIR)
        return

    if args.action == "start":
        env = os.environ.copy()
        if args.port:
            env["PORT"] = str(args.port)
        cmd = ["npm", "run", "start"]
        if args.port:
            cmd = ["npm", "run", "start", "--", "--port", str(args.port)]
        _run(cmd, cwd=GOVCODE_DIR, env=env)
        return

    if args.action == "lint":
        _run(["npm", "run", "lint"], cwd=GOVCODE_DIR)
        return

    raise SystemExit(f"Unknown govcode-ai action: {args.action}")


def cmd_privacy_beacon(args: argparse.Namespace) -> None:
    _ensure_dir_exists(PRIVACY_BEACON_DIR, "privacy_beacon")
    _which_or_die("python3")
    _run(["python3", str(PRIVACY_BEACON_DIR / "server.py"), *args.pb_args], cwd=ROOT)


def cmd_network_monitor(args: argparse.Namespace) -> None:
    _ensure_dir_exists(NETWORK_MONITOR_DIR, "network_monitor")
    _which_or_die("python3")
    # Capturing packets typically requires elevated privileges.
    if os.geteuid() != 0:
        print(
            "[network-monitor] Warning: packet capture usually requires sudo/root.\n"
            "Try: sudo python3 app.py network-monitor run",
            file=sys.stderr,
        )
    _run(["python3", str(NETWORK_MONITOR_DIR / "app.py")], cwd=NETWORK_MONITOR_DIR)


def cmd_all(args: argparse.Namespace) -> None:
    """
    Start multiple services at once (long-running).

    - GovCode AI (Next.js) dev server on --govcode-port
    - Privacy Beacon on its configured port (default 8080)
    """
    _ensure_dir_exists(GOVCODE_DIR, "govcode-ai")
    _ensure_dir_exists(PRIVACY_BEACON_DIR, "privacy_beacon")

    _which_or_die("python3")
    _which_or_die("node")
    _which_or_die("npm")

    _npm_install_if_needed(GOVCODE_DIR)

    env = os.environ.copy()
    govcode_port = int(args.govcode_port)
    env["PORT"] = str(govcode_port)

    procs: list[subprocess.Popen] = []

    def shutdown(_signum: int, _frame) -> None:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=10)
            except Exception:
                pass
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"[all] Starting privacy_beacon (dashboard on http://127.0.0.1:8080/)", file=sys.stderr)
    procs.append(_popen(["python3", str(PRIVACY_BEACON_DIR / "server.py"), "run"], cwd=ROOT, env=env))

    print(f"[all] Starting govcode-ai (http://127.0.0.1:{govcode_port}/)", file=sys.stderr)
    procs.append(_popen(["npm", "run", "dev", "--", "--port", str(govcode_port)], cwd=GOVCODE_DIR, env=env))

    # Wait for any process to exit; if one exits, shut down the rest.
    while True:
        for p in procs:
            code = p.poll()
            if code is not None:
                print(f"[all] A service exited with code {code}. Shutting down.", file=sys.stderr)
                shutdown(signal.SIGTERM, None)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.py", description="Workspace launcher")
    # If no command is provided, we'll print help (see main()).
    sub = p.add_subparsers(dest="command", required=False)

    gov = sub.add_parser("govcode-ai", help="Run GovCode AI (Next.js) app")
    gov.add_argument("action", choices=["dev", "build", "start", "lint"])
    gov.add_argument("--port", type=int, default=None)
    gov.set_defaults(func=cmd_govcode_ai)

    pb = sub.add_parser("privacy-beacon", help="Run privacy_beacon/server.py CLI")
    pb.add_argument("pb_args", nargs=argparse.REMAINDER, help="Arguments passed to privacy_beacon/server.py")
    pb.set_defaults(func=cmd_privacy_beacon)

    nm = sub.add_parser("network-monitor", help="Run network_monitor app")
    nm.add_argument("action", choices=["run"])
    nm.set_defaults(func=cmd_network_monitor)

    allp = sub.add_parser("all", help="Start govcode-ai + privacy beacon")
    allp.add_argument("--govcode-port", type=int, default=3000)
    allp.set_defaults(func=cmd_all)

    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "command", None):
        parser.print_help(sys.stdout)
        return 0
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

