from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

import tkinter as tk
from tkinter import simpledialog, ttk


@dataclass
class UiState:
    connected: bool = False
    recording: bool = False
    status: str = "Idle"
    last_ts_lsl: float = 0.0
    delta: float = 0.0
    theta: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    gamma: float = 0.0


class MuseVisionUi:
    def __init__(
        self,
        *,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_mark_utterance: Callable[[str], None],
    ) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_mark_utterance = on_mark_utterance

        self.root = tk.Tk()
        self.root.title("Muse Vision Recorder (prototype)")

        self.state = UiState()

        self._status_var = tk.StringVar(value=self.state.status)
        self._conn_var = tk.StringVar(value="Disconnected")
        self._rec_var = tk.StringVar(value="Not recording")

        top = ttk.Frame(self.root, padding=10)
        top.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._build_controls(top)
        self._build_bands(top)
        self._build_grid(top)

        self.root.bind("<space>", lambda _e: self.prompt_utterance())

        # dot grid state
        self._grid_w = 64
        self._grid_h = 64
        self._cell = 6
        self._pixels = [[0 for _ in range(self._grid_w)] for _ in range(self._grid_h)]

    def _build_controls(self, parent: ttk.Frame) -> None:
        frm = ttk.LabelFrame(parent, text="Controls", padding=10)
        frm.grid(row=0, column=0, sticky="ew")
        parent.columnconfigure(0, weight=1)

        ttk.Label(frm, textvariable=self._conn_var).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, textvariable=self._rec_var).grid(row=1, column=0, sticky="w")
        ttk.Label(frm, textvariable=self._status_var).grid(row=2, column=0, sticky="w", pady=(6, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=0, column=1, rowspan=3, sticky="e")

        self._start_btn = ttk.Button(btns, text="Start recording", command=self._on_start)
        self._start_btn.grid(row=0, column=0, padx=(10, 0), pady=2)

        self._stop_btn = ttk.Button(btns, text="Stop recording", command=self._on_stop)
        self._stop_btn.grid(row=1, column=0, padx=(10, 0), pady=2)

        self._mark_btn = ttk.Button(btns, text="Mark utterance (Space)", command=self.prompt_utterance)
        self._mark_btn.grid(row=2, column=0, padx=(10, 0), pady=2)

    def _build_bands(self, parent: ttk.Frame) -> None:
        frm = ttk.LabelFrame(parent, text="Band power (mean across channels)", padding=10)
        frm.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self._band_vars = {
            "delta": tk.StringVar(value="0"),
            "theta": tk.StringVar(value="0"),
            "alpha": tk.StringVar(value="0"),
            "beta": tk.StringVar(value="0"),
            "gamma": tk.StringVar(value="0"),
        }

        for i, k in enumerate(["delta", "theta", "alpha", "beta", "gamma"]):
            ttk.Label(frm, text=f"{k}:").grid(row=0, column=i * 2, sticky="e")
            ttk.Label(frm, textvariable=self._band_vars[k], width=14).grid(
                row=0, column=i * 2 + 1, sticky="w", padx=(4, 12)
            )

    def _build_grid(self, parent: ttk.Frame) -> None:
        frm = ttk.LabelFrame(parent, text="Dot grid (feature visualization, not decoded vision)", padding=10)
        frm.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        parent.rowconfigure(2, weight=1)

        w = self._grid_w * self._cell
        h = self._grid_h * self._cell
        self._canvas = tk.Canvas(frm, width=w, height=h, bg="black", highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

    def prompt_utterance(self) -> None:
        label = simpledialog.askstring("Utterance", "Type the utterance/label (what you said/thought):")
        if label is None:
            return
        label = label.strip()
        if not label:
            return
        self._on_mark_utterance(label)

    def update_state(
        self,
        *,
        connected: Optional[bool] = None,
        recording: Optional[bool] = None,
        status: Optional[str] = None,
        bands: Optional[dict[str, float]] = None,
        ts_lsl: Optional[float] = None,
    ) -> None:
        if connected is not None:
            self.state.connected = connected
            self._conn_var.set("Connected" if connected else "Disconnected")
        if recording is not None:
            self.state.recording = recording
            self._rec_var.set("Recording" if recording else "Not recording")
        if status is not None:
            self.state.status = status
            self._status_var.set(status)
        if ts_lsl is not None:
            self.state.last_ts_lsl = ts_lsl
        if bands is not None:
            for k, v in bands.items():
                if k in self._band_vars:
                    self._band_vars[k].set(f"{v:.6g}")
            # Also update grid visualization based on bands.
            self._add_feature_dots(bands)

        # Disable/enable buttons based on recording state
        if self.state.recording:
            self._start_btn.state(["disabled"])
            self._stop_btn.state(["!disabled"])
        else:
            self._start_btn.state(["!disabled"])
            self._stop_btn.state(["disabled"])

    def _add_feature_dots(self, bands: dict[str, float]) -> None:
        """
        A deterministic “dot placement” visualization. This does NOT decode vision.

        It just maps band ratios into (x,y) locations and gradually fills the grid.
        """
        alpha = float(bands.get("alpha", 0.0))
        beta = float(bands.get("beta", 0.0))
        theta = float(bands.get("theta", 0.0))
        gamma = float(bands.get("gamma", 0.0))
        delta = float(bands.get("delta", 0.0))

        s = alpha + beta + theta + gamma + delta + 1e-12
        ax = (alpha + 0.5 * gamma) / s
        ay = (theta + 0.5 * delta) / s

        x = int(ax * (self._grid_w - 1))
        y = int(ay * (self._grid_h - 1))

        # Slowly fade old pixels
        for yy in range(self._grid_h):
            row = self._pixels[yy]
            for xx in range(self._grid_w):
                if row[xx] > 0:
                    row[xx] = max(0, row[xx] - 1)

        # Add a small cluster around (x, y)
        strength = 10
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xx = min(self._grid_w - 1, max(0, x + dx))
                yy = min(self._grid_h - 1, max(0, y + dy))
                self._pixels[yy][xx] = min(255, self._pixels[yy][xx] + strength)

        # Redraw (simple; could be optimized later)
        self._canvas.delete("all")
        for yy in range(self._grid_h):
            for xx in range(self._grid_w):
                v = self._pixels[yy][xx]
                if v <= 0:
                    continue
                c = v
                color = f"#{c:02x}{c:02x}{c:02x}"
                x0 = xx * self._cell
                y0 = yy * self._cell
                self._canvas.create_rectangle(x0, y0, x0 + self._cell, y0 + self._cell, fill=color, outline="")

