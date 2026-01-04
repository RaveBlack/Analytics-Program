#!/usr/bin/env python3
"""
Entry point for PyInstaller / easy launching.

This "main.py" simply loads and forwards into `turbo_pad_win.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional, Sequence


def _load_turbo_module():
    here = Path(__file__).resolve().parent
    target = here / "turbo_pad_win.py"
    spec = importlib.util.spec_from_file_location("turbo_pad_win", target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {target}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def main(argv: Optional[Sequence[str]] = None) -> int:
    mod = _load_turbo_module()
    # turbo_pad_win.py defines main(argv=None) -> int
    return int(mod.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())

