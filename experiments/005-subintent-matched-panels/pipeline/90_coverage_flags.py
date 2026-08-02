"""Exploratory (H4) — phrasing-coverage flags per panel -> results/coverage_flags.txt.

Codes every prompt with 002's 15 regex attribute flags plus length stats,
then compares flag prevalence per panel against the human panel: which
sub-intents (budget constraints, named recipients, travel context, format
requests, ...) do synthetic generators reach for unaided, and which human
phrasing behaviors do they never emit?

Prompt-side only — runs on data/raw/prompts.csv, needs no responses, and can
therefore run pre-collection (it makes no claim about outcomes). Prompt text
stays internal; only flags/aggregates leave this script. Labelled exploratory
per the 9x convention.
"""

from __future__ import annotations

import pandas as pd
from common import CONTRAST_ARM, PRIMARY_ARM, PROMPTS_CSV, RESULTS, SYNTH_ARMS
from flags import FLAGS


def main() -> None:
    prompts = pd.read_csv(PROMPTS_CSV)
    hp = prompts[prompts["arm"] != CONTRAST_ARM].copy()
    t = hp["text"].str.lower()
    for flag, pattern in FLAGS.items():
        hp[flag] = t.str.contains(pattern)

    arms = [PRIMARY_ARM, *SYNTH_ARMS]
    out: list[str] = ["# Experiment 005 — H4 phrasing coverage (exploratory)\n"]

    prev = pd.DataFrame({
        arm: hp[hp["arm"] == arm][list(FLAGS)].mean() for arm in arms
    })
    out.append("## Flag prevalence per panel (share of prompts)")
    out.append(prev.round(2).to_string())

    delta = prev[list(SYNTH_ARMS)].sub(prev[PRIMARY_ARM], axis=0)
    out.append("\n## Prevalence delta vs the human panel (synthetic - human)")
    out.append(delta.round(2).to_string())

    never = {
        arm: [f for f in FLAGS if prev.loc[f, PRIMARY_ARM] > 0 and prev.loc[f, arm] == 0]
        for arm in SYNTH_ARMS
    }
    out.append("\n## Human phrasing behaviors a panel NEVER emits")
    for arm, missing in never.items():
        out.append(f"{arm}: {missing or '(none)'}")

    out.append("\n## Prompt length (words)")
    stats = hp.groupby("arm")["n_words"].agg(["min", "median", "max", "std"]).round(1)
    out.append(stats.loc[[a for a in arms if a in stats.index]].to_string())

    # Simple coverage index: share of the human panel's flag profile space
    # (unique 15-bit flag vectors) that each synthetic panel also produces.
    hum_profiles = {tuple(v) for v in hp.loc[hp["arm"] == PRIMARY_ARM, list(FLAGS)].to_numpy()}
    out.append("\n## Profile coverage: share of distinct human flag-profiles reproduced")
    for arm in SYNTH_ARMS:
        arm_profiles = {tuple(v) for v in hp.loc[hp["arm"] == arm, list(FLAGS)].to_numpy()}
        covered = len(hum_profiles & arm_profiles) / len(hum_profiles)
        out.append(
            f"{arm}: {covered:.2f} ({len(arm_profiles)} distinct profiles vs "
            f"{len(hum_profiles)} human)"
        )

    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "coverage_flags.txt"
    path.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
