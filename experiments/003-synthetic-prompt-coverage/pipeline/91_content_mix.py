"""Exploratory (post-hoc) — content mix and funnel stage -> results/ + figures.

Added 2026-08-02 AFTER the pre-registered results were computed and logged
under "Deviations from the frozen spec". Nothing here changes an H1-H3
verdict (results/model_summary.txt is the record); this is the
interpretation layer, labelled per the 9x convention.

Three questions:

A. **Funnel stage.** The product excludes awareness-stage prompts from share
   of voice. Dropping the generator's own awareness query types
   (category_entry_point, buyers_journey_awareness) from the spy panels,
   how much of H2/H3 remains?
B. **Content mix.** The generator's Mad-Libs frame provably encodes the
   anchor's promoted features and segments (data/raw/generator/*.json).
   Raking the human panel to each spy panel's H4-flag marginals asks: if
   humans posed the panel's mix of questions, would they see the panel's
   market? The answer is the share of the H2 gap explained by content mix.
C. **Home turf.** Where does each anchor brand rank on its own panel vs the
   rival's, the human panel, and the neutral panel?

Figures: F5 content-mix-reweight (raking), F6 panel-rank-swing (bump chart).
"""

from __future__ import annotations

import importlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import (
    ANCHORS,
    CONTRAST_ARM,
    FIGURES,
    N_BOOT,
    PRIMARY_ARM,
    PROMPTS_CSV,
    RESULTS,
    SEED,
    SHARE_FLOOR,
    load_responses,
)

from aeo_research.plotting import CATEGORICAL, GRID, INK_MUTED, save_figure, theme

model_stage = importlib.import_module("03_model")
coverage_stage = importlib.import_module("90_coverage_flags")

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
ARM_MARKERS = {"spy_a": "o", "spy_b": "s", "neu": "D"}

#: The generator's awareness-stage query types (the product excludes this
#: funnel stage from share of voice).
AWARENESS_TYPES = {"category_entry_point", "buyers_journey_awareness"}

#: Flags with the largest prompt-side prevalence deltas vs the human panel
#: (results/coverage_flags.txt) — the raking marginals.
RAKE_FLAGS = ["f_form_factor", "f_wireless", "f_travel_context", "f_usage_music"]

#: Flags shown in the within-human conditional table (mechanism evidence).
CONDITIONAL_FLAGS = [
    "f_form_factor", "f_wireless", "f_noise_cancel",
    "f_budget_specific", "f_travel_context", "f_usage_music",
]


def flagged_prompts() -> pd.DataFrame:
    prompts = pd.read_csv(PROMPTS_CSV)
    hp = prompts[prompts["arm"] != CONTRAST_ARM].copy()
    text = hp["text"].str.lower()
    for flag, pattern in coverage_stage.FLAGS.items():
        hp[flag] = text.str.contains(pattern)
    return hp


def per_prompt_shares(df: pd.DataFrame, brands: list[str]) -> pd.DataFrame:
    """One row per prompt: arm + fraction of its runs mentioning each brand."""
    rows = df.groupby(["arm", "item_id"])["brand_set"].apply(
        lambda sets: pd.Series({b: np.mean([b in s for s in sets]) for b in brands})
    )
    return rows.unstack().reset_index()


def rake(base: pd.DataFrame, targets: dict[str, float], iters: int = 100) -> np.ndarray:
    """Iterative proportional fitting of prompt weights to flag marginals."""
    w = np.ones(len(base))
    for _ in range(iters):
        for flag, target in targets.items():
            x = base[flag].to_numpy(float)
            current = np.average(x, weights=w)
            if 0 < current < 1:
                w = w * np.where(x == 1, target / current, (1 - target) / (1 - current))
    return w


# ------------------------------------------------------------ A. funnel stage


def funnel_subset(df: pd.DataFrame, prompts: pd.DataFrame, basket: list[str],
                  out: list[str]) -> None:
    aware = set(prompts.loc[prompts["query_type"].isin(AWARENESS_TYPES), "item_id"])
    sub = df[~df["item_id"].isin(aware)].reset_index(drop=True)
    out.append("\n## A. Decision-stage subset (awareness query types dropped)")
    out.append(
        f"Dropped {len(aware & set(df['item_id']))} prompts "
        f"({', '.join(sorted(AWARENESS_TYPES))}); spy_a keeps 24/37, spy_b 25/37; "
        "hum/neu carry no query-type labels and are unchanged."
    )
    zero = sub.groupby("arm").apply(
        lambda g: (g["n_brands"] == 0).mean(), include_groups=False
    )
    out.append("Zero-brand response rate: " +
               ", ".join(f"{a} {zero[a]:.3f}" for a in ("hum", "spy_a", "spy_b", "neu")))

    cols = sorted(set(basket) | set(ANCHORS.values()))
    j = {b: i for i, b in enumerate(cols)}
    basket_idx = np.array([j[b] for b in basket])
    mats = {arm: model_stage.prompt_share_matrix(sub[sub["arm"] == arm], cols)
            for arm in (PRIMARY_ARM, *ANCHORS)}

    stat_fns: dict = {}
    for arm in ANCHORS:
        stat_fns[f"H2_{arm}"] = lambda s, arm=arm: float(
            np.abs(s[arm][basket_idx] - s[PRIMARY_ARM][basket_idx]).mean())
    (arm_a, anchor_a), (arm_b, anchor_b) = ANCHORS.items()
    for arm, anchor in ANCHORS.items():
        stat_fns[f"H3_own_vs_hum:{arm}"] = lambda s, arm=arm, anchor=anchor: float(
            s[arm][j[anchor]] - s[PRIMARY_ARM][j[anchor]])
    stat_fns["H3_did"] = lambda s: float(
        (s[arm_a][j[anchor_a]] - s[arm_b][j[anchor_a]])
        - (s[arm_a][j[anchor_b]] - s[arm_b][j[anchor_b]]))

    res = model_stage.boot_share_stats(mats, stat_fns, N_BOOT, SEED)
    for name, (obs, lo, hi) in res.items():
        out.append(f"- {name}: {obs:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    out.append(
        "Reading: intent mix explains roughly a third of spy_a's H2 gap "
        "(0.248 -> 0.162) and none of spy_b's (0.261 -> 0.280); the anchor "
        "DiD *grows* on the decision-stage subset (+0.411 -> +0.571). "
        "The pre-registered verdicts are not an artifact of funnel stage."
    )


# ------------------------------------------------------------ B. content mix


def content_mix(pp: pd.DataFrame, prompts: pd.DataFrame, basket: list[str],
                out: list[str]) -> dict[str, dict]:
    hum_pp = pp[pp["arm"] == PRIMARY_ARM].merge(
        prompts[["item_id", *coverage_stage.FLAGS]], on="item_id")

    out.append("\n## B. Content mix — does asking the panel's questions "
               "produce the panel's market?")
    out.append("\nWithin the HUMAN panel: share shift when a flag is present "
               "(percentage points; n = prompts with flag):")
    for flag in CONDITIONAL_FLAGS:
        on, off = hum_pp[hum_pp[flag]], hum_pp[~hum_pp[flag]]
        delta = on[basket].mean() - off[basket].mean()
        out.append(f"- {flag} (n={len(on)}): " +
                   ", ".join(f"{b} {delta[b]:+.2f}" for b in basket))
    out.append(
        "The budget flip (bose down, jbl up) replicates 002's exploratory "
        "sub-intent finding on fresh data: prompt content steers brand mix."
    )

    results: dict[str, dict] = {}
    for arm in ANCHORS:
        prev = prompts.loc[prompts["arm"] == arm, RAKE_FLAGS].mean()
        targets = {f: float(prev[f]) for f in RAKE_FLAGS}
        w = rake(hum_pp, targets)
        ess = w.sum() ** 2 / (w**2).sum()
        obs_hum = hum_pp[basket].mean()
        rw_hum = pd.Series({b: np.average(hum_pp[b], weights=w) for b in basket})
        obs_arm = pp.loc[pp["arm"] == arm, basket].mean()
        before = float(np.abs(obs_arm - obs_hum).mean())
        after = float(np.abs(obs_arm - rw_hum).mean())
        explained = 1 - after / before
        results[arm] = {
            "targets": targets, "ess": ess, "hum": obs_hum,
            "reweighted": rw_hum, "observed": obs_arm,
            "before": before, "after": after, "explained": explained,
        }
        out.append(f"\nRaking hum to {arm}'s flag mix "
                   f"({ {k.removeprefix('f_'): round(v, 2) for k, v in targets.items()} }):")
        out.append(f"- effective sample size {ess:.0f} of {len(hum_pp)} human prompts")
        tab = pd.DataFrame({"hum": obs_hum, "hum_reweighted": rw_hum, arm: obs_arm})
        out.append(tab.round(3).to_string())
        out.append(f"- share MAD vs {arm}: {before:.3f} -> {after:.3f} "
                   f"({explained:.0%} of the gap explained by content mix)")
    return results


# ------------------------------------------------------------ C. home turf


def home_turf(pp: pd.DataFrame, basket: list[str], out: list[str]) -> pd.DataFrame:
    shares = pp.groupby("arm")[basket].mean()
    ranks = shares.rank(axis=1, ascending=False).astype(int)
    out.append("\n## C. Home turf — anchor share and rank by panel")
    for anchor in ANCHORS.values():
        out.append(f"\n{anchor}:")
        for arm in (PRIMARY_ARM, *ANCHORS, "neu"):
            out.append(f"- {ARM_LABELS[arm]}: share {shares.loc[arm, anchor]:.3f}, "
                       f"rank {ranks.loc[arm, anchor]}/{len(basket)}")
    out.append(
        "Reading: bose ranks 2nd everywhere — it trails sony even on its own "
        "panel (the instrument does not flatter its anchor). anker swings "
        "from 1st on its own panel to 5th on the rival's; panel choice sets "
        "the leaderboard."
    )
    return ranks


# ------------------------------------------------------------ figures


def f5_reweight(results: dict[str, dict], basket: list[str]) -> None:
    order = list(results[next(iter(results))]["hum"].sort_values().index)
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.2), sharey=True, sharex=True)
    for ax, (arm, r) in zip(axes, results.items()):
        y = np.arange(len(order))
        for i, b in enumerate(order):
            ax.plot([r["hum"][b] * 100, r["observed"][b] * 100], [i, i],
                    color=GRID, lw=1.5, zorder=1)
        ax.scatter([r["hum"][b] * 100 for b in order], y, marker="o", s=65,
                   facecolor="white", edgecolor=ARM_COLORS["hum"], linewidth=1.6,
                   zorder=3, label="Human panel (all prompts)")
        ax.scatter([r["reweighted"][b] * 100 for b in order], y, marker="P", s=80,
                   color=ARM_COLORS["hum"], edgecolor="white", linewidth=0.8,
                   zorder=4, label="Humans reweighted to the panel's content mix")
        ax.scatter([r["observed"][b] * 100 for b in order], y,
                   marker=ARM_MARKERS[arm], s=65, color=ARM_COLORS[arm],
                   edgecolor="white", linewidth=0.8, zorder=4,
                   label="Anchored panel, observed")
        ax.set_yticks(y, [b.title() for b in order])
        ax.set_xlabel("Share of responses mentioning the brand (%)")
        ax.set_title(
            f"{ARM_LABELS[arm]}\ncontent mix explains {r['explained']:.0%} of the "
            f"gap (eff. n = {r['ess']:.0f})", fontsize=10,
        )
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle("Ask the brand's questions, see the brand's market?", y=1.0)
    save_figure(fig, FIGURES, "content-mix-reweight")


def f6_rank_swing(ranks: pd.DataFrame, basket: list[str]) -> None:
    arms = [PRIMARY_ARM, "spy_a", "spy_b", "neu"]
    xlabels = ["Human\n(survey)", "Bose-\nanchored", "Soundcore-\nanchored",
               "Neutral\ngenerator"]
    anchor_style = {
        "bose": (ARM_COLORS["spy_a"], "o"),
        "anker": (ARM_COLORS["spy_b"], "s"),
    }
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(arms))
    for b in basket:
        r = [ranks.loc[a, b] for a in arms]
        if b in anchor_style:
            color, marker = anchor_style[b]
            ax.plot(x, r, color=color, lw=2.5, marker=marker, markersize=8,
                    markeredgecolor="white", zorder=3)
            for xi, ri in zip(x, r):
                ax.annotate(str(ri), (xi, ri), textcoords="offset points",
                            xytext=(0, -14), ha="center", fontsize=8,
                            color=color, fontweight="bold")
        else:
            ax.plot(x, r, color=INK_MUTED, lw=1, marker="o", markersize=3,
                    alpha=0.55, zorder=2)
        label_color = anchor_style[b][0] if b in anchor_style else INK_MUTED
        ax.annotate(b.title(), (x[-1] + 0.08, ranks.loc["neu", b]),
                    va="center", fontsize=8, color=label_color)
    ax.set_xticks(x, xlabels)
    ax.set_xlim(-0.3, len(arms) - 0.4)
    ax.set_ylim(len(basket) + 0.6, 0.4)
    ax.set_yticks(range(1, len(basket) + 1))
    ax.set_ylabel("Brand rank within panel (1 = most mentioned)")
    ax.set_title("The panel's anchor sets the leaderboard")
    save_figure(fig, FIGURES, "panel-rank-swing")


def main() -> None:
    theme()
    prompts = flagged_prompts()
    df = load_responses().reset_index(drop=True)
    df = df[df["arm"] != CONTRAST_ARM]

    hum = df[df["arm"] == PRIMARY_ARM]
    all_brands = sorted({b for s in hum["brand_set"] for b in s})
    hum_share = {b: hum["brand_set"].map(lambda s, b=b: b in s).mean()
                 for b in all_brands}
    basket = [b for b in all_brands if hum_share[b] >= SHARE_FLOOR]

    out: list[str] = [
        "# Experiment 003 — exploratory content-mix and funnel-stage analysis",
        "",
        "**Status: post-hoc (2026-08-02), after the pre-registered results.**",
        "Motivated by the product-interpretation question: is the anchored",
        "panels' divergence an artifact of funnel stage, and how much of it is",
        "the panel measuring the anchor's own claimed territory? The frozen",
        "H1-H3 verdicts in results/model_summary.txt stand unchanged.",
        "",
        "Caveats: raking uses 4 flag marginals only (no interactions);",
        "effective sample sizes are small because few human prompts phrase",
        "things the way the panels do — treat the explained-fraction numbers",
        "as descriptive, not tested. The generator snapshots",
        "(data/raw/generator/*.json) document the encoded positioning: Bose =",
        "noise cancelling / wireless / battery / frequent-flyer segments;",
        "Soundcore = earbud product lines (open-ear, sleep, workout) from a",
        "homepage-only crawl.",
    ]

    pp = per_prompt_shares(df, basket)
    funnel_subset(df, prompts, basket, out)
    results = content_mix(pp, prompts, basket, out)
    ranks = home_turf(pp, basket, out)

    out.append(
        "\n## What this supports, and what it does not\n"
        "Supports: the conditional-share-of-voice reading of an anchored\n"
        "panel (it asks the questions the brand's positioning claims; for\n"
        "the Bose panel ~72% of the share gap is content mix), and the\n"
        "asymmetric signal (winning at home is expected; bose trailing sony\n"
        "at home is the notable finding).\n"
        "Does not rescue: spy_b (37% explained, eff. n 7 — its mix largely\n"
        "leaves human phrasing space; the catalog-tilt critique stands for\n"
        "that draw), the neutral panel's H2 miss, or any absolute\n"
        "market-share claim from an anchored panel."
    )

    f5_reweight(results, basket)
    f6_rank_swing(ranks, basket)

    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "exploratory_content_mix.md"
    path.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nwrote {path}; figures -> {FIGURES}")


if __name__ == "__main__":
    main()
