"""DOCUMENTED DEVIATION from the frozen spec (recorded in spec §Deviations).

The §5 shuffle placebo FAILED under the frozen pooled logit (M1 shuffle OR
0.907 CI 0.838–0.982; M2 shuffle 1.072 CI 1.031–1.115): with 363k rows, the
pooled estimator picks up answer-level composition (answers differ in
category mix, pool size, and consulted count), which a within-answer shuffle
preserves. The repair: CONDITIONAL logit grouped by answer (execution), which
eliminates every answer's intercept and estimates purely within-answer
contrasts — the estimand §1 actually describes. Same predictors, same
SESOIs, same seed. The shuffle placebo is re-run under the conditional
estimator and must be null; uncertainty via a 200-draw domain-cluster
bootstrap (resample domains, keep rows of sampled domains, refit).

Usage: uv run python experiments/007-site-consultations-observational/pipeline/05b_conditional_model.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.discrete.conditional_models import ConditionalLogit

EXP = Path(__file__).resolve().parents[1]
INTERIM, RESULTS = EXP / "data" / "interim", EXP / "results"
SEED = 20260901
BOOT_DRAWS = 200
SESOI = {"M1": 1.5, "M2": 1.30, "M3": 1.5}


def informative(df: pd.DataFrame) -> pd.DataFrame:
    """Rows in answers with outcome variation (others carry no information)."""
    g = df.groupby("discovery_execution_id")["consulted"]
    keep = g.transform("sum").gt(0) & g.transform("sum").lt(g.transform("size"))
    return df[keep]


def fit_cl(df: pd.DataFrame, xcol: str) -> float | None:
    d = informative(df.dropna(subset=[xcol]))
    if d.empty or d[xcol].nunique() < 2:
        return None
    fit = ConditionalLogit(
        d["consulted"].to_numpy(dtype=float),
        d[[xcol]].to_numpy(dtype=float),
        groups=d["discovery_execution_id"].to_numpy(),
    ).fit(disp=0)
    return float(np.exp(fit.params[0]))


def boot_cl(df: pd.DataFrame, xcol: str, rng) -> tuple[float, float]:
    base = df.dropna(subset=[xcol])
    groups = {d: idx.to_numpy() for d, idx in base.groupby("domain").groups.items()}
    names = np.array(list(groups))
    ors = []
    while len(ors) < BOOT_DRAWS:
        take = set(rng.choice(names, size=len(names), replace=True))
        sample = base[base["domain"].isin(take)]
        try:
            or_ = fit_cl(sample, xcol)
        except Exception:  # noqa: BLE001 — separation draws
            or_ = None
        if or_ is not None and np.isfinite(or_):
            ors.append(or_)
    return float(np.percentile(ors, 5)), float(np.percentile(ors, 95))


def verdict(or_: float, ci: tuple[float, float], sesoi: float) -> str:
    lo, hi = ci
    if 1 / sesoi < lo and hi < sesoi:
        return "NULL (equivalent)"
    excludes = lo > 1.0 or hi < 1.0
    beyond = hi > sesoi or lo < 1 / sesoi
    if excludes and beyond:
        return "REAL"
    if excludes:
        return "NEGLIGIBLE"
    return "INCONCLUSIVE"


def main() -> None:
    rng = np.random.default_rng(SEED)
    pool = pd.read_csv(INTERIM / "pool_with_metrics.csv",
                       keep_default_na=False, na_values=[""])
    pool["consulted"] = pool["consulted"].astype(str).str.lower().eq("true").astype(int)
    pool["ranked_in_cc"] = pool["hc_rank"].notna().astype(float)
    ranked = pool["hc_rank"].notna()
    pool.loc[ranked, "z_log_rank"] = -(
        np.log10(pool.loc[ranked, "hc_rank"])
        - np.log10(pool.loc[ranked, "hc_rank"]).mean()
    )
    pool["premium_or_strong"] = np.where(
        pool["aipvs"].notna(),
        pool["tier_label"].isin(["Premium", "Strong"]).astype(float),
        np.nan,
    )

    shuffled = pool.copy()
    shuffled["consulted"] = (
        shuffled.groupby("discovery_execution_id")["consulted"]
        .transform(lambda s: rng.permutation(s.to_numpy()))
    )

    lines = [f"CONDITIONAL (execution-FE) MODEL — deviation run, seed {SEED}",
             "reason: frozen pooled-logit shuffle placebo failed (answer-level "
             "composition); estimator repaired to within-answer conditional logit"]
    rows = []
    for name, xcol in [("M1", "ranked_in_cc"), ("M2", "z_log_rank"),
                       ("M3", "premium_or_strong")]:
        or_ = fit_cl(pool, xcol)
        ci = boot_cl(pool, xcol, rng)
        or_sh = fit_cl(shuffled, xcol)
        ci_sh = boot_cl(shuffled, xcol, rng)
        d = informative(pool.dropna(subset=[xcol]))
        rows.append({
            "model": name, "n_rows": len(d),
            "n_answers": d["discovery_execution_id"].nunique(),
            "n_domains": d["domain"].nunique(),
            "or": round(or_, 3), "ci90_lo": round(ci[0], 3),
            "ci90_hi": round(ci[1], 3), "sesoi": SESOI[name],
            "verdict": verdict(or_, ci, SESOI[name]),
            "shuffle_or": round(or_sh, 3),
            "shuffle_ci": f"{ci_sh[0]:.3f}-{ci_sh[1]:.3f}",
            "shuffle_null": ci_sh[0] <= 1.0 <= ci_sh[1],
        })
    res = pd.DataFrame(rows)
    ok = bool(res["shuffle_null"].all())
    lines.append(f"shuffle placebo null on all models: {'PASS' if ok else 'FAIL — STOP'}")
    lines.append("")
    lines.append(res.to_string(index=False))
    res.to_csv(RESULTS / "conditional_model_results.csv", index=False)
    (RESULTS / "conditional_model_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
