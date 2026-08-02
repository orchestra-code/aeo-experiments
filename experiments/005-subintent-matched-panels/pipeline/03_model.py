"""Stage 03 — pre-registered tests (spec §4/§5) -> results/model_*.{csv,txt}.

Sequence (house rule: positive control FIRST — exit 1 if it fails):
  H_pos  between:hum domain overlap >> cross:coffee|hum overlap (gate)
  H_pla  row-parity placebo split of between:hum pairs is NULL/NEGLIGIBLE
  H1     TOST per synthetic arm: cross:hum|<arm> vs between:hum overlap
         (brands, domains, grounding tokens; SESOI 0.10 absolute Jaccard)
  H2     panel share agreement per synthetic arm: mean absolute per-brand
         mention-share difference vs the human panel (SESOI 0.05) + rank tau
  H3'    matched-stratum exchangeability: for each stratified flag with
         >= H3P_MIN_PROMPTS mat prompts, cross:hum|mat pairs where BOTH
         prompts carry the flag vs between:hum pairs where both carry it
         (TOST, same 0.10 band) — the 003 pilot's analysis, pre-registered
  levels descriptive within/between/cross levels per artifact family
  robustness: RBO swap, drop wave 1, dedup, non-empty fan-outs,
              within-panel repeatability contrast, dominant-model subset
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from common import (
    ALPHA,
    CONTRAST_ARM,
    H3P_MIN_PROMPTS,
    N_BOOT,
    N_PERM,
    PRIMARY_ARM,
    PROMPTS_CSV,
    RESULTS,
    SEED,
    SESOI,
    SESOI_SHARE,
    SHARE_FLOOR,
    SYNTH_ARMS,
    load_responses,
)
from flags import FLAGS, STRATIFY_FLAGS
from scipy import stats as scipy_stats

from aeo_research.overlap import (
    arm_condition_pairs,
    cluster_boot,
    jaccard,
    pair_values,
    permutation_pvalue,
    rbo,
)
from aeo_research.stats import Verdict

FAMILIES = {
    "brands": ("brand_set", jaccard),
    "domains": ("domain_set", jaccard),
    "urls": ("url_set", jaccard),
    "grounding_tokens": ("fanout_token_set", jaccard),
}

BETWEEN_HUM = f"between:{PRIMARY_ARM}"


def cross_cond(arm: str) -> str:
    a, b = sorted((PRIMARY_ARM, arm))
    return f"cross:{a}|{b}"


def build_pairs(df: pd.DataFrame) -> pd.DataFrame:
    pairs = arm_condition_pairs(df)
    for family, (col, metric) in FAMILIES.items():
        pairs[family] = pair_values(pairs, list(df[col]), metric)
    ranked = [b.split("|") if b and not pd.isna(b) else [] for b in df["brands"]]
    pairs["brands_rbo"] = pair_values(pairs, ranked, rbo)
    return pairs


# ------------------------------------------------------------ gate + placebo


def h_pos_gate(df: pd.DataFrame, pairs: pd.DataFrame, rows: list, lines: list) -> bool:
    """Same-intent between-prompt vs cross-intent cited-domain overlap."""
    res = cluster_boot(
        pairs.rename(columns={"domains": "value"}),
        contrast=(BETWEEN_HUM, cross_cond(CONTRAST_ARM)),
        alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
    )

    # Permutation test on wave 1 (the only wave where coffee runs): shuffle
    # hum/coffee arm labels over prompts, recompute same-label minus
    # cross-label mean domain Jaccard.
    w1 = df[(df["wave"] == 1) & df["arm"].isin([PRIMARY_ARM, CONTRAST_ARM])].reset_index(drop=True)
    domain_sets = list(w1["domain_set"])
    prompts = w1["item_id"].to_numpy()
    pair_list = []
    for i in range(len(w1)):
        for j in range(i + 1, len(w1)):
            if prompts[i] != prompts[j]:
                pair_list.append((i, j, jaccard(domain_sets[i], domain_sets[j])))
    pi = np.array([p[0] for p in pair_list])
    pj = np.array([p[1] for p in pair_list])
    vals = np.array([p[2] for p in pair_list])
    ok = ~np.isnan(vals)
    pi, pj, vals = pi[ok], pj[ok], vals[ok]
    _, prompt_codes = np.unique(prompts, return_inverse=True)
    base_labels = (
        pd.Series(w1["arm"].to_numpy()).groupby(prompt_codes).first().to_numpy()
    )

    def diff_for(labels_by_prompt: np.ndarray) -> float:
        lab_i = labels_by_prompt[prompt_codes[pi]]
        lab_j = labels_by_prompt[prompt_codes[pj]]
        same = lab_i == lab_j
        return float(vals[same].mean() - vals[~same].mean())

    observed = diff_for(base_labels)

    def perm_stat(rng: np.random.Generator) -> float:
        return diff_for(rng.permutation(base_labels))

    p_perm = permutation_pvalue(observed, perm_stat, n_perm=N_PERM, seed=SEED)

    passed = res.estimate >= 0.10 and res.lo > 0 and p_perm < 0.05
    rows.append(
        {"test": "H_pos", "family": "domains",
         "contrast": f"{BETWEEN_HUM} - {cross_cond(CONTRAST_ARM)}", **res.as_dict(),
         "p_perm": p_perm, "passed": passed}
    )
    lines.append(
        f"H_pos (gate): between:hum minus cross-intent domain Jaccard = "
        f"{res.estimate:.3f} [{res.lo:.3f}, {res.hi:.3f}], perm p = {p_perm:.4f} -> "
        f"{'PASS' if passed else 'FAIL — STOP, collection/extraction is broken'}"
    )
    return passed


def h_pla(pairs: pd.DataFrame, rows: list, lines: list) -> None:
    between = pairs[pairs["condition"] == BETWEEN_HUM].copy()
    par_i = between["cluster_i"].str[1:].astype(int) % 2
    par_j = between["cluster_j"].str[1:].astype(int) % 2
    between["condition"] = np.where(
        par_i == par_j, "between_same_parity", "between_mixed_parity"
    )
    res = cluster_boot(
        between.rename(columns={"domains": "value"}),
        contrast=("between_same_parity", "between_mixed_parity"),
        sesoi=SESOI, alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
    )
    rows.append({"test": "H_pla", "family": "domains",
                 "contrast": "same-parity - mixed-parity", **res.as_dict()})
    ok = res.verdict in (Verdict.NULL, Verdict.NEGLIGIBLE)
    lines.append(
        f"H_pla (placebo): parity split = {res.estimate:.3f} [{res.lo:.3f}, {res.hi:.3f}] "
        f"-> {res.verdict.name}{'' if ok else '  ** WARNING: placebo not null **'}"
    )


# ------------------------------------------------------------ H1 exchangeability


def tost_contrast(pairs, family, cond_a, cond_b, label, rows, lines, *, sesoi=SESOI) -> None:
    res = cluster_boot(
        pairs.rename(columns={family: "value"}),
        contrast=(cond_a, cond_b),
        sesoi=sesoi, alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
    )
    rows.append({"test": label, "family": family,
                 "contrast": f"{cond_a} - {cond_b}", **res.as_dict()})
    lines.append(
        f"{label} ({family}): {cond_a} - {cond_b} = {res.estimate:.3f} "
        f"[{res.lo:.3f}, {res.hi:.3f}] (n_pairs {res.n_pairs}, NaN {res.n_nan}) "
        f"-> {res.verdict.name}"
    )


def level(pairs, family, condition, rows, lines) -> None:
    res = cluster_boot(
        pairs.rename(columns={family: "value"}),
        contrast=(condition, None), alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
    )
    rows.append({"test": f"level_{condition}", "family": family,
                 "contrast": condition, **res.as_dict()})
    lines.append(
        f"level ({family}, {condition}): {res.estimate:.3f} [{res.lo:.3f}, {res.hi:.3f}]"
    )


# ------------------------------------------------------------ H2/H3 panel shares


def prompt_share_matrix(df_arm: pd.DataFrame, brands: list[str]) -> np.ndarray:
    """P x B matrix: fraction of each prompt's responses mentioning each brand.

    Panel share = column mean (prompts within an arm have equal wave counts,
    so the mean over prompts equals the mean over responses). Bootstrapping a
    prompt resample is then a row-resampled column mean — all waves of a
    drawn prompt travel together by construction.
    """
    grouped = df_arm.groupby("item_id")["brand_set"]
    return np.array([
        [np.mean([b in s for s in sets]) for b in brands]
        for _, sets in grouped
    ])


def boot_share_stats(
    mats: dict[str, np.ndarray], stat_fns: dict[str, callable], n_boot: int, seed: int
) -> dict[str, tuple[float, float, float]]:
    """Cluster bootstrap of panel-share statistics: resample prompts (rows)
    with replacement independently within each arm — arms are independent
    panels by design — and evaluate every statistic on the resulting share
    vectors. Returns name -> (observed, lo, hi)."""
    rng = np.random.default_rng(seed)
    observed_shares = {arm: m.mean(axis=0) for arm, m in mats.items()}
    observed = {name: fn(observed_shares) for name, fn in stat_fns.items()}
    draws = {name: np.empty(n_boot) for name in stat_fns}
    for k in range(n_boot):
        shares = {}
        for arm, m in mats.items():
            idx = rng.integers(0, len(m), size=len(m))
            shares[arm] = m[idx].mean(axis=0)
        for name, fn in stat_fns.items():
            draws[name][k] = fn(shares)
    out = {}
    for name in stat_fns:
        d = draws[name]
        lo, hi = np.quantile(d[~np.isnan(d)], [ALPHA / 2, 1 - ALPHA / 2])
        out[name] = (float(observed[name]), float(lo), float(hi))
    return out


def h2_panel_shares(df: pd.DataFrame, rows: list, lines: list) -> None:
    hp = df[df["arm"] != CONTRAST_ARM]
    hum = hp[hp["arm"] == PRIMARY_ARM]
    all_brands = sorted({b for s in hp["brand_set"] for b in s})
    hum_share = pd.Series(
        {b: hum["brand_set"].map(lambda s, b=b: b in s).mean() for b in all_brands}
    )
    basket = [b for b in all_brands if hum_share[b] >= SHARE_FLOOR]
    lines.append(
        f"\nH2 basket: {len(basket)} brands with human-panel share >= {SHARE_FLOOR:.0%}"
    )
    cols = sorted(basket)
    j = {b: cols.index(b) for b in cols}
    basket_idx = np.array([j[b] for b in basket])
    mats = {arm: prompt_share_matrix(hp[hp["arm"] == arm], cols)
            for arm in (PRIMARY_ARM, *SYNTH_ARMS)}

    stat_fns: dict[str, callable] = {}
    for arm in SYNTH_ARMS:
        stat_fns[f"H2_{arm}"] = (
            lambda s, arm=arm: float(
                np.abs(s[arm][basket_idx] - s[PRIMARY_ARM][basket_idx]).mean()
            )
        )

    results = boot_share_stats(mats, stat_fns, N_BOOT, SEED)

    for arm in SYNTH_ARMS:
        obs, lo, hi = results[f"H2_{arm}"]
        equivalent = hi < SESOI_SHARE
        verdict = (
            Verdict.NULL if equivalent
            else (Verdict.REAL if lo > SESOI_SHARE else Verdict.INCONCLUSIVE)
        )
        tau = scipy_stats.kendalltau(
            mats[PRIMARY_ARM].mean(axis=0)[basket_idx],
            mats[arm].mean(axis=0)[basket_idx],
        ).statistic
        rows.append({"test": f"H2_{arm}", "family": "brand_share",
                     "contrast": f"MAD({arm}, hum) over basket", "estimate": obs,
                     "lo": lo, "hi": hi, "sesoi": SESOI_SHARE,
                     "verdict": verdict.value, "kendall_tau": tau})
        lines.append(
            f"H2 ({arm}): mean |share diff| = {obs:.3f} [{lo:.3f}, {hi:.3f}] "
            f"(one-sided band {SESOI_SHARE}), rank tau = {tau:.3f} -> {verdict.name}"
        )


# ------------------------------------------------------------ H3' matched strata


def h3prime_matched(df: pd.DataFrame, pairs: pd.DataFrame, rows: list, lines: list) -> None:
    """Pre-registered version of the 003 pilot: does sharing a stratified
    sub-intent flag make a synthetic prompt's answer exchangeable with a
    human prompt's? Contrast cross:hum|<arm> both-flag vs between:hum
    both-flag, TOST at the house band. Flags qualify per arm when the arm
    has >= H3P_MIN_PROMPTS prompts carrying the flag (frozen floor)."""
    prompts = pd.read_csv(PROMPTS_CSV)
    low = prompts.set_index("item_id")["text"].str.lower()
    flag_of = {
        f: low.str.contains(FLAGS[f], regex=True) for f in STRATIFY_FLAGS
    }
    lines.append("")
    for arm in SYNTH_ARMS:
        arm_ids = prompts.loc[prompts["arm"] == arm, "item_id"]
        for f in STRATIFY_FLAGS:
            n_arm = int(flag_of[f].loc[arm_ids].sum())
            if n_arm < H3P_MIN_PROMPTS:
                continue
            fi = flag_of[f].loc[pairs["cluster_i"]].to_numpy()
            fj = flag_of[f].loc[pairs["cluster_j"]].to_numpy()
            both = fi & fj
            sub = pd.concat([
                pairs[(pairs["condition"] == BETWEEN_HUM) & both].assign(
                    condition="hum_both"),
                pairs[(pairs["condition"] == cross_cond(arm)) & both].assign(
                    condition="cross_both"),
            ])
            res = cluster_boot(
                sub.rename(columns={"brands": "value"}),
                contrast=("cross_both", "hum_both"),
                sesoi=SESOI, alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
            )
            rows.append({"test": f"H3p_{arm}:{f}", "family": "brands",
                         "contrast": f"matched-{f} cross - matched between:hum",
                         "n_arm_prompts": n_arm, **res.as_dict()})
            lines.append(
                f"H3' ({arm}, {f.removeprefix('f_')}, n={n_arm}): "
                f"{res.estimate:+.3f} [{res.lo:+.3f}, {res.hi:+.3f}] "
                f"-> {res.verdict.name}"
            )


# ------------------------------------------------------------ robustness


def robustness(df, pairs, rows, lines) -> None:
    lines.append("\n-- robustness --")
    # R1: rank-sensitive brand overlap for each H1 contrast.
    for arm in SYNTH_ARMS:
        tost_contrast(pairs, "brands_rbo", cross_cond(arm), BETWEEN_HUM,
                      f"R1_rbo_{arm}", rows, lines)
    # R2: drop wave 1 (lexicon-mining wave).
    waves = df["wave"].to_numpy()
    not_w1 = pairs[(waves[pairs["i"]] > 1) & (waves[pairs["j"]] > 1)]
    for arm in SYNTH_ARMS:
        tost_contrast(not_w1, "brands", cross_cond(arm), BETWEEN_HUM,
                      f"R2_no_w1_{arm}", rows, lines)
    # R3: drop duplicate-text prompts.
    prompts = pd.read_csv(PROMPTS_CSV)
    dups = set(prompts.loc[prompts["is_dup"], "item_id"])
    no_dup = pairs[~pairs["cluster_i"].isin(dups) & ~pairs["cluster_j"].isin(dups)]
    for arm in SYNTH_ARMS:
        tost_contrast(no_dup, "brands", cross_cond(arm), BETWEEN_HUM,
                      f"R3_dedup_{arm}", rows, lines)
    # R4: grounding overlap among responses that actually ran fan-outs.
    has_fan = df["n_fanout"].to_numpy() > 0
    fan_pairs = pairs[has_fan[pairs["i"]] & has_fan[pairs["j"]]]
    for arm in SYNTH_ARMS:
        tost_contrast(fan_pairs, "grounding_tokens", cross_cond(arm), BETWEEN_HUM,
                      f"R4_nonempty_grounding_{arm}", rows, lines)
    # R5: within-panel repeatability — do synthetic prompts have the same
    # run-to-run noise as human prompts? (level contrast, no equivalence claim)
    for arm in SYNTH_ARMS:
        tost_contrast(pairs, "brands", f"within:{arm}", f"within:{PRIMARY_ARM}",
                      f"R5_within_repeat_{arm}", rows, lines)
    # R6: dominant model subset (drift guard).
    top_model = df["model"].mode().iat[0] if df["model"].notna().any() else None
    if top_model and df["model"].nunique() > 1:
        same_model = (df["model"].to_numpy() == top_model)
        sub = pairs[same_model[pairs["i"]] & same_model[pairs["j"]]]
        for arm in SYNTH_ARMS:
            tost_contrast(sub, "brands", cross_cond(arm), BETWEEN_HUM,
                          f"R6_dominant_model_{arm}", rows, lines)
    else:
        lines.append("R6: single model across all waves — no subgroup refit needed")


def main() -> None:
    df = load_responses().reset_index(drop=True)
    synthetic = int(df.get("synthetic", pd.Series([0])).max()) == 1
    if synthetic:
        print("NOTE: modeling a SYNTHETIC frame")

    pairs = build_pairs(df)
    rows: list[dict] = []
    lines: list[str] = [
        f"# Experiment 005 — model results{' (SYNTHETIC)' if synthetic else ''}",
        f"SESOI={SESOI} (absolute Jaccard) / {SESOI_SHARE} (share MAD), "
        f"alpha={ALPHA}, n_boot={N_BOOT}\n",
    ]

    passed = h_pos_gate(df, pairs, rows, lines)
    if passed:
        h_pla(pairs, rows, lines)
        for arm in SYNTH_ARMS:
            for family in ("brands", "domains", "grounding_tokens"):
                tost_contrast(pairs, family, cross_cond(arm), BETWEEN_HUM,
                              f"H1_{arm}", rows, lines)
        h2_panel_shares(df, rows, lines)
        h3prime_matched(df, pairs, rows, lines)
        lines.append("")
        for family in FAMILIES:
            level(pairs, family, BETWEEN_HUM, rows, lines)
            level(pairs, family, f"within:{PRIMARY_ARM}", rows, lines)
            for arm in SYNTH_ARMS:
                level(pairs, family, f"between:{arm}", rows, lines)
                level(pairs, family, cross_cond(arm), rows, lines)
        robustness(df, pairs, rows, lines)

    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(RESULTS / "model_results.csv", index=False)
    summary = "\n".join(lines) + "\n"
    (RESULTS / "model_summary.txt").write_text(summary)
    print(summary)
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
