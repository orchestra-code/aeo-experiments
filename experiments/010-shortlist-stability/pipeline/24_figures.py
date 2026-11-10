"""Stage 24: watermarked Stage 1 figures (spec §9) -> results/figures/stage1_*.{svg,png}.

The article leads with the shortlist alone (Jim, 2026-10-11, at the Stage 1
review): F0 is the lead figure, F3 and F4 support it, and F1 and F2 (every
status side by side) are kept for the appendix.

F0 stage1_shortlist  LEAD. Shortlist (R) retention within prompt, one row per
   platform, with its 90% interval.
F3 stage1_shortlist_runs  What a shortlist is made of: of all shortlist
   appearances across a prompt's 7 runs, the share taken by vendors
   shortlisted in every run, in 5 or 6, in 2 to 4, and in one run only (new
   collection; claude.ai has 3 runs and is left out).
F4 stage1_platform_agreement  Shortlist agreement for the same question:
   same platform on another day (within-prompt R retention) against two
   platforms on the same day (cross-platform R agreement).
F1 stage1_retention  Retention by status, a dot plot with 90% intervals:
   the shortlist (R), the best-for use case (WS), the top choice (T), the
   first-named vendor (P1) and the exact position (Pk), within prompt, one
   panel per platform (ChatGPT, Gemini, Claude API, claude.ai).
F2 stage1_gaps  The tested differences for the four platforms (H1 shortlist
   vs exact position, H2 shortlist vs top choice, H3 top choice vs first
   named, H7 shortlist vs use case) with their intervals and the 0.10 line.
   H1 uses the interval its Holm-adjusted verdict used.

Reads only ``results/stage1_model.json`` from 22_model.py, so it computes no
metric and cannot run before 22_model.py has passed its gate and H_pos.
Color follows the platform (aeo_research.plotting.PLATFORM_COLORS, validated
palette); claude.ai shares Claude's hue with a hollow marker.

Stage 2 (``--stage 2``, reads only ``results/stage2_model.json``), spec §9
article 2 lead figure, split the way Jim chose at Stage 1 (the shortlist is
the story):

S0 stage2_shortlist_by_lag  LEAD. Shortlist (R) retention by days between
   the two answers, one line per platform (ChatGPT, Gemini, Claude API) with
   its 90% band; the two bins H5 compares are shaded, and each platform's
   label carries its far-minus-near change.
S1 stage2_status_by_lag  The same curve for the shortlist, the best-for use
   case (WS) and the top choice (T), one panel per platform.

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/24_figures.py --stage 1
  uv run python .../24_figures.py --stage 1 --split explore | --synthetic planted
  uv run python .../24_figures.py --stage 2 [--synthetic planted_stable]
"""

from __future__ import annotations

import argparse
import json

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from common import MARGIN, PRIMARY, add_mode_args, mode_from_args

from aeo_research.plotting import (
    BLUE_RAMP,
    GRID,
    INK,
    INK_MUTED,
    PLATFORM_COLORS,
    PLATFORM_MARKERS,
    save_figure,
    theme,
)

STATUS_ROWS = (
    ("R", "On the shortlist (recommended)"),
    ("WS", "Best for the same use case"),
    ("T", "The top pick"),
    ("P1", "Named first"),
    ("Pk", "In the exact same position"),
)
GAP_PANELS = (
    ("H1", "Shortlist minus exact position"),
    ("H2", "Shortlist minus top pick"),
    ("H3", "Top pick minus named first"),
    ("H7", "Shortlist minus best-for use case"),
)


def hollow(ds: str) -> bool:
    return ds == "claude_b2b"


def marker_kw(ds: str, color: str) -> dict:
    return dict(marker="o", ms=8, mec=color, mew=2,
                mfc="white" if hollow(ds) else color, zorder=3)


#: Row order for the shortlist figures: the three new platforms, then claude.ai.
SHORTLIST_ORDER = ("chatgpt_b2b", "claude_api_b2b", "claude_b2b", "gemini_b2b")
NEW_PLATFORMS = ("chatgpt_b2b", "claude_api_b2b", "gemini_b2b")
#: Runs shortlisted (out of 7) -> bin, light (one-off) to dark (every run).
RUN_BINS = (
    ("In every run", lambda c: c == 7, BLUE_RAMP[4], "white"),
    ("In 5 or 6 runs", lambda c: c in (5, 6), BLUE_RAMP[3], "white"),
    ("In 2 to 4 runs", lambda c: 2 <= c <= 4, BLUE_RAMP[2], INK),
    ("In one run only", lambda c: c == 1, BLUE_RAMP[0], INK),
)


def f0_shortlist(res: dict, outdir, tag: str) -> None:
    meta, desc = res["meta"], res["descriptives"]
    datasets = [ds for ds in SHORTLIST_ORDER if ds in desc and desc[ds].get("headline_R")]
    if not datasets:
        print("no shortlist levels in the model results; F0 skipped")
        return
    fig, ax = plt.subplots(figsize=(12, 1.1 * len(datasets) + 2.2))
    y = np.arange(len(datasets))[::-1]
    for yi, ds in zip(y, datasets):
        est, lo, hi = desc[ds]["headline_R"]
        color = PLATFORM_COLORS[meta["color_keys"][ds]]
        ax.hlines(yi, lo, hi, color=color, lw=2.5, zorder=2)
        ax.plot([est], [yi], **{**marker_kw(ds, color), "ms": 11})
        ax.text(hi + 0.015, yi, f"{est:.0%}", va="center", fontsize=13, color=INK,
                fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{meta['labels'][ds]}  ({meta['n_answers'][ds]:,} answers)"
                        for ds in datasets], fontsize=12)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.6, len(datasets) - 0.4)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Share of shortlisted vendors shortlisted again in another run")
    fig.suptitle(f"When AI shortlists a vendor, how often it shortlists that vendor again{tag}\n"
                 "40 B2B buying questions, each asked on 7 days (claude.ai: 26 questions, 3 "
                 "runs). Dot: share. Line: 90% interval.", x=0.01, ha="left", fontsize=14,
                 color=INK, linespacing=1.6)
    save_figure(fig, outdir, "stage1_shortlist")


def f3_shortlist_runs(res: dict, outdir, tag: str) -> None:
    meta, desc = res["meta"], res["descriptives"]
    datasets = [ds for ds in SHORTLIST_ORDER if ds in NEW_PLATFORMS and ds in desc
                and desc[ds].get("runs_shortlisted")]
    if not datasets:
        print("no runs-shortlisted counts in the model results; F3 skipped")
        return
    fig, ax = plt.subplots(figsize=(12, 1.0 * len(datasets) + 3.0))
    y = np.arange(len(datasets))[::-1]
    for yi, ds in zip(y, datasets):
        hist = {int(k.split("/")[0]): v for k, v in desc[ds]["runs_shortlisted"].items()
                if k.endswith("/7")}
        slots = {c: c * n for c, n in hist.items()}  # appearances, not vendors
        total = sum(slots.values())
        left = 0.0
        for label, test, color, text_color in RUN_BINS:
            share = sum(v for c, v in slots.items() if test(c)) / total
            ax.barh(yi, share, left=left, height=0.62, color=color, edgecolor="white",
                    linewidth=2, label=label if yi == y[0] else None)
            if share >= 0.035:
                ax.text(left + share / 2, yi, f"{share:.0%}", ha="center", va="center",
                        fontsize=11, color=text_color)
            left += share
    ax.set_yticks(y)
    ax.set_yticklabels([meta["labels"][ds] for ds in datasets], fontsize=12)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(False)
    ax.set_xlabel("Share of all shortlist places across the 7 runs of a question")
    ax.legend(ncol=4, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=11)
    fig.suptitle(f"Most of each shortlist is a stable core of vendors{tag}\n"
                 "Each place on a shortlist, by how many of the question's 7 runs that vendor "
                 "was shortlisted in.", x=0.01, ha="left", fontsize=14, color=INK,
                 linespacing=1.6)
    fig.subplots_adjust(top=0.70)
    save_figure(fig, outdir, "stage1_shortlist_runs")


def f4_platform_agreement(res: dict, outdir, tag: str) -> None:
    meta, desc = res["meta"], res["descriptives"]
    cross = desc.get("cross_platform") or {}
    within = [ds for ds in SHORTLIST_ORDER if ds in NEW_PLATFORMS and ds in desc]
    if not cross or not within:
        print("no cross-platform agreement in the model results; F4 skipped")
        return
    rows = [(f"{meta['labels'][ds]}, asked again", desc[ds]["headline_R"],
             PLATFORM_COLORS[meta["color_keys"][ds]]) for ds in within]
    for key, v in cross.items():
        a, b = key.split("|")
        rows.append((f"{meta['labels'][a]} vs {meta['labels'][b]}, same day", v["R"], INK_MUTED))
    fig, ax = plt.subplots(figsize=(12, 0.62 * len(rows) + 2.6))
    y = np.arange(len(rows))[::-1].astype(float)
    y[len(within):] -= 0.6  # a gap between the two groups
    for yi, (_, (est, lo, hi), color) in zip(y, rows):
        ax.hlines(yi, lo, hi, color=color, lw=2.5, zorder=2)
        ax.plot([est], [yi], marker="o", ms=10, color=color, mec=color, zorder=3)
        ax.text(hi + 0.015, yi, f"{est:.0%}", va="center", fontsize=12, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=12)
    ax.set_xlim(0, 1.0)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Shortlist overlap for the same buying question")
    fig.suptitle(f"Each platform repeats its own shortlist more than it agrees with the "
                 f"others{tag}\nSame question, same platform on another day, against two "
                 "platforms on the same day. Dot: overlap. Line: 90% interval.", x=0.01,
                 ha="left", fontsize=14, color=INK, linespacing=1.6)
    save_figure(fig, outdir, "stage1_platform_agreement")


def f1_retention(res: dict, outdir, tag: str) -> None:
    meta = res["meta"]
    datasets = [ds for ds in PRIMARY if ds in res["levels"]]
    if not datasets:
        print("no primary datasets in the model results; F1 skipped")
        return
    n = len(datasets)
    ncols = 2 if n > 1 else 1
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 3.0 * nrows + 1.6), sharex=True,
                             squeeze=False)
    y = np.arange(len(STATUS_ROWS))[::-1]
    for k, ds in enumerate(datasets):
        ax = axes[k // ncols][k % ncols]
        color = PLATFORM_COLORS[meta["color_keys"][ds]]
        lv = res["levels"][ds]
        for yi, (key, _) in zip(y, STATUS_ROWS):
            cell = (lv.get(key) or {}).get("within")
            if not cell or cell[0] is None:
                ax.text(0.02, yi, "not available", va="center", fontsize=9, color=INK_MUTED)
                continue
            est, lo, hi = cell
            ax.hlines(yi, lo, hi, color=color, lw=2, zorder=2)
            ax.plot([est], [yi], **marker_kw(ds, color))
            if key in ("R", "Pk"):
                ax.text(hi + 0.02, yi, f"{est:.2f}", va="center", fontsize=10, color=INK)
        ax.set_yticks(y)
        ax.set_yticklabels([lab for _, lab in STATUS_ROWS] if k % ncols == 0 else [])
        ax.set_xlim(0, 1.08)
        ax.set_ylim(-0.6, len(STATUS_ROWS) - 0.4)
        ax.grid(axis="x", color=GRID)
        ax.grid(axis="y", visible=False)
        ax.set_title(f"{meta['labels'][ds]} ({meta['n_answers'][ds]:,} answers)", fontsize=12)
    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")
    for ax in axes[-1]:
        ax.set_xlabel("Share kept in another run")
    fig.suptitle(f"How often a vendor keeps its place from one run to the next{tag}\n"
                 "The same question asked again in another run. Dot: share kept. Line: 90% "
                 "interval.", x=0.01, ha="left", fontsize=14, color=INK, linespacing=1.6)
    save_figure(fig, outdir, "stage1_retention")


def f2_gaps(res: dict, outdir, tag: str) -> None:
    meta = res["meta"]
    rows = {}
    for sec in ("primary", "secondary"):
        for r in res.get(sec, []):
            if r.get("test") in dict(GAP_PANELS) and r.get("estimate") is not None:
                rows[(r["dataset"], r["test"])] = r
    datasets = [ds for ds in PRIMARY if any((ds, t) in rows for t, _ in GAP_PANELS)]
    if not datasets:
        print("no tested differences in the model results; F2 skipped")
        return
    fig, axes = plt.subplots(1, len(GAP_PANELS), figsize=(13, max(3.6, 2.0 + 0.6 * len(datasets))),
                             sharey=True)
    y = np.arange(len(datasets))[::-1]
    for ax, (test, title) in zip(axes, GAP_PANELS):
        ax.axvline(0, color=INK_MUTED, lw=1)
        ax.axvline(MARGIN, color=INK_MUTED, lw=1, ls="--")
        for yi, ds in zip(y, datasets):
            r = rows.get((ds, test))
            if not r or r.get("lo") is None:
                continue
            color = PLATFORM_COLORS[meta["color_keys"][ds]]
            ax.hlines(yi, r["lo"], r["hi"], color=color, lw=2, zorder=2)
            ax.plot([r["estimate"]], [yi], **marker_kw(ds, color))
        ax.set_title(title, fontsize=11)
        ax.set_yticks(y)
        ax.set_yticklabels([meta["labels"][ds] for ds in datasets])
        ax.grid(axis="x", color=GRID)
        ax.grid(axis="y", visible=False)
    for ax in axes:
        ax.set_xlabel("Difference in share kept")
    fig.suptitle(f"Which status holds up better between runs{tag}\n"
                 "Dot: difference. Line: 90% interval. Dashed line: the 0.10 margin the study "
                 "tests against.", x=0.01, ha="left", fontsize=13, color=INK, linespacing=1.6)
    save_figure(fig, outdir, "stage1_gaps")


# ------------------------------------------------------------------ Stage 2

S2_ORDER = ("chatgpt_b2b", "gemini_b2b", "claude_api_b2b")
#: Bins with fewer pairs than this (about one per prompt) are left off the
#: lines; they are in the model tables.
S2_MIN_PAIRS = 40
S2_STATUS = (("R", "On the shortlist", "-", "o"), ("WS", "Best for the same use case", "--", "s"),
             ("T", "The top pick", ":", "^"))


def s2_points(curve: dict, key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    bins = [b for b in curve["bins"] if b["pairs"] >= S2_MIN_PAIRS and b[key][0] is not None]
    x = np.array([b["mean_lag"] for b in bins])
    est, lo, hi = (np.array([b[key][i] for b in bins], dtype=float) for i in range(3))
    return x, est, lo, hi


def s2_days_axis(ax) -> None:
    ax.set_xlim(-0.5, 36)
    ax.set_xticks([0, 7, 14, 21, 28, 35])
    ax.set_ylim(0, 1.0)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="y", color=GRID)
    ax.grid(axis="x", visible=False)


def change_words(r: dict | None) -> str:
    """H5 in words for the legend: the change a month apart against a day or two apart."""
    if not r or r.get("estimate") is None:
        return ""
    pts = round(100 * r["estimate"])
    if pts == 0:
        return ": no change a month apart against a day or two apart"
    unit = "point" if abs(pts) == 1 else "points"
    return f": {abs(pts)} {unit} {'lower' if pts < 0 else 'higher'} a month apart than a day or two apart"


def s0_shortlist_by_lag(res: dict, outdir, tag: str) -> None:
    meta, curves = res["meta"], (res.get("descriptives") or {}).get("curve") or {}
    datasets = [ds for ds in S2_ORDER if ds in curves]
    if not datasets:
        print("no lag curves in the Stage 2 model results; S0 skipped")
        return
    h5 = {r["dataset"]: r for r in res.get("primary", [])}
    fig, ax = plt.subplots(figsize=(12, 6.4))
    for lo, hi in ((1, 2), (27, 34)):
        ax.axvspan(lo - 0.5, hi + 0.5, color=GRID, alpha=0.35, lw=0, zorder=0)
    ax.text(1.5, 0.03, "1 to 2\ndays", ha="center", va="bottom", fontsize=10, color=INK_MUTED)
    ax.text(30.5, 0.03, "27 days\nor more", ha="center", va="bottom", fontsize=10,
            color=INK_MUTED)
    ends = []
    for ds in datasets:
        x, est, lo, hi = s2_points(curves[ds], "R")
        color = PLATFORM_COLORS[meta["color_keys"][ds]]
        marker = PLATFORM_MARKERS.get(meta["color_keys"][ds], "o")
        ax.fill_between(x, lo, hi, color=color, alpha=0.15, lw=0, zorder=1)
        ax.plot(x, est, color=color, lw=2, marker=marker, ms=8, mec="white", mew=1.5,
                zorder=3, label=f"{meta['labels'][ds]}{change_words(h5.get(ds))}")
        ends.append([est[-1], x[-1], f"{meta['labels'][ds]} {est[-1]:.0%}"])
    # direct labels at the line ends, nudged apart so they never overlap
    ends.sort()
    for k in range(1, len(ends)):
        ends[k][0] = max(ends[k][0], ends[k - 1][0] + 0.045)
    for yv, xv, text in ends:
        ax.text(xv + 0.6, yv, text, va="center", fontsize=11, color=INK)
    s2_days_axis(ax)
    ax.set_xlim(-0.5, 39)
    ax.set_xlabel("Days between the two answers to the same question")
    ax.set_ylabel("Shortlisted vendors shortlisted again")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 0.12), frameon=False, fontsize=11)
    fig.suptitle(f"How often AI shortlists a vendor again, by days between the answers{tag}\n"
                 "40 B2B buying questions asked on 11 days over five weeks. Line: share. Band: "
                 "90% interval. Shaded: the two gaps the study compares.", x=0.01, ha="left",
                 fontsize=14, color=INK, linespacing=1.6)
    fig.subplots_adjust(top=0.84)
    save_figure(fig, outdir, "stage2_shortlist_by_lag")


def s1_status_by_lag(res: dict, outdir, tag: str) -> None:
    meta, curves = res["meta"], (res.get("descriptives") or {}).get("curve") or {}
    datasets = [ds for ds in S2_ORDER if ds in curves]
    if not datasets:
        print("no lag curves in the Stage 2 model results; S1 skipped")
        return
    fig, axes = plt.subplots(1, len(datasets), figsize=(13, 6.0), sharey=True, squeeze=False)
    for ax, ds in zip(axes[0], datasets):
        color = PLATFORM_COLORS[meta["color_keys"][ds]]
        for key, label, ls, marker in S2_STATUS:
            x, est, lo, hi = s2_points(curves[ds], key)
            if not x.size:
                continue
            ax.fill_between(x, lo, hi, color=color, alpha=0.10, lw=0, zorder=1)
            ax.plot(x, est, color=color, lw=2, ls=ls, marker=marker, ms=8, mec="white",
                    mew=1.5, zorder=3, label=label)
        s2_days_axis(ax)
        ax.set_title(f"{meta['labels'][ds]} ({meta['n_answers'][ds]:,} answers)", fontsize=12)
        ax.set_xlabel("Days between the two answers")
    axes[0][0].set_ylabel("Share kept in the other answer")
    handles = [Line2D([], [], color=INK_MUTED, lw=2, ls=ls, marker=marker, ms=8, label=label)
               for _, label, ls, marker in S2_STATUS]
    leg = axes[0][0].legend(handles=handles, loc="lower left", bbox_to_anchor=(-0.02, 1.07),
                            ncol=3, frameon=False, fontsize=11)
    leg.set_in_layout(False)  # keeps the wide legend from squeezing the panels
    fig.suptitle(f"The shortlist, the use case and the top pick over five weeks{tag}\n"
                 "Same question, answers some days apart. Line: share kept. Band: 90% "
                 "interval.\n ", x=0.01, ha="left", fontsize=14, color=INK, linespacing=1.6)
    fig.subplots_adjust(top=0.72)
    save_figure(fig, outdir, "stage2_status_by_lag")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_mode_args(ap)
    a = ap.parse_args()
    mode = mode_from_args(a)
    path = mode.results / f"stage{mode.stage}_model.json"
    if not path.exists():
        raise SystemExit(f"no {path.name}; run 22_model.py first")
    res = json.loads(path.read_text())
    if not res["meta"].get("h_pos_passed"):
        raise SystemExit("H_pos failed in 22_model.py: no figures (spec §7.1)")
    tag = {"synthetic": " (synthetic test data)", "explore": " (exploration data)"}.get(
        mode.kind, "")
    theme()
    if mode.stage == 2:
        s0_shortlist_by_lag(res, mode.figures, tag)
        s1_status_by_lag(res, mode.figures, tag)
        print(f"wrote figures to {mode.figures}")
        return
    f0_shortlist(res, mode.figures, tag)
    f3_shortlist_runs(res, mode.figures, tag)
    f4_platform_agreement(res, mode.figures, tag)
    f1_retention(res, mode.figures, tag)
    f2_gaps(res, mode.figures, tag)
    print(f"wrote figures to {mode.figures}")


if __name__ == "__main__":
    main()
