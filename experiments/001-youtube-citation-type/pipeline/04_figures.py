#!/usr/bin/env python3
"""Step 4 — figures. Everything goes through save_figure (watermark + caption).

Writes SVG+PNG pairs to figures/, including a 1200×630 OG variant of the
lead chart (timestamped citations by platform).
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


def timestamp_share_by_platform(rows: pd.DataFrame, og: bool = False) -> dict:
    """Lead chart: share of YouTube citations carrying a t= timestamp."""
    inline = rows[rows["citation_type"] == "CITED_INLINE"].copy()
    inline["has_ts"] = inline["timestamp_seconds"].notna()
    platforms = [p for p in PLATFORM_COLORS if p in set(inline["platform"])]

    shares, los, his, ns = [], [], [], []
    for plat in platforms:
        sub = inline[inline["platform"] == plat]
        s = int(sub["has_ts"].sum())
        lo, hi = wilson_interval(s, len(sub))
        shares.append(s / len(sub)), los.append(lo), his.append(hi), ns.append(len(sub))

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = np.arange(len(platforms))
    shares = np.array(shares)
    ax.bar(x, shares, 0.62, color=[PLATFORM_COLORS[p] for p in platforms])
    ax.errorbar(x, shares, yerr=[shares - np.array(los), np.array(his) - shares],
                fmt="none", ecolor=INK_MUTED, capsize=3, lw=1.2)
    for xi, share, n in zip(x, shares, ns):
        ax.annotate(f"{share:.0%}", (xi, share), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=11, color="#222222")
    ax.set_xticks(x, [PLATFORM_LABELS[p] for p in platforms])
    ax.set_ylabel("Share of cited YouTube videos with a t= timestamp")
    ax.set_ylim(0, 1)
    ax.set_title("Only one AI surface cites YouTube moments")
    name = "timestamp-share-by-platform" + ("-og" if og else "")
    return save_figure(fig, FIGURES, name, og=og)


def moment_rate_decile(df: pd.DataFrame, x: str, xlabel: str, name: str) -> dict:
    fig = decile_plot(
        df[df[x].notna()],
        x,
        "moment_cited",
        xlabel=xlabel,
        ylabel="Share moment-cited",
        title=f"Moment-citation rate — {xlabel.split(' — ')[0].lower()}\n"
        "(among YouTube videos cited by Google AI Overviews)",
    )
    return save_figure(fig, FIGURES, name)


def rate_by(df: pd.DataFrame, col: str, labels: dict, title: str, name: str) -> dict:
    d = df[df[col].notna()]
    g = d.groupby(col)["moment_cited"].agg(["mean", "count", "sum"]).sort_values("mean")
    lo, hi = wilson_interval(g["sum"], g["count"])
    fig, ax = plt.subplots(figsize=(9, 0.8 + 0.55 * len(g)))
    y = np.arange(len(g))
    ax.barh(y, g["mean"], color=BRAND_BLUE, height=0.62)
    ax.errorbar(g["mean"], y, xerr=[g["mean"] - lo, hi - g["mean"]],
                fmt="none", ecolor=INK_MUTED, capsize=3, lw=1.2)
    ax.set_yticks(y, [labels.get(i, str(i)) for i in g.index])
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share moment-cited")
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.25)
    ax.grid(axis="y", visible=False)
    return save_figure(fig, FIGURES, name)


def timestamp_position(df: pd.DataFrame) -> dict:
    """How deep into videos do AI answers point?"""
    d = df[(df["moment_cited"] == 1) & df["duration_seconds"].notna()].copy()
    d = d[d["timestamp_seconds"] <= d["duration_seconds"]]
    frac = d["timestamp_seconds"] / d["duration_seconds"]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(frac, bins=20, color=BRAND_BLUE, edgecolor="white")
    ax.set_xlabel("Timestamp position within the video (0 = start, 1 = end)")
    ax.set_ylabel("Moment citations")
    ax.set_title("How deep into videos do AI answers point?\n"
                 "(among moment-cited YouTube videos, Google AI Overviews)")
    ax.set_xlim(0, 1)
    return save_figure(fig, FIGURES, "timestamp-position")


def main() -> None:
    theme()
    units = load_videos()
    df = primary_frame(units)
    rows = pd.read_csv(CITATIONS_CSV)

    made = [
        timestamp_share_by_platform(rows),
        timestamp_share_by_platform(rows, og=True),
        moment_rate_decile(df, "log_duration", "Video duration — decile (1 = shortest)",
                           "moment-rate-by-duration"),
        moment_rate_decile(df, "log_subs", "Channel subscriber count — decile (1 = smallest)",
                           "moment-rate-by-channel-size"),
        rate_by(df, "has_chapters_f", {0.0: "No chapters", 1.0: "Has chapters"},
                "Moment-citation rate by description chapters", "moment-rate-by-chapters"),
        rate_by(df, "has_captions", {0.0: "No captions", 1.0: "Has captions"},
                "Moment-citation rate by caption availability", "moment-rate-by-captions"),
        rate_by(df, "category", {}, "Moment-citation rate by video category",
                "moment-rate-by-category"),
        timestamp_position(df),
    ]
    for m in made:
        print(f"  {m['svg'].relative_to(FIGURES.parent)}")


if __name__ == "__main__":
    main()
