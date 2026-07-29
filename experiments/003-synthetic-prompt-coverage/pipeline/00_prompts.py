"""Stage 00 — assemble the four-panel prompts file -> data/raw/prompts.csv.

Sources (all frozen before the spec freeze):
- hum:    002's data/raw/prompts.csv headphone rows (SparkToro survey; h054 is
          pre-excluded — DataForSEO rejected its 2,341-char text in 002 with
          `40501 Invalid Field: 'keyword'`, so 003 drops it up front)
- coffee: 002's coffee rows c001..c040 (cross-intent floor, wave 1 only)
- spy_a / spy_b / neu: harness outputs in data/raw/generator/<arm>.json

Output columns: item_id, intent, text, arm, is_dup, n_words, n_chars,
framework, query_type. The submit CLI only needs item_id/intent/text; arm is
derivable from the item_id prefix but stored for convenience. Prompt text
never leaves data/raw (survey text is SparkToro's; generated text is
product-derived — both stay internal per the data policy).
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from common import (
    ARM_BY_PREFIX,
    EXP002_PROMPTS_CSV,
    GENERATOR_DIR,
    N_COFFEE,
    PROMPTS_CSV,
)

EXCLUDED_ITEMS = {"h054"}  # over the DataForSEO keyword length limit (002 deviation log)

PREFIX_BY_ARM = {arm: prefix for prefix, arm in ARM_BY_PREFIX.items()}


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def human_rows() -> pd.DataFrame:
    src = pd.read_csv(EXP002_PROMPTS_CSV)
    hum = src[(src["intent"] == "headphones") & ~src["item_id"].isin(EXCLUDED_ITEMS)].copy()
    hum["arm"] = "hum"
    coffee = src[src["intent"] == "coffee"].sort_values("item_id").head(N_COFFEE).copy()
    coffee["arm"] = "coffee"
    out = pd.concat([hum, coffee], ignore_index=True)
    out["framework"] = ""
    out["query_type"] = ""
    return out


def generator_rows(arm: str) -> pd.DataFrame:
    payload = json.loads((GENERATOR_DIR / f"{arm}.json").read_text())
    if arm == "neu":
        records = [{"text": p, "framework": "neutral", "query_type": ""} for p in payload["prompts"]]
    else:
        records = [
            {"text": q["query"], "framework": q["framework"], "query_type": q["queryType"]}
            for q in payload["queries"]
        ]
    df = pd.DataFrame(records)
    assert (df["text"].str.strip() != "").all(), f"blank prompt in {arm}"
    prefix = PREFIX_BY_ARM[arm]
    df["item_id"] = [f"{prefix}{i + 1:03d}" for i in range(len(df))]
    df["intent"] = "headphones"
    df["arm"] = arm
    return df


def main() -> None:
    frames = [human_rows()] + [generator_rows(a) for a in ("spy_a", "spy_b", "neu")]
    out = pd.concat(frames, ignore_index=True)

    normed = out["text"].map(norm)
    out["is_dup"] = normed.duplicated(keep=False)
    out["n_words"] = out["text"].str.split().str.len()
    out["n_chars"] = out["text"].str.len()
    out = out[
        ["item_id", "intent", "text", "arm", "is_dup", "n_words", "n_chars",
         "framework", "query_type"]
    ]

    assert out["item_id"].is_unique
    assert (out["n_chars"] <= 2000).all(), "prompt over the DataForSEO keyword limit"

    PROMPTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROMPTS_CSV, index=False)

    for arm, sub in out.groupby("arm"):
        print(
            f"{arm}: {len(sub)} prompts, {int(sub['is_dup'].sum())} in duplicate groups, "
            f"median {int(sub['n_words'].median())} words "
            f"(range {int(sub['n_words'].min())}-{int(sub['n_words'].max())})"
        )
    print(f"wrote {PROMPTS_CSV}")


if __name__ == "__main__":
    sys.exit(main())
