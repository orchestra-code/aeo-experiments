"""Pre-freeze figures: refined consultation taxonomy (F6 v2) and the
AIPVS-tier authority contrast (F5 v1).

Usage: uv run python experiments/007-site-consultations-observational/pipeline/04b_figures_prefreeze.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aeo_research.plotting import (  # noqa: E402
    BLUE_RAMP,
    CATEGORICAL,
    INK,
    INK_MUTED,
    save_figure,
    theme,
)

EXP = Path(__file__).resolve().parents[1]
INTERIM, FIGURES = EXP / "data" / "interim", EXP / "figures"

KIND_LABELS = {
    "government_or_courts": "Government & courts",
    "ai_or_software_vendor": "AI & software vendors",
    "law_firm": "Law firms",
    "bar_or_professional_association": "Bar & professional assocs.",
    "other_business": "Other businesses",
    "healthcare_provider": "Healthcare providers",
    "nonprofit_or_foundation": "Nonprofits & foundations",
    "agency_or_consultancy": "Agencies & consultancies",
    "financial_or_insurance": "Financial & insurance",
    "ecommerce_or_retail": "E-commerce & retail",
    "directory_or_ratings": "Directories & ratings",
    "news_or_media": "News & media",
    "academic_or_reference": "Academic & reference",
    "unknown": "Unclassified",
}
SHOWN_KINDS = 10  # rest folds into "Everything else"


def f6v2(tp: pd.DataFrame) -> None:
    raw = tp["kind"].value_counts(normalize=True) * 100
    sector_kind = (
        tp.groupby("trigger_sector")["kind"]
        .value_counts(normalize=True).rename("share").reset_index()
    )
    balanced = sector_kind.groupby("kind")["share"].mean() * 100
    balanced = 100 * balanced / balanced.sum()

    top = raw.sort_values(ascending=False).head(SHOWN_KINDS).index.tolist()
    def fold(series: pd.Series) -> pd.Series:
        kept = series.reindex(top).fillna(0)
        kept["__other__"] = series.drop(index=top, errors="ignore").sum()
        return kept
    raw_f, bal_f = fold(raw), fold(balanced)
    labels = [KIND_LABELS.get(k, k) if k != "__other__" else "Everything else"
              for k in raw_f.index]

    y = np.arange(len(raw_f))
    h = 0.38
    fig, ax = plt.subplots(figsize=(9.8, 6.4))
    ax.barh(y - h / 2, raw_f.values, height=h, color=CATEGORICAL[0],
            label="As observed (client-weighted)")
    ax.barh(y + h / 2, bal_f.values, height=h, color=CATEGORICAL[1],
            label="Sector-balanced (each client sector equal)")
    for yi, v in zip(y - h / 2, raw_f.values):
        ax.text(v + 0.4, yi, f"{v:.0f}%", va="center", fontsize=9.5, color=INK)
    for yi, v in zip(y + h / 2, bal_f.values):
        ax.text(v + 0.4, yi, f"{v:.0f}%", va="center", fontsize=9.5,
                color=INK_MUTED)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("share of third-party site consultations  (%)")
    ax.set_title("Who AI consults directly — with the client-mix skew shown honestly")
    ax.grid(axis="x", alpha=0.6)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=2)
    save_figure(fig, FIGURES, "f6v2-consultation-kinds")


def f5(pool: pd.DataFrame) -> None:
    dl = (pool.sort_values("consulted", ascending=False)
              .drop_duplicates("domain"))
    tiers = ["Premium", "Strong", "Moderate", "Limited"]
    colors = {t: c for t, c in zip(tiers, [BLUE_RAMP[4], BLUE_RAMP[3],
                                           BLUE_RAMP[1], BLUE_RAMP[0]])}
    mix = (dl.dropna(subset=["tier_label"])
             .groupby("consulted")["tier_label"]
             .value_counts(normalize=True).mul(100).unstack()
             .reindex(columns=tiers))

    fig, ax = plt.subplots(figsize=(9.8, 4.4))
    # matplotlib puts y=0 at the bottom — list the hero row last.
    rows = [(False, "Cited but never consulted"), (True, "Consulted directly")]
    for yi, (flag, _label) in enumerate(rows):
        left = 0.0
        for tier in tiers:
            v = float(mix.loc[flag, tier])
            ax.barh(yi, v, left=left, height=0.56, color=colors[tier],
                    edgecolor="white", linewidth=2,
                    label=tier if yi == 0 else None)
            if v >= 5:
                ax.text(left + v / 2, yi, f"{v:.0f}%", ha="center", va="center",
                        fontsize=10.5,
                        color="white" if tier in ("Premium", "Strong") else INK)
            left += v
    ax.set_yticks(range(len(rows)), [label for _, label in rows])
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of domains by AI Placement Value tier  (%)")
    ax.set_title("The sites AI consults directly carry higher AI Placement Value")
    ax.grid(visible=False)
    ax.spines["left"].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4)
    save_figure(fig, FIGURES, "f5-aipvs-tier-contrast")


def main() -> None:
    theme()
    tp = pd.read_csv(INTERIM / "third_party_consultations.csv",
                     keep_default_na=False, na_values=[""])
    pool = pd.read_csv(INTERIM / "pool_with_metrics.csv",
                       keep_default_na=False, na_values=[""])
    f6v2(tp)
    f5(pool)
    print(f"figures -> {FIGURES}")


if __name__ == "__main__":
    main()
