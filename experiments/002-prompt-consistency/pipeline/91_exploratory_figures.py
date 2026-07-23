"""Exploratory figures (NOT pre-registered) — prompt-attribute (sub-intent)
effects on brand mentions. Companion to 90_exploratory_features.py; numbers
match results/exploratory_prompt_features.md.

F6  budget-flip: mention rate with vs without a specific dollar budget
F7  sub-intent deltas: dot-and-interval chart, substantiated vs inconclusive
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import FIGURES, PROMPTS_CSV, RESPONSES_CSV

from aeo_research.plotting import CATEGORICAL, INK_MUTED, save_figure, theme

SEED = 20260716


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    prompts = pd.read_csv(PROMPTS_CSV)
    hp_prompts = prompts[prompts.intent == "headphones"].copy()
    t = hp_prompts.text.str.lower()
    hp_prompts["f_budget_specific"] = t.str.contains(
        r"[\$€£]\s?\d|\d+\s?(dollars|bucks|euros?|pounds)|under \d|less than \d|budget of"
    )
    hp_prompts["f_recipient_named"] = t.str.contains(
        r"\b(sister|brother|wife|husband|mom|mother|dad|father|daughter|son|aunt|uncle|niece|nephew|girlfriend|boyfriend|partner|friend|cousin|grandm|grandf|in[- ]law)\b"
    )
    hp_prompts["f_noise_cancel"] = t.str.contains(r"noise[- ]?cancel|\banc\b|noise[- ]reduc")
    hp_prompts["f_form_factor"] = t.str.contains(
        r"over[- ]?(the[- ])?ear|on[- ]ear|in[- ]ear|earbud|ear[- ]bud"
    )
    hp_prompts["f_usage_movies"] = t.str.contains(r"movie|video|film|netflix|show")
    hp_prompts["f_usage_music"] = t.str.contains(r"music|listen|song|audio ?book|podcast")
    hp_prompts["f_travel_context"] = t.str.contains(
        r"travel|flight|plane|airplane|trip|commut|airport"
    )

    resp = pd.read_csv(RESPONSES_CSV)
    hp = resp[resp.intent == "headphones"].copy()
    hp["bset"] = hp.brands.fillna("").str.split(r"\|").map(
        lambda x: frozenset(d for d in x if d)
    )
    feats = [c for c in hp_prompts.columns if c.startswith("f_")]
    hp = hp.merge(hp_prompts[["item_id"] + feats], on="item_id")
    return hp, hp_prompts


def boot_delta(hp: pd.DataFrame, feat: str, brand: str,
               rng: np.random.Generator, n_boot: int = 2000):
    hp = hp.assign(hit=hp.bset.map(lambda s, b=brand: b in s))
    per = hp.groupby("item_id").agg(p=("hit", "mean"), f=(feat, "first"))
    a, b = per[per.f].p.to_numpy(), per[~per.f].p.to_numpy()
    obs = a.mean() - b.mean()
    draws = [
        rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean()
        for _ in range(n_boot)
    ]
    lo, hi = np.quantile(draws, [0.05, 0.95])
    return obs, lo, hi


def f6_budget_flip(hp: pd.DataFrame) -> None:
    brands = ["bose", "sennheiser", "sony", "anker", "apple", "jbl"]
    rng = np.random.default_rng(SEED)
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    width = 0.38
    x = np.arange(len(brands))
    for k, (flag, color, label) in enumerate(
        [(False, CATEGORICAL[0], "No budget stated"),
         (True, CATEGORICAL[1], "Specific dollar budget in prompt")]
    ):
        sub = hp[hp.f_budget_specific == flag]
        rates, lo, hi = [], [], []
        for b in brands:
            # prompt-cluster bootstrap: responses within a prompt are not
            # independent, so resample prompts, not responses
            per = (
                sub.assign(hit=sub.bset.map(lambda s, b=b: b in s))
                .groupby("item_id")["hit"].mean().to_numpy()
            )
            draws = [rng.choice(per, len(per)).mean() for _ in range(2000)]
            rates.append(per.mean())
            qlo, qhi = np.quantile(draws, [0.05, 0.95])
            lo.append(qlo)
            hi.append(qhi)
        pos = x + (k - 0.5) * width
        ax.bar(pos, np.array(rates) * 100, width * 0.92, color=color, label=label)
        ax.errorbar(
            pos, np.array(rates) * 100,
            yerr=[(np.array(rates) - np.array(lo)) * 100,
                  (np.array(hi) - np.array(rates)) * 100],
            fmt="none", ecolor="#333333", capsize=3, lw=1,
        )
    ax.set_xticks(x, [b.title() if b != "jbl" else "JBL" for b in brands])
    ax.set_ylabel("Share of answers mentioning the brand (%)")
    ax.set_title("Naming a dollar budget flips the recommendation set")
    ax.legend(frameon=False)
    save_figure(fig, FIGURES, "budget-flip")


def f7_subintent_deltas(hp: pd.DataFrame) -> None:
    rng = np.random.default_rng(SEED)
    contrasts = [
        # (feature, brand, display) — substantiated set first, then inconclusive
        ("f_budget_specific", "bose", "Dollar budget → Bose"),
        ("f_budget_specific", "jbl", "Dollar budget → JBL"),
        ("f_budget_specific", "sennheiser", "Dollar budget → Sennheiser"),
        ("f_usage_music", "sennheiser", "Music usage → Sennheiser"),
        ("f_travel_context", "anker", "Travel context → Anker"),
        ("f_recipient_named", "bose", "Named gift recipient → Bose"),
        ("f_recipient_named", "jbl", "Named gift recipient → JBL"),
        ("f_form_factor", "anker", "Form factor stated → Anker"),
        ("f_usage_music", "sony", "Music usage → Sony"),
        ("f_noise_cancel", "sony", "Noise-cancelling → Sony"),
        ("f_noise_cancel", "anker", "Noise-cancelling → Anker"),
        ("f_usage_movies", "apple", "Movie usage → Apple"),
        ("f_form_factor", "apple", "Form factor stated → Apple"),
    ]
    rows = []
    for feat, brand, label in contrasts:
        obs, lo, hi = boot_delta(hp, feat, brand, rng)
        rows.append((label, obs, lo, hi, lo > 0 or hi < 0))
    rows.sort(key=lambda r: r[1])

    fig, ax = plt.subplots(figsize=(9, 6.5))
    y = np.arange(len(rows))
    for i, (label, obs, lo, hi, sig) in enumerate(rows):
        color = CATEGORICAL[1] if (sig and obs < 0) else (
            CATEGORICAL[2] if sig else INK_MUTED
        )
        ax.plot([lo * 100, hi * 100], [i, i], color=color, lw=2,
                alpha=1.0 if sig else 0.55)
        ax.plot(obs * 100, i, "o", color=color, markersize=7,
                markerfacecolor=color if sig else "white",
                markeredgecolor=color, markeredgewidth=1.5)
    ax.axvline(0, color=INK_MUTED, lw=1, ls="--")
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlabel(
        "Change in brand-mention rate when the prompt has the attribute "
        "(percentage points, 90% CI)"
    )
    ax.set_title("How prompt attributes move brand mentions")
    ax.text(
        0.99, 0.02,
        "Filled = 90% CI excludes zero · hollow grey = not substantiated",
        transform=ax.transAxes, ha="right", fontsize=8.5, color=INK_MUTED,
    )
    save_figure(fig, FIGURES, "subintent-deltas")


def main() -> None:
    theme()
    hp, _ = load()
    f6_budget_flip(hp)
    f7_subintent_deltas(hp)
    print(f"exploratory figures -> {FIGURES}")


if __name__ == "__main__":
    main()
