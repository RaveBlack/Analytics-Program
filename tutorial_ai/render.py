from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .steps import BBox, Scene, TutorialPlan


@dataclass(frozen=True)
class RenderStyle:
    header_h: int = 90
    footer_h: int = 170
    pad: int = 28
    title_size: int = 44
    body_size: int = 30
    accent_rgb: tuple[int, int, int] = (65, 160, 255)
    dim_alpha: int = 150
    panel_alpha: int = 170


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Prefer common fonts if available; fall back to PIL's default.
    for name in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        p = Path(name)
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        candidate = (" ".join(cur + [w])).strip()
        if draw.textlength(candidate, font=font) <= max_w:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines


def _fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(math.ceil(iw * scale)), int(math.ceil(ih * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _bbox_px(b: BBox, w: int, h: int) -> tuple[int, int, int, int]:
    x1 = int(round(b.x * w))
    y1 = int(round(b.y * h))
    x2 = int(round((b.x + b.w) * w))
    y2 = int(round((b.y + b.h) * h))
    return x1, y1, x2, y2


def render_scene_frame(
    blueprint: Image.Image,
    plan: TutorialPlan,
    scene: Scene,
    *,
    style: RenderStyle,
) -> Image.Image:
    base = _fit_cover(blueprint, plan.width, plan.height).convert("RGBA")
    draw = ImageDraw.Draw(base)

    # Optional highlight overlay (dim everything except the bbox)
    if scene.highlight is not None:
        x1, y1, x2, y2 = _bbox_px(scene.highlight, plan.width, plan.height)
        dim = Image.new("RGBA", (plan.width, plan.height), (0, 0, 0, style.dim_alpha))
        # Cut out the highlight region to keep it bright
        cut = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, 0))
        dim.paste(cut, (x1, y1))
        base = Image.alpha_composite(base, dim)
        draw = ImageDraw.Draw(base)
        # Accent rectangle
        for t in range(4):
            draw.rectangle((x1 - t, y1 - t, x2 + t, y2 + t), outline=style.accent_rgb, width=2)

    # Header + footer panels
    header = Image.new("RGBA", (plan.width, style.header_h), (0, 0, 0, style.panel_alpha))
    footer = Image.new("RGBA", (plan.width, style.footer_h), (0, 0, 0, style.panel_alpha))
    base.paste(header, (0, 0), header)
    base.paste(footer, (0, plan.height - style.footer_h), footer)
    draw = ImageDraw.Draw(base)

    title_font = _load_font(style.title_size)
    body_font = _load_font(style.body_size)

    # Header title
    draw.text(
        (style.pad, int((style.header_h - style.title_size) * 0.35)),
        scene.title,
        fill=(255, 255, 255, 255),
        font=title_font,
    )

    # Footer bullets + narration
    y = plan.height - style.footer_h + style.pad
    max_w = plan.width - style.pad * 2

    bullet_lines: list[str] = []
    for b in scene.bullets[:6]:
        wrapped = _wrap(draw, b, body_font, max_w - 32)
        for i, line in enumerate(wrapped[:2]):
            bullet_lines.append(("• " if i == 0 else "  ") + line)

    if bullet_lines:
        for line in bullet_lines[:8]:
            draw.text((style.pad, y), line, fill=(255, 255, 255, 255), font=body_font)
            y += style.body_size + 6
        y += 8

    narration = (scene.narration or "").strip()
    if narration:
        for line in _wrap(draw, narration, body_font, max_w)[:3]:
            draw.text((style.pad, y), line, fill=(220, 235, 255, 255), font=body_font)
            y += style.body_size + 6

    return base.convert("RGB")


def iter_scene_frames(
    blueprint: Image.Image,
    plan: TutorialPlan,
    scene: Scene,
    *,
    style: RenderStyle,
) -> Iterable[np.ndarray]:
    frame = render_scene_frame(blueprint, plan, scene, style=style)
    n = max(1, int(round(scene.duration_s * plan.fps)))
    arr = np.asarray(frame, dtype=np.uint8)
    for _ in range(n):
        yield arr

