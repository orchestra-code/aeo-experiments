"""Stage 02 — data-quality audits A-D (spec §2) -> results/audit.txt.

A: collection completeness + degenerate-response rates per intent/wave.
B: what the outcome labels mean (extraction definitions, quoted from code).
C: independence/clustering structure -> justifies the prompt-level bootstrap.
D: extraction validity — spot-check sample (human labels), model-version
   drift table, SparkToro top-brand frequency anchor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from common import (
    CONTRAST_INTENT,
    INTERIM,
    LEDGER,
    PRIMARY_INTENT,
    PROMPTS_CSV,
    RESULTS,
    SEED,
    load_responses,
)

from aeo_research.dataforseo import Ledger
from aeo_research.overlap import condition_pairs

SPOTCHECK_N = 30


def audit_a(df: pd.DataFrame, out: list[str]) -> None:
    out.append("## Audit A — collection completeness and degenerate responses\n")
    ledger_path = Path(LEDGER)
    if ledger_path.exists():
        lf = Ledger(ledger_path).frame()
        out.append("Ledger status counts:")
        out.append(lf.groupby(["intent", "wave", "status"]).size().to_string())
    else:
        out.append("(no ledger — synthetic run)")
    checks = df.assign(
        empty_reply=(df["reply_word_count"] == 0).astype(int),
        no_brands=(df["n_brands"] == 0).astype(int),
        no_fanout=(df["n_fanout"] == 0).astype(int),
        no_sources=(df["n_sources"] == 0).astype(int),
    )
    rates = checks.groupby(["intent", "wave"])[
        ["empty_reply", "no_brands", "no_fanout", "no_sources", "had_web_search"]
    ].mean()
    out.append("\nDegenerate-response rates (mean per intent/wave):")
    out.append(rates.round(3).to_string())
    worst = checks.groupby("intent")["no_fanout"].mean()
    out.append(
        f"\nEmpty fan-out rate overall: {worst.round(3).to_dict()} "
        "(spec §6: if >0.30 for headphones, H2 grounding claims are INCONCLUSIVE territory)"
    )


def audit_b(out: list[str]) -> None:
    out.append("\n## Audit B — outcome-label meaning\n")
    out.append(
        "- 'brand recommended' = canonical brand whose alias matches the cleaned answer\n"
        "  markdown (URLs stripped, word-boundary, longest-alias-first) — brands.py::extract_brands.\n"
        "- 'domain cited' = registered domain of a normalized URL in result.sources[]\n"
        "  (search_results[] are SERP extras and are EXCLUDED) — 01_features.py.\n"
        "- 'grounding tokens' = stopword-filtered token union over result.fan_out_queries\n"
        "  — aeo_research.overlap.token_set."
    )


def audit_c(df: pd.DataFrame, out: list[str]) -> None:
    out.append("\n## Audit C — independence and clustering\n")
    prompts = pd.read_csv(PROMPTS_CSV)
    dups = prompts[prompts["is_dup"]]
    out.append(
        f"{prompts.groupby('intent').size().to_dict()} prompts; duplicate-text groups: "
        f"{dups.groupby('intent').size().to_dict() if not dups.empty else 'none'} "
        f"({sorted(dups['item_id'])})"
    )
    pairs = condition_pairs(
        df.reset_index(drop=True),
        primary_intent=PRIMARY_INTENT,
        contrast_intent=CONTRAST_INTENT,
    )
    out.append("Pair counts by condition (each response participates in many pairs — all")
    out.append("inference is prompt-level cluster bootstrap, never pair-level SEs):")
    out.append(pairs["condition"].value_counts().to_string())


def audit_d(df: pd.DataFrame, out: list[str]) -> None:
    out.append("\n## Audit D — extraction validity and drift\n")
    out.append("Model version by intent/wave:")
    out.append(
        df.groupby(["intent", "wave", "model"]).size().to_string()
    )
    hp = df[df["intent"] == PRIMARY_INTENT]
    all_brands = sorted({b for s in hp["brand_set"] for b in s})
    share = pd.Series(
        {b: hp["brand_set"].map(lambda s, b=b: b in s).mean() for b in all_brands}
    ).sort_values(ascending=False)
    out.append(
        "\nShare of headphone responses mentioning each brand (SparkToro anchor: their"
        "\ntop brands appeared in 55-77% of responses):"
    )
    out.append(share.head(12).round(3).to_string() if not hp.empty else "(none)")

    # Cross-check vs DataForSEO's own product/brand entities where present.
    from brands import extract_brands

    with_ents = hp[hp["n_entities"] > 0]
    if not with_ents.empty:
        agree = []
        for r in with_ents.itertuples():
            ent_brands = set(
                extract_brands(str(r.entity_titles).replace("|", "\n"), r.intent)
            )
            if ent_brands:
                agree.append(len(ent_brands & r.brand_set) / len(ent_brands))
        out.append(
            f"\nEntity cross-check: {len(with_ents)}/{len(hp)} responses carry DataForSEO"
            f"\nbrand/product entities; extractor recovers "
            f"{pd.Series(agree).mean():.3f} of entity-derived brands on average."
            if agree else "\nEntity cross-check: entities present but none map to the lexicon."
        )
    else:
        out.append("\nEntity cross-check: no DataForSEO brand entities in this frame.")

    sample = hp.sample(min(SPOTCHECK_N, len(hp)), random_state=SEED)
    lines = ["# Audit D spot-check sample — label manually, keep out of git\n"]
    for r in sample.itertuples():
        lines.append(f"\n---\n## {r.item_id} w{r.wave}\nExtracted: {r.brands}\n")
        lines.append(str(r.answer_text))
    spot = INTERIM / "spotcheck_sample.md"
    spot.write_text("\n".join(lines))
    out.append(
        f"\nSpot-check sample of {len(sample)} responses written to {spot} (gitignored).\n"
        "Manually list recommended brands per response; require precision >= 0.95 and\n"
        "recall >= 0.90 vs the extractor, else refine the lexicon (log in Deviations)."
    )


def main() -> None:
    df = load_responses()
    if int(df.get("synthetic", pd.Series([0])).max()) == 1:
        print("NOTE: auditing a SYNTHETIC frame")
    out: list[str] = ["# Experiment 002 — data-quality audits\n"]
    audit_a(df, out)
    audit_b(out)
    audit_c(df, out)
    audit_d(df, out)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "audit.txt"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())
