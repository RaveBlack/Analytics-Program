#!/usr/bin/env bash
set -euo pipefail

echo "Building macOS agent..." >&2

python3 -m pip install --upgrade pip
python3 -m pip install -r "requirements-agent.txt"

rm -rf dist build

python3 -m PyInstaller agent.spec

echo "Built: dist/network-monitor-agent" >&2
echo "" >&2
echo "Optional signing/notarization requires Apple Developer credentials." >&2
