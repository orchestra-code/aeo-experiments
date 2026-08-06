"""Exploratory (post-hoc) — where the residual share gap lives -> results/ + figures.

Added 2026-08-06 AFTER the pre-registered results were computed and logged.
Nothing here changes an H1/H2/H3' verdict (results/model_summary.txt is the
record); this is the interpretation layer, labelled per the 9x convention.

The pre-registered result is a dissociation: mat is exchangeable with the
human panel at the response level (H1 brands -0.001, H3' NULL in both
qualifying strata) yet still misses the human share vector by 8.9 points
(H2 REAL, band 0.05). Three questions about that residual:

A. **Where does it live?** Per-brand decomposition of the H2 basket, the
   stratified-vs-unstratified flag error split, and a check on the obvious
   suspect: human prompts may name brands, synthetic ones cannot.
B. **Does conditioning on sub-intent close it?** The commercial framing is
   "a client names its sub-intents, we generate prompts for those". So
   compare human and synthetic prompts that CARRY THE SAME FLAG, in share
   units rather than H3's Jaccard.
C. **Pool or consistency?** Panel share pools a binary per response. Split
   it: how many prompts EVER surface a brand (pool membership) vs how
   consistently they do (rate across the 5 runs). Includes the human
   panel's own run-to-run stability, which bounds what any panel can match.

Figures: F5 pool-vs-consistency (the carrier for "the pool transfers, the
consistency does not"), F6 conditioning-mad (conditioning on sub-intent
does not shrink the gap).
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import (
    ALPHA,
    CONTRAST_ARM,
    FIGURES,
    H3P_MIN_PROMPTS,
    N_BOOT,
    PRIMARY_ARM,
    PROMPTS_CSV,
    RESULTS,
    SEED,
    SHARE_FLOOR,
    SYNTH_ARMS,
    load_responses,
)
from flags import FLAGS, STRATIFY_FLAGS

from aeo_research.plotting import CATEGORICAL, GRID, INK_MUTED, save_figure, theme

ARM_LABELS = {
    "hum": "Human prompts (survey)",
    "mat": "Stratified scenario panel",
    "neu2": "Unstratified scenario panel",
}
ARM_COLORS = {"hum": CATEGORICAL[0], "mat": CATEGORICAL[1], "neu2": CATEGORICAL[3]}

#: str.title() mangles initialisms ("Jbl"). Override the ones that matter.
BRAND_LABELS = {"jbl": "JBL", "jlab": "JLab"}


def brand_label(b: str) -> str:
    return BRAND_LABELS.get(b, b.title())

#: Apple-ecosystem terms. NOT one of the 15 frozen flags — synthetic panels
#: are brand-name-free by construction, so this tests a structural asymmetry
#: between the arms rather than a sub-intent difference.
ECOSYSTEM = r"\b(iphone|ipad|macbook|apple|airpod|ios)\b"


def flagged_prompts() -> pd.DataFrame:
    p = pd.read_csv(PROMPTS_CSV)
    low = p["text"].str.lower()
    for f, pat in FLAGS.items():
        p[f] = low.str.contains(pat, regex=True)
    p["f_apple_ecosystem"] = low.str.contains(ECOSYSTEM, regex=True)
    return p


def brand_share(df: pd.DataFrame, brand: str) -> float:
    return df["brand_set"].map(lambda s: brand in s).mean()


def basket_of(hum: pd.DataFrame) -> list[str]:
    brands = sorted({b for s in hum["brand_set"] for b in s})
    return [b for b in brands if brand_share(hum, b) >= SHARE_FLOOR]


def prompt_share_matrix(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """One row per prompt, one column per brand = share of that prompt's runs
    mentioning the brand. Prompts are the clustering unit, as in 03_model."""
    g = df.groupby("item_id")["brand_set"]
    return np.array([[s.map(lambda x, b=b: b in x).mean() for b in cols] for _, s in g])


def boot_mad(mats: dict[str, np.ndarray], seed: int) -> tuple[float, float, float]:
    """Cluster bootstrap of the mean absolute share difference: resample
    prompts within each arm independently (arms are independent panels)."""
    rng = np.random.default_rng(seed)
    obs = {a: m.mean(axis=0) for a, m in mats.items()}
    observed = float(np.abs(obs["synth"] - obs["hum"]).mean())
    draws = np.empty(N_BOOT)
    for k in range(N_BOOT):
        s = {a: m[rng.integers(0, len(m), size=len(m))].mean(axis=0)
             for a, m in mats.items()}
        draws[k] = np.abs(s["synth"] - s["hum"]).mean()
    lo, hi = np.quantile(draws, [ALPHA / 2, 1 - ALPHA / 2])
    return observed, float(lo), float(hi)


# --------------------------------------------------------------- section A


def section_a(hp: pd.DataFrame, prompts: pd.DataFrame, out: list[str]) -> list[str]:
    out.append("## A. Where the residual lives\n")
    hum = hp[hp["arm"] == PRIMARY_ARM]
    basket = basket_of(hum)

    tab = pd.DataFrame(
        {a: {b: brand_share(hp[hp["arm"] == a], b) for b in basket}
         for a in [PRIMARY_ARM, *SYNTH_ARMS]}
    )
    for a in SYNTH_ARMS:
        tab[f"{a}-hum"] = tab[a] - tab[PRIMARY_ARM]
    out.append("Per-brand share over the H2 basket:\n")
    out.append(tab.round(3).to_string())

    dev = tab["mat-hum"].abs()
    top = dev.idxmax()
    out.append(
        f"\n{top.title()} alone is {dev[top] / dev.sum():.0%} of mat's total "
        f"absolute deviation (MAD {dev.mean():.4f})."
    )

    # Stratified vs unstratified flag error.
    unstrat = [f for f in FLAGS if f not in STRATIFY_FLAGS]
    out.append("\nMean |flag-prevalence delta| vs the human panel:\n")
    rows = []
    hp_pr = prompts[prompts["arm"] == PRIMARY_ARM]
    for arm in SYNTH_ARMS:
        a = prompts[prompts["arm"] == arm]
        rows.append(dict(
            arm=arm,
            stratified_6=np.mean([abs(a[f].mean() - hp_pr[f].mean()) for f in STRATIFY_FLAGS]),
            unstratified_9=np.mean([abs(a[f].mean() - hp_pr[f].mean()) for f in unstrat]),
        ))
    err = pd.DataFrame(rows).set_index("arm")
    out.append(err.round(3).to_string())
    out.append(
        "\nThe manipulation worked precisely where it was applied and bought "
        "nothing elsewhere. One flag dominates the unstratified column: mat "
        f"emits comfort language in {prompts[prompts.arm=='mat']['f_comfort'].mean():.0%} "
        f"of prompts vs the human panel's {hp_pr['f_comfort'].mean():.0%}. "
        "Excluding it, the two panels are effectively tied on the "
        "unstratified flags — the honest statement is that constraining six "
        "dimensions did not improve the other nine, not that it degraded them."
    )

    # Structural asymmetry: human prompts may name brands, synthetic cannot.
    out.append("\n### Is the Apple gap a brand-naming artifact? No.\n")
    eco_ids = set(prompts[prompts["f_apple_ecosystem"]]["item_id"])
    hum_eco = hum[hum["item_id"].isin(eco_ids)]
    hum_noeco = hum[~hum["item_id"].isin(eco_ids)]
    n_eco = {a: prompts[(prompts.arm == a) & prompts.f_apple_ecosystem].shape[0]
             for a in [PRIMARY_ARM, *SYNTH_ARMS]}
    out.append(f"Prompts naming the Apple ecosystem, by arm: {n_eco}")
    out.append(
        f"hum apple share | naming prompts: {brand_share(hum_eco, 'apple'):.3f} "
        f"(n={hum_eco.item_id.nunique()} prompts); "
        f"| other prompts: {brand_share(hum_noeco, 'apple'):.3f} "
        f"(n={hum_noeco.item_id.nunique()})"
    )
    mad_all = np.mean([abs(brand_share(hp[hp.arm == "mat"], b) - brand_share(hum, b))
                       for b in basket])
    mad_noeco = np.mean([abs(brand_share(hp[hp.arm == "mat"], b) - brand_share(hum_noeco, b))
                         for b in basket])
    out.append(
        f"\nDropping every brand-naming human prompt moves mat's H2 MAD "
        f"{mad_all:.4f} -> {mad_noeco:.4f}. The residual is a property of what "
        "human phrasings ASK FOR, not of what they name."
    )
    return basket


# --------------------------------------------------------------- section B


def section_b(hp: pd.DataFrame, prompts: pd.DataFrame, out: list[str]) -> pd.DataFrame:
    out.append("\n\n## B. Does conditioning on sub-intent close the gap?\n")
    out.append(
        "H3' answers this in Jaccard; this restates it in share units. If a\n"
        "client names its sub-intents and we generate prompts for those, the\n"
        "relevant comparison is human vs synthetic prompts carrying the SAME\n"
        "flag — the panel mix is then given, not estimated.\n"
    )
    flags = prompts.set_index("item_id")[list(FLAGS)]
    joined = hp.join(flags, on="item_id")

    rows = []
    for flag in FLAGS:
        sub = joined[joined[flag]]
        hum, mat = sub[sub.arm == PRIMARY_ARM], sub[sub.arm == "mat"]
        if hum.item_id.nunique() < H3P_MIN_PROMPTS or mat.item_id.nunique() < H3P_MIN_PROMPTS:
            continue
        basket = basket_of(hum)
        cols = sorted(basket)
        mats = {"hum": prompt_share_matrix(hum, cols), "synth": prompt_share_matrix(mat, cols)}
        mad, lo, hi = boot_mad(mats, SEED)
        obs_h = mats["hum"].mean(axis=0)
        obs_m = mats["synth"].mean(axis=0)
        tau = pd.Series(obs_m, index=cols).corr(pd.Series(obs_h, index=cols), method="kendall")
        rows.append(dict(flag=flag, n_hum=hum.item_id.nunique(), n_mat=mat.item_id.nunique(),
                         basket=len(cols), mad=mad, lo=lo, hi=hi, rank_tau=tau))
    tab = pd.DataFrame(rows).set_index("flag")
    out.append(tab.round(3).to_string())
    out.append(
        "\nConditioning does NOT shrink the gap: the within-sub-intent MADs sit\n"
        "at or above the unconditional 0.089. The H2 failure is therefore not\n"
        "primarily a mix artifact — something about synthetic phrasing shifts\n"
        "the proportions in a consistent direction within every stratum."
    )
    return tab


# --------------------------------------------------------------- section C


def decompose(df: pd.DataFrame, brands: list[str]) -> pd.DataFrame:
    """Split panel share into pool membership vs consistency."""
    out = {}
    for b in brands:
        hit = df.assign(h=df["brand_set"].map(lambda s, b=b: b in s))
        per_prompt = hit.groupby("item_id")["h"].mean()
        ever = per_prompt > 0
        out[b] = dict(
            resp_share=hit["h"].mean(),
            ever=ever.mean(),
            always=(per_prompt == 1).mean(),
            rate_given_ever=per_prompt[ever].mean() if ever.any() else np.nan,
            pct_prompts_unstable=((per_prompt > 0) & (per_prompt < 1)).mean(),
        )
    return pd.DataFrame(out).T


def section_c(hp: pd.DataFrame, prompts: pd.DataFrame, basket: list[str],
              out: list[str]) -> pd.DataFrame:
    out.append("\n\n## C. Pool membership or consistency?\n")
    out.append(
        "Panel share pools a binary per response, so a gap can mean either\n"
        "'fewer prompts surface the brand at all' (pool) or 'they surface it\n"
        "less consistently across the 5 runs' (consistency). These are very\n"
        "different claims commercially.\n"
    )
    flags = prompts.set_index("item_id")[list(FLAGS)]
    joined = hp.join(flags, on="item_id")

    trav = joined[joined["f_travel_context"]]
    hum_d = decompose(trav[trav.arm == PRIMARY_ARM], basket)
    mat_d = decompose(trav[trav.arm == "mat"], basket)
    out.append("Travel sub-intent — human panel:\n")
    out.append(hum_d.round(3).to_string())
    out.append("\nTravel sub-intent — stratified panel:\n")
    out.append(mat_d.round(3).to_string())
    out.append(
        "\n'ever' agrees closely across arms while 'always' and "
        "'rate_given_ever' diverge: the panels broadly agree on WHICH brands "
        "belong to the sub-intent and disagree on HOW OFTEN they come back."
    )

    # The human panel's own run-to-run stability bounds what anything can match.
    hum_all = hp[hp["arm"] == PRIMARY_ARM]
    tail = [b for b in sorted({x for s in hum_all["brand_set"] for x in s})
            if b not in basket and brand_share(hum_all, b) >= 0.02]
    full = decompose(hum_all, basket + tail)
    full["tier"] = ["head"] * len(basket) + ["tail"] * len(tail)
    out.append("\n### The human panel's own stability (the noise floor)\n")
    out.append(full.round(3).to_string())
    out.append(
        "\nNo tail brand is returned by any meaningful share of human prompts "
        "in all five runs. Tail instability is a property of the medium, not "
        "of synthetic panels — and mid-frequency head brands are barely more "
        "stable: a share of 0.45 that flips run-to-run within most prompts is "
        "not a stable brand fact being missed, it is a coin flip being averaged."
    )
    return full


# ------------------------------------------------------------------ figures


def f5_pool_vs_consistency(hp: pd.DataFrame, prompts: pd.DataFrame,
                           basket: list[str]) -> None:
    flags = prompts.set_index("item_id")[list(FLAGS)]
    trav = hp.join(flags, on="item_id")
    trav = trav[trav["f_travel_context"]]
    hum_d = decompose(trav[trav.arm == PRIMARY_ARM], basket)
    mat_d = decompose(trav[trav.arm == "mat"], basket)
    order = hum_d.sort_values("resp_share", ascending=True).index.tolist()

    fig, axes = plt.subplots(1, 2, figsize=(10, 5), sharey=True)
    y = np.arange(len(order))
    for ax, col, title in [
        (axes[0], "ever", "Pool: prompts surfacing the brand\nat least once in 5 runs"),
        (axes[1], "always", "Consistency: prompts surfacing it\nin all 5 runs"),
    ]:
        ax.barh(y - 0.2, [hum_d.loc[b, col] * 100 for b in order], height=0.4,
                color=ARM_COLORS["hum"], label=ARM_LABELS["hum"])
        ax.barh(y + 0.2, [mat_d.loc[b, col] * 100 for b in order], height=0.4,
                color=ARM_COLORS["mat"], label=ARM_LABELS["mat"])
        ax.set_xlim(0, 100)
        ax.set_xlabel("% of prompts")
        ax.set_title(title, fontsize=10)
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_yticks(y, [brand_label(b) for b in order])
    axes[0].legend(frameon=False, fontsize=8, loc="lower right",
                   bbox_to_anchor=(1.0, -0.02))
    fig.suptitle("The pool transfers. The consistency does not.", y=0.99)
    save_figure(fig, FIGURES, "pool-vs-consistency")


def f6_conditioning_mad(within: pd.DataFrame, uncond: float) -> None:
    labels = ["Unconditional\n(pre-registered H2)"] + [
        f"{f.replace('f_', '').replace('_', ' ')}\n"
        f"(n={int(r.n_hum)} hum / {int(r.n_mat)} mat)"
        for f, r in within.iterrows()
    ]
    vals = [uncond] + within["mad"].tolist()
    los = [np.nan] + within["lo"].tolist()
    his = [np.nan] + within["hi"].tolist()

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    x = np.arange(len(vals))
    colors = [ARM_COLORS["hum"]] + [ARM_COLORS["mat"]] * len(within)
    ax.bar(x, vals, color=colors, width=0.6)
    for xi, v, lo, hi in zip(x, vals, los, his):
        if not np.isnan(lo):
            ax.plot([xi, xi], [lo, hi], color=INK_MUTED, lw=1.4)
    ax.axhline(0.05, color=INK_MUTED, ls="--", lw=1.2)
    ax.annotate("equivalence band (0.05)", (len(vals) - 0.45, 0.052),
                ha="right", fontsize=8, color=INK_MUTED)
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("Mean absolute brand-share difference")
    ax.set_title("Holding sub-intent fixed does not close the share gap")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    save_figure(fig, FIGURES, "conditioning-mad")


# --------------------------------------------------------------------- main


def main() -> None:
    theme()
    prompts = flagged_prompts()
    hp = load_responses()
    hp = hp[hp["arm"] != CONTRAST_ARM]

    out = [
        "# Experiment 005 — exploratory: where the residual share gap lives",
        "",
        "**Post-hoc, not pre-registered** (9x convention). Added 2026-08-06",
        "after the pre-registered results were computed and logged; nothing",
        "here changes an H1/H2/H3' verdict — `results/model_summary.txt` is",
        "the record. Generated by `pipeline/91_subintent_residual.py`.",
        "",
    ]

    basket = section_a(hp, prompts, out)
    within = section_b(hp, prompts, out)
    section_c(hp, prompts, basket, out)

    hum = hp[hp["arm"] == PRIMARY_ARM]
    uncond = float(np.mean([abs(brand_share(hp[hp.arm == "mat"], b) - brand_share(hum, b))
                            for b in basket]))
    f5_pool_vs_consistency(hp, prompts, basket)
    f6_conditioning_mad(within, uncond)

    out.append(
        "\n\n## What this layer supports\n\n"
        "A sub-intent-matched synthetic panel is a defensible instrument for\n"
        "**which brands belong to a use case, and roughly in what order**. It\n"
        "is not one for **what percent of the time** — and part of that metric\n"
        "is noise the human panel does not clear against itself. The tail is\n"
        "unstable for every panel, human included.\n\n"
        "Figures: `pool-vs-consistency` (F5), `conditioning-mad` (F6)."
    )
    path = RESULTS / "exploratory_subintent_residual.md"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")
    print(f"figures -> {FIGURES}")


if __name__ == "__main__":
    main()
