"""Stage 03 — pre-registered tests (spec §4/§5) -> results/model_*.{csv,txt}.

Sequence (house rule: positive control FIRST — exit 1 if it fails):
  H_pos  between-prompt within-intent domain overlap >> cross-intent overlap
  H_pla  row-parity placebo split of between-prompt pairs is NULL/NEGLIGIBLE
  H1     TOST: within-prompt vs between-prompt brand-set Jaccard (SESOI 0.10)
  H2     TOST: same for cited-domain Jaccard and grounding-token Jaccard
  levels descriptive between-prompt levels per artifact family
  H3     exploratory: TF-IDF answer-text cosine (no verdict by design)
  robustness: RBO swap, drop-wave-1, dedup duplicate prompts, non-empty
  fan-outs only, across-wave between pairs, dominant-model subset
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from common import (
    ALPHA,
    CONTRAST_INTENT,
    N_BOOT,
    N_PERM,
    PRIMARY_INTENT,
    PROMPTS_CSV,
    RESULTS,
    SEED,
    SESOI,
    load_responses,
)

from aeo_research.overlap import (
    cluster_boot,
    condition_pairs,
    jaccard,
    pair_values,
    permutation_pvalue,
    rbo,
    tfidf_cosine,
)
from aeo_research.stats import Verdict

FAMILIES = {
    "brands": ("brand_set", jaccard),
    "domains": ("domain_set", jaccard),
    "urls": ("url_set", jaccard),
    "grounding_tokens": ("fanout_token_set", jaccard),
}


def build_pairs(df: pd.DataFrame) -> pd.DataFrame:
    pairs = condition_pairs(
        df, primary_intent=PRIMARY_INTENT, contrast_intent=CONTRAST_INTENT
    )
    for family, (col, metric) in FAMILIES.items():
        pairs[family] = pair_values(pairs, list(df[col]), metric)
    ranked = [b.split("|") if b and not pd.isna(b) else [] for b in df["brands"]]
    pairs["brands_rbo"] = pair_values(pairs, ranked, rbo)
    return pairs


def h_pos_gate(df: pd.DataFrame, pairs: pd.DataFrame, rows: list, lines: list) -> bool:
    """Between-prompt (within-intent) vs cross-intent cited-domain overlap."""
    res = cluster_boot(
        pairs.rename(columns={"domains": "value"}),
        contrast=("between_prompt", "cross_intent"),
        alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
    )

    # Permutation test: shuffle intent labels over PROMPTS (wave-1 responses
    # only — the only wave where both intents ran), recompute the same-label
    # minus cross-label mean difference.
    w1 = df[df["wave"] == 1].reset_index(drop=True)
    w1_pairs = []
    domain_sets = list(w1["domain_set"])
    prompts = w1["item_id"].to_numpy()
    for i in range(len(w1)):
        for j in range(i + 1, len(w1)):
            if prompts[i] != prompts[j]:
                w1_pairs.append((i, j, jaccard(domain_sets[i], domain_sets[j])))
    pi = np.array([p[0] for p in w1_pairs])
    pj = np.array([p[1] for p in w1_pairs])
    vals = np.array([p[2] for p in w1_pairs])
    ok = ~np.isnan(vals)
    pi, pj, vals = pi[ok], pj[ok], vals[ok]
    prompt_ids, prompt_codes = np.unique(prompts, return_inverse=True)
    base_labels = (
        pd.Series(w1["intent"].to_numpy()).groupby(prompt_codes).first().to_numpy()
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
         "contrast": "between_prompt - cross_intent", **res.as_dict(),
         "p_perm": p_perm, "passed": passed}
    )
    lines.append(
        f"H_pos (gate): between-within-intent minus cross-intent domain Jaccard = "
        f"{res.estimate:.3f} [{res.lo:.3f}, {res.hi:.3f}], perm p = {p_perm:.4f} -> "
        f"{'PASS' if passed else 'FAIL — STOP, collection/extraction is broken'}"
    )
    return passed


def h_pla(pairs: pd.DataFrame, rows: list, lines: list) -> None:
    between = pairs[pairs["condition"] == "between_prompt"].copy()
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


def tost_family(pairs, family, label, rows, lines, *, sesoi=SESOI) -> None:
    res = cluster_boot(
        pairs.rename(columns={family: "value"}),
        contrast=("within_prompt", "between_prompt"),
        sesoi=sesoi, alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
    )
    rows.append({"test": label, "family": family,
                 "contrast": "within - between", **res.as_dict()})
    lines.append(
        f"{label} ({family}): within-between = {res.estimate:.3f} "
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


def h3_text(df, pairs, rows, lines) -> None:
    sims = tfidf_cosine(list(df["answer_text"].fillna("")))
    pairs = pairs.copy()
    pairs["value"] = sims[pairs["i"], pairs["j"]]
    for cond in ("within_prompt", "between_prompt"):
        res = cluster_boot(
            pairs, contrast=(cond, None), alpha=ALPHA, n_boot=N_BOOT, seed=SEED
        )
        rows.append({"test": "H3_text_cosine", "family": "answer_text",
                     "contrast": cond, **res.as_dict()})
        lines.append(
            f"H3 (exploratory) TF-IDF cosine, {cond}: "
            f"{res.estimate:.3f} [{res.lo:.3f}, {res.hi:.3f}]"
        )


def robustness(df, pairs, rows, lines) -> None:
    lines.append("\n-- robustness --")
    # R1: rank-sensitive brand overlap.
    tost_family(pairs, "brands_rbo", "R1_rbo", rows, lines)
    # R2: drop wave 1 (cold start / lexicon-mining wave).
    waves = df["wave"].to_numpy()
    not_w1 = pairs[(waves[pairs["i"]] > 1) & (waves[pairs["j"]] > 1)]
    for fam in ("brands", "domains"):
        tost_family(not_w1, fam, f"R2_no_w1_{fam}", rows, lines)
    # R3: drop duplicate-text prompts.
    prompts = pd.read_csv(PROMPTS_CSV)
    dups = set(prompts.loc[prompts["is_dup"], "item_id"])
    no_dup = pairs[~pairs["cluster_i"].isin(dups) & ~pairs["cluster_j"].isin(dups)]
    tost_family(no_dup, "brands", "R3_dedup_brands", rows, lines)
    # R4: grounding overlap among responses that actually ran fan-outs.
    has_fan = df["n_fanout"].to_numpy() > 0
    fan_pairs = pairs[has_fan[pairs["i"]] & has_fan[pairs["j"]]]
    tost_family(fan_pairs, "grounding_tokens", "R4_nonempty_grounding", rows, lines)
    # R5: day drift — across-wave between-prompt pairs vs same-wave.
    hp = df["intent"].to_numpy() == PRIMARY_INTENT
    rng = np.random.default_rng(SEED)
    idx = np.flatnonzero(hp)
    take = rng.choice(idx, size=(min(30000, len(idx) ** 2), 2))
    take = take[
        (df["item_id"].to_numpy()[take[:, 0]] != df["item_id"].to_numpy()[take[:, 1]])
        & (waves[take[:, 0]] != waves[take[:, 1]])
    ]
    dsets = list(df["domain_set"])
    xwave = pd.DataFrame(
        {
            "condition": "between_xwave",
            "cluster_i": df["item_id"].to_numpy()[take[:, 0]],
            "cluster_j": df["item_id"].to_numpy()[take[:, 1]],
            "value": [jaccard(dsets[i], dsets[j]) for i, j in take],
        }
    )
    res = cluster_boot(xwave, contrast=("between_xwave", None),
                       alpha=ALPHA, n_boot=N_BOOT, seed=SEED)
    rows.append({"test": "R5_between_xwave", "family": "domains",
                 "contrast": "between_xwave level", **res.as_dict()})
    lines.append(
        f"R5 across-wave between-prompt domain level: {res.estimate:.3f} "
        f"[{res.lo:.3f}, {res.hi:.3f}] (compare to same-wave level above)"
    )
    # R6: dominant model subset (drift guard).
    top_model = df["model"].mode().iat[0] if df["model"].notna().any() else None
    if top_model and df["model"].nunique() > 1:
        same_model = df["model"].to_numpy() == top_model
        sub = pairs[same_model[pairs["i"]] & same_model[pairs["j"]]]
        tost_family(sub, "brands", "R6_dominant_model_brands", rows, lines)
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
        f"# Experiment 002 — model results{' (SYNTHETIC)' if synthetic else ''}",
        f"SESOI={SESOI} (absolute Jaccard), alpha={ALPHA}, n_boot={N_BOOT}\n",
    ]

    passed = h_pos_gate(df, pairs, rows, lines)
    if passed:
        h_pla(pairs, rows, lines)
        tost_family(pairs, "brands", "H1", rows, lines)
        tost_family(pairs, "domains", "H2_domains", rows, lines)
        tost_family(pairs, "grounding_tokens", "H2_grounding", rows, lines)
        tost_family(pairs, "urls", "H2b_urls_descriptive", rows, lines)
        for fam in FAMILIES:
            level(pairs, fam, "between_prompt", rows, lines)
            level(pairs, fam, "within_prompt", rows, lines)
        h3_text(df, pairs, rows, lines)
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
