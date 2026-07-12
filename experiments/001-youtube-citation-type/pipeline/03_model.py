#!/usr/bin/env python3
"""Step 3 — pre-registered hypotheses + robustness suite (spec §4, §5, §7).

Writes results/model_results.csv and results/model_summary.txt.
Stops (exit 1) if the positive control H4 fails — per spec, no other result
is interpretable in that case.
"""

from __future__ import annotations

import io
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from aeo_research import collinearity_report, fit_clustered_logit
from common import ALPHA, RESULTS, SESOI_OR, load_videos, primary_frame

CONTROLS = "engagement_rate + log_duration + log_age + n_sources_evaluated"
CLUSTERS = ["execution_id", "video_id"]

FOCALS = {
    "H1": ("log_subs", "log10 channel subscribers"),
    "H2": ("engagement_rate", "engagement rate"),
    "H3": ("log_views", "log10 video views"),
    "H6": ("has_captions", "has captions"),
    "H8": ("has_chapters_f", "description has chapters"),
}


def formula(focal: str, df: pd.DataFrame) -> str:
    terms = ["similarity", focal]
    if focal != "engagement_rate":
        terms.append(CONTROLS)
    else:
        terms.append("log_duration + log_age + n_sources_evaluated")
    if df["platform"].nunique() > 1:
        terms.append("C(platform)")
    return "cited ~ " + " + ".join(terms)


def fit_tost(df: pd.DataFrame, focal: str, **kw):
    res = fit_clustered_logit(df, formula(focal, df), CLUSTERS)
    return res, res.tost(focal, sesoi_or=SESOI_OR, alpha=ALPHA, **kw)


def main() -> None:
    df = primary_frame(load_videos())
    out = io.StringIO()

    def p(*args):
        print(*args)
        print(*args, file=out)

    p("=" * 72)
    p(f"MODELS — n = {len(df):,} units evaluated in this study")
    p(f"SESOI: OR in [{1 / SESOI_OR:.3f}, {SESOI_OR:.3f}] per SD; {int((1 - ALPHA) * 100)}% CIs")
    p("Two-way cluster-robust SEs (execution, video); one focal per model (§5a)")
    p("=" * 72)

    # The collider demonstration — the number NOT to publish.
    naive = smf.logit("cited ~ log_subs", data=df).fit(disp=False)
    p("\nTHE COLLIDER TRAP (naive, no similarity control — do not publish):")
    p(f"  cited ~ log_subs -> OR = {np.exp(naive.params['log_subs']):.3f}"
      f"  p = {naive.pvalues['log_subs']:.4f}")

    # H4 positive control, from the H1 model.
    res1, _ = fit_tost(df, "log_subs")
    h4 = res1.tost("similarity")
    p(f"\n[H4] POSITIVE CONTROL — similarity")
    p(f"  OR = {h4.odds_ratio:.3f} [{h4.or_lo:.3f}, {h4.or_hi:.3f}]  p = {h4.p_nhst:.2e}")
    if h4.p_nhst < 0.05 and h4.beta > 0:
        p("  PASS — the data can detect things.")
    else:
        p("  *** FAIL — STOP. Similarity does not predict citation; nothing below is interpretable.")
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "model_summary.txt").write_text(out.getvalue())
        sys.exit(1)

    rows = []
    for hyp, (focal, label) in FOCALS.items():
        sub = df[df[focal].notna()]
        res, t = fit_tost(sub, focal)
        rows.append({"hypothesis": hyp, "label": label, "n": len(sub),
                     "cgm_floored": res.cgm_floored, **t.as_dict()})
        p(f"\n[{hyp}] {label}  (n = {len(sub):,})")
        p(f"  OR = {t.odds_ratio:.3f} [{t.or_lo:.3f}, {t.or_hi:.3f}]  SE = {t.se:.4f}")
        p(f"  p(nhst) = {t.p_nhst:.3f}  p(TOST) = {t.p_tost:.4f}")
        p(f"  --> {t.verdict.value}")

    # H7: category — global comparison vs Other (exploratory slices).
    res7 = fit_clustered_logit(
        df, "cited ~ similarity + C(category, Treatment('Other')) + " + CONTROLS + " + C(platform)",
        CLUSTERS,
    )
    p("\n[H7] video_category (vs 'Other'):")
    for name in res7.params.index:
        if "category" in name:
            t = res7.tost(name, sesoi_or=SESOI_OR, alpha=ALPHA)
            p(f"  {name:55s} OR = {t.odds_ratio:.3f} [{t.or_lo:.3f}, {t.or_hi:.3f}]")

    # H5 placebo.
    res5 = fit_clustered_logit(df, "cited ~ placebo_dow", CLUSTERS)
    t5 = res5.tost("placebo_dow")
    p(f"\n[H5] PLACEBO — publish day-of-week: OR = {t5.odds_ratio:.3f}  p = {t5.p_nhst:.3f}")
    p("  PASS — placebo null." if t5.p_nhst > 0.05 else
      "  *** WARN — placebo shows an effect; SEs are too small. Re-examine clustering.")

    # Collinearity (§5a).
    rep = collinearity_report(df.dropna(subset=["log_subs", "log_views"]), ["log_subs", "log_views"])
    p(f"\ncorr(log_subs, log_views) = {rep['corr'].iloc[0, 1]:.3f}  VIFs = "
      + ", ".join(f"{k}={v:.1f}" for k, v in rep["vif"].items()))

    # Robustness.
    p("\nROBUSTNESS")
    dedup = df.sort_values("response_at").drop_duplicates("video_id")
    _, td = fit_tost(dedup, "log_subs")
    p(f"  #5 dedup (one row/video, n={len(dedup):,}): H1 OR = {td.odds_ratio:.3f} "
      f"[{td.or_lo:.3f}, {td.or_hi:.3f}] -> {td.verdict.value}")
    for plat in sorted(df["platform"].unique()):
        sub = df[df["platform"] == plat]
        if sub["cited"].nunique() < 2:
            continue
        _, tp = fit_tost(sub, "log_subs")
        p(f"  #6 {plat} (n={len(sub):,}): H1 OR = {tp.odds_ratio:.3f} "
          f"[{tp.or_lo:.3f}, {tp.or_hi:.3f}] -> {tp.verdict.value}")
    single = df[df["n_youtube_in_execution"] == 1]
    _, ts = fit_tost(single, "log_subs")
    p(f"  #9 single-YouTube executions only (n={len(single):,}): H1 OR = {ts.odds_ratio:.3f} "
      f"[{ts.or_lo:.3f}, {ts.or_hi:.3f}] -> {ts.verdict.value}")
    nonnull = df[df["audience_size"].notna()] if df["audience_size"].isna().any() else df
    p(f"  #8 audience_size missingness: {df['audience_size'].isna().mean():.1%} null; "
      f"cited-rate null={df[df['audience_size'].isna()]['cited'].mean() if df['audience_size'].isna().any() else float('nan'):.3f} "
      f"vs non-null={nonnull['cited'].mean():.3f}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(RESULTS / "model_results.csv", index=False)
    (RESULTS / "model_summary.txt").write_text(out.getvalue())
    print(f"\n  -> {RESULTS / 'model_results.csv'}\n  -> {RESULTS / 'model_summary.txt'}")


if __name__ == "__main__":
    main()
