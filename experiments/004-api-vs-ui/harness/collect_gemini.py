"""Gemini API collector for experiment 004's Gemini API arms (sketch, Arms).

Arms (both ``gemini-3.5-flash-lite`` via REST ``generateContent``, tools
``[{"google_search": {}}]``, default thinking, one user turn = the prompt text
byte for byte; the grounding tool has no location setting):

- ``gm_api_plain``: no system instruction.
- ``gm_api_leak``: ``systemInstruction`` = ``adapted_gemini.txt``.

The full raw response (``groundingMetadata``, ``modelVersion``, ``usageMetadata``)
goes to ``data/raw/<prefix>responses/r<round>/<arm>/<item>.json`` with the
normalized answer; one ledger record per attempt to
``<prefix>ledger_api_gemini.jsonl``, the same shape as the OpenAI ledger. Reruns
skip collected answers; failures are retried.

Usage (repo root):
    uv run python experiments/004-api-vs-ui/harness/collect_gemini.py run --round 1 \
        --arms gm_api_plain --items b2b_01 --prefix smoke_
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answers  # noqa: E402
import exp004  # noqa: E402
import leaks  # noqa: E402

URL = f"https://generativelanguage.googleapis.com/v1beta/models/{exp004.GEMINI_MODEL}:generateContent"
TOOLS = [{"google_search": {}}]


def send(body: dict) -> exp004.HttpResult:
    return exp004.post_json(URL, body, {"x-goog-api-key": exp004.env_value("GOOGLE_GENERATIVE_AI_API_KEY")})


def build(arm: str, text: str) -> tuple[dict, dict]:
    body = {"contents": [{"role": "user", "parts": [{"text": text}]}], "tools": TOOLS}
    meta = {"effort_requested": None, "instructions_sha256": None, "model": exp004.GEMINI_MODEL}
    if exp004.ARMS[arm].leak:
        instructions = leaks.load_adapted("gemini")
        body["systemInstruction"] = {"parts": [{"text": instructions}]}
        meta["instructions_sha256"] = exp004.sha256_text(instructions)
    return body, meta


def cost(raw: dict, norm: dict) -> dict:
    # Grounding bills per search request; each webSearchQueries entry is counted.
    return exp004.gemini_cost(raw.get("usageMetadata"), norm.get("n_searches") or 0)


def run(arms: list[str], items: list[str], rnd: int, prefix: str = "", log=print) -> dict:
    bad = [a for a in arms if a not in exp004.GEMINI_ARMS]
    if bad:
        raise SystemExit(f"not Gemini API arms: {bad}")
    return exp004.run_api_jobs(instrument="gemini", arms=arms, items=items, rnd=rnd, prefix=prefix,
                               build=build, send=send, normalize=answers.from_gemini, cost=cost,
                               check_model=exp004.GEMINI_MODEL, log=log)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--round", type=int, required=True)
    r.add_argument("--arms", default=",".join(exp004.GEMINI_ARMS))
    r.add_argument("--items", default=",".join(exp004.PILOT_ITEMS))
    r.add_argument("--prefix", default="", help='"smoke_" for the smoke ledger')
    a = ap.parse_args()
    run(a.arms.split(","), a.items.split(","), a.round, a.prefix)


if __name__ == "__main__":
    main()
