"""Stage 02 — data-quality audits A-D (spec §2) -> results/audit.txt.

A: collection completeness + degenerate-response rates per arm/wave.
B: what the outcome labels mean (extraction definitions, quoted from code).
C: independence/clustering structure -> justifies the prompt-level bootstrap.
D: extraction validity — spot-check sample (human labels), model-version
   drift table, 003 brand-share anchor comparison.
E: stratification manipulation check — the mat panel's achieved cell and
   length-band distributions vs its frozen targets (regex re-validation).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
from common import (
    ARM_BY_PREFIX,
    GENERATOR_DIR,
    INTERIM,
    LEDGER,
    PRIMARY_ARM,
    PROMPTS_CSV,
    RESULTS,
    SEED,
    load_responses,
)
from flags import FLAGS, STRATIFY_FLAGS

from aeo_research.dataforseo import Ledger
from aeo_research.overlap import arm_condition_pairs

SPOTCHECK_N = 30

#: 003's final hum-arm brand shares (headphones, gpt-5-5, 29 Jul – 2 Aug
#: 2026) — an anchor for the hum arm, not a hypothesis: drift is a
#: reportable observation, not a failure.
EXP003_ANCHOR = {"sony": 0.877, "bose": 0.824, "sennheiser": 0.776,
                 "anker": 0.729, "apple": 0.485, "jbl": 0.241}


def audit_a(df: pd.DataFrame, out: list[str]) -> None:
    out.append("## Audit A — collection completeness and degenerate responses\n")
    ledger_path = Path(LEDGER)
    if ledger_path.exists():
        lf = Ledger(ledger_path).frame()
        lf["arm"] = lf["item_id"].str[0].map(ARM_BY_PREFIX)
        out.append("Ledger status counts:")
        out.append(lf.groupby(["arm", "wave", "status"]).size().to_string())
    else:
        out.append("(no ledger — synthetic run)")
    checks = df.assign(
        empty_reply=(df["reply_word_count"] == 0).astype(int),
        no_brands=(df["n_brands"] == 0).astype(int),
        no_fanout=(df["n_fanout"] == 0).astype(int),
        no_sources=(df["n_sources"] == 0).astype(int),
    )
    rates = checks.groupby(["arm", "wave"])[
        ["empty_reply", "no_brands", "no_fanout", "no_sources", "had_web_search"]
    ].mean()
    out.append("\nDegenerate-response rates (mean per arm/wave):")
    out.append(rates.round(3).to_string())
    worst = checks.groupby("arm")["no_fanout"].mean()
    out.append(
        f"\nEmpty fan-out rate per arm: {worst.round(3).to_dict()} "
        "(spec §6: if >0.30 for any headphone arm, that arm's grounding "
        "claims are INCONCLUSIVE territory)"
    )


def audit_b(out: list[str]) -> None:
    out.append("\n## Audit B — outcome-label meaning\n")
    out.append(
        "- 'brand recommended' = canonical brand whose alias matches the cleaned answer\n"
        "  markdown (URLs stripped, word-boundary, longest-alias-first) — brands.py::extract_brands\n"
        "  (verbatim copy of 002's post-curation extraction).\n"
        "- 'domain cited' = registered domain of a normalized URL in result.sources[]\n"
        "  (search_results[] are SERP extras and are EXCLUDED) — 01_features.py.\n"
        "- 'grounding tokens' = stopword-filtered token union over result.fan_out_queries\n"
        "  — aeo_research.overlap.token_set.\n"
        "- 'panel share' (H2/H3) = fraction of an arm's responses whose brand set\n"
        "  contains the brand — 03_model.py::brand_share."
    )


def audit_c(df: pd.DataFrame, out: list[str]) -> None:
    out.append("\n## Audit C — independence and clustering\n")
    prompts = pd.read_csv(PROMPTS_CSV)
    dups = prompts[prompts["is_dup"]]
    out.append(
        f"{prompts.groupby('arm').size().to_dict()} prompts; duplicate-text groups: "
        f"{dups.groupby('arm').size().to_dict() if not dups.empty else 'none'} "
        f"({sorted(dups['item_id'])})"
    )
    out.append(
        "Note: h016/c016 is the same respondent's refusal text pasted into both\n"
        "survey questions — a valid human behavior, kept; R3 refits without dups."
    )
    pairs = arm_condition_pairs(df.reset_index(drop=True))
    out.append("Pair counts by condition (each response participates in many pairs — all")
    out.append("inference is prompt-level cluster bootstrap, never pair-level SEs):")
    out.append(pairs["condition"].value_counts().to_string())


def audit_d(df: pd.DataFrame, out: list[str]) -> None:
    out.append("\n## Audit D — extraction validity and drift\n")
    out.append("Model version by arm/wave:")
    out.append(df.groupby(["arm", "wave", "model"]).size().to_string())

    hp = df[df["intent"] == "headphones"]
    out.append("\nShare of responses mentioning each brand, per arm (top 12 by hum share):")
    all_brands = sorted({b for s in hp["brand_set"] for b in s})
    shares = pd.DataFrame({
        arm: {b: sub["brand_set"].map(lambda s, b=b: b in s).mean() for b in all_brands}
        for arm, sub in hp.groupby("arm")
    })
    if PRIMARY_ARM in shares:
        shares = shares.sort_values(PRIMARY_ARM, ascending=False)
    out.append(shares.head(12).round(3).to_string())
    out.append(
        "\n003 anchor (gpt-5-5, 29 Jul - 2 Aug 2026) for the hum arm — drift is"
        f"\nreportable, not a failure: {EXP003_ANCHOR}"
    )

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
        lines.append(f"\n---\n## {r.item_id} ({r.arm}) w{r.wave}\nExtracted: {r.brands}\n")
        lines.append(str(r.answer_text))
    spot = INTERIM / "spotcheck_sample.md"
    spot.write_text("\n".join(lines))
    out.append(
        f"\nSpot-check sample of {len(sample)} responses written to {spot} (gitignored).\n"
        "Manually list recommended brands per response; require precision >= 0.95 and\n"
        "recall >= 0.90 vs the extractor, else refine the lexicon (log in Deviations)."
    )


def audit_e(out: list[str]) -> None:
    """Manipulation check: the mat panel must actually BE stratified."""
    out.append("\n## Audit E — mat stratification manipulation check\n")
    payload = json.loads((GENERATOR_DIR / "mat.json").read_text())
    prompts = pd.read_csv(PROMPTS_CSV)
    mat = prompts[prompts["arm"] == "mat"].copy()

    name = {"f_travel_context": "travel", "f_usage_music": "music",
            "f_budget_specific": "budget", "f_recipient_named": "recipient",
            "f_form_factor": "form", "f_wireless": "wireless"}
    achieved_cell = mat.apply(
        lambda r: "+".join(
            name[f] for f in STRATIFY_FLAGS
            if re.search(FLAGS[f], str(r["text"]).lower())
        ) or "plain",
        axis=1,
    )
    target = pd.Series(payload["cell_targets"])
    achieved = achieved_cell.value_counts().reindex(target.index).fillna(0).astype(int)
    tab = pd.DataFrame({"target": target, "achieved": achieved})
    out.append(tab.to_string())
    exact = bool((tab["target"] == tab["achieved"]).all())
    out.append(f"Exact cell match (regex re-validation): {exact}")
    stray = achieved_cell[~achieved_cell.isin(target.index)]
    if not stray.empty:
        out.append(f"** prompts outside the target frame: {stray.tolist()} **")
    out.append(
        "Any mismatch here means the measured object is a mis-stratified "
        "panel; H2_mat's verdict must be reported against the ACHIEVED "
        "distribution and logged in Deviations."
    )
    bands = pd.cut(mat["n_words"], [0, 15, 45, 10**6],
                   labels=["short", "medium", "long"]).value_counts(normalize=True)
    out.append(f"\nAchieved length bands: {bands.round(3).to_dict()} "
               f"(target marginal: {payload['band_marginal']})")


def main() -> None:
    df = load_responses()
    if int(df.get("synthetic", pd.Series([0])).max()) == 1:
        print("NOTE: auditing a SYNTHETIC frame")
    out: list[str] = ["# Experiment 005 — data-quality audits\n"]
    audit_a(df, out)
    audit_b(out)
    audit_c(df, out)
    audit_d(df, out)
    audit_e(out)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "audit.txt"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())
