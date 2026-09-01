"""FROZEN model run — spec §4/§5 at commit 065e37d. Do not edit the models.

M1: logit consulted ~ ranked_in_cc            (all pool rows)      SESOI OR 1.5
M2: logit consulted ~ z(log10 hc_rank)        (ranked rows)        SESOI OR 1.30 per 10× rank
M3: logit consulted ~ premium_or_strong       (AIPVS-scored rows)  SESOI OR 1.5

Uncertainty: cluster-robust SEs by domain + 500-draw domain-cluster bootstrap;
report the wider CI. Gates: H_pos (gov/bar cohort rate ≥3× base), H_pla
(length-parity OR CI covers 1), and a within-execution label-shuffle that must
return null on every model. Seed 20260901. TOST verdicts at 90% CI.

Usage: uv run python experiments/007-site-consultations-observational/pipeline/05_frozen_model.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

EXP = Path(__file__).resolve().parents[1]
INTERIM, RESULTS = EXP / "data" / "interim", EXP / "results"
SEED = 20260901
BOOT_DRAWS = 500
SESOI = {"M1": 1.5, "M2": 1.30, "M3": 1.5}


def fit_or(df: pd.DataFrame, xcol: str):
    """Logit OR with domain-cluster-robust 90% CI."""
    X = sm.add_constant(df[[xcol]].astype(float))
    fit = sm.Logit(df["consulted"].astype(float), X).fit(
        disp=0, cov_type="cluster", cov_kwds={"groups": df["domain"]}
    )
    lo, hi = fit.conf_int(alpha=0.10).loc[xcol]
    return float(np.exp(fit.params[xcol])), (float(np.exp(lo)), float(np.exp(hi)))


def boot_or(df: pd.DataFrame, xcol: str, rng: np.random.Generator):
    """Domain-cluster bootstrap 90% CI for the OR."""
    groups = {d: idx.to_numpy() for d, idx in df.groupby("domain").groups.items()}
    names = np.array(list(groups))
    ors = []
    for _ in range(BOOT_DRAWS):
        take = rng.choice(names, size=len(names), replace=True)
        idx = np.concatenate([groups[d] for d in take])
        sample = df.loc[idx]
        if sample[xcol].nunique() < 2 or sample["consulted"].nunique() < 2:
            continue
        X = sm.add_constant(sample[[xcol]].astype(float))
        try:
            fit = sm.Logit(sample["consulted"].astype(float), X).fit(disp=0)
            ors.append(np.exp(fit.params[xcol]))
        except Exception:  # noqa: BLE001 — rare separation draws are dropped
            continue
    return (float(np.percentile(ors, 5)), float(np.percentile(ors, 95)))


def verdict(or_: float, ci: tuple[float, float], sesoi: float) -> str:
    lo, hi = ci
    inside_band = 1 / sesoi < lo and hi < sesoi
    excludes_1 = lo > 1.0 or hi < 1.0
    beyond_band = hi > sesoi or lo < 1 / sesoi
    if inside_band:
        return "NULL (equivalent)"
    if excludes_1 and beyond_band:
        return "REAL"
    if excludes_1:
        return "NEGLIGIBLE"
    return "INCONCLUSIVE"


def run_models(pool: pd.DataFrame, label: str, rng) -> list[dict]:
    rows = []
    specs = [
        ("M1", pool, "ranked_in_cc"),
        ("M2", pool[pool["ranked_in_cc"] == 1].assign(
            z_log_rank=lambda d: -(d["log10_rank"] - d["log10_rank"].mean())
        ), "z_log_rank"),  # negated: OR per 10× rank IMPROVEMENT
        ("M3", pool[pool["scored"]], "premium_or_strong"),
    ]
    for name, df, xcol in specs:
        or_, robust_ci = fit_or(df, xcol)
        boot_ci = boot_or(df, xcol, rng)
        ci = (min(robust_ci[0], boot_ci[0]), max(robust_ci[1], boot_ci[1]))
        rows.append({
            "run": label, "model": name, "n": len(df),
            "n_domains": df["domain"].nunique(),
            "or": round(or_, 3),
            "ci90_lo": round(ci[0], 3), "ci90_hi": round(ci[1], 3),
            "robust_ci": f"{robust_ci[0]:.3f}-{robust_ci[1]:.3f}",
            "boot_ci": f"{boot_ci[0]:.3f}-{boot_ci[1]:.3f}",
            "sesoi": SESOI[name],
            "verdict": verdict(or_, ci, SESOI[name]) if label == "primary" else "",
        })
    return rows


def main() -> None:
    rng = np.random.default_rng(SEED)
    pool = pd.read_csv(INTERIM / "pool_with_metrics.csv",
                       keep_default_na=False, na_values=[""])
    kinds = json.loads((INTERIM / "domain_kinds.json").read_text())

    pool["consulted"] = pool["consulted"].astype(str).str.lower().eq("true").astype(int)
    pool["ranked_in_cc"] = pool["hc_rank"].notna().astype(int)
    pool["log10_rank"] = np.log10(pool["hc_rank"])
    pool["scored"] = pool["aipvs"].notna()
    pool["premium_or_strong"] = pool["tier_label"].isin(["Premium", "Strong"]).astype(int)
    pool["parity"] = (pool["domain"].str.len() % 2).astype(int)
    pool = pool.reset_index(drop=True)

    lines = [f"FROZEN MODEL RUN — spec 065e37d, seed {SEED}",
             f"pool: {len(pool):,} rows, {pool['domain'].nunique():,} domains, "
             f"{int(pool['consulted'].sum()):,} consulted"]

    # Gates first.
    base = pool["consulted"].mean()
    cohort = pool["domain"].map(kinds).isin(
        ["government_or_courts", "bar_or_professional_association"])
    pos_rate = pool.loc[cohort, "consulted"].mean()
    lines.append(f"H_pos: gov/bar cohort rate {pos_rate:.3%} vs base {base:.3%} "
                 f"= {pos_rate / base:.1f}x (gate ≥3x) -> "
                 f"{'PASS' if pos_rate / base >= 3 else 'FAIL — STOP'}")

    or_pla, ci_pla = fit_or(pool, "parity")
    pla_ok = ci_pla[0] <= 1.0 <= ci_pla[1]
    lines.append(f"H_pla: parity OR {or_pla:.3f} CI90 {ci_pla[0]:.3f}-{ci_pla[1]:.3f} "
                 f"-> {'PASS (null)' if pla_ok else 'FAIL — STOP'}")

    # Shuffle placebo: permute consulted within execution.
    shuffled = pool.copy()
    shuffled["consulted"] = (
        shuffled.groupby("discovery_execution_id")["consulted"]
        .transform(lambda s: rng.permutation(s.to_numpy()))
    )
    results = run_models(pool, "primary", rng) + run_models(shuffled, "shuffle", rng)

    # Audit-D sensitivity: unranked imputed at the graph floor (rank 10M).
    sens = pool.copy()
    sens["log10_rank"] = sens["log10_rank"].fillna(np.log10(10_000_000))
    sens["ranked_in_cc"] = 1
    or_s, ci_s = fit_or(sens.assign(
        z_log_rank=lambda d: -(d["log10_rank"] - d["log10_rank"].mean())
    ), "z_log_rank")
    lines.append(f"Sensitivity (M2, unranked imputed at rank 10M): "
                 f"OR {or_s:.3f} CI90 {ci_s[0]:.3f}-{ci_s[1]:.3f}")

    res = pd.DataFrame(results)
    shuffle_null = all(
        r["ci90_lo"] <= 1.0 <= r["ci90_hi"]
        for r in results if r["run"] == "shuffle"
    )
    lines.append(f"Shuffle placebo null on all models: "
                 f"{'PASS' if shuffle_null else 'FAIL — STOP'}")
    lines.append("")
    lines.append(res.to_string(index=False))

    RESULTS.mkdir(exist_ok=True)
    res.to_csv(RESULTS / "model_results.csv", index=False)
    (RESULTS / "model_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
