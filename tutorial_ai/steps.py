from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass(frozen=True)
class BBox:
    """Normalized bounding box (0..1) in blueprint image coordinates."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Scene:
    title: str
    bullets: list[str]
    narration: str
    duration_s: float
    highlight: BBox | None = None


@dataclass(frozen=True)
class TutorialPlan:
    title: str
    fps: int
    width: int
    height: int
    scenes: list[Scene]


def _as_float(v: Any, *, field: str) -> float:
    try:
        return float(v)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Invalid float for '{field}': {v!r}") from e


def _as_int(v: Any, *, field: str) -> int:
    try:
        return int(v)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Invalid int for '{field}': {v!r}") from e


def _as_str(v: Any, *, field: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"Invalid string for '{field}': {v!r}")
    return v


def _as_list_of_str(v: Any, *, field: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        raise ValueError(f"Invalid list for '{field}': {v!r}")
    out: list[str] = []
    for i, item in enumerate(v):
        if not isinstance(item, str):
            raise ValueError(f"Invalid string at {field}[{i}]: {item!r}")
        s = item.strip()
        if s:
            out.append(s)
    return out


def _parse_bbox(obj: Any) -> BBox | None:
    if obj is None:
        return None
    if not isinstance(obj, dict):
        raise ValueError(f"highlight must be an object, got: {obj!r}")
    typ = obj.get("type", "bbox")
    if typ != "bbox":
        raise ValueError(f"Unsupported highlight type: {typ!r} (only 'bbox')")
    x = _as_float(obj.get("x"), field="highlight.x")
    y = _as_float(obj.get("y"), field="highlight.y")
    w = _as_float(obj.get("w"), field="highlight.w")
    h = _as_float(obj.get("h"), field="highlight.h")
    for name, val in [("x", x), ("y", y), ("w", w), ("h", h)]:
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"highlight.{name} must be in [0..1], got {val}")
    if w <= 0 or h <= 0:
        raise ValueError("highlight.w and highlight.h must be > 0")
    if x + w > 1.0 or y + h > 1.0:
        raise ValueError("highlight bbox must fit within [0..1]")
    return BBox(x=x, y=y, w=w, h=h)


def load_steps(path: str | Path) -> TutorialPlan:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    text = p.read_text(encoding="utf-8")
    data: Any
    if p.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    elif p.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        raise ValueError("Steps file must be .yaml/.yml or .json")

    if not isinstance(data, dict):
        raise ValueError("Steps root must be an object")

    title = _as_str(data.get("title", "Build Tutorial"), field="title")
    fps = _as_int(data.get("fps", 30), field="fps")
    width = _as_int(data.get("width", 1280), field="width")
    height = _as_int(data.get("height", 720), field="height")

    scenes_raw = data.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise ValueError("steps.scenes must be a non-empty list")

    scenes: list[Scene] = []
    for idx, s in enumerate(scenes_raw):
        if not isinstance(s, dict):
            raise ValueError(f"scene[{idx}] must be an object")
        stitle = _as_str(s.get("title", f"Step {idx+1}"), field=f"scenes[{idx}].title")
        bullets = _as_list_of_str(s.get("bullets", []), field=f"scenes[{idx}].bullets")
        narration = str(s.get("narration", "") or "").strip()
        duration_s = _as_float(s.get("duration_s", 5), field=f"scenes[{idx}].duration_s")
        if duration_s <= 0:
            raise ValueError(f"scenes[{idx}].duration_s must be > 0")
        highlight = _parse_bbox(s.get("highlight"))
        scenes.append(
            Scene(
                title=stitle,
                bullets=bullets,
                narration=narration,
                duration_s=duration_s,
                highlight=highlight,
            )
        )

    return TutorialPlan(title=title, fps=fps, width=width, height=height, scenes=scenes)


def dump_steps_yaml(plan: dict[str, Any]) -> str:
    """Serialize a plan-like dict to YAML."""
    return yaml.safe_dump(plan, sort_keys=False, allow_unicode=True)

