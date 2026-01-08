#!/usr/bin/env python3
"""
Controller input monitor + analog curve tuner.

This app:
- Polls a connected game controller (via pygame)
- Samples state at a fixed interval (default: 0.1s)
- Applies deadzone + response curve + optional smoothing for *analysis*
- Shows a small visualization window
- Logs sampled values to a CSV file

Important: This tool does NOT inject inputs into games.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def apply_deadzone_and_curve(x: float, deadzone: float, gamma: float) -> float:
    """
    Map raw axis [-1, 1] -> adjusted [-1, 1] with:
    - symmetric deadzone
    - rescale outside deadzone to keep full range
    - power curve (gamma)
    """
    x = clamp(x, -1.0, 1.0)
    dz = clamp(deadzone, 0.0, 0.99)
    if abs(x) <= dz:
        return 0.0

    sign = -1.0 if x < 0 else 1.0
    mag = (abs(x) - dz) / (1.0 - dz)
    mag = clamp(mag, 0.0, 1.0)

    g = max(0.01, float(gamma))
    curved = math.pow(mag, g)
    return sign * curved


@dataclass
class Config:
    sample_interval_s: float = 0.1
    deadzone: float = 0.12
    curve_gamma: float = 1.6
    smoothing_alpha: float = 0.35
    csv_log_path: str = "controller_log.csv"

    @staticmethod
    def from_json_file(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config(
            sample_interval_s=float(data.get("sample_interval_s", 0.1)),
            deadzone=float(data.get("deadzone", 0.12)),
            curve_gamma=float(data.get("curve_gamma", 1.6)),
            smoothing_alpha=float(data.get("smoothing_alpha", 0.35)),
            csv_log_path=str(data.get("csv_log_path", "controller_log.csv")),
        )


def _try_import_pygame():
    try:
        import pygame  # type: ignore
    except Exception as e:  # pragma: no cover
        raise SystemExit(
            "pygame is required.\n"
            "Install:\n"
            "  python3 -m pip install -r controller_tools/requirements.txt\n"
            f"\nImport error: {e}\n"
        )
    return pygame


def _format_bool(b: bool) -> str:
    return "1" if b else "0"


def _init_first_joystick(pygame):
    pygame.joystick.init()
    n = pygame.joystick.get_count()
    if n <= 0:
        raise SystemExit("No controllers detected. Plug one in and re-run.")
    js = pygame.joystick.Joystick(0)
    js.init()
    return js


def _draw_bar(pygame, screen, x: int, y: int, w: int, h: int, value: float, label: str):
    # value expected in [-1, 1]
    value = clamp(value, -1.0, 1.0)
    mid = x + w // 2
    pygame.draw.rect(screen, (40, 40, 40), pygame.Rect(x, y, w, h), border_radius=6)
    pygame.draw.line(screen, (80, 80, 80), (mid, y), (mid, y + h), 2)

    # fill left/right from center
    fill = int((w // 2) * abs(value))
    if value >= 0:
        rect = pygame.Rect(mid, y, fill, h)
        color = (80, 180, 120)
    else:
        rect = pygame.Rect(mid - fill, y, fill, h)
        color = (200, 110, 110)
    pygame.draw.rect(screen, color, rect, border_radius=6)

    font = pygame.font.SysFont("consolas", 16)
    txt = font.render(f"{label}: {value:+.3f}", True, (230, 230, 230))
    screen.blit(txt, (x, y - 18))


def run(config: Config) -> int:
    pygame = _try_import_pygame()

    os.makedirs(os.path.dirname(config.csv_log_path) or ".", exist_ok=True)

    pygame.init()
    pygame.display.set_caption("Controller Monitor (no injection)")
    screen = pygame.display.set_mode((760, 520))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)

    js = _init_first_joystick(pygame)
    name = js.get_name()

    num_axes = js.get_numaxes()
    num_buttons = js.get_numbuttons()
    num_hats = js.get_numhats()

    # Exponential smoothing state (per-axis)
    smoothed_axes: List[float] = [0.0 for _ in range(num_axes)]
    alpha = clamp(config.smoothing_alpha, 0.0, 1.0)

    sample_interval = max(0.01, float(config.sample_interval_s))
    next_sample = time.perf_counter()

    # CSV logging
    # We log both raw and adjusted axes so you can tune curves.
    fieldnames = (
        ["unix_ts", "monotonic_s"]
        + [f"axis_raw_{i}" for i in range(num_axes)]
        + [f"axis_adj_{i}" for i in range(num_axes)]
        + [f"btn_{i}" for i in range(num_buttons)]
        + [f"hat_{i}_x" for i in range(num_hats)]
        + [f"hat_{i}_y" for i in range(num_hats)]
    )

    with open(config.csv_log_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        running = True
        last_status_line = ""

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            now = time.perf_counter()
            if now >= next_sample:
                # Keep schedule stable even if we miss a frame.
                missed = int((now - next_sample) // sample_interval)
                next_sample = next_sample + (missed + 1) * sample_interval

                pygame.event.pump()

                axes_raw = [float(js.get_axis(i)) for i in range(num_axes)]
                axes_adj = [
                    apply_deadzone_and_curve(v, config.deadzone, config.curve_gamma)
                    for v in axes_raw
                ]

                if alpha > 0.0:
                    for i, v in enumerate(axes_adj):
                        smoothed_axes[i] = (alpha * v) + ((1.0 - alpha) * smoothed_axes[i])
                    axes_view = smoothed_axes[:]
                else:
                    axes_view = axes_adj

                buttons = [bool(js.get_button(i)) for i in range(num_buttons)]
                hats: List[Tuple[int, int]] = [js.get_hat(i) for i in range(num_hats)]

                row = {
                    "unix_ts": f"{time.time():.3f}",
                    "monotonic_s": f"{now:.6f}",
                }
                for i, v in enumerate(axes_raw):
                    row[f"axis_raw_{i}"] = f"{v:+.6f}"
                for i, v in enumerate(axes_adj):
                    row[f"axis_adj_{i}"] = f"{v:+.6f}"
                for i, b in enumerate(buttons):
                    row[f"btn_{i}"] = _format_bool(b)
                for i, (hx, hy) in enumerate(hats):
                    row[f"hat_{i}_x"] = str(hx)
                    row[f"hat_{i}_y"] = str(hy)

                writer.writerow(row)
                f.flush()

                # Draw UI
                screen.fill((18, 18, 20))

                header = font.render(
                    f"Controller: {name} | axes={num_axes} buttons={num_buttons} hats={num_hats} | "
                    f"sample={sample_interval:.2f}s dz={config.deadzone:.2f} gamma={config.curve_gamma:.2f} alpha={alpha:.2f}",
                    True,
                    (230, 230, 230),
                )
                screen.blit(header, (16, 14))

                info = font.render(
                    f"Logging to: {os.path.abspath(config.csv_log_path)} (ESC to quit)",
                    True,
                    (170, 170, 170),
                )
                screen.blit(info, (16, 38))

                # Axes bars (show adjusted/smoothed view)
                y0 = 90
                for i, v in enumerate(axes_view[:10]):  # cap to avoid clutter
                    _draw_bar(
                        pygame,
                        screen,
                        x=40,
                        y=y0 + i * 42,
                        w=520,
                        h=18,
                        value=v,
                        label=f"axis {i}",
                    )

                # Buttons grid
                bx0, by0 = 600, 90
                bw, bh = 48, 28
                cols = 3
                for i, pressed in enumerate(buttons[:24]):  # cap for display
                    cx = i % cols
                    cy = i // cols
                    r = pygame.Rect(bx0 + cx * (bw + 10), by0 + cy * (bh + 10), bw, bh)
                    pygame.draw.rect(
                        screen,
                        (70, 160, 100) if pressed else (55, 55, 60),
                        r,
                        border_radius=6,
                    )
                    label = font.render(str(i), True, (235, 235, 235))
                    screen.blit(label, (r.x + 16, r.y + 6))

                # Hats
                hats_line = " | ".join([f"hat{i}={h}" for i, h in enumerate(hats)]) or "hat0=(n/a)"
                if hats_line != last_status_line:
                    last_status_line = hats_line
                hats_txt = font.render(last_status_line, True, (170, 170, 170))
                screen.blit(hats_txt, (16, 480))

                pygame.display.flip()

            # Keep event loop responsive; don't burn CPU.
            clock.tick(120)

    pygame.quit()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Controller input monitor (no injection).")
    p.add_argument(
        "--config",
        default=None,
        help="Path to JSON config (see controller_tools/config.example.json).",
    )
    p.add_argument("--sample", type=float, default=None, help="Sample interval seconds (e.g. 0.1).")
    p.add_argument("--deadzone", type=float, default=None, help="Analog deadzone (0.0-0.99).")
    p.add_argument("--gamma", type=float, default=None, help="Response curve gamma (e.g. 1.6).")
    p.add_argument("--alpha", type=float, default=None, help="Smoothing alpha (0-1). 0 disables.")
    p.add_argument("--log", default=None, help="CSV log path (default from config).")
    args = p.parse_args(argv)

    cfg = Config()
    if args.config:
        cfg = Config.from_json_file(args.config)

    if args.sample is not None:
        cfg.sample_interval_s = float(args.sample)
    if args.deadzone is not None:
        cfg.deadzone = float(args.deadzone)
    if args.gamma is not None:
        cfg.curve_gamma = float(args.gamma)
    if args.alpha is not None:
        cfg.smoothing_alpha = float(args.alpha)
    if args.log is not None:
        cfg.csv_log_path = str(args.log)

    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())

