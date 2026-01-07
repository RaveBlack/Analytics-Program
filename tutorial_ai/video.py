from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
from PIL import Image

from .render import RenderStyle, iter_scene_frames
from .srt import Subtitle, to_srt
from .steps import TutorialPlan


def write_tutorial_video(
    *,
    blueprint_path: str | Path,
    plan: TutorialPlan,
    out_mp4: str | Path,
    style: RenderStyle | None = None,
) -> tuple[Path, Path]:
    style = style or RenderStyle()
    blueprint_path = Path(blueprint_path)
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_srt = out_mp4.with_suffix(".srt")

    blueprint = Image.open(blueprint_path)

    subs: list[Subtitle] = []
    t = 0.0
    for s in plan.scenes:
        if (s.narration or "").strip():
            subs.append(Subtitle(start_s=t, end_s=t + s.duration_s, text=s.narration.strip()))
        t += s.duration_s

    # imageio uses ffmpeg under the hood (via imageio-ffmpeg) for MP4 output.
    # macro_block_size=1 avoids resizing to multiples of 16.
    with imageio.get_writer(
        out_mp4,
        fps=plan.fps,
        codec="libx264",
        quality=8,
        macro_block_size=1,
    ) as writer:
        for scene in plan.scenes:
            for frame in iter_scene_frames(blueprint, plan, scene, style=style):
                writer.append_data(frame)

    out_srt.write_text(to_srt(subs), encoding="utf-8")
    return out_mp4, out_srt

