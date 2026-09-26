"""Anthropic client construction for the experiment 009 harness.

The key is read the way ``008/harness/collect_openai.py`` reads its key: the
``--env-file`` first, then ``.env.local`` in this repo, then the spyglasses
``.env.local``; the process environment is the last resort. The key is never
printed or logged.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = "/Users/jcw/projects/spyglasses/.env.local"


def load_key(env_file: str | None) -> str:
    candidates = [Path(env_file)] if env_file else []
    candidates += [REPO / ".env.local", REPO.parent / "spyglasses" / ".env.local"]
    for env in candidates:
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    raise SystemExit("No ANTHROPIC_API_KEY found in --env-file, .env.local or the environment")


def make_client(env_file: str | None = DEFAULT_ENV_FILE, *, max_retries: int = 4, timeout: float = 900.0):
    import anthropic

    return anthropic.Anthropic(api_key=load_key(env_file), max_retries=max_retries, timeout=timeout)
