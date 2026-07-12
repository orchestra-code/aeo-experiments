#!/usr/bin/env python3
"""Step 4 — figures. Everything goes through save_figure (watermark + caption).

Writes SVG+PNG pairs to figures/, including a 1200×630 OG variant of the
money chart.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from aeo_research import (
    BRAND_BLUE,
    PLATFORM_COLORS,
    PLATFORM_LABELS,
    decile_plot,
    save_figure,
    theme,
    wilson_interval,
)
from common import CITATIONS_CSV, FIGURES, load_videos, primary_frame

INK_MUTED = "#6b7280"


def money_chart(df: pd.DataFrame, og: bool = False) -> dict:
    fig = decile_plot(
        df[df["audience_size"].notna()],
        "log_subs",
        "cited",
        xlabel="Channel subscriber count — decile (1 = smallest)",
        ylabel="Share cited inline",
        title="Citation rate by channel size\n(among YouTube videos the assistant already retrieved)",
    )
    name = "citation-rate-by-channel-size" + ("-og" if og else "")
    return save_figure(fig, FIGURES, name, og=og)


def views_deciles(df: pd.DataFrame) -> dict:
    fig = decile_plot(
        df[df["video_view_count"].notna()],
        "log_views",
        "cited",
        xlabel="Video view count — decile (1 = fewest views)",
        ylabel="Share cited inline",
        title="Citation rate by video popularity\n(among YouTube videos the assistant already retrieved)",
    )
    return save_figure(fig, FIGURES, "citation-rate-by-view-count")


def rate_by(df: pd.DataFrame, col: str, labels: dict, title: str, name: str) -> dict:
    g = df.groupby(col)["cited"].agg(["mean", "count", "sum"]).sort_values("mean")
    lo, hi = wilson_interval(g["sum"], g["count"])
    fig, ax = plt.subplots(figsize=(9, 0.8 + 0.55 * len(g)))
    y = np.arange(len(g))
    ax.barh(y, g["mean"], color=BRAND_BLUE, height=0.62)
    ax.errorbar(g["mean"], y, xerr=[g["mean"] - lo, hi - g["mean"]],
                fmt="none", ecolor=INK_MUTED, capsize=3, lw=1.2)
    ax.set_yticks(y, [labels.get(i, str(i)) for i in g.index])
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share cited inline")
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.25)
    ax.grid(axis="y", visible=False)
    return save_figure(fig, FIGURES, name)


def timestamp_share(rows: pd.DataFrame) -> dict:
    """Stretch: timestamped-citation share by platform, split by source class."""
    rows = rows.copy()
    rows["has_ts"] = rows["timestamp_seconds"].notna()
    classes = [
        ("Model-cited (CITED_INLINE)", rows["citation_type"] == "CITED_INLINE"),
        ("SERP-appended (SEARCH_RESULT)", rows["citation_type"] == "SEARCH_RESULT"),
    ]
    platforms = [p for p in PLATFORM_COLORS if p in set(rows["platform"])]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    width = 0.38
    x = np.arange(len(platforms))
    hatches = [None, "//"]
    for i, (label, mask) in enumerate(classes):
        shares, los, his = [], [], []
        for plat in platforms:
            sub = rows[mask & (rows["platform"] == plat)]
            if len(sub) == 0:
                shares.append(np.nan), los.append(np.nan), his.append(np.nan)
                continue
            s = sub["has_ts"].sum()
            lo, hi = wilson_interval(s, len(sub))
            shares.append(s / len(sub)), los.append(lo), his.append(hi)
        shares = np.array(shares, dtype=float)
        ax.bar(x + (i - 0.5) * width, shares, width * 0.92, label=label,
               color=[PLATFORM_COLORS[p] for p in platforms],
               alpha=1.0 if i == 0 else 0.45, hatch=hatches[i], edgecolor="white")
        ax.errorbar(x + (i - 0.5) * width, shares,
                    yerr=[shares - np.array(los), np.array(his) - shares],
                    fmt="none", ecolor=INK_MUTED, capsize=3, lw=1.2)
    ax.set_xticks(x, [PLATFORM_LABELS[p] for p in platforms])
    ax.set_ylabel("Share of YouTube citations with a t= timestamp")
    ax.set_title("Timestamped YouTube citations by platform\n(SERP-appended results = no model choice involved)")
    ax.legend()
    return save_figure(fig, FIGURES, "timestamp-share-by-platform")


def main() -> None:
    theme()
    units = load_videos()
    df = primary_frame(units)
    rows = pd.read_csv(CITATIONS_CSV)

    made = [
        money_chart(df),
        money_chart(df, og=True),
        views_deciles(df),
        rate_by(df, "category", {}, "Citation rate by video category", "citation-rate-by-category"),
        rate_by(
            df[df["has_captions"].notna()], "has_captions",
            {0.0: "No captions", 1.0: "Has captions"},
            "Citation rate by caption availability", "citation-rate-by-captions",
        ),
        timestamp_share(rows),
    ]
    for m in made:
        print(f"  {m['svg'].relative_to(FIGURES.parent)}")


if __name__ == "__main__":
    main()
