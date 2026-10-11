"""Stage 24: watermarked Stage 1 figures (spec §9) -> results/figures/stage1_*.{svg,png}.

F1 stage1_retention  LEAD. Retention by status, a dot plot with 90% intervals:
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

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/24_figures.py --stage 1
  uv run python .../24_figures.py --stage 1 --split explore | --synthetic planted
"""

from __future__ import annotations

import argparse
import json

import matplotlib.pyplot as plt
import numpy as np
from common import MARGIN, PRIMARY, add_mode_args, mode_from_args

from aeo_research.plotting import GRID, INK, INK_MUTED, PLATFORM_COLORS, save_figure, theme

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
    f1_retention(res, mode.figures, tag)
    f2_gaps(res, mode.figures, tag)
    print(f"wrote figures to {mode.figures}")


if __name__ == "__main__":
    main()
