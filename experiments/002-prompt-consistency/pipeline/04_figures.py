"""Stage 04 — watermarked figures (spec §8) -> figures/*.{svg,png}.

F1  top-brand mention share with Wilson CIs (the SparkToro-comparable chart)
F2  ECDF of pairwise brand-set Jaccard by condition (carries H1)
F3  ECDF of pairwise cited-domain Jaccard by condition (carries H2)
F4  domain citation concentration (share of responses citing each domain)
F5  within-prompt stability by wave gap, annotated with model versions
"""

from __future__ import annotations

import importlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import ALPHA, FIGURES, PRIMARY_INTENT, load_responses

from aeo_research.plotting import CATEGORICAL, save_figure, theme
from aeo_research.stats import wilson_interval

model_stage = importlib.import_module("03_model")

COND_COLORS = {
    "within_prompt": CATEGORICAL[0],
    "between_prompt": CATEGORICAL[1],
    "cross_intent": CATEGORICAL[2],
}
COND_LABELS = {
    "within_prompt": "Same prompt, repeated runs",
    "between_prompt": "Different prompts, same intent",
    "cross_intent": "Different intent",
}


def f1_brand_share(hp: pd.DataFrame) -> None:
    brands = sorted({b for s in hp["brand_set"] for b in s})
    share = pd.Series(
        {b: hp["brand_set"].map(lambda s, b=b: b in s).mean() for b in brands}
    ).sort_values()
    top = share.tail(12)
    n = len(hp)
    lo, hi = wilson_interval((top * n).round().astype(int), n, alpha=ALPHA)

    fig, ax = plt.subplots(figsize=(8, 5.5))
    y = np.arange(len(top))
    ax.barh(y, top * 100, color=CATEGORICAL[0])
    ax.errorbar(
        top * 100, y, xerr=[(top - lo) * 100, (hi - top) * 100],
        fmt="none", ecolor="#333333", capsize=3, lw=1,
    )
    ax.set_yticks(y, [b.title() for b in top.index])
    ax.set_xlabel("Share of responses mentioning the brand (%)")
    ax.set_title("The same brands dominate, however the question is phrased")
    save_figure(fig, FIGURES, "brand-share")


def ecdf_by_condition(pairs: pd.DataFrame, family: str, title: str, name: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for cond, color in COND_COLORS.items():
        vals = pairs.loc[pairs["condition"] == cond, family].dropna().sort_values()
        if vals.empty:
            continue
        ax.plot(
            vals, np.linspace(0, 1, len(vals)), drawstyle="steps-post",
            color=color, lw=2, label=COND_LABELS[cond],
        )
    ax.set_xlabel(f"Pairwise Jaccard overlap ({family.replace('_', ' ')})")
    ax.set_ylabel("Cumulative share of pairs")
    ax.set_title(title)
    ax.legend(frameon=False)
    save_figure(fig, FIGURES, name)


def f4_domain_concentration(hp: pd.DataFrame) -> None:
    domains = sorted({d for s in hp["domain_set"] for d in s})
    share = pd.Series(
        {d: hp["domain_set"].map(lambda s, d=d: d in s).mean() for d in domains}
    ).sort_values()
    top = share.tail(15)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(np.arange(len(top)), top * 100, color=CATEGORICAL[3])
    ax.set_yticks(np.arange(len(top)), top.index)
    ax.set_xlabel("Share of responses citing the domain (%)")
    ax.set_title("Citations concentrate on the same sources")
    save_figure(fig, FIGURES, "domain-concentration")


def f5_stability(df: pd.DataFrame, pairs: pd.DataFrame) -> None:
    waves = df["wave"].to_numpy()
    within = pairs[pairs["condition"] == "within_prompt"].copy()
    within["gap"] = np.abs(waves[within["i"]] - waves[within["j"]])
    by_gap = within.groupby("gap")["brands"].mean()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(by_gap.index, by_gap.to_numpy(), marker="o", color=CATEGORICAL[0], lw=2)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Days between runs of the same prompt")
    ax.set_ylabel("Mean brand-set Jaccard")
    models = df.groupby("wave")["model"].agg(
        lambda s: s.mode().iat[0] if s.notna().any() else "?"
    )
    ax.set_title("Run-to-run consistency holds across the week")
    ax.text(
        0.02, 0.04, "Models seen: " + ", ".join(sorted(set(models.astype(str)))),
        transform=ax.transAxes, fontsize=8, color="#666666",
    )
    save_figure(fig, FIGURES, "stability-by-gap")


def main() -> None:
    theme()
    df = load_responses().reset_index(drop=True)
    pairs = model_stage.build_pairs(df)
    hp = df[df["intent"] == PRIMARY_INTENT]

    f1_brand_share(hp)
    ecdf_by_condition(
        pairs, "brands",
        "Rewording a prompt costs real brand overlap", "brand-jaccard-ecdf",
    )
    ecdf_by_condition(
        pairs, "domains",
        "Cited sources shift when the prompt is reworded", "domain-jaccard-ecdf",
    )
    f4_domain_concentration(hp)
    f5_stability(df, pairs)
    print(f"figures -> {FIGURES}")


if __name__ == "__main__":
    main()
