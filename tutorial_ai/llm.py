from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    timeout_s: int = 60


SYSTEM_PROMPT = """You generate step-by-step build tutorial plans.

Return ONLY valid YAML matching this schema:

title: string
fps: int (20-60)
width: int (>=640)
height: int (>=360)
scenes:
  - title: string
    duration_s: number (3-20)
    bullets: [string, ...]   # short, action-oriented
    narration: string        # 1-3 sentences
    highlight:              # optional
      type: bbox
      x: number (0..1)
      y: number (0..1)
      w: number (0..1)
      h: number (0..1)

Guidelines:
- Use clear phases: prep, layout, build, inspect/test, finish.
- Include safety notes where appropriate (PPE, power isolation, load limits).
- Avoid claiming code-compliance certainty; recommend verification.
"""


def _env_cfg() -> OpenAIConfig:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip()
    timeout_s = int(os.environ.get("OPENAI_TIMEOUT_S", "60"))
    return OpenAIConfig(api_key=api_key, base_url=base_url, model=model, timeout_s=timeout_s)


def generate_steps_yaml(prompt: str, *, cfg: OpenAIConfig | None = None) -> str:
    cfg = cfg or _env_cfg()

    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=cfg.timeout_s)
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM request failed ({resp.status_code}): {resp.text[:4000]}")
    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Unexpected LLM response shape: {data!r}") from e
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM returned empty content")
    return content.strip() + ("\n" if not content.endswith("\n") else "")

