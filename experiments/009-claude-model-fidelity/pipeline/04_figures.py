"""Stage 04 — watermarked figures (spec §9) -> results/figures/*.{svg,png}.

F1 gap-vs-cost  LEAD. Two panels (brands named, domains cited). Each API arm
   is a point: x = measured $/call (ledger, batch-priced, cache effects
   included), y = its same-prompt, same-day Jaccard with claude.ai
   (``cross:arm|ui_default``) with the 90% cluster-bootstrap CI. The shaded
   band is claude.ai's own day-to-day floor (``within:ui_default``, 90% CI)
   and the dashed line sits 0.10 below the floor: an arm whose CI stays above
   it is within the equivalence band, so the vertical distance from the band
   is the gap the tests price. An arm over the Audit A no-search limit is
   drawn hollow on the domain panel (its domain claims are INCONCLUSIVE).
F2 brand-gap  Per-answer gap to claude.ai for every API arm, in two panels:
   which brands (H1b/H1-ref brand-set Jaccard gap) and their order (RBO
   gap), each with the interval its verdict used (Holm-adjusted for the
   three primary arms) and the +/-0.10 equivalence band. Stories 1 and 2.
F3 panel-agreement  The per-category vendor lists (H1s, descriptive, spec
   deviation 9) for every API arm against claude.ai: (a) same vendors in the
   same order (panel RBO) and (b) same vendors in any order (Jaccard of the
   vendors named in at least 2 of 6 answers), with claude.ai's High setting
   against its default as the same-surface reference band.
F4 reasoning-level  H2: the reasoning-level gaps (claude.ai High vs Medium;
   Sonnet 5 default vs low effort) on brands and cited domains with the
   +/-0.10 band, next to searches per answer for the same four arms.

Reads only ``results/model_results.json`` from 03_model, so it computes no
metric of its own and cannot run on real data before 03_model has passed its
pre-registration gate. Color follows the model family (Opus, Sonnet, Haiku)
in the theme's fixed categorical order; marker shape follows the request
configuration.

Usage:
  uv run python experiments/009-claude-model-fidelity/pipeline/04_figures.py
  uv run python .../04_figures.py --synthetic planted
"""

from __future__ import annotations

import argparse
import json

import matplotlib.pyplot as plt
from common import (
    API_ARMS,
    NO_SEARCH_MAX,
    REFERENCE,
    SESOI,
    SYNTHETIC_WORLDS,
    cross,
    figures_dir,
    results_dir,
    within,
)

from aeo_research.plotting import CATEGORICAL, INK_MUTED, save_figure, theme

FAMILY_COLOR = {"opus": CATEGORICAL[0], "sonnet": CATEGORICAL[1], "haiku": CATEGORICAL[2]}
FAMILY_LABEL = {"opus": "Opus 5.5", "sonnet": "Sonnet 5", "haiku": "Haiku 4.5"}
ARM_LABEL = {
    "opus55_plain": "no system prompt",
    "opus55_leak": "leaked claude.ai prompt",
    "sonnet5_plain": "no system prompt",
    "sonnet5_leak_think": "leaked prompt",
    "sonnet5_leak_low": "leaked prompt, low effort",
    "sonnet5_prod": "production request",
    "haiku45_leak": "leaked prompt",
}
ARM_MARKER = {
    "opus55_plain": "o", "opus55_leak": "s", "sonnet5_plain": "o", "sonnet5_leak_think": "s",
    "sonnet5_leak_low": "D", "sonnet5_prod": "v", "haiku45_leak": "s",
}
PANELS = (("brand_j", "Brands named"), ("cited_j", "Domains cited"))

#: Bottom-to-top plotting order for the per-arm dot plots (F2, F3): the
#: closest configurations sit at the top.
ARM_ORDER = (
    "haiku45_leak", "sonnet5_prod", "sonnet5_leak_low", "sonnet5_plain",
    "sonnet5_leak_think", "opus55_plain", "opus55_leak",
)
VERDICT_LABEL = {
    "REAL": "real gap",
    "NEGLIGIBLE": "small, inside the band",
    "NULL": "equivalent",
    "INCONCLUSIVE": "inconclusive",
}
GAP_SECTIONS = ("H1b_primary", "H1b_secondary", "H1_ref")


def family(arm: str) -> str:
    return arm.split("5", 1)[0].rstrip("4")


def level(rows: list[dict], metric: str, condition: str) -> dict | None:
    return next((r for r in rows if r.get("section") == "level" and r.get("metric") == metric
                 and r.get("test") == f"level {condition}"), None)


def f1_gap_vs_cost(results: dict, outdir, synthetic: str | None) -> None:
    rows = results["rows"]
    cost = {d["arm"]: d.get("usd_call") for d in results["descriptives"]["by_arm"]}
    no_search = results["meta"].get("no_search_rate") or {}
    fig = plt.figure(figsize=(12, 6.8))
    grid = fig.add_gridspec(2, 2, height_ratios=[5, 1.1])
    axes = [fig.add_subplot(grid[0, 0])]
    axes.append(fig.add_subplot(grid[0, 1], sharey=axes[0]))
    legend_ax = fig.add_subplot(grid[1, :])
    legend_ax.axis("off")
    xs = [cost[a] for a in API_ARMS if cost.get(a) is not None]
    x_max = max(xs) * 1.15 if xs else 1.0
    for ax, (metric, title) in zip(axes, PANELS):
        floor = level(rows, metric, within(REFERENCE))
        if floor:
            ax.axhspan(floor["lo"], floor["hi"], color=INK_MUTED, alpha=0.15, lw=0,
                       label="claude.ai vs itself, across days (90% CI)")
            ax.axhline(floor["estimate"], color=INK_MUTED, lw=1)
            ax.axhline(floor["estimate"] - SESOI, color=INK_MUTED, lw=1, ls="--",
                       label=f"{SESOI:.2f} below the floor (equivalence edge)")
        for arm in API_ARMS:
            r = level(rows, metric, cross(arm, REFERENCE))
            if r is None or cost.get(arm) is None:
                continue
            hollow = metric == "cited_j" and (no_search.get(arm, 0) > NO_SEARCH_MAX
                                              or no_search.get(REFERENCE, 0) > NO_SEARCH_MAX)
            color = FAMILY_COLOR[family(arm)]
            ax.errorbar(cost[arm], r["estimate"],
                        yerr=[[max(0.0, r["estimate"] - r["lo"])], [max(0.0, r["hi"] - r["estimate"])]],
                        fmt=ARM_MARKER[arm], color=color, ms=9, capsize=3, lw=1.3,
                        mfc="white" if hollow else color, mec=color)
        ax.set_title(title)
        ax.set_xlim(0, x_max)
        ax.set_xlabel("Measured cost per API call (USD, batch pricing)")
    axes[0].set_ylabel("Same-prompt, same-day Jaccard with claude.ai")
    axes[0].set_ylim(0, 1)
    handles = [plt.Line2D([], [], marker=ARM_MARKER[a], ls="", ms=8,
                          color=FAMILY_COLOR[family(a)],
                          label=f"{FAMILY_LABEL[family(a)]}: {ARM_LABEL[a]}") for a in API_ARMS]
    h, _ = axes[0].get_legend_handles_labels()
    legend_ax.legend(handles=handles + h, fontsize=8.5, loc="center", ncol=3)
    banner = "SYNTHETIC DRY RUN: " if synthetic else ""
    fig.suptitle(f"{banner}How closely cheaper Claude API calls match claude.ai on Opus 5.5, "
                 "by cost", x=0.01, ha="left", fontsize=14)
    save_figure(fig, outdir, "gap-vs-cost")


def note_grid(width_ratios=(1, 1), sharey: bool = True):
    """A figure with one row of panels and a thin text row for the note.

    The note lives in its own axes so tight_layout keeps it clear of the
    footer band that save_figure reserves for the caption and watermark.
    """
    fig = plt.figure(figsize=(12, 6.6))
    grid = fig.add_gridspec(2, len(width_ratios), height_ratios=[12, 0.7],
                            width_ratios=list(width_ratios))
    axes = [fig.add_subplot(grid[0, 0])]
    for k in range(1, len(width_ratios)):
        axes.append(fig.add_subplot(grid[0, k], sharey=axes[0] if sharey else None))
        if sharey:
            axes[-1].tick_params(labelleft=False)
    note_ax = fig.add_subplot(grid[1, :])
    note_ax.axis("off")
    return fig, axes, note_ax


def write_note(note_ax, text: str) -> None:
    note_ax.text(0, 0.5, text, fontsize=9, color=INK_MUTED, ha="left", va="center",
                 transform=note_ax.transAxes)


def arm_label(arm: str) -> str:
    return f"{FAMILY_LABEL[family(arm)]}: {ARM_LABEL[arm]}"


def find(rows: list[dict], section: str | tuple[str, ...], test: str, metric: str) -> dict | None:
    sections = (section,) if isinstance(section, str) else section
    return next((r for r in rows if r.get("section") in sections and r.get("test") == test
                 and r.get("metric") == metric), None)


def _gap_panel(ax, rows: list[dict], title: str, xlabel: str) -> None:
    """Horizontal dot plot of per-arm gaps with the +/-SESOI band."""
    ax.axvspan(-SESOI, SESOI, color=INK_MUTED, alpha=0.12, lw=0)
    ax.axvline(0, color=INK_MUTED, lw=1)
    for y, (label, arm, r) in enumerate(rows):
        if r is None:
            continue
        color = FAMILY_COLOR[family(arm)] if arm in FAMILY_COLOR_ARMS else INK_MUTED
        marker = ARM_MARKER.get(arm, "o")
        ax.errorbar(r["estimate"], y, xerr=[[r["estimate"] - r["lo"]], [r["hi"] - r["estimate"]]],
                    fmt=marker, color=color, mfc=color, mec=color, ms=8, capsize=3, lw=1.3)
        ax.annotate(VERDICT_LABEL.get(r.get("verdict", ""), ""), (r["hi"], y),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=9,
                    color=INK_MUTED)
    ax.set_yticks(range(len(rows)), [label for label, _, _ in rows])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)


FAMILY_COLOR_ARMS = set(API_ARMS)


def f2_brand_gap(results: dict, outdir, synthetic: str | None) -> None:
    rows = results["rows"]
    sets = [(arm_label(a), a, find(rows, GAP_SECTIONS, f"H1b {a}", "brand_j")) for a in ARM_ORDER]
    order = [(arm_label(a), a, find(rows, "rbo_gap", f"gap {a}", "brand_rbo")) for a in ARM_ORDER]
    fig, axes, note_ax = note_grid()
    xlabel = "Gap to claude.ai (0 = as close as claude.ai is to itself across days)"
    _gap_panel(axes[0], sets, "Which brands are named", xlabel)
    _gap_panel(axes[1], order, "The order they are named in", xlabel)
    hi = max(r["hi"] for _, _, r in sets + order if r)
    for ax in axes:
        ax.set_xlim(-0.15, max(0.36, hi + 0.12))
    banner = "SYNTHETIC DRY RUN: " if synthetic else ""
    fig.suptitle(f"{banner}No Sonnet or Haiku configuration matched the brands named by "
                 "claude.ai on Opus 5.5", x=0.01, ha="left", fontsize=14)
    write_note(note_ax, "Shaded: the +/-0.10 equivalence band. Whiskers: 90% intervals "
               "(Holm-adjusted 95% to 97% for the Sonnet no-prompt and leaked-prompt arms).")
    save_figure(fig, outdir, "brand-gap")


def f3_panel_agreement(results: dict, outdir, synthetic: str | None) -> None:
    rows = results["rows"]
    panels = (("panel_rbo", "(a) Same vendors, same order", "Rank-biased overlap of the category "
               "vendor rankings"),
              ("panel_jaccard_third", "(b) Same vendors, any order", "Overlap of vendors named "
               "in at least 2 of 6 answers"))
    fig, axes, note_ax = note_grid()
    for ax, (metric, title, xlabel) in zip(axes, panels):
        ref = find(rows, "H1s", "H1s panel ui_think", metric)
        if ref:
            ax.axvspan(ref["lo"], ref["hi"], color=INK_MUTED, alpha=0.15, lw=0)
            ax.axvline(ref["estimate"], color=INK_MUTED, lw=1)
        for y, arm in enumerate(ARM_ORDER):
            r = find(rows, "H1s", f"H1s panel {arm}", metric)
            if r is None:
                continue
            color = FAMILY_COLOR[family(arm)]
            ax.errorbar(r["estimate"], y, xerr=[[r["estimate"] - r["lo"]], [r["hi"] - r["estimate"]]],
                        fmt=ARM_MARKER[arm], color=color, ms=8, capsize=3, lw=1.3)
        ax.set_yticks(range(len(ARM_ORDER)), [arm_label(a) for a in ARM_ORDER])
        ax.set_ylim(-0.6, len(ARM_ORDER) - 0.4)
        ax.set_xlim(0.4, 1.0)
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
    banner = "SYNTHETIC DRY RUN: " if synthetic else ""
    fig.suptitle(f"{banner}Per-category vendor lists compared with claude.ai on Opus 5.5 "
                 "(1 = identical)", x=0.01, ha="left", fontsize=14)
    write_note(note_ax, "Gray band and line: claude.ai High against claude.ai Medium, the "
               "same product at a different setting. Whiskers: 90% intervals over the 20 "
               "categories.")
    save_figure(fig, outdir, "panel-agreement")


def f4_reasoning_level(results: dict, outdir, synthetic: str | None) -> None:
    rows = results["rows"]
    pairs = (("ui_default vs ui_think", "claude.ai: High vs Medium"),
             ("sonnet5_leak_think vs sonnet5_leak_low", "Sonnet 5 API: default vs low effort"))
    metrics = (("cited_j", "domains cited"), ("brand_j", "brands named"))
    gap_rows = []
    for test, label in reversed(pairs):
        for metric, mlabel in metrics:
            gap_rows.append((f"{label}, {mlabel}", "", find(rows, "H2", f"H2 {test}", metric)))
    fig, (ax, bx), note_ax = note_grid((1.5, 1), sharey=False)
    _gap_panel(ax, gap_rows, "Reasoning level and what gets named",
               "Gap between the two settings (0 = as close as each is to itself)")
    ax.set_xlim(-0.15, 0.2)
    by_arm = {d["arm"]: d for d in results["descriptives"]["by_arm"]}
    bars = (("ui_default", "claude.ai Medium"), ("ui_think", "claude.ai High"),
            ("sonnet5_leak_low", "Sonnet 5, low effort"), ("sonnet5_leak_think", "Sonnet 5, default"))
    colors = [CATEGORICAL[0], CATEGORICAL[0], CATEGORICAL[1], CATEGORICAL[1]]
    vals = [by_arm[a]["searches"] if a in by_arm else 0.0 for a, _ in bars]
    bx.barh(range(len(bars)), vals, color=colors,
            alpha=0.9, height=0.6)
    for y, v in enumerate(vals):
        bx.annotate(f"{v:.1f}", (v, y), xytext=(4, 0), textcoords="offset points", va="center",
                    fontsize=10)
    bx.set_yticks(range(len(bars)), [label for _, label in bars])
    bx.invert_yaxis()
    bx.set_xlim(0, max(vals + [1.0]) * 1.25)
    bx.set_title("Web searches per answer")
    bx.set_xlabel("Mean searches per answer")
    bx.grid(axis="y", visible=False)
    bx.grid(axis="x", visible=True)
    banner = "SYNTHETIC DRY RUN: " if synthetic else ""
    fig.suptitle(f"{banner}A higher reasoning level searched more but named the same brands",
                 x=0.01, ha="left", fontsize=14)
    write_note(note_ax, "Shaded: the +/-0.10 equivalence band. Whiskers: 90% intervals.")
    save_figure(fig, outdir, "reasoning-level")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    a = ap.parse_args()

    path = results_dir(a.synthetic) / "model_results.json"
    if not path.exists():
        raise SystemExit(f"no {path}; run 03_model.py first (it gates the real data)")
    results = json.loads(path.read_text())
    meta = results["meta"]
    if (meta.get("synthetic") or None) != a.synthetic:
        raise SystemExit("model_results.json does not belong to this world; refusing")
    if not meta.get("h_pos_passed"):
        raise SystemExit("H_pos failed in model_results.json; the study stopped, no figures")
    theme()
    outdir = figures_dir(a.synthetic)
    f1_gap_vs_cost(results, outdir, a.synthetic)
    f2_brand_gap(results, outdir, a.synthetic)
    f3_panel_agreement(results, outdir, a.synthetic)
    f4_reasoning_level(results, outdir, a.synthetic)
    for name in ("gap-vs-cost", "brand-gap", "panel-agreement", "reasoning-level"):
        print(f"wrote {outdir / name}.svg and .png")


if __name__ == "__main__":
    main()
