# Build Tutorial AI (v1)

Generate **step-by-step video tutorials** (MP4) from a blueprint/schematic image and a structured step plan (YAML/JSON). Optionally, draft the step plan from a natural-language prompt using an OpenAI-compatible API.

## What v1 does

- Takes a **blueprint/schematic image** (PNG/JPG/WebP)
- Takes a **steps file** (YAML/JSON) describing scenes (title, bullets, narration, optional highlight boxes)
- Renders:
  - an **MP4** tutorial video (slides w/ blueprint background + highlighted regions + captions)
  - an **SRT** subtitle file from the narration text

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r build_tutorial_ai/requirements.txt
```

## Quick demo (generates a sample blueprint + video)

```bash
python build_tutorial_ai/examples/make_sample_blueprint.py \
  --out build_tutorial_ai/examples/sample_blueprint.png

python -m tutorial_ai render \
  --blueprint build_tutorial_ai/examples/sample_blueprint.png \
  --steps build_tutorial_ai/examples/sample_steps.yaml \
  --out build_tutorial_ai/out/tutorial.mp4
```

Outputs:

- `build_tutorial_ai/out/tutorial.mp4`
- `build_tutorial_ai/out/tutorial.srt`

## Render your own tutorial video

```bash
python -m tutorial_ai render \
  --blueprint /path/to/your/blueprint.png \
  --steps /path/to/steps.yaml \
  --out /path/to/out.mp4
```

## (Optional) “AI” step planning via LLM

This repo does **not** bundle a proprietary model. If you set an API key, it can call an OpenAI-compatible endpoint to draft a steps YAML you can tweak.

```bash
export OPENAI_API_KEY="..."
# optional:
export OPENAI_MODEL="gpt-4.1-mini"
export OPENAI_BASE_URL="https://api.openai.com/v1"

python -m tutorial_ai plan \
  --prompt "Make a build tutorial for a basic 8x10 garden shed. Use clear phases and safety notes." \
  --out build_tutorial_ai/out/steps.yaml
```

Then render:

```bash
python -m tutorial_ai render \
  --blueprint /path/to/blueprint.png \
  --steps build_tutorial_ai/out/steps.yaml \
  --out build_tutorial_ai/out/shed_tutorial.mp4
```

## Steps file format (YAML)

See: `build_tutorial_ai/examples/sample_steps.yaml`

Highlights are optional; if provided, `bbox` uses **normalized** coordinates in \([0..1]\):

- `x`, `y`: top-left
- `w`, `h`: width/height

## Safety / reality check

- This tool generates **visual instructions** from inputs; it does **not** replace an engineer/architect/electrician, code compliance checks, or site-specific safety requirements.
- Always validate dimensions, materials, fasteners, tolerances, and local code requirements with a qualified professional.

## Roadmap (phases)

- **v1 (this)**: blueprint image + structured steps → MP4 + SRT (highlights + captions)
- **v2**: PDF import, multi-page drawings, per-scene zoom/pan, voice narration (TTS), more export formats
- **v3**: CAD/IFC parsing, automatic step segmentation, part lists/BOM extraction, “tool callouts”, interactive web player

