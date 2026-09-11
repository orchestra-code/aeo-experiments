"""Stage 04 — watermarked figures (spec §9.5) -> figures/*.{svg,png}.

F1 tier-accuracy  LEAD. Call-level accuracy by tier with 95% Wilson whiskers,
   the two prompt templates side by side, on the primary outcome (the first
   BRAND-ATTRIBUTABLE site: query). The "does it know your domain" chart.
F2 error-content  Stacked share of own-domain errors by kind and tier — the
   H3 carrier (stale / morphological guess / name-bearing, split by the
   signed Audit D attribution into the brand's own sites vs another
   company's / nonexistent). Empty kinds are dropped from the legend.
F3 transitions    H4 as a 2x2 heatmap: what happens the day after a correct
   consultation vs the day after a wrong one.
F4 tier-c-persistence  Per-brand stale rate by wave for tier C — the
   persistence picture. Brands are named here because they ARE the study
   panel and the tier is the unit of the claim; no figure title names a
   brand (spec §1: no per-brand shaming lead).

Colour comes from the theme's categorical palette only.

Usage: uv run python experiments/008-brand-domain-knowledge/pipeline/04_figures.py
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import (
    ALPHA,
    FIGURES,
    SYNTHETIC_WORLDS,
    TEMPLATE_LABELS,
    TIERS,
    apply_resolution,
    load_observations,
    load_responses,
)

from matplotlib.colors import LinearSegmentedColormap

import importlib

from aeo_research.plotting import BLUE_RAMP, CATEGORICAL, INK_MUTED, save_figure, theme
from aeo_research.stats import wilson_interval

#: Stage 03 holds the shared derivations (transitions, the Audit D kind
#: split); the module name is not a legal identifier, so import it by path.
model_stage = importlib.import_module("03_model")

#: The theme's single-hue ramp as a continuous map (magnitude encoding).
BLUE_CMAP = LinearSegmentedColormap.from_list("spyglasses_blue", ["#ffffff", *BLUE_RAMP])

TIER_AXIS = {
    "A": "A\nguessable",
    "B": "B\nnon-obvious",
    "C": "C\nmigrated",
    "D": "D\nobscure",
}
TEMPLATE_COLOR = {"p1": CATEGORICAL[0], "p2": CATEGORICAL[1]}
#: name_bearing_other splits by the signed Audit D attribution — a site the
#: brand owns is a different thing from somebody else's site.
KIND_LABELS = {
    "stale_old_domain": "The brand's old domain",
    "morphological_guess": "A plausible guess at the name",
    "name_bearing:own_property": "Another site the brand owns",
    "name_bearing:other_company": "An unrelated company with the same name",
    "name_bearing:unreviewed": "Name-bearing, attribution unreviewed",
    "nonexistent": "A domain that does not resolve",
}
#: Colour follows the error kind, in the theme's fixed categorical order;
#: "unreviewed" is a missing judgment rather than a finding, so it takes the
#: theme's muted ink instead of a categorical slot.
KIND_COLORS = {
    "stale_old_domain": CATEGORICAL[0],
    "morphological_guess": CATEGORICAL[1],
    "name_bearing:own_property": CATEGORICAL[2],
    "name_bearing:other_company": CATEGORICAL[3],
    "nonexistent": CATEGORICAL[4],
    "name_bearing:unreviewed": INK_MUTED,
}


def f1_tier_accuracy(calls: pd.DataFrame) -> None:
    """Lead figure: accuracy of the model's FIRST site: commitment, by tier."""
    emit = calls[calls["emitted_brand_site_query"] == 1]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    offsets = {"p1": -0.13, "p2": 0.13}
    ys_all: list[float] = []
    for template, offset in offsets.items():
        xs, ys, lo_err, hi_err = [], [], [], []
        for i, tier in enumerate(TIERS):
            sub = emit[(emit["tier"] == tier) & (emit["template"] == template)]
            if sub.empty:
                continue
            k, n = int(sub["first_site_correct"].sum()), len(sub)
            lo, hi = wilson_interval(k, n, alpha=ALPHA)
            xs.append(i + offset)
            ys.append(100 * k / n)
            # Wilson's bound can land a float-epsilon inside the point
            # estimate at a 0/1 boundary; errorbar refuses negative lengths.
            lo_err.append(max(0.0, 100 * (k / n - lo)))
            hi_err.append(max(0.0, 100 * (hi - k / n)))
        ys_all += [y - e for y, e in zip(ys, lo_err)]
        ax.errorbar(xs, ys, yerr=[lo_err, hi_err], fmt="o", capsize=4, lw=1.4,
                    markersize=9, color=TEMPLATE_COLOR[template],
                    markeredgecolor="white", markeredgewidth=0.8,
                    label=TEMPLATE_LABELS[template].capitalize())
    ax.set_xticks(range(len(TIERS)), [TIER_AXIS[t] for t in TIERS])
    ax.set_ylabel("First site: search used the canonical domain (%)")
    ax.set_ylim(bottom=min(85, min(ys_all) - 4), top=101)
    ax.set_title("When ChatGPT consults a brand's site, does it pick the right domain?")
    ax.set_xlabel(
        "Calls whose first site: search named the brand's own site rather than "
        "a competitor's\n(comparison prompts that only ever opened competitors "
        "are out of the frame; see the H1 funnel)"
    )
    ax.legend(loc="lower left", fontsize=9)
    save_figure(fig, FIGURES, "tier-accuracy")


def f2_error_content(obs: pd.DataFrame) -> None:
    own = obs[(obs["label"] != "correct") & (obs["error_kind"] != "third_party")]
    own = own.assign(kind=model_stage.kind_detail(own))
    counts = (
        own.pivot_table(index="tier", columns="kind", aggfunc="size", fill_value=0)
        .reindex(index=list(TIERS), columns=list(KIND_LABELS), fill_value=0)
    )
    totals = counts.sum(axis=1)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    bottom = np.zeros(len(TIERS))
    for kind, label in KIND_LABELS.items():
        values = counts[kind].to_numpy(dtype=float)
        if not values.any():
            continue
        ax.bar(range(len(TIERS)), values, bottom=bottom, width=0.6,
               color=KIND_COLORS[kind], label=label)
        bottom += values
    for i, tier in enumerate(TIERS):
        ax.text(i, bottom[i] + max(bottom.max(), 1) * 0.02,
                f"n={int(totals[tier])}" if totals[tier] else "none observed",
                ha="center", fontsize=9, color=INK_MUTED)
    ax.set_xticks(range(len(TIERS)), [TIER_AXIS[t] for t in TIERS])
    ax.set_ylabel("Own-domain error consultations")
    ax.set_ylim(0, max(bottom.max() * 1.18, 1))
    ax.set_title("What the wrong consultations actually are, by tier")
    ax.legend(fontsize=9)
    save_figure(fig, FIGURES, "error-content")


def f3_transitions(calls: pd.DataFrame) -> None:
    trans = model_stage.transitions(calls, "first_site_correct")
    if trans.empty or trans["prev"].nunique() < 2:
        print("f3: no day-over-day transitions to plot — skipped")
        return
    erred = set(trans.loc[trans["prev"] == "wrong", "slug"])
    matched = trans[trans["slug"].isin(erred)]

    grid = np.array([
        [
            matched.loc[matched["prev"] == prev, "next_correct"].mean(),
            1 - matched.loc[matched["prev"] == prev, "next_correct"].mean(),
        ]
        for prev in ("correct", "wrong")
    ])
    counts = matched.groupby("prev").size()

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.imshow(grid, cmap=BLUE_CMAP, vmin=0, vmax=1, aspect="auto")
    ax.grid(False)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{grid[i, j]:.0%}", ha="center", va="center",
                    fontsize=15, color="white" if grid[i, j] > 0.55 else INK_MUTED)
    ax.set_xticks([0, 1], ["right the next day", "wrong the next day"])
    ax.set_yticks([0, 1], [f"right today\n(n={counts.get('correct', 0)})",
                           f"wrong today\n(n={counts.get('wrong', 0)})"])
    ax.set_title("Does a wrong consultation fix itself the next day?")
    ax.set_xlabel("Brands that got it wrong at least once, consecutive daily waves")
    save_figure(fig, FIGURES, "transitions")


def f4_tier_c_persistence(obs: pd.DataFrame) -> None:
    """The persistence picture: which days each migrated brand's old domain came back."""
    tier_c = obs[(obs["tier"] == "C") & (obs["intent"] == "core") & (obs["replicate"] == 0)]
    own_error = tier_c.assign(
        bad=((tier_c["label"] != "correct") & (tier_c["error_kind"] != "third_party")).astype(int)
    )
    per_brand = own_error.groupby("brand")["bad"].mean().sort_values(ascending=False)
    show = [b for b in per_brand.index if per_brand[b] > 0]
    if not show:
        print("f4: no tier-C own-domain errors to plot — skipped")
        return
    grid = (
        own_error[own_error["brand"].isin(show)]
        .pivot_table(index="brand", columns="wave", values="bad", aggfunc="mean")
        .reindex(show)
    )
    waves = list(grid.columns)
    fig, ax = plt.subplots(figsize=(8.5, 0.75 * len(show) + 2.6))
    im = ax.imshow(grid.to_numpy(dtype=float), cmap=BLUE_CMAP, vmin=0, vmax=1,
                   aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(len(waves)), [f"day {w}" for w in waves])
    ax.set_yticks(range(len(show)), show)
    for row in range(len(show)):
        for col in range(len(waves)):
            value = grid.to_numpy(dtype=float)[row, col]
            if not np.isnan(value):
                ax.text(col, row, f"{value:.0%}", ha="center", va="center", fontsize=9,
                        color="white" if value > 0.55 else INK_MUTED)
    fig.colorbar(im, ax=ax, shrink=0.8, label="share of that day's site: searches")
    ax.set_title("Migrated-domain brands: how often the old domain came back, day by day")
    ax.set_xlabel(
        "Share of the brand's site: searches that day naming a non-canonical "
        "domain of its own (core series)"
    )
    save_figure(fig, FIGURES, "tier-c-persistence")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    a = ap.parse_args()

    theme()
    calls = load_responses(synthetic=a.synthetic)
    obs, _ = apply_resolution(load_observations(synthetic=a.synthetic))

    f1_tier_accuracy(calls)
    f2_error_content(obs)
    f3_transitions(calls)
    f4_tier_c_persistence(obs)
    print(f"figures -> {FIGURES}")


if __name__ == "__main__":
    main()
