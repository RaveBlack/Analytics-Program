from __future__ import annotations

import argparse
from pathlib import Path

from .llm import generate_steps_yaml
from .steps import load_steps
from .video import write_tutorial_video


def _cmd_render(args: argparse.Namespace) -> int:
    plan = load_steps(args.steps)
    out_mp4, out_srt = write_tutorial_video(
        blueprint_path=args.blueprint,
        plan=plan,
        out_mp4=args.out,
    )
    print(f"Wrote video: {out_mp4}")
    print(f"Wrote subtitles: {out_srt}")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    yaml_text = generate_steps_yaml(args.prompt)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml_text, encoding="utf-8")
    print(f"Wrote steps: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tutorial_ai", description="Generate build tutorial videos from blueprints + steps.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render an MP4 tutorial from a blueprint image and a steps YAML/JSON.")
    r.add_argument("--blueprint", required=True, help="Path to blueprint/schematic image (png/jpg/webp).")
    r.add_argument("--steps", required=True, help="Path to steps YAML/JSON.")
    r.add_argument("--out", required=True, help="Output MP4 path.")
    r.set_defaults(func=_cmd_render)

    pl = sub.add_parser("plan", help="Draft a steps YAML using an OpenAI-compatible API.")
    pl.add_argument("--prompt", required=True, help="Natural language description of what to build and how to teach it.")
    pl.add_argument("--out", required=True, help="Output steps YAML path.")
    pl.set_defaults(func=_cmd_plan)

    args = p.parse_args(argv)
    return int(args.func(args))

