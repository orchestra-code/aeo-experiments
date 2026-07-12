#!/usr/bin/env python3
"""Step 3 — pre-registered hypotheses + robustness (spec §4, §5, §7, post-pivot).

Outcome: moment_cited among AIO inline YouTube citations.
Writes results/model_results.csv and results/model_summary.txt.
Stops (exit 1) if H3 (duration, the positive control) fails — per spec, a
moment-picker blind to duration means the outcome or predictors are broken.
"""

from __future__ import annotations

import io
import sys

import numpy as np
import pandas as pd
from aeo_research import collinearity_report, fit_clustered_logit
from common import ALPHA, RESULTS, SESOI_OR, load_videos, primary_frame

BASE_CONTROLS = "similarity + engagement_rate + log_age + desc_word_count_z + n_sources_evaluated"
CLUSTERS = ["execution_id", "video_id"]

#: hypothesis -> (focal term, label, duration stays as control?)
FOCALS = {
    "H1": ("has_chapters_f", "description has chapters", True),
    "H2": ("has_captions", "has captions", True),
    "H3": ("log_duration", "log10 duration (positive control)", False),
    "H5": ("log_subs", "log10 channel subscribers (null-form)", True),
    "H6": ("log_views", "log10 video views (null-form)", True),
}


def formula(focal: str, with_duration: bool) -> str:
    terms = [focal, BASE_CONTROLS]
    if with_duration and focal != "log_duration":
        terms.append("log_duration")
    return "moment_cited ~ " + " + ".join(terms)


def fit_tost(df: pd.DataFrame, focal: str, with_duration: bool = True):
    sub = df[df[focal].notna()]
    res = fit_clustered_logit(sub, formula(focal, with_duration), CLUSTERS)
    return sub, res, res.tost(focal, sesoi_or=SESOI_OR, alpha=ALPHA)


def main() -> None:
    df = primary_frame(load_videos())
    out = io.StringIO()

    def p(*args):
        print(*args)
        print(*args, file=out)

    p("=" * 72)
    p(f"MODELS — n = {len(df):,} AIO video citations evaluated in this study")
    p(f"Outcome: moment_cited ({df['moment_cited'].mean():.1%} of units)")
    p(f"SESOI: OR in [{1 / SESOI_OR:.3f}, {SESOI_OR:.3f}] per SD; {int((1 - ALPHA) * 100)}% CIs")
    p("Two-way cluster-robust SEs (execution, video); one focal per model (§5a)")
    p("=" * 72)

    # H3 first — the canary.
    sub3, res3, t3 = fit_tost(df, "log_duration", with_duration=False)
    p(f"\n[H3] POSITIVE CONTROL — log10 duration (n = {len(sub3):,})")
    p(f"  OR = {t3.odds_ratio:.3f} [{t3.or_lo:.3f}, {t3.or_hi:.3f}]  p = {t3.p_nhst:.2e}")
    if t3.p_nhst < 0.05 and t3.beta > 0:
        p("  PASS — the moment-picker sees duration; the data can detect things.")
    else:
        p("  *** FAIL — STOP. Duration does not predict moment citation;")
        p("  the outcome or predictors are broken. Nothing below is interpretable.")
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "model_summary.txt").write_text(out.getvalue())
        sys.exit(1)

    rows = [{"hypothesis": "H3", "label": FOCALS["H3"][1], "n": len(sub3),
             "cgm_floored": res3.cgm_floored, **t3.as_dict()}]
    for hyp, (focal, label, with_dur) in FOCALS.items():
        if hyp == "H3":
            continue
        sub, res, t = fit_tost(df, focal, with_dur)
        rows.append({"hypothesis": hyp, "label": label, "n": len(sub),
                     "cgm_floored": res.cgm_floored, **t.as_dict()})
        p(f"\n[{hyp}] {label}  (n = {len(sub):,})")
        p(f"  OR = {t.odds_ratio:.3f} [{t.or_lo:.3f}, {t.or_hi:.3f}]  SE = {t.se:.4f}")
        p(f"  p(nhst) = {t.p_nhst:.3f}  p(TOST) = {t.p_tost:.4f}")
        p(f"  --> {t.verdict.value}")

    # H7: category — exploratory, reported with intervals only.
    res7 = fit_clustered_logit(
        df,
        "moment_cited ~ C(category, Treatment('Other')) + log_duration + " + BASE_CONTROLS,
        CLUSTERS,
    )
    p("\n[H7] video_category (vs 'Other', exploratory):")
    for name in res7.params.index:
        if "category" in name:
            t = res7.tost(name, sesoi_or=SESOI_OR, alpha=ALPHA)
            p(f"  {name:55s} OR = {t.odds_ratio:.3f} [{t.or_lo:.3f}, {t.or_hi:.3f}]")

    # H4 placebo.
    res4 = fit_clustered_logit(df, "moment_cited ~ placebo_dow", CLUSTERS)
    t4 = res4.tost("placebo_dow")
    p(f"\n[H4] PLACEBO — publish day-of-week: OR = {t4.odds_ratio:.3f}  p = {t4.p_nhst:.3f}")
    p("  PASS — placebo null." if t4.p_nhst > 0.05 else
      "  *** WARN — placebo shows an effect; SEs are too small. Re-examine clustering.")

    # §5a collinearity.
    both = df.dropna(subset=["log_subs", "log_views"])
    rep = collinearity_report(both, ["log_subs", "log_views"])
    p(f"\ncorr(log_subs, log_views) = {rep['corr'].iloc[0, 1]:.3f}  VIFs = "
      + ", ".join(f"{k}={v:.1f}" for k, v in rep["vif"].items()))

    # H8 mechanism check (descriptive): cited timestamp vs chapter markers.
    ts = df[(df["moment_cited"] == 1) & df["timestamp_seconds"].notna()].copy()
    if len(ts):
        def matches(row) -> bool:
            raw = row.get("chapter_times_list")
            if not isinstance(raw, str) or not raw:
                return False
            chapters = [int(x) for x in raw.split("|") if x.isdigit()]
            return any(abs(row["timestamp_seconds"] - c) <= 5 for c in chapters)

        share = ts.apply(matches, axis=1).mean()
        p(f"\n[H8] cited timestamps matching a description chapter (±5 s): {share:.1%}")
        p("  (high -> chapter-sourced; low -> transcript/visual-derived key moments)")

    # Robustness.
    p("\nROBUSTNESS")
    dedup = df.sort_values("response_at").drop_duplicates("video_id")
    _, _, td = fit_tost(dedup, "log_subs")
    p(f"  #5 dedup (one row/video, n={len(dedup):,}): H5 OR = {td.odds_ratio:.3f} "
      f"[{td.or_lo:.3f}, {td.or_hi:.3f}] -> {td.verdict.value}")

    meta_ok = df[df["duration_seconds"].notna()]
    p(f"  #6 metadata coverage: {len(meta_ok):,}/{len(df):,} units have duration; "
      f"moment-rate with metadata = {meta_ok['moment_cited'].mean():.3f} vs "
      f"without = {df[df['duration_seconds'].isna()]['moment_cited'].mean() if df['duration_seconds'].isna().any() else float('nan'):.3f}")

    ok_ts = df[
        (df["moment_cited"] == 0)
        | df["duration_seconds"].isna()
        | (df["timestamp_seconds"] <= df["duration_seconds"])
    ]
    if len(ok_ts) < len(df):
        _, _, t7 = fit_tost(ok_ts, "has_chapters_f")
        p(f"  #7 excl. timestamp>duration (n={len(ok_ts):,}): H1 OR = {t7.odds_ratio:.3f} "
          f"[{t7.or_lo:.3f}, {t7.or_hi:.3f}] -> {t7.verdict.value}")

    df["_half"] = pd.to_datetime(df["response_at"], utc=True, format="mixed").rank(pct=True) > 0.5
    for half, label in [(False, "first half"), (True, "second half")]:
        sub = df[df["_half"] == half]
        if sub["moment_cited"].nunique() < 2:
            continue
        _, _, t8 = fit_tost(sub, "has_chapters_f")
        p(f"  #8 {label} (n={len(sub):,}): H1 OR = {t8.odds_ratio:.3f} "
          f"[{t8.or_lo:.3f}, {t8.or_hi:.3f}] -> {t8.verdict.value}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(RESULTS / "model_results.csv", index=False)
    (RESULTS / "model_summary.txt").write_text(out.getvalue())
    print(f"\n  -> {RESULTS / 'model_results.csv'}\n  -> {RESULTS / 'model_summary.txt'}")


if __name__ == "__main__":
    main()
