from __future__ import annotations

import io
from typing import Optional


# 1×1 transparent PNG (hardcoded, valid)
_TRANSPARENT_1X1_PNG = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000A49444154789C63000100000500010D0A2DB40000000049454E44AE426082"
)


def transparent_pixel_png() -> bytes:
    return _TRANSPARENT_1X1_PNG


def glyph_png(*, text: str = "•", size: int = 18) -> bytes:
    """
    Symbol-based fallback: renders a tiny glyph PNG (e.g. '•', 'i', 'A').

    Uses Pillow if available. If not, falls back to the 1×1 pixel.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:
        return transparent_pixel_png()

    t = (text or "•")[:2]
    w = max(12, int(size))
    h = max(12, int(size))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Simple centered draw; keep it readable on dark/light backgrounds.
    bbox = draw.textbbox((0, 0), t, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) // 2
    y = (h - th) // 2
    draw.text((x, y), t, fill=(255, 255, 255, 220), font=font)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
