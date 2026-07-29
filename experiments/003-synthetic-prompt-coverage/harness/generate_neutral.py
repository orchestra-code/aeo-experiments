#!/usr/bin/env python3
"""Experiment 003 harness — the NEU arm: a neutral, category-level synthetic
prompt panel from a plain LLM call, no brand anchor, no vendor framework.

This is the *best-case* synthetic panel: it is told the survey scenario (the
one-line intent SparkToro gave respondents) and nothing else — no attribute
checklist, no examples — so H4 coverage measures what a generator reaches for
unaided. It deliberately uses the SAME model as the Spyglasses generator
(claude-haiku-4-5) so the SPY-vs-NEU contrast isolates the prompting strategy,
not the model.

Usage (from the aeo-experiments repo root):

    uv run python experiments/003-synthetic-prompt-coverage/harness/generate_neutral.py \
        --env-file /Users/jcw/projects/spyglasses/.env.local [--n 40] [--out <dir>]

Output: <out>/neu.json (prompt text stays in data/raw, gitignored).
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "data" / "raw" / "generator"

MODEL = "claude-haiku-4-5"
API_URL = "https://api.anthropic.com/v1/messages"

# Frozen with the spec. The system prompt encodes only "write like real,
# varied users"; the brief encodes only the survey scenario.
SYSTEM_PROMPT = (
    "You write realistic prompts that real people type into AI assistants "
    "(like ChatGPT) when they want help with a purchase decision. Vary "
    "length, tone, specificity, and style the way real users do: some terse "
    "keyword-like queries, some long personal messages with context and "
    "constraints, some asking for specific output formats. Never mention any "
    "brand name. Never include a year. Each prompt must stand alone."
)

BRIEF = (
    "Generate {n} distinct prompts a person might send to an AI assistant in "
    "this scenario: they are shopping for headphones as a gift for a family "
    "member who travels frequently. Write them the way {n} different real "
    "people would each phrase it."
)

TOOL = {
    "name": "emit_prompts",
    "description": "Return the generated prompts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "prompts": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["prompts"],
    },
}


def load_key(env_file: str | None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if env_file:
        for line in Path(env_file).read_text().splitlines():
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No ANTHROPIC_API_KEY in the environment or --env-file.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--env-file", default=None)
    a = ap.parse_args()

    body = {
        "model": MODEL,
        "max_tokens": 8000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": BRIEF.format(n=a.n)}],
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": "emit_prompts"},
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": load_key(a.env_file),
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())

    prompts = next(
        block["input"]["prompts"]
        for block in payload["content"]
        if block["type"] == "tool_use"
    )
    prompts = [p.strip() for p in prompts if p and p.strip()]
    print(f"[003:neu] generated {len(prompts)} prompts (asked for {a.n})")

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "neu.json"
    out_path.write_text(
        json.dumps(
            {
                "arm": "neu",
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "generator_model": payload.get("model", MODEL),
                "system_prompt": SYSTEM_PROMPT,
                "brief": BRIEF.format(n=a.n),
                "n_requested": a.n,
                "prompts": prompts,
            },
            indent=1,
        )
    )
    print(f"[003:neu] wrote {out_path}")


if __name__ == "__main__":
    main()
