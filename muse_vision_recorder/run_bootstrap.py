"""
Bootstrap runner: installs pip deps automatically, then runs the app.

This is for SOURCE runs (not the packaged EXE).

Usage:
  python muse_vision_recorder/run_bootstrap.py
  python muse_vision_recorder/run_bootstrap.py --mode headless
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _pip_install(requirements_file: Path) -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
    )


def _ensure_importable(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def main() -> None:
    here = Path(__file__).resolve().parent
    req = here / "requirements.txt"

    missing = [m for m in ("numpy", "pylsl") if not _ensure_importable(m)]
    if missing:
        print(f"Installing missing packages: {', '.join(missing)}", flush=True)
        _pip_install(req)

    # Run the module so imports resolve correctly
    os.execv(sys.executable, [sys.executable, "-m", "muse_vision_recorder", *sys.argv[1:]])


if __name__ == "__main__":
    main()

