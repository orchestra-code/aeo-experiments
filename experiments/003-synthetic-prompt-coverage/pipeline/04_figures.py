"""Stage 04 — watermarked figures (spec §8) -> figures/*.{svg,png}.

F1  brand mention share: human panel bars + synthetic-arm dot markers
    (the sampling-frame chart — do synthetic panels see the same market?)
F2  ECDF of pairwise brand-set Jaccard: hum baseline vs each cross:hum|arm
F3  same for cited domains
F4  anchor bias: bose & anker share across the four panels (H3 carrier)
"""

from __future__ import annotations

import importlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import ALPHA, ANCHORS, CONTRAST_ARM, FIGURES, PRIMARY_ARM, SYNTH_ARMS, load_responses

from aeo_research.plotting import CATEGORICAL, save_figure, theme
from aeo_research.stats import wilson_interval

model_stage = importlib.import_module("03_model")

ARM_LABELS = {
    "hum": "Human prompts (survey)",
    "spy_a": "Spyglasses panel — Bose anchor",
    "spy_b": "Spyglasses panel — Soundcore anchor",
    "neu": "Neutral generator panel",
}
ARM_COLORS = {
    "hum": CATEGORICAL[0],
    "spy_a": CATEGORICAL[1],
    "spy_b": CATEGORICAL[2],
    "neu": CATEGORICAL[3],
}


def f1_share_dotplot(hp: pd.DataFrame) -> None:
    hum = hp[hp["arm"] == PRIMARY_ARM]
    brands = sorted({b for s in hum["brand_set"] for b in s})
    hum_share = pd.Series(
        {b: hum["brand_set"].map(lambda s, b=b: b in s).mean() for b in brands}
    ).sort_values()
    top = hum_share.tail(12)
    n = len(hum)
    lo, hi = wilson_interval((top * n).round().astype(int), n, alpha=ALPHA)

    fig, ax = plt.subplots(figsize=(8.5, 6))
    y = np.arange(len(top))
    ax.barh(y, top * 100, color=ARM_COLORS["hum"], alpha=0.85,
            label=ARM_LABELS["hum"])
    ax.errorbar(
        top * 100, y, xerr=[(top - lo) * 100, (hi - top) * 100],
        fmt="none", ecolor="#333333", capsize=3, lw=1,
    )
    markers = {"spy_a": "o", "spy_b": "s", "neu": "D"}
    for arm in SYNTH_ARMS:
        sub = hp[hp["arm"] == arm]
        share = [sub["brand_set"].map(lambda s, b=b: b in s).mean() * 100 for b in top.index]
        ax.scatter(share, y, marker=markers[arm], s=55, zorder=3,
                   color=ARM_COLORS[arm], edgecolor="white", linewidth=0.8,
                   label=ARM_LABELS[arm])
    ax.set_yticks(y, [b.title() for b in top.index])
    ax.set_xlabel("Share of responses mentioning the brand (%)")
    ax.set_title("Do synthetic prompt panels see the market humans see?")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    save_figure(fig, FIGURES, "share-dotplot")


def ecdf_vs_hum(pairs: pd.DataFrame, family: str, title: str, name: str) -> None:
    conds = {f"between:{PRIMARY_ARM}": ("Human vs human (baseline)", ARM_COLORS["hum"])}
    for arm in SYNTH_ARMS:
        conds[model_stage.cross_cond(arm)] = (
            f"Human vs {ARM_LABELS[arm].lower()}", ARM_COLORS[arm]
        )
    fig, ax = plt.subplots(figsize=(8, 5))
    for cond, (label, color) in conds.items():
        vals = pairs.loc[pairs["condition"] == cond, family].dropna().sort_values()
        if vals.empty:
            continue
        ax.plot(
            vals, np.linspace(0, 1, len(vals)), drawstyle="steps-post",
            color=color, lw=2, label=label,
        )
    ax.set_xlabel(f"Pairwise Jaccard overlap ({family.replace('_', ' ')})")
    ax.set_ylabel("Cumulative share of pairs")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8)
    save_figure(fig, FIGURES, name)


def f4_anchor_bias(hp: pd.DataFrame) -> None:
    anchors = list(ANCHORS.values())
    arms = [PRIMARY_ARM, *SYNTH_ARMS]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    width = 0.8 / len(arms)
    x = np.arange(len(anchors))
    for k, arm in enumerate(arms):
        sub = hp[hp["arm"] == arm]
        share = [sub["brand_set"].map(lambda s, b=b: b in s).mean() * 100 for b in anchors]
        ax.bar(x + k * width, share, width, color=ARM_COLORS[arm], label=ARM_LABELS[arm])
    ax.set_xticks(x + width * (len(arms) - 1) / 2, [a.title() for a in anchors])
    ax.set_ylabel("Share of responses mentioning the brand (%)")
    ax.set_title("Does a brand-anchored panel inflate its own brand?")
    ax.legend(frameon=False, fontsize=8)
    save_figure(fig, FIGURES, "anchor-bias")


def main() -> None:
    theme()
    df = load_responses().reset_index(drop=True)
    pairs = model_stage.build_pairs(df)
    hp = df[df["arm"] != CONTRAST_ARM]

    f1_share_dotplot(hp)
    ecdf_vs_hum(
        pairs, "brands",
        "Synthetic-vs-human overlap against the human-vs-human baseline",
        "brand-jaccard-ecdf",
    )
    ecdf_vs_hum(
        pairs, "domains",
        "Cited-source overlap: synthetic panels vs the human baseline",
        "domain-jaccard-ecdf",
    )
    f4_anchor_bias(hp)
    print(f"figures -> {FIGURES}")


if __name__ == "__main__":
    main()
