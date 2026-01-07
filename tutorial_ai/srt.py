from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subtitle:
    start_s: float
    end_s: float
    text: str


def _ts(t: float) -> str:
    if t < 0:
        t = 0
    ms = int(round(t * 1000))
    h = ms // 3_600_000
    ms -= h * 3_600_000
    m = ms // 60_000
    ms -= m * 60_000
    s = ms // 1000
    ms -= s * 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(subs: list[Subtitle]) -> str:
    lines: list[str] = []
    for i, sub in enumerate(subs, start=1):
        text = (sub.text or "").strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{_ts(sub.start_s)} --> {_ts(sub.end_s)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

