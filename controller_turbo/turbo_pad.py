#!/usr/bin/env python3
"""
Xbox/controller auto-tap (0.1s) + 10Hz analog sampling (Linux).

Reads a physical controller via evdev and emits events through a virtual uinput device.

Requires root (or appropriate udev permissions) for /dev/input/event* and /dev/uinput.
"""

from __future__ import annotations

import argparse
import select
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import evdev
from evdev import ecodes


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    name: str


def _iter_devices() -> List[DeviceInfo]:
    out: List[DeviceInfo] = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            out.append(DeviceInfo(path=path, name=dev.name))
        except OSError:
            # Device may disappear between enumeration and open.
            continue
    return out


def _pick_device_by_name(substring: str) -> evdev.InputDevice:
    substring_l = substring.lower()
    matches = [d for d in _iter_devices() if substring_l in d.name.lower()]
    if not matches:
        raise SystemExit(f"No input devices matched --name {substring!r}")
    # Prefer "event" nodes that are likely gamepads (have EV_ABS + EV_KEY).
    def score(d: DeviceInfo) -> Tuple[int, int]:
        try:
            dev = evdev.InputDevice(d.path)
            caps = dev.capabilities()
            return (1 if ecodes.EV_ABS in caps and ecodes.EV_KEY in caps else 0, 0)
        except OSError:
            return (0, 1)

    matches.sort(key=score, reverse=True)
    return evdev.InputDevice(matches[0].path)


def _parse_key_codes(tokens: Sequence[str]) -> Set[int]:
    """
    Parse key tokens like:
      - "BTN_SOUTH"
      - "KEY_SPACE"
      - "304" (numeric code)
    """
    out: Set[int] = set()
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if tok.isdigit():
            out.add(int(tok))
            continue
        if not tok.startswith(("BTN_", "KEY_")):
            raise SystemExit(
                f"Unknown key token {tok!r}. Use BTN_* / KEY_* (e.g. BTN_SOUTH) or a numeric code."
            )
        code = getattr(ecodes, tok, None)
        if code is None:
            raise SystemExit(f"Unknown key name {tok!r} (not found in evdev.ecodes).")
        out.add(int(code))
    return out


def _format_code(code: int) -> str:
    return ecodes.KEY[code] if code in ecodes.KEY else str(code)


def _list_devices() -> None:
    devices = _iter_devices()
    if not devices:
        print("No /dev/input devices found.")
        return
    for d in devices:
        print(f"{d.path}\t{d.name}")


def _ensure_interval(seconds: float) -> float:
    if seconds <= 0:
        raise SystemExit("--interval must be > 0")
    if seconds < 0.01:
        raise SystemExit("--interval too small; minimum is 0.01s")
    return seconds


def _is_press(value: int) -> bool:
    # evdev: 1 = press, 2 = autorepeat, 0 = release
    return value in (1, 2)


def _copy_absinfo(
    caps_abs: Iterable[Tuple[int, evdev.AbsInfo]] | Iterable[int],
) -> List[Tuple[int, evdev.AbsInfo]]:
    """
    Normalize ABS capabilities to the format UInput expects: [(code, AbsInfo), ...]
    """
    out: List[Tuple[int, evdev.AbsInfo]] = []
    for item in caps_abs:
        if isinstance(item, tuple) and len(item) == 2:
            code, info = item
            out.append((int(code), info))
        else:
            # If AbsInfo isn't available, create a generic range.
            code = int(item)  # type: ignore[arg-type]
            out.append((code, evdev.AbsInfo(value=0, min=-32768, max=32767, fuzz=0, flat=0, resolution=0)))
    return out


def _build_uinput_from_device(dev: evdev.InputDevice) -> evdev.UInput:
    caps = dev.capabilities(absinfo=True)
    # Some devices return ABS caps in mixed formats; normalize to (code, AbsInfo).
    if ecodes.EV_ABS in caps:
        caps[ecodes.EV_ABS] = _copy_absinfo(caps[ecodes.EV_ABS])  # type: ignore[assignment]
    ui = evdev.UInput(
        events=caps,
        name=f"{dev.name} (turbo)",
        bustype=ecodes.BUS_USB,
        vendor=0x045E,  # Microsoft
        product=0x0001,
        version=0x0001,
    )
    return ui


def _key_caps(dev: evdev.InputDevice) -> Set[int]:
    caps = dev.capabilities()
    keys = caps.get(ecodes.EV_KEY, [])
    return set(int(k) for k in keys)


def _abs_caps(dev: evdev.InputDevice) -> Set[int]:
    caps = dev.capabilities()
    axes = caps.get(ecodes.EV_ABS, [])
    return set(int(a) for a in axes)


def run(
    dev: evdev.InputDevice,
    *,
    interval_s: float,
    turbo_keys: Set[int],
    turbo_all: bool,
    grab: bool,
    analog_10hz: bool,
    print_events: bool,
) -> None:
    interval_s = _ensure_interval(interval_s)

    if grab:
        try:
            dev.grab()
        except OSError as e:
            raise SystemExit(f"Failed to grab {dev.path}: {e}")

    ui = _build_uinput_from_device(dev)

    all_keys = _key_caps(dev)
    all_axes = _abs_caps(dev)

    if turbo_all:
        turbo_keys = set(all_keys)

    # "Auto-tap" semantics:
    # - On physical press: emit key down immediately, schedule key up after interval_s
    # - While held: NO repeated pulses (user requested "1 press" not "10 presses/sec")
    tap_release_at: Dict[int, float] = {}
    tap_is_down: Dict[int, bool] = {k: False for k in turbo_keys}

    axis_state: Dict[int, int] = {}
    next_axes_emit = 0.0

    print(f"Input:  {dev.path}  ({dev.name})", file=sys.stderr)
    print(f"Output: {ui.devnode}  ({ui.name})", file=sys.stderr)
    if turbo_keys:
        keys_pretty = ", ".join(sorted((_format_code(k) for k in turbo_keys)))
    else:
        keys_pretty = "(none)"
    print(f"Auto-tap keys: {keys_pretty}", file=sys.stderr)
    print(f"Interval: {interval_s:.3f}s", file=sys.stderr)
    if grab:
        print("Mode: grab enabled (real device hidden from apps)", file=sys.stderr)
    else:
        print("Mode: grab disabled (apps may see both devices)", file=sys.stderr)

    # Preload current ABS values if supported (best effort).
    try:
        for code in all_axes:
            try:
                axis_state[code] = dev.absinfo(code).value
            except Exception:
                pass
    except Exception:
        pass

    try:
        while True:
            # Use select with a timeout so we can do 10Hz ticks without threads.
            timeout = interval_s
            r, _, _ = select.select([dev.fd], [], [], timeout)
            now = time.monotonic()

            if r:
                for event in dev.read():
                    if print_events:
                        print(repr(event), file=sys.stderr)

                    if event.type == ecodes.EV_KEY:
                        code = int(event.code)
                        if code in turbo_keys:
                            if _is_press(int(event.value)):
                                # Begin a synthetic tap.
                                if not tap_is_down.get(code, False):
                                    ui.write(ecodes.EV_KEY, code, 1)
                                    ui.syn()
                                    tap_is_down[code] = True
                                tap_release_at[code] = now + interval_s
                            else:
                                # Swallow physical release; we control release timing.
                                pass
                            continue

                        # passthrough for non-turbo keys
                        ui.write(event.type, event.code, event.value)
                        ui.syn()
                        continue

                    if event.type == ecodes.EV_ABS:
                        if analog_10hz:
                            axis_state[int(event.code)] = int(event.value)
                        else:
                            ui.write(event.type, event.code, event.value)
                            ui.syn()
                        continue

                    # passthrough everything else (EV_SYN not needed; we do ui.syn())
                    ui.write(event.type, event.code, event.value)
                    ui.syn()

            # Tick: release pending auto-taps + (optional) 10Hz analog forwarding.
            did_anything = False

            # Auto-tap releases
            if tap_release_at:
                # Copy items so we can delete while iterating.
                for code, release_at in list(tap_release_at.items()):
                    if now + 1e-9 < release_at:
                        continue
                    ui.write(ecodes.EV_KEY, code, 0)
                    did_anything = True
                    tap_release_at.pop(code, None)
                    tap_is_down[code] = False

            # Analog sampling
            if analog_10hz and now + 1e-9 >= next_axes_emit:
                for code, value in axis_state.items():
                    ui.write(ecodes.EV_ABS, code, value)
                    did_anything = True
                next_axes_emit = max(next_axes_emit + interval_s, now + interval_s)

            if did_anything:
                ui.syn()

    except KeyboardInterrupt:
        print("\nStopping.", file=sys.stderr)
    finally:
        try:
            ui.close()
        except Exception:
            pass
        try:
            if grab:
                dev.ungrab()
        except Exception:
            pass
        try:
            dev.close()
        except Exception:
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Auto-tap (single fast press) virtual controller for Linux (evdev/uinput)."
    )
    p.add_argument("--list", action="store_true", help="List available /dev/input/event* devices and exit.")
    p.add_argument("--device", help="Input device path, e.g. /dev/input/event17")
    p.add_argument("--name", help="Pick the first input device whose name contains this substring (case-insensitive).")
    p.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="Tap duration / analog sampling interval in seconds (default: 0.1).",
    )
    p.add_argument(
        "--turbo",
        nargs="*",
        default=[],
        help="Key names to auto-tap (e.g. BTN_SOUTH BTN_EAST). You can also pass numeric codes.",
    )
    p.add_argument(
        "--turbo-all",
        action="store_true",
        help="Auto-tap all EV_KEY buttons reported by the device.",
    )
    p.add_argument(
        "--no-grab",
        action="store_true",
        help="Do not grab the real device (apps may see both real + virtual input).",
    )
    p.add_argument(
        "--no-analog-10hz",
        action="store_true",
        help="Forward analog events immediately instead of sampling at --interval.",
    )
    p.add_argument("--print-events", action="store_true", help="Print incoming events to stderr for debugging.")
    args = p.parse_args(argv)

    if args.list:
        _list_devices()
        return 0

    if not args.device and not args.name:
        p.error("Provide --device /dev/input/eventX or --name 'Xbox' (or use --list).")

    if args.device and args.name:
        p.error("Use only one of --device or --name.")

    if args.device:
        dev = evdev.InputDevice(args.device)
    else:
        dev = _pick_device_by_name(args.name)

    turbo_keys = _parse_key_codes(args.turbo)

    run(
        dev,
        interval_s=float(args.interval),
        turbo_keys=turbo_keys,
        turbo_all=bool(args.turbo_all),
        grab=not bool(args.no_grab),
        analog_10hz=not bool(args.no_analog_10hz),
        print_events=bool(args.print_events),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

