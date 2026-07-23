"""Exploratory panel-design simulation (NOT pre-registered).

Question: how accurately does a tracking panel of k distinct phrasings,
each run on d days, estimate a brand's population mention rate (its rate
across all 143 phrasings x 7 days)?

Method: draw k prompts and d waves without replacement from the observed
143 x 7 hit matrix, take the panel mean, repeat; the 90% margin of error is
half the 5th-95th percentile span of panel estimates around the truth.
Because phrasing-level inclusion propensities are stable across days
(see results/exploratory_prompt_features.md), rerunning a fixed panel
shrinks only the run-to-run component — the phrasing-sampling component
persists. Outputs:

F8  panel-moe: margin of error vs number of distinct phrasings, one run
    vs daily-for-a-week, averaged over the six focal brands
results/panel_sim.csv: full grid per brand
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import FIGURES, RESPONSES_CSV, RESULTS

from aeo_research.plotting import CATEGORICAL, INK_MUTED, save_figure, theme

SEED = 20260716
BRANDS = ["sony", "bose", "sennheiser", "anker", "apple", "jbl"]
K_GRID = [5, 10, 15, 25, 40, 70, 100]
N_SIM = 4000


def hit_matrix(hp: pd.DataFrame, brand: str) -> np.ndarray:
    ind = hp.assign(hit=hp.bset.map(lambda s, b=brand: b in s))
    return np.array(ind.groupby("item_id")["hit"].apply(list).tolist())


def moe(arr: np.ndarray, k: int, d: int, rng: np.random.Generator) -> float:
    ests = np.empty(N_SIM)
    for s in range(N_SIM):
        pi = rng.choice(arr.shape[0], k, replace=False)
        di = rng.choice(arr.shape[1], d, replace=False)
        ests[s] = arr[np.ix_(pi, di)].mean()
    lo, hi = np.quantile(ests, [0.05, 0.95])
    return float((hi - lo) / 2)


def main() -> None:
    theme()
    rng = np.random.default_rng(SEED)
    resp = pd.read_csv(RESPONSES_CSV)
    hp = resp[resp.intent == "headphones"].copy()
    hp["bset"] = hp.brands.fillna("").str.split(r"\|").map(
        lambda x: frozenset(d for d in x if d)
    )

    rows = []
    for b in BRANDS:
        arr = hit_matrix(hp, b)
        for k in K_GRID:
            for d, design in [(1, "once"), (7, "daily_week")]:
                rows.append(
                    {"brand": b, "k_prompts": k, "days": d, "design": design,
                     "moe90": moe(arr, k, d, rng), "runs": k * d}
                )
    grid = pd.DataFrame(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    grid.to_csv(RESULTS / "panel_sim.csv", index=False)

    avg = grid.groupby(["design", "k_prompts"])["moe90"].mean().unstack(0)

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    ax.plot(
        avg.index, avg["once"] * 100, marker="o", lw=2, color=CATEGORICAL[0],
        label="Each phrasing run once",
    )
    ax.plot(
        avg.index, avg["daily_week"] * 100, marker="s", lw=2,
        color=CATEGORICAL[1], label="Each phrasing run daily for a week (7× the runs)",
    )
    ax.set_xlabel("Number of distinct phrasings in the panel")
    ax.set_ylabel("90% margin of error on mention rate (percentage points)")
    ax.set_title("Phrasing variety, not repetition, buys accuracy")
    ax.set_xticks(K_GRID)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False)
    ax.text(
        0.99, 0.03,
        "Average over six focal brands; sampled from the observed 143×7 grid",
        transform=ax.transAxes, ha="right", fontsize=8.5, color=INK_MUTED,
    )
    save_figure(fig, FIGURES, "panel-moe")
    print(f"panel simulation -> {RESULTS / 'panel_sim.csv'} + figures/panel-moe")


if __name__ == "__main__":
    main()
