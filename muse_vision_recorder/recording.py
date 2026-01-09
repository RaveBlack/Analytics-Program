from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class SessionPaths:
    root: Path
    metadata_json: Path
    eeg_csv: Path
    bands_csv: Path
    events_csv: Path


def create_session_folder(base_dir: Path) -> SessionPaths:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = base_dir / f"session_{ts}"
    root.mkdir(parents=True, exist_ok=False)
    return SessionPaths(
        root=root,
        metadata_json=root / "metadata.json",
        eeg_csv=root / "eeg.csv",
        bands_csv=root / "bands.csv",
        events_csv=root / "events.csv",
    )


class SessionWriter:
    def __init__(
        self,
        paths: SessionPaths,
        *,
        channel_labels: list[str],
    ) -> None:
        self.paths = paths
        self.channel_labels = channel_labels

        self._eeg_f = open(paths.eeg_csv, "w", newline="", encoding="utf-8")
        self._bands_f = open(paths.bands_csv, "w", newline="", encoding="utf-8")
        self._events_f = open(paths.events_csv, "w", newline="", encoding="utf-8")

        self._eeg = csv.writer(self._eeg_f)
        self._bands = csv.writer(self._bands_f)
        self._events = csv.writer(self._events_f)

        self._eeg.writerow(["ts_lsl", "ts_local_iso", *channel_labels])
        self._bands.writerow(
            [
                "ts_lsl",
                "ts_local_iso",
                "delta",
                "theta",
                "alpha",
                "beta",
                "gamma",
            ]
        )
        self._events.writerow(["ts_lsl", "ts_local_iso", "event_type", "label"])

        self._closed = False

    def write_metadata(self, metadata: dict) -> None:
        data = dict(metadata)
        data.setdefault("created_utc", utc_now_iso())
        self.paths.metadata_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def write_eeg_row(self, *, ts_lsl: float, values: list[float]) -> None:
        self._eeg.writerow([f"{ts_lsl:.6f}", utc_now_iso(), *[f"{v:.6f}" for v in values]])

    def write_band_row(
        self,
        *,
        ts_lsl: float,
        delta: float,
        theta: float,
        alpha: float,
        beta: float,
        gamma: float,
    ) -> None:
        self._bands.writerow(
            [
                f"{ts_lsl:.6f}",
                utc_now_iso(),
                f"{delta:.9f}",
                f"{theta:.9f}",
                f"{alpha:.9f}",
                f"{beta:.9f}",
                f"{gamma:.9f}",
            ]
        )

    def write_event(self, *, ts_lsl: float, event_type: str, label: str) -> None:
        self._events.writerow([f"{ts_lsl:.6f}", utc_now_iso(), event_type, label])

    def close(self) -> None:
        if self._closed:
            return
        for f in (self._eeg_f, self._bands_f, self._events_f):
            try:
                f.flush()
            finally:
                f.close()
        self._closed = True

    def __enter__(self) -> "SessionWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

