"""Stage 00 — survey TSV -> data/raw/prompts.csv (item_id, intent, text, flags).

The survey file is SparkToro's prompt-collection export (de-identified; the
Email column is empty for every row — asserted here). Prompt text never leaves
data/raw: downstream stages key everything off item_id.
"""

from __future__ import annotations

import sys

import pandas as pd

from common import N_PROMPTS_EXPECTED, PROMPTS_CSV, SURVEY_TSV

HEADPHONE_COL = 3 - 1  # column order in the Google-Forms export
COFFEE_COL = 4 - 1


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def main() -> None:
    df = pd.read_csv(SURVEY_TSV, sep="\t", dtype=str).fillna("")
    assert len(df) == N_PROMPTS_EXPECTED, f"expected {N_PROMPTS_EXPECTED} rows, got {len(df)}"
    email_col = df.columns[1]
    assert (df[email_col] == "").all(), "survey export must be de-identified (emails present!)"

    frames = []
    for intent, prefix, col in (
        ("headphones", "h", df.columns[HEADPHONE_COL]),
        ("coffee", "c", df.columns[COFFEE_COL]),
    ):
        text = df[col].str.strip()
        assert (text != "").all(), f"blank {intent} prompt found"
        sub = pd.DataFrame(
            {
                "item_id": [f"{prefix}{i + 1:03d}" for i in range(len(df))],
                "intent": intent,
                "text": text,
            }
        )
        normed = sub["text"].map(norm)
        sub["is_dup"] = normed.duplicated(keep=False)
        sub["n_words"] = sub["text"].str.split().str.len()
        sub["n_chars"] = sub["text"].str.len()
        frames.append(sub)

    out = pd.concat(frames, ignore_index=True)
    PROMPTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROMPTS_CSV, index=False)

    for intent, sub in out.groupby("intent"):
        print(
            f"{intent}: {len(sub)} prompts, {int(sub['is_dup'].sum())} in duplicate groups, "
            f"median {int(sub['n_words'].median())} words"
        )
    print(f"wrote {PROMPTS_CSV}")


if __name__ == "__main__":
    sys.exit(main())
