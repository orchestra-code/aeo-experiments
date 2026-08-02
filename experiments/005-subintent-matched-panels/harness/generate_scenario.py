#!/usr/bin/env python3
"""Experiment 005 harness — the MAT and NEU2 scenario panels.

MAT is the study's headline object: a scenario-generated panel whose joint
sub-intent profile is STRATIFIED to the 003 human panel's — the Mad-Libs
clause design used as a measurement instrument. Strata are the joint
profiles of the six STRATIFY_FLAGS over 003's 143 human prompts (cells with
>=2 human prompts enter the frame, ~90% of panel mass); 55 slots are
allocated proportionally by largest remainder; per-slot length bands are
sampled from the human panel's band marginal. Every generated prompt is
validated against the FROZEN flag regexes (required flags present, the
other stratified flags absent), the 003 brand lexicon (zero brand aliases),
and a no-year rule; invalid candidates are regenerated (never hand-edited).

NEU2 replicates 003's neu arm exactly: same model, same system prompt, same
brief, fresh draw — the unstratified control.

Usage (from the aeo-experiments repo root):

    uv run python experiments/005-subintent-matched-panels/harness/generate_scenario.py \
        --arm mat --env-file /Users/jcw/projects/spyglasses/.env.local
    uv run python experiments/005-subintent-matched-panels/harness/generate_scenario.py \
        --arm neu2 --env-file /Users/jcw/projects/spyglasses/.env.local

Output: data/raw/generator/<arm>.json (prompt text stays in data/raw until
the release step; the data policy's synthetic-study-prompts exemption
applies at release time).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "pipeline"))

from brands import LEXICONS  # noqa: E402 — frozen 002/003 lexicon
from flags import FLAG_REQUIREMENTS, FLAGS, STRATIFY_FLAGS  # noqa: E402

OUT_DIR = EXP / "data" / "raw" / "generator"
HUM_SOURCE = EXP.parent / "003-synthetic-prompt-coverage" / "data" / "raw" / "prompts.csv"

MODEL = "claude-haiku-4-5"
API_URL = "https://api.anthropic.com/v1/messages"
SEED = 20260802
PANEL_SIZE = 55
MIN_CELL = 2          # human prompts required for a cell to enter the frame
MAX_ROUNDS = 6
MAX_CHARS = 1800      # DataForSEO keyword limit is ~2000; margin for safety

FLAG_NAMES = {
    "f_travel_context": "travel", "f_usage_music": "music",
    "f_budget_specific": "budget", "f_recipient_named": "recipient",
    "f_form_factor": "form", "f_wireless": "wireless",
}

#: Verbatim from 003's generate_neutral.py — neu2 must be an exact replication.
NEUTRAL_SYSTEM_PROMPT = (
    "You write realistic prompts that real people type into AI assistants "
    "(like ChatGPT) when they want help with a purchase decision. Vary "
    "length, tone, specificity, and style the way real users do: some terse "
    "keyword-like queries, some long personal messages with context and "
    "constraints, some asking for specific output formats. Never mention any "
    "brand name. Never include a year. Each prompt must stand alone."
)
NEUTRAL_BRIEF = (
    "Generate {n} distinct prompts a person might send to an AI assistant in "
    "this scenario: they are shopping for headphones as a gift for a family "
    "member who travels frequently. Write them the way {n} different real "
    "people would each phrase it."
)

MAT_SYSTEM_PROMPT = NEUTRAL_SYSTEM_PROMPT + (
    " When given requirements about which details to include or omit, follow "
    "them exactly — include a detail only when asked to."
)

BANDS = {
    "short": (1, 15, "terse and keyword-like, roughly 6 to 14 words"),
    "medium": (16, 45, "a sentence or three of context, roughly 18 to 40 words"),
    "long": (46, 10**6, "a long personal message with several constraints and "
                        "details, roughly 55 to 110 words"),
}

TOOL = {
    "name": "emit_prompts",
    "description": "Return the generated prompts.",
    "input_schema": {
        "type": "object",
        "properties": {"prompts": {"type": "array", "items": {"type": "string"}}},
        "required": ["prompts"],
    },
}

YEAR_RE = re.compile(r"\b20\d{2}\b")
ALIAS_RES = [
    re.compile(rf"\b{re.escape(alias)}\b")
    for aliases in LEXICONS["headphones"].values()
    for alias in aliases
]


def load_key(env_file: str | None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if env_file:
        for line in Path(env_file).read_text().splitlines():
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No ANTHROPIC_API_KEY in the environment or --env-file.")


def call_llm(key: str, system: str, brief: str) -> list[str]:
    body = {
        "model": MODEL, "max_tokens": 8000, "system": system,
        "messages": [{"role": "user", "content": brief}],
        "tools": [TOOL], "tool_choice": {"type": "tool", "name": "emit_prompts"},
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    prompts = next(b["input"]["prompts"] for b in payload["content"]
                   if b["type"] == "tool_use")
    return [p.strip() for p in prompts if p and p.strip()]


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def flags_of(text: str) -> set[str]:
    low = text.lower()
    return {f for f, pat in FLAGS.items() if re.search(pat, low)}


def clean(text: str) -> bool:
    low = text.lower()
    return (
        len(text) <= MAX_CHARS
        and not YEAR_RE.search(text)
        and not any(r.search(low) for r in ALIAS_RES)
    )


def band_of(n_words: int) -> str:
    for band, (lo, hi, _) in BANDS.items():
        if lo <= n_words <= hi:
            return band
    return "long"


# ------------------------------------------------------------------- mat


def stratification_frame() -> tuple[dict[str, int], pd.Series, dict[str, set[str]]]:
    """(cell -> slot count, band marginal, cell -> set of ON flags)."""
    hum = pd.read_csv(HUM_SOURCE)
    hum = hum[hum["arm"] == "hum"].copy()
    low = hum["text"].str.lower()
    for f in STRATIFY_FLAGS:
        hum[f] = low.str.contains(FLAGS[f])
    hum["cell"] = hum[STRATIFY_FLAGS].apply(
        lambda r: "+".join(FLAG_NAMES[f] for f in STRATIFY_FLAGS if r[f]) or "plain",
        axis=1,
    )
    counts = hum["cell"].value_counts()
    frame = counts[counts >= MIN_CELL]
    covered = frame.sum() / len(hum)
    print(f"[mat] {len(frame)} cells with >={MIN_CELL} human prompts "
          f"cover {covered:.1%} of the human panel")

    # Largest-remainder allocation of PANEL_SIZE slots.
    quotas = frame / frame.sum() * PANEL_SIZE
    alloc = quotas.astype(int)
    for cell in quotas.sub(alloc).sort_values(ascending=False).index:
        if alloc.sum() >= PANEL_SIZE:
            break
        alloc[cell] += 1

    bands = pd.cut(
        hum["n_words"], [0, 15, 45, 10**6], labels=["short", "medium", "long"]
    ).value_counts(normalize=True)

    cell_flags = {
        cell: {f for f in STRATIFY_FLAGS
               if FLAG_NAMES[f] in (cell.split("+") if cell != "plain" else [])}
        for cell in alloc.index
    }
    return alloc.to_dict(), bands, cell_flags


def mat_brief(k: int, on: set[str], band: str) -> str:
    must = [FLAG_REQUIREMENTS[f]["must"] for f in STRATIFY_FLAGS if f in on]
    must_not = [FLAG_REQUIREMENTS[f]["must_not"] for f in STRATIFY_FLAGS if f not in on]
    lines = [
        "The real situation: a person is shopping for headphones as a gift "
        "for a family member who travels frequently. Real people often leave "
        "parts of their situation out of what they actually type into an AI "
        "assistant.",
        f"Generate {k} distinct prompts this person might type, each "
        f"{BANDS[band][2]}.",
    ]
    if must:
        lines.append("Every prompt MUST " + "; and ".join(must) + ".")
    lines.append("Every prompt must NOT " + "; and must not ".join(must_not) + ".")
    lines.append(f"Write them the way {k} different real people would each phrase it.")
    return "\n\n".join(lines)


def generate_mat(key: str) -> dict:
    rng = np.random.default_rng(SEED)
    alloc, band_marginal, cell_flags = stratification_frame()
    band_names = list(band_marginal.index.astype(str))
    band_probs = band_marginal.to_numpy()

    seen: set[str] = set()
    prompts: list[dict] = []
    for cell, k_cell in alloc.items():
        on = cell_flags[cell]
        draws = rng.choice(band_names, size=k_cell, p=band_probs)
        for band in sorted(set(draws)):
            need = int((draws == band).sum())
            got: list[str] = []
            for round_no in range(1, MAX_ROUNDS + 1):
                cands = call_llm(key, MAT_SYSTEM_PROMPT,
                                 mat_brief(need - len(got) + 2, on, band))
                for text in cands:
                    if len(got) >= need:
                        break
                    hits = flags_of(text)
                    if (clean(text) and norm(text) not in seen
                            and hits >= on
                            and not (hits & set(STRATIFY_FLAGS) - on)):
                        seen.add(norm(text))
                        got.append(text)
                if len(got) >= need:
                    break
                print(f"[mat] {cell}/{band}: {len(got)}/{need} after round {round_no}")
            if len(got) < need:
                raise SystemExit(f"[mat] could not fill {cell}/{band} "
                                 f"({len(got)}/{need}) after {MAX_ROUNDS} rounds")
            for text in got:
                n_words = len(text.split())
                prompts.append({
                    "text": text, "cell": cell, "band_target": band,
                    "band_achieved": band_of(n_words), "n_words": n_words,
                })
        print(f"[mat] {cell}: {k_cell} prompts done")

    return {
        "arm": "mat",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator_model": MODEL,
        "seed": SEED,
        "system_prompt": MAT_SYSTEM_PROMPT,
        "stratify_flags": STRATIFY_FLAGS,
        "source": "003 hum panel joint flag profiles (cells >= 2 prompts)",
        "cell_targets": alloc,
        "band_marginal": {b: round(float(p), 4)
                          for b, p in zip(band_names, band_probs)},
        "prompts": prompts,
    }


# ------------------------------------------------------------------- neu2


def generate_neu2(key: str, n: int = 40) -> dict:
    seen: set[str] = set()
    kept: list[str] = []
    for round_no in range(1, MAX_ROUNDS + 1):
        cands = call_llm(key, NEUTRAL_SYSTEM_PROMPT,
                         NEUTRAL_BRIEF.format(n=n - len(kept)))
        for text in cands:
            if len(kept) < n and clean(text) and norm(text) not in seen:
                seen.add(norm(text))
                kept.append(text)
        if len(kept) >= n:
            break
        print(f"[neu2] {len(kept)}/{n} after round {round_no}")
    if len(kept) < n:
        raise SystemExit(f"[neu2] only {len(kept)}/{n} clean prompts")
    return {
        "arm": "neu2",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator_model": MODEL,
        "system_prompt": NEUTRAL_SYSTEM_PROMPT,
        "brief": NEUTRAL_BRIEF.format(n=n),
        "n_requested": n,
        "prompts": kept,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=["mat", "neu2"], required=True)
    ap.add_argument("--env-file", default=None)
    a = ap.parse_args()

    key = load_key(a.env_file)
    payload = generate_mat(key) if a.arm == "mat" else generate_neu2(key)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{a.arm}.json"
    out.write_text(json.dumps(payload, indent=1))
    n = len(payload["prompts"])
    print(f"[{a.arm}] wrote {n} prompts -> {out}")


if __name__ == "__main__":
    main()
