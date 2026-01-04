#!/usr/bin/env python3
"""
Windows: read a real gamepad and emit a virtual Xbox 360 controller.

Features:
- Auto-tap buttons: on physical press, emit down immediately, then release after --interval
- Forward sticks/triggers; optionally sample at --interval

Dependencies:
- ViGEmBus driver (system)
- Python packages: inputs, vgamepad
"""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from inputs import devices, get_gamepad  # type: ignore[import-not-found]
import vgamepad as vg  # type: ignore[import-not-found]


@dataclass(frozen=True)
class GamepadEvent:
    ev_type: str  # "Key" or "Absolute"
    code: str
    state: int


# inputs -> vgamepad button map (common Xbox layout)
BTN_MAP: Dict[str, vg.XUSB_BUTTON] = {
    "BTN_SOUTH": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    "BTN_EAST": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
    "BTN_WEST": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
    "BTN_NORTH": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
    "BTN_TL": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    "BTN_TR": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "BTN_SELECT": vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    "BTN_START": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
    "BTN_THUMBL": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
    "BTN_THUMBR": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
    # Some controllers expose the Xbox/Guide button; games may ignore it.
    "BTN_MODE": vg.XUSB_BUTTON.XUSB_GAMEPAD_GUIDE,
}


def _normalize_signed_axis(raw: int) -> int:
    """
    Normalize various raw ranges to signed int16 (-32768..32767).

    Common ranges seen via `inputs` on Windows:
    - 0..255 (center 128)
    - 0..65535 (center 32768)
    - already -32768..32767
    """
    if -32768 <= raw <= 32767:
        val = raw
    elif 0 <= raw <= 255:
        center = 128
        span = 127
        val = int((raw - center) * 32767 / span)
    elif 0 <= raw <= 65535:
        center = 32768
        span = 32767
        val = int((raw - center) * 32767 / span)
    else:
        # Fallback: clamp
        val = raw

    if val < -32768:
        return -32768
    if val > 32767:
        return 32767
    return val


def _normalize_trigger(raw: int) -> int:
    """
    Normalize triggers to 0..255.
    """
    if 0 <= raw <= 255:
        return raw
    if 0 <= raw <= 65535:
        return int(raw / 257)  # 65535/255 ~ 257
    # fallback clamp
    if raw < 0:
        return 0
    if raw > 255:
        return 255
    return int(raw)


def _list_gamepads() -> None:
    gps = getattr(devices, "gamepads", [])
    if not gps:
        print("No gamepads found via inputs/devices.")
        return
    for i, d in enumerate(gps):
        name = getattr(d, "name", "(unknown)")
        print(f"[{i}] {name}")


def _event_reader(stop: threading.Event, q: Queue[GamepadEvent]) -> None:
    # get_gamepad() blocks; run it in a thread.
    while not stop.is_set():
        try:
            events = get_gamepad()
        except Exception:
            # Avoid hard crash if device is unplugged; small backoff.
            time.sleep(0.1)
            continue

        for e in events:
            # The inputs lib uses objects with .ev_type / .code / .state
            q.put(GamepadEvent(ev_type=str(e.ev_type), code=str(e.code), state=int(e.state)))


def _parse_auto_codes(tokens: Sequence[str]) -> Set[str]:
    return {t.strip().upper() for t in tokens if t.strip()}


def run(
    *,
    interval_s: float,
    auto_codes: Set[str],
    auto_all: bool,
    analog_sample: bool,
    print_events: bool,
) -> None:
    if interval_s <= 0:
        raise SystemExit("--interval must be > 0")
    if interval_s < 0.01:
        raise SystemExit("--interval too small; minimum is 0.01s")

    pad = vg.VX360Gamepad()

    supported_auto = set(BTN_MAP.keys())
    if auto_all:
        auto_codes = set(supported_auto)
    else:
        # Keep only known codes for auto-tap. Unknown codes can still be passed-through.
        auto_codes = {c for c in auto_codes if c in supported_auto}

    print("Virtual controller created (Xbox 360).", flush=True)
    if auto_codes:
        print(f"Auto-tap codes: {', '.join(sorted(auto_codes))}", flush=True)
    else:
        print("Auto-tap codes: (none)", flush=True)
    print(f"Tap duration: {interval_s:.3f}s", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    stop = threading.Event()
    q: Queue[GamepadEvent] = Queue()
    t = threading.Thread(target=_event_reader, args=(stop, q), daemon=True)
    t.start()

    # Auto-tap state
    tap_release_at: Dict[str, float] = {}
    tap_is_down: Dict[str, bool] = {c: False for c in auto_codes}

    # Analog state (for sampling mode)
    lx = 0
    ly = 0
    rx = 0
    ry = 0
    lt = 0
    rt = 0
    hat_x = 0  # -1/0/1
    hat_y = 0  # -1/0/1 (up is -1)
    next_analog_emit = 0.0

    def set_dpad_from_hat() -> None:
        # Clear all
        for b in (
            vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        ):
            pad.release_button(b)
        if hat_y == -1:
            pad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        elif hat_y == 1:
            pad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        if hat_x == -1:
            pad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        elif hat_x == 1:
            pad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)

    try:
        while True:
            now = time.monotonic()

            # Drain any queued events quickly.
            did_update = False
            while True:
                try:
                    e = q.get_nowait()
                except Empty:
                    break

                if print_events:
                    print(f"{e.ev_type} {e.code} {e.state}")

                if e.ev_type == "Key":
                    # Auto-tap
                    if e.code in auto_codes:
                        if e.state == 1:
                            btn = BTN_MAP[e.code]
                            if not tap_is_down.get(e.code, False):
                                pad.press_button(btn)
                                did_update = True
                                tap_is_down[e.code] = True
                            tap_release_at[e.code] = now + interval_s
                        else:
                            # swallow physical release
                            pass
                        continue

                    # Passthrough other buttons if mapped
                    btn = BTN_MAP.get(e.code)
                    if btn is not None:
                        if e.state == 1:
                            pad.press_button(btn)
                        else:
                            pad.release_button(btn)
                        did_update = True
                    continue

                if e.ev_type == "Absolute":
                    code = e.code
                    if code == "ABS_HAT0X":
                        hat_x = int(e.state)
                        set_dpad_from_hat()
                        did_update = True
                        continue
                    if code == "ABS_HAT0Y":
                        hat_y = int(e.state)
                        set_dpad_from_hat()
                        did_update = True
                        continue

                    if code == "ABS_X":
                        lx = _normalize_signed_axis(e.state)
                        if not analog_sample:
                            pad.left_joystick(x_value=lx, y_value=ly)
                            did_update = True
                        continue
                    if code == "ABS_Y":
                        # Invert so up is positive (XInput convention)
                        ly = -_normalize_signed_axis(e.state)
                        if not analog_sample:
                            pad.left_joystick(x_value=lx, y_value=ly)
                            did_update = True
                        continue
                    if code == "ABS_RX":
                        rx = _normalize_signed_axis(e.state)
                        if not analog_sample:
                            pad.right_joystick(x_value=rx, y_value=ry)
                            did_update = True
                        continue
                    if code == "ABS_RY":
                        ry = -_normalize_signed_axis(e.state)
                        if not analog_sample:
                            pad.right_joystick(x_value=rx, y_value=ry)
                            did_update = True
                        continue
                    if code == "ABS_Z":
                        lt = _normalize_trigger(e.state)
                        if not analog_sample:
                            pad.left_trigger(value=lt)
                            did_update = True
                        continue
                    if code == "ABS_RZ":
                        rt = _normalize_trigger(e.state)
                        if not analog_sample:
                            pad.right_trigger(value=rt)
                            did_update = True
                        continue

            # Release auto-taps when their timers expire
            if tap_release_at:
                for code, release_at in list(tap_release_at.items()):
                    if now + 1e-9 < release_at:
                        continue
                    btn = BTN_MAP.get(code)
                    if btn is not None:
                        pad.release_button(btn)
                        did_update = True
                    tap_release_at.pop(code, None)
                    tap_is_down[code] = False

            # Sample analog at fixed interval (optional)
            if analog_sample and now + 1e-9 >= next_analog_emit:
                pad.left_joystick(x_value=lx, y_value=ly)
                pad.right_joystick(x_value=rx, y_value=ry)
                pad.left_trigger(value=lt)
                pad.right_trigger(value=rt)
                did_update = True
                next_analog_emit = max(next_analog_emit + interval_s, now + interval_s)

            if did_update:
                pad.update()

            # Small sleep to keep CPU reasonable while still timing releases accurately.
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Windows auto-tap virtual Xbox controller (ViGEmBus required).")
    p.add_argument("--list", action="store_true", help="List detected gamepads and exit.")
    p.add_argument(
        "--index",
        type=int,
        default=0,
        help="(Reserved) Controller index from --list. Inputs library uses a global hook; kept for future filtering.",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="Tap duration (seconds). Default: 0.1",
    )
    p.add_argument("--auto", nargs="*", default=[], help="Button codes to auto-tap (e.g. BTN_SOUTH BTN_EAST).")
    p.add_argument("--auto-all", action="store_true", help="Auto-tap all common mapped buttons.")
    p.add_argument(
        "--analog-sample",
        action="store_true",
        help="Sample sticks/triggers at --interval instead of forwarding immediately.",
    )
    p.add_argument("--print-events", action="store_true", help="Print incoming events for debugging.")
    args = p.parse_args(argv)

    if args.list:
        _list_gamepads()
        return 0

    # args.index currently not used because inputs.get_gamepad() does not expose per-device filtering.
    _ = args.index

    run(
        interval_s=float(args.interval),
        auto_codes=_parse_auto_codes(args.auto),
        auto_all=bool(args.auto_all),
        analog_sample=bool(args.analog_sample),
        print_events=bool(args.print_events),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

