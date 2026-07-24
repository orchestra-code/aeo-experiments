"""Exploratory (NOT pre-registered): how stable is the ORDER of ChatGPT's
brand recommendations, separate from set membership?

Prompted by a reader question after publication. "Rank" is the order of
first mention in the answer text (a proxy — answers are prose, not explicit
rankings). For each pair of runs we compute Kendall's tau over the
INTERSECTION of the two brand lists (>=3 shared brands), making the
statistic order-only, conditional on membership — the churn the set-Jaccard
results already measure is deliberately excluded. Inference: prompt-level
cluster bootstrap, 90% CIs, seed as frozen.

Outputs:
  results/rank_stability.md
  figures/rank-tau-ecdf       ECDF of pairwise tau by condition
  figures/top-slot-agreement  first-mentioned-brand agreement vs chance
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import FIGURES, N_BOOT, RESULTS, SEED, load_responses
from scipy.stats import kendalltau

from aeo_research.plotting import CATEGORICAL, INK_MUTED, save_figure, theme

MIN_SHARED = 3
COND_COLORS = {"within": CATEGORICAL[0], "between": CATEGORICAL[1]}
COND_LABELS = {
    "within": "Same prompt, repeated runs",
    "between": "Different prompts, same intent",
}


def pair_stats(la: list[str], lb: list[str]):
    rb = {b: i for i, b in enumerate(lb)}
    shared = [b for b in la if b in rb]
    top = (la[0] == lb[0]) if (la and lb) else None
    conc2 = None
    if len(shared) == 2:
        # excluded from tau, but their single order comparison is checkable:
        # concordant (same relative order in both answers) vs chance 50%
        ra = {b: i for i, b in enumerate(la)}
        conc2 = (ra[shared[0]] < ra[shared[1]]) == (rb[shared[0]] < rb[shared[1]])
    if len(shared) < MIN_SHARED:
        return None, len(shared), top, conc2
    t, _ = kendalltau(list(range(len(shared))), [rb[b] for b in shared])
    return t, len(shared), top, conc2


def build_pairs(hp: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cols = ["a", "b", "tau", "n_shared", "top", "conc2"]
    out = {}
    rows = []
    for item, sub in hp.groupby("item_id"):
        ls = list(sub["blist"])
        for i in range(len(ls)):
            for j in range(i + 1, len(ls)):
                rows.append((item, item, *pair_stats(ls[i], ls[j])))
    out["within"] = pd.DataFrame(rows, columns=cols)

    rows = []
    for _, sub in hp.groupby("wave"):
        sub = sub.reset_index(drop=True)
        ids = sub["item_id"].to_numpy()
        ls = list(sub["blist"])
        for i in range(len(sub)):
            for j in range(i + 1, len(sub)):
                if ids[i] != ids[j]:
                    rows.append((ids[i], ids[j], *pair_stats(ls[i], ls[j])))
    out["between"] = pd.DataFrame(rows, columns=cols)
    return out


def boot_mean(df: pd.DataFrame, col: str, rng: np.random.Generator):
    d = df.dropna(subset=[col]).copy()
    d[col] = d[col].astype(float)
    obs = d[col].mean()
    clusters = pd.unique(pd.concat([d["a"], d["b"]]))
    draws = []
    for _ in range(N_BOOT):
        take = set(rng.choice(clusters, len(clusters)))
        s = d[d["a"].isin(take) & d["b"].isin(take)]
        if len(s):
            draws.append(s[col].mean())
    lo, hi = np.quantile(draws, [0.05, 0.95])
    return obs, lo, hi


def main() -> None:
    theme()
    rng = np.random.default_rng(SEED)
    df = load_responses().reset_index(drop=True)
    hp = df[df["intent"] == "headphones"].copy()
    hp["blist"] = hp["brands"].fillna("").str.split(r"\|").map(
        lambda x: [b for b in x if b]
    )
    pairs = build_pairs(hp)

    first = hp["blist"].map(lambda x: x[0] if x else None).dropna()
    p_first = first.value_counts(normalize=True)
    chance_top = float((p_first**2).sum())

    lines = [
        "# Exploratory: rank stability of first-mention brand order",
        "",
        f"Kendall's tau over shared brands (>= {MIN_SHARED}), prompt-cluster",
        f"bootstrap 90% CIs (n_boot={N_BOOT}, seed={SEED}). NOT pre-registered;",
        "computed post-publication in response to a reader question.",
        "",
    ]
    stats = {}
    for cond, dfp in pairs.items():
        d = dfp.dropna(subset=["tau"])
        tau, tlo, thi = boot_mean(dfp, "tau", rng)
        top, plo, phi = boot_mean(dfp, "top", rng)
        stats[cond] = dict(tau=tau, d=d, top=top)
        lines += [
            f"## {COND_LABELS[cond]}",
            f"- pairs with >= {MIN_SHARED} shared brands: {len(d)}/{len(dfp)}"
            f" ({len(d) / len(dfp):.0%}); mean shared {dfp['n_shared'].mean():.2f}",
            f"- mean Kendall tau = {tau:+.3f} [{tlo:+.3f}, {thi:+.3f}]",
            f"- perfect agreement (tau=1): {(d['tau'] > 0.999).mean():.1%};"
            f" zero-or-negative: {(d['tau'] <= 0).mean():.1%};"
            f" full reversal: {(d['tau'] < -0.999).mean():.1%}",
            f"- same first-mentioned brand: {top:.1%} [{plo:.1%}, {phi:.1%}]",
            "",
        ]
    lines += [
        "## Chance baseline",
        f"- top-slot agreement from the empirical first-brand mix: {chance_top:.1%}",
        f"- most common opener: {p_first.index[0]} ({p_first.iloc[0]:.1%} of answers)",
        "",
        "## Robustness checks (reader-raised selection concerns)",
        "",
    ]
    # (a) The excluded 2-shared pairs: is the dropped tail chaotic?
    for cond, dfp in pairs.items():
        two = dfp[dfp["n_shared"] == 2]
        by_ns = (
            dfp.dropna(subset=["tau"]).groupby("n_shared")["tau"]
            .mean().round(3).to_dict()
        )
        lines += [
            f"- {COND_LABELS[cond]}: excluded pairs with exactly 2 shared brands"
            f" (n={len(two)}) are concordant {two['conc2'].mean():.1%}"
            " (chance 50%) — less ordered than included pairs, not chaotic;"
            f" mean tau by shared-set size {by_ns}",
        ]
    # (b) Is the zero-or-negative within-prompt mass concentrated?
    d = pairs["within"].dropna(subset=["tau"])
    per = d.groupby("a")["tau"].mean()
    neg_pairs = d[d["tau"] <= 0]
    lines += [
        f"- within-prompt zero-or-negative pairs ({len(neg_pairs)}) are spread"
        f" across {neg_pairs['a'].nunique()} prompts; prompts whose MEAN"
        f" within-prompt tau <= 0: {(per <= 0).sum()} of {len(per)};"
        f" per-prompt mean tau 10th pct {per.quantile(0.10):+.2f},"
        f" median {per.median():+.2f}",
        "",
    ]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "rank_stability.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    # F: ECDF of tau by condition
    fig, ax = plt.subplots(figsize=(8, 5))
    for cond, dfp in pairs.items():
        vals = dfp["tau"].dropna().sort_values()
        ax.plot(
            vals, np.linspace(0, 1, len(vals)), drawstyle="steps-post",
            color=COND_COLORS[cond], lw=2, label=COND_LABELS[cond],
        )
    ax.axvline(0, color=INK_MUTED, lw=1, ls="--")
    ax.set_xlabel("Kendall's tau over shared brands (order agreement)")
    ax.set_ylabel("Cumulative share of pairs")
    ax.set_title("Brand order agrees far more than chance, even across phrasings")
    ax.legend(frameon=False, loc="upper left")
    save_figure(fig, FIGURES, "rank-tau-ecdf")

    # F: top-slot agreement vs chance
    fig, ax = plt.subplots(figsize=(7, 4.8))
    conds = ["within", "between"]
    vals = [stats[c]["top"] * 100 for c in conds]
    ax.bar(
        np.arange(2), vals, 0.55,
        color=[COND_COLORS[c] for c in conds],
    )
    ax.axhline(chance_top * 100, color=INK_MUTED, lw=1.5, ls="--")
    ax.text(
        1.42, chance_top * 100 + 1, f"chance ({chance_top:.0%})",
        color=INK_MUTED, fontsize=9, ha="right",
    )
    ax.set_xticks(np.arange(2), [COND_LABELS[c] for c in conds])
    ax.set_ylabel("Pairs agreeing on the first-mentioned brand (%)")
    ax.set_title("Rewording resets the top slot to chance; re-running keeps it")
    save_figure(fig, FIGURES, "top-slot-agreement")
    print(f"figures -> {FIGURES}")


if __name__ == "__main__":
    main()
