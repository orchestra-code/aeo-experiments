"""Stage 04: watermarked figures -> results/figures/*.{svg,png}.

F1 brand-gap  LEAD. Gap to claude.ai for the three Claude Code arms in two panels: which
   brands are named (H1 brand-set Jaccard gap) and their order (RBO gap). Each whisker is
   the interval its verdict used (95% Holm-adjusted for the first-ranked primary arm, 90%
   otherwise), with the +/-0.10 equivalence band. ``opus55_plain`` is left out; it is in
   the appendix figure.
F2 scheduled-vs-local  H3 (the scheduled task against a local run) next to the level
   overlaps it is built from: each arm against itself across days, the two arms against
   each other on the same day, and claude.ai against itself.
F3 search-behavior  Searches per answer and answer length for claude.ai and the Claude
   Code arms. The scheduled task has no search count (a subagent's searches are not in
   the pulled transcript), so its search bar is marked n/a.
F4 claude-ai-then-now  claude.ai (``ui_default``) in 009's waves 1 to 3 against 011's:
   searches per answer and the share of answers with no search, from each study's
   stored feature frame. 009's export parser knew only ``web_search`` and
   ``web_search_fast``, and 009's exports contain no other search tool name, so its
   counts are complete (011 spec, deviation 1).
F5 api-appendix  Low-emphasis appendix: the H1 brand-set gap for all four arms,
   ``opus55_plain`` included, with 009's published ``opus55_plain`` gap as a reference.

Every number comes from ``results/model_results.json`` (03_model), the interim feature
frame, or 009's stored results and frame. Nothing is hardcoded. No figure shows a brand,
domain, prompt or answer text.

Usage (repo root):
  uv run python experiments/011-claude-code-fidelity/pipeline/04_figures.py
"""

from __future__ import annotations

import json
from datetime import date

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd
from common import (
    ANCHOR,
    EXP009,
    REFERENCE,
    RESULTS,
    SESOI,
    cross,
    load_features,
    within,
)

from aeo_research.plotting import BLUE_RAMP, CATEGORICAL, INK, INK_MUTED, save_figure, theme

FIGURES = RESULTS / "figures"
FEATURES_009 = EXP009 / "data" / "interim" / "features.jsonl"
RESULTS_009 = EXP009 / "results" / "model_results.json"

ARM_LABEL = {
    "ui_default": "claude.ai (by hand)",
    "sched_kit": "Scheduled task (cloud)",
    "cc_stock_full": "Claude Code, local, stock",
    "cc_none_search": "Claude Code, local, no system prompt",
    "opus55_plain": "Claude API, Opus 5.5",
}
#: Color follows the arm in a fixed categorical order; claude.ai, the reference, is ink.
ARM_COLOR = {
    "ui_default": INK,
    "sched_kit": CATEGORICAL[0],
    "cc_stock_full": CATEGORICAL[1],
    "cc_none_search": CATEGORICAL[2],
    "opus55_plain": CATEGORICAL[3],
}
ARM_MARKER = {"sched_kit": "o", "cc_stock_full": "s", "cc_none_search": "D", "opus55_plain": "^",
              "ui_default": "o"}
#: Bottom-to-top order in the dot plots, so the scheduled task sits at the top.
CC_ORDER = ("cc_none_search", "cc_stock_full", "sched_kit")
VERDICT_LABEL = {
    "REAL": "real gap",
    "NEGLIGIBLE": "small, inside the band",
    "NULL": "equivalent",
    "INCONCLUSIVE": "inconclusive",
}
MONTHS = ("Jan", "Feb", "March", "April", "May", "June", "July", "Aug", "Sept", "Oct", "Nov",
          "Dec")
GAP_XLABEL = "Gap to claude.ai (0 = as close as claude.ai is to itself across days)"


# ----------------------------------------------------------------- helpers


def find(rows: list[dict], test: str, metric: str) -> dict:
    r = next((r for r in rows if r.get("test") == test and r.get("metric") == metric), None)
    if r is None:
        raise SystemExit(f"model_results.json has no row {test!r} / {metric!r}")
    return r


def h1_row(rows: list[dict], arm: str) -> dict:
    return next(r for r in rows if r.get("section") in ("H1_primary", "H1_secondary")
                and r.get("test") == f"H1 {arm}" and r.get("metric") == "brand_j")


def level(rows: list[dict], condition: str) -> dict:
    return find(rows, f"level {condition}", "brand_j")


def pct(x: float) -> str:
    return f"{round(100 * x)}%"


def date_range(dates) -> str:
    """'Sept 27 to Oct 1, 2026' from ISO date strings."""
    ds = sorted(date.fromisoformat(d) for d in dates if d)
    a, b = ds[0], ds[-1]
    left = f"{MONTHS[a.month - 1]} {a.day}"
    right = f"{b.day}" if a.month == b.month else f"{MONTHS[b.month - 1]} {b.day}"
    return f"{left} to {right}, {b.year}"


def note_grid(width_ratios=(1, 1), sharey: bool = True, figsize=(12, 6.6), note_h: float = 0.7):
    """One row of panels plus a thin text row for the note (kept clear of the footer)."""
    fig = plt.figure(figsize=figsize)
    grid = fig.add_gridspec(2, len(width_ratios), height_ratios=[12, note_h],
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


def gap_panel(ax, rows: list[tuple[str, dict, str, str, bool]], title: str, xlabel: str,
              annotate: str = "verdict") -> None:
    """Horizontal dot plot of gaps with the +/-SESOI band.

    ``rows`` are (label, result row, color, marker, hollow), bottom to top.
    """
    ax.axvspan(-SESOI, SESOI, color=INK_MUTED, alpha=0.12, lw=0)
    ax.axvline(0, color=INK_MUTED, lw=1)
    for y, (_, r, color, marker, hollow) in enumerate(rows):
        ax.errorbar(r["estimate"], y,
                    xerr=[[r["estimate"] - r["lo"]], [r["hi"] - r["estimate"]]],
                    fmt=marker, color=color, mfc="white" if hollow else color, mec=color,
                    ms=8, capsize=3, lw=1.3)
        verdict = VERDICT_LABEL.get(r.get("verdict") or "", "")
        text = {"verdict": verdict, "value": f"{r['estimate']:+.3f}",
                "both": f"{r['estimate']:+.3f}, {verdict}" if verdict else f"{r['estimate']:+.3f}",
                }[annotate]
        ax.annotate(text, (r["hi"], y), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=INK_MUTED)
    ax.set_yticks(range(len(rows)), [label for label, *_ in rows])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.xaxis.set_major_locator(MultipleLocator(0.1))
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)


def interval_note(rows: list[dict], names: list[str]) -> str:
    """'Whiskers: 90% intervals' plus any row whose level differs."""
    base = 0.9
    odd = [f"{n}: {pct(r['ci_level'])}, Holm-adjusted" for n, r in zip(names, rows)
           if abs(r["ci_level"] - base) > 1e-9]
    text = f"Whiskers: {pct(base)} intervals"
    return text + (f" ({'; '.join(odd)})" if odd else "") + "."


def sample_line(results: dict) -> str:
    """'40 prompts, 3 days, 120 answers per setup.' from model_results.json."""
    meta = results["meta"]
    per_arm = {d["answers"] for d in results["descriptives"]["by_arm"]}
    n_prompts = next(r["n_clusters"] for r in results["rows"] if r.get("section") == "H_pos")
    n_days = len(meta["r4_coverage"])
    per = f"{per_arm.pop()} answers per setup" if len(per_arm) == 1 else "answers vary by setup"
    return f"{n_prompts} prompts, {n_days} days, {per}."


# ----------------------------------------------------------------- figures


def f1_brand_gap(results: dict) -> None:
    rows = results["rows"]
    sets = [(ARM_LABEL[a], h1_row(rows, a), ARM_COLOR[a], ARM_MARKER[a], False)
            for a in CC_ORDER]
    order = [(ARM_LABEL[a], find(rows, f"RBO {a}", "brand_rbo"), ARM_COLOR[a], ARM_MARKER[a],
              False) for a in CC_ORDER]
    fig, axes, note_ax = note_grid()
    gap_panel(axes[0], sets, "Which brands are named", GAP_XLABEL)
    gap_panel(axes[1], order, "The order they are named in", GAP_XLABEL)
    hi = max(r["hi"] for _, r, *_ in sets + order)
    lo = min(r["lo"] for _, r, *_ in sets + order)
    for ax in axes:
        ax.set_xlim(min(-0.15, lo - 0.05), max(0.3, hi + 0.14))
    all_in_band = all(r["hi"] < SESOI and r["verdict"] in ("NULL", "NEGLIGIBLE")
                      for _, r, *_ in sets)
    title = ("All three Claude Code setups named nearly the same brands as claude.ai"
             if all_in_band else "Gap to claude.ai on the brands named, by Claude Code setup")
    fig.suptitle(title, x=0.01, ha="left", fontsize=14)
    names = ["Scheduled task, which brands" if a == "sched_kit" else ARM_LABEL[a]
             for a in CC_ORDER]
    write_note(note_ax, f"Shaded: the +/-{SESOI:.2f} equivalence band. "
               + interval_note([r for _, r, *_ in sets], names)
               + f" {sample_line(results)}")
    save_figure(fig, FIGURES, "brand-gap")


def f2_scheduled_vs_local(results: dict) -> None:
    rows = results["rows"]
    levels = [
        ("claude.ai vs itself, across days", level(rows, within(REFERENCE)), ARM_COLOR[REFERENCE]),
        ("Claude Code local vs itself, across days", level(rows, within("cc_stock_full")),
         ARM_COLOR["cc_stock_full"]),
        ("Scheduled task vs itself, across days", level(rows, within("sched_kit")),
         ARM_COLOR["sched_kit"]),
        ("Scheduled task vs Claude Code local,\nsame day", level(rows, cross("cc_stock_full",
                                                                           "sched_kit")),
         INK_MUTED),
    ]
    h3 = find(rows, "H3 sched_kit vs cc_stock_full", "brand_j")
    fig, (ax, bx), note_ax = note_grid((1.5, 1), sharey=False, note_h=1.0)
    for y, (_, r, color) in enumerate(levels):
        ax.errorbar(r["estimate"], y, xerr=[[r["estimate"] - r["lo"]], [r["hi"] - r["estimate"]]],
                    fmt="o", color=color, mfc=color, mec=color, ms=8, capsize=3, lw=1.3)
        ax.annotate(f"{r['estimate']:.2f}", (r["hi"], y), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK_MUTED)
    ax.set_yticks(range(len(levels)), [label for label, *_ in levels])
    ax.set_ylim(-0.6, len(levels) - 0.4)
    lo = min(r["lo"] for _, r, _ in levels)
    hi = max(r["hi"] for _, r, _ in levels)
    ax.set_xlim(np.floor((lo - 0.05) * 20) / 20, np.ceil((hi + 0.06) * 20) / 20)
    ax.set_title("Brand overlap on the same prompt")
    ax.set_xlabel("Mean Jaccard overlap of the brands named (1 = identical)")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)

    gap_panel(bx, [("Scheduled task\nvs Claude Code local", h3, INK_MUTED, "o", False)],
              "Gap between the two", "Gap (0 = as close as each is to itself)",
              annotate="both")
    bx.set_xlim(-0.15, max(0.4, h3["hi"] + 0.3))
    bx.set_ylim(-1.5, 1.5)
    title = ("The scheduled task and a local Claude Code run named similar brands"
             if h3["verdict"] in ("NULL", "NEGLIGIBLE") else
             "The scheduled task against a local Claude Code run")
    fig.suptitle(title, x=0.01, ha="left", fontsize=14)
    write_note(note_ax, "Left: whiskers are 90% intervals. Right: the mean of the two "
               "across-day overlaps minus their same-day overlap, with the "
               f"+/-{SESOI:.2f} equivalence band shaded.\nThe scheduled task differs from "
               "the local run in two ways at once (cloud surface, and a subagent with an "
               "added instruction), so this does not separate them.")
    save_figure(fig, FIGURES, "scheduled-vs-local")


def f3_search_behavior(df: pd.DataFrame) -> dict:
    arms = (REFERENCE, "cc_stock_full", "cc_none_search", "sched_kit")
    sizes = {int((df["arm"] == a).sum()) for a in arms}
    n_per = sizes.pop() if len(sizes) == 1 else "Up to " + str(max(sizes))
    stats = {}
    for a in arms:
        d = df[df["arm"] == a]
        s = pd.to_numeric(d["n_searches"], errors="coerce")
        stats[a] = {
            "searches": float(s.mean()) if s.notna().all() and len(s) else None,
            "median_chars": float(d["chars"].median()),
            "mean_chars": float(d["chars"].mean()),
        }
    fig, (ax, bx), note_ax = note_grid((1, 1), sharey=True)
    ys = range(len(arms))
    labels = [ARM_LABEL[a] for a in arms]
    vals = [stats[a]["searches"] for a in arms]
    known = [v for v in vals if v is not None]
    for y, a, v in zip(ys, arms, vals):
        if v is None:
            ax.annotate("n/a: not recorded for this setup", (0, y), xytext=(4, 0),
                        textcoords="offset points", va="center", fontsize=9.5, color=INK_MUTED,
                        style="italic")
            continue
        ax.barh(y, v, color=ARM_COLOR[a], height=0.6, alpha=0.9)
        ax.annotate(f"{v:.1f}", (v, y), xytext=(4, 0), textcoords="offset points", va="center",
                    fontsize=10)
    ax.set_yticks(list(ys), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, max(known) * 1.3)
    ax.set_title("Web searches per answer")
    ax.set_xlabel("Mean searches per answer")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)

    meds = [stats[a]["median_chars"] for a in arms]
    means = [stats[a]["mean_chars"] for a in arms]
    for y, a, m, mu in zip(ys, arms, meds, means):
        bx.barh(y, m, color=ARM_COLOR[a], height=0.6, alpha=0.9)
        bx.plot([mu, mu], [y - 0.36, y + 0.36], color=INK, lw=2)
        bx.annotate(f"median {m:,.0f}, mean {mu:,.0f}", (max(m, mu), y), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9.5)
    bx.set_xlim(0, max(meds + means) * 1.55)
    bx.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    bx.set_title("Answer length")
    bx.set_xlabel("Characters per answer (bar: median; black tick: mean)")
    bx.grid(axis="y", visible=False)
    bx.grid(axis="x", visible=True)

    ref = stats[REFERENCE]
    cc = [a for a in arms if a != REFERENCE]
    more = all(stats[a]["searches"] > ref["searches"] for a in cc if stats[a]["searches"])
    longer = all(stats[a]["median_chars"] > ref["median_chars"] for a in cc)
    title = ("Claude Code wrote longer answers than claude.ai, and the local runs searched more"
             if more and longer else "Searches and answer length, by setup")
    fig.suptitle(title, x=0.01, ha="left", fontsize=14)
    write_note(note_ax, f"{n_per} answers per setup. The scheduled task runs each prompt in a "
               "subagent whose searches are not in the transcript we can pull, so it has no "
               "search count.")
    save_figure(fig, FIGURES, "search-behavior")
    return stats


def f4_claude_ai_then_now(df: pd.DataFrame) -> dict:
    if not FEATURES_009.exists():
        raise SystemExit(f"no 009 feature frame at {FEATURES_009}")
    old = pd.DataFrame([json.loads(x) for x in FEATURES_009.read_text().splitlines() if x.strip()])
    old = old[(old["arm"] == REFERENCE) & old["wave"].isin([1, 2, 3])]
    new = df[df["arm"] == REFERENCE]
    studies = []
    for name, d in (("009", old), ("011", new)):
        s = pd.to_numeric(d["n_searches"], errors="raise")
        per_wave = d.assign(s=s).groupby("wave")["s"].agg(
            searches="mean", no_search=lambda x: float((x == 0).mean()))
        studies.append({
            "study": name,
            "label": f"Experiment {name}\n{date_range(d['run_date'].unique())}",
            "range": date_range(d["run_date"].unique()),
            "n": len(d),
            "searches": float(s.mean()),
            "no_search": float((s == 0).mean()),
            "no_search_n": int((s == 0).sum()),
            "per_wave": per_wave,
        })
    colors = [BLUE_RAMP[0], BLUE_RAMP[3]]
    fig, (ax, bx), note_ax = note_grid((1, 1), sharey=False, figsize=(12, 6.2))
    panels = ((ax, "searches", "Web searches per answer", "Mean searches per answer",
               lambda v: f"{v:.2f}"),
              (bx, "no_search", "Answers with no web search", "Share of answers", pct))
    for axis, key, title, xlabel, fmt in panels:
        xs = np.arange(len(studies))
        vals = [s[key] for s in studies]
        axis.bar(xs, vals, color=colors, width=0.55)
        for x, s in zip(xs, studies):
            w = s["per_wave"][key].to_numpy()
            axis.scatter(np.full(len(w), x) + np.linspace(-0.12, 0.12, len(w)), w, s=22,
                         color=INK, zorder=3, clip_on=False)
            text = (fmt(s[key]) if key == "searches"
                    else f"{100 * s[key]:.1f}% ({s['no_search_n']} of {s['n']})")
            axis.annotate(text, (x, max(s[key], w.max())), xytext=(0, 6),
                          textcoords="offset points", ha="center", fontsize=10.5)
        axis.set_xticks(xs, [s["label"] for s in studies])
        top = max(max(s[key], s["per_wave"][key].max()) for s in studies)
        axis.set_ylim(0, max(top * 1.25, 0.05 if key == "no_search" else 1.0))
        if key == "no_search":
            axis.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: pct(v)))
        axis.set_title(title)
        axis.set_ylabel(xlabel)
    a, b = studies
    title = ("claude.ai searched more in November than in late September"
             if b["searches"] > a["searches"] else "claude.ai search behavior, 009 against 011")
    fig.suptitle(title, x=0.01, ha="left", fontsize=14)
    write_note(note_ax, f"Same Pro account and the same {new['item_id'].nunique()} prompts, "
               f"collected by hand. "
               + (f"{a['n']} answers in each study" if a["n"] == b["n"]
                  else f"{a['n']} and {b['n']} answers") + ". Bars: all "
               f"{new['wave'].nunique()} days of each study; dots: each day.")
    save_figure(fig, FIGURES, "claude-ai-then-now")
    return {s["study"]: {k: s[k] for k in ("range", "n", "searches", "no_search", "no_search_n")}
            | {"per_wave": s["per_wave"].round(4).to_dict("index")} for s in studies}


def f5_api_appendix(results: dict) -> dict:
    rows = results["rows"]
    ref = json.loads(RESULTS_009.read_text())
    r009 = next(r for r in ref["rows"] if r.get("section") == "H1_ref"
                and r.get("test") == f"H1b {ANCHOR}" and r.get("metric") == "brand_j")
    old = pd.DataFrame([json.loads(x) for x in FEATURES_009.read_text().splitlines() if x.strip()])
    rng = date_range(old[(old["arm"] == REFERENCE) & old["wave"].isin([1, 2, 3])]["run_date"].unique())
    rng_short = rng.rsplit(",", 1)[0]
    arms = (ANCHOR,) + CC_ORDER
    plotted = [(f"{ARM_LABEL[ANCHOR]}: 009 ({rng_short})", r009, INK_MUTED, "^", True)]
    plotted += [(ARM_LABEL[a] + (": 011" if a == ANCHOR else ""), h1_row(rows, a),
                 INK if a == ANCHOR else INK_MUTED, ARM_MARKER[a], False) for a in arms]
    fig, (ax,), note_ax = note_grid((1,), sharey=False, figsize=(11, 6.0), note_h=1.6)
    gap_panel(ax, plotted, "Which brands are named", GAP_XLABEL)
    ax.title.set_color(INK_MUTED)
    hi = max(r["hi"] for _, r, *_ in plotted)
    ax.set_xlim(-0.15, max(0.3, hi + 0.14))
    fig.suptitle("Appendix: brand-set gap to claude.ai, every arm, with 009's Claude API "
                 "result", x=0.01, ha="left", fontsize=12.5, color=INK_MUTED)
    names = ["Scheduled task" if a == "sched_kit" else ARM_LABEL[a] for a in arms]
    write_note(note_ax, f"Shaded: the +/-{SESOI:.2f} equivalence band. "
               + interval_note([h1_row(rows, a) for a in arms], names)
               + "\nThe 009 point is that study's published result, measured against "
               "claude.ai as it behaved then.\nclaude.ai changed between the two studies.")
    save_figure(fig, FIGURES, "api-appendix")
    return {"009": {k: r009[k] for k in ("estimate", "lo", "hi", "ci_level", "verdict")},
            "range_009": rng}


def main() -> None:
    path = RESULTS / "model_results.json"
    if not path.exists():
        raise SystemExit(f"no {path}; run 03_model.py first (it gates the real data)")
    results = json.loads(path.read_text())
    meta = results["meta"]
    if meta.get("synthetic"):
        raise SystemExit("model_results.json is a synthetic world; refusing")
    if not meta.get("h_pos_passed"):
        raise SystemExit("H_pos failed in model_results.json; the study stopped, no figures")
    df = load_features()
    if int(df["synthetic"].max()) == 1:
        raise SystemExit("refusing to draw a SYNTHETIC frame")
    theme()
    f1_brand_gap(results)
    f2_scheduled_vs_local(results)
    behavior = f3_search_behavior(df)
    then_now = f4_claude_ai_then_now(df)
    appendix = f5_api_appendix(results)
    for name in ("brand-gap", "scheduled-vs-local", "search-behavior", "claude-ai-then-now",
                 "api-appendix"):
        print(f"wrote {FIGURES / name}.svg and .png")
    print("search-behavior:", json.dumps(behavior, indent=1))
    print("claude-ai-then-now:", json.dumps(then_now, indent=1, default=str))
    print("api-appendix 009 reference:", json.dumps(appendix, indent=1))


if __name__ == "__main__":
    main()
