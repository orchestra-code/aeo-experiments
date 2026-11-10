"""Stage 22: pre-registered Stage 1 tests (spec §4, §5) -> results/stage1_model.md + .json.

Sequence (spec §7: positive control first):

  H_pos   per dataset: within-prompt R retention minus cross-category R
          retention (same platform, same wave; for chatgpt_consumer and
          chatgpt_agency, headphone vs agency answers of the same study wave)
          at least 0.10 with the 90% CI excluding 0. Any failure: write the
          summary and exit 1.
  H_pla   per primary dataset: the H1 gap on one seeded random half of the
          prompts (split within intent, deviation 4) minus the gap on the
          other half, TOST +/-0.10.
  H1      primary family (chatgpt_b2b, gemini_b2b, claude_api_b2b, claude_b2b
          with arm ui_default): R - Pk > 0.10, one-sided; Holm at family alpha
          0.05 with p = share of draws at or below 0.10; each verdict from the
          CI at its Holm-adjusted level.
  H2-H7   secondary, unadjusted 90% CIs, same four datasets: H2 R - T > 0.10;
          H3 T - P1 upper bound < +0.10; H4 directional T->R lower bound >=
          0.90; H6 R - M TOST +/-0.05; H7 R - WS > 0.10 (WP reported as an
          estimate).
  general H1-H4, H6, H7 on chatgpt_consumer and chatgpt_agency (agency
          labeled underpowered; H1 here is outside the Holm family).
  descriptives (spec §4 Stage 1 descriptive): R level with its CI (headline);
          retention by status within, between and cross with pair-mean
          Jaccard (aeo_research.overlap.cluster_boot) alongside; share of
          shortlisted brand-prompt pairs shortlisted in at least 80% of a
          prompt's runs; answers with a top choice, a caution, demoted raw
          top choices; cautioned retention at >= 30 appearances; caveat reason
          mix; cross-platform shortlist agreement (same prompt, same wave);
          claude_b2b arms.

Inference: pooled Dice retention, prompt-level cluster bootstrap (2,000 draws,
seed 20261003, 90% percentile intervals), contrasts draw by draw (common.py).

Real data is gated (common.analysis_gate): frozen lexicon v3 and taxonomy,
Audit D passed and signed, the Audit E second passes present, classified
best-for phrases, the Stage 1 firewall, and the full 2,000 draws.

Stage 2 (``--stage 2``, new-collection waves 1 to 11 plus the holdouts) ->
results/stage2_model.md + .json:

  H_pos   as Stage 1, on all 11 waves; any failure: summary and exit 1.
  H_pla   per primary dataset: H5 (below) on one seeded random half of the
          prompts minus H5 on the other half (the Stage 1 halves, deviation
          4), TOST +/-0.05.
  H5      primary family (chatgpt_b2b, gemini_b2b, claude_api_b2b): shortlist
          (R) retention over within-prompt pairs at least 27 days apart minus
          retention over pairs 1 to 2 days apart, TOST +/-0.05; Holm at family
          alpha 0.05 with p = the larger of the two tail shares at the band
          edges; each verdict from the CI at its Holm-adjusted level. Lag =
          days between the two answers' run dates (true dates, spec §3 and
          deviation 2). A wave below 36 of 40 on a platform leaves that
          platform's bins (Audit A).
  second. H5 on chatgpt_consumer (holdout lags: 15+ days vs 0 to 2 days);
          H5 applied to the top choice (T) and the best-for use case (WS) on
          the three new datasets; all TOST +/-0.05, unadjusted 90% CIs.
  descr.  retention by days apart (R, T, P1, Pk, WS), per platform, binned
          and by day, with 90% CIs; H1 to H4, H6, H7 recomputed on all 11
          waves (DESCRIPTIVE ONLY, firewall rule 3: estimates and intervals,
          no verdicts); the reported model of every wave; claude_api_b2b
          answers against 009's opus55_plain answers to the 26 holdout
          prompts (the 14 exploration prompts left out).

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/22_model.py --stage 1
  uv run python .../22_model.py --stage 1 --split explore
  uv run python .../22_model.py --stage 1 --synthetic planted --expect planted
  uv run python .../22_model.py --stage 2 [--synthetic planted_stable --expect planted]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from common import (
    CURVE_BINS,
    EQ_BAND,
    H5_CONSUMER,
    H5_DATASETS,
    STAGE2_NEW_WAVES,
    brands009,
    days_label,
    derive,
    h5_excluded,
    h5_panel,
    h5_row,
    h5_est,
    h5_bins_for,
    lag_days,
    load_stage_bestfor,
    model_modal,
    read_jsonl,
    ALPHA,
    AUDIT_E_MIN,
    CAUTION_MIN,
    CLAUDE_ARMS,
    DECISION_TABLE,
    FAMILY_ALPHA,
    H_POS_MIN,
    HELD_SHARE,
    JACCARD_KEYS,
    MARGIN,
    MARGIN_LABELS,
    N_BOOT,
    NEW_DATASETS,
    PLA_BAND,
    PRIMARY,
    REC,
    SEED,
    SPEC,
    STAGE_WAVES,
    STATUS_LABELS,
    Est,
    Panel,
    analysis_gate,
    add_mode_args,
    audit_e,
    placebo_halves,
    cross_arm_pairs,
    dataset_panel,
    eq_verdict,
    EQ_LABELS,
    fmt,
    fmt_ci,
    jsonable,
    load_answers,
    load_bestfor,
    margin_verdict,
    mode_from_args,
    p_tost,
    pct,
    primary_answers,
    refuse,
    run_suite,
    same_wave_pairs,
    suite_line,
    unit_strata,
    within_pairs,
)

from aeo_research.overlap import cluster_boot

RETENTION_KEYS = ("M", "R", "T", "C", "P1", "Pk", "Rpos", "WP", "WS")
FIGURE_KEYS = ("R", "WS", "T", "P1", "Pk")


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.data: dict = {"h_pos": [], "h_pla": [], "primary": [], "secondary": [],
                           "generalization": [], "levels": {}, "descriptives": {}}

    def say(self, line: str = "") -> None:
        self.lines.append(line)


# ---------------------------------------------------------------- pieces


def level_cells(panel: Panel, key: str) -> dict:
    out = {}
    for name in ("within", "between", "cross"):
        if name in panel.sets and panel.sets[name].n_pairs:
            e = panel.est(name, key)
            out[name] = [e.point, *e.ci()]
    if "within" in out and "between" in out:
        d = panel.est("within", key) - panel.est("between", key)
        out["within_minus_between"] = [d.point, *d.ci()]
    return out


def jaccard_ci(panel: Panel, key: str, contrast: tuple[str, str | None], n_boot: int) -> list:
    frames = []
    for name in (c for c in contrast if c):
        ps = panel.sets.get(name)
        if ps is None or not ps.n_pairs:
            return [float("nan")] * 3
        frames.append(pd.DataFrame({"value": ps.jac[key], "condition": name,
                                    "cluster_i": ps.ci, "cluster_j": ps.cj}))
    df = pd.concat(frames, ignore_index=True)
    if df["value"].notna().sum() == 0:
        return [float("nan")] * 3
    try:
        r = cluster_boot(df, contrast=contrast, alpha=ALPHA, n_boot=n_boot, seed=SEED)
    except ValueError:
        return [float("nan")] * 3
    return [r.estimate, r.lo, r.hi]


def h_pos(rep: Report, panels: dict[str, Panel]) -> bool:
    rep.say("## H_pos (positive control; the study stops if it fails)\n")
    rep.say("Within-prompt R retention minus cross-category R retention (same platform, same "
            f"wave). Need at least {H_POS_MIN:.2f} with the 90% CI excluding 0. For the consumer "
            "and agency datasets, cross = headphone vs agency answers of the same study wave.\n")
    rep.say("| Dataset | Within | Cross | Difference [90% CI] | Cross pairs | Result |")
    rep.say("|---|---|---|---|---|---|")
    ok_all = True
    for ds, p in panels.items():
        w, c = p.est("within", "R"), p.est("cross", "R")
        d = w - c
        lo, hi = d.ci()
        ok = bool(np.isfinite(d.point) and d.point >= H_POS_MIN and lo > 0)
        ok_all &= ok
        rep.data["h_pos"].append({"dataset": ds, "within": w.point, "cross": c.point,
                                  "estimate": d.point, "lo": lo, "hi": hi, "passed": ok,
                                  "cross_pairs": p.sets["cross"].n_pairs})
        rep.say(f"| {ds} | {fmt(w.point)} | {fmt(c.point)} | {fmt_ci(d.point, lo, hi)} | "
                f"{p.sets['cross'].n_pairs} | "
                f"{'PASS' if ok else '**FAIL: STOP, the prompt join or extraction is broken**'} |")
    rep.say("")
    return ok_all


def h_pla(rep: Report, ans: list[dict], datasets: list[str], n_boot: int) -> bool:
    rep.say("## H_pla (placebo)\n")
    rep.say("The H1 gap (R minus Pk) on one seeded random half of the prompts minus the same "
            f"gap on the other half, TOST +/-{PLA_BAND:.2f}. Must be null or negligible. The "
            "halves are drawn within each intent stratum (spec deviation 4: the frozen odd/even "
            "split coincided with the shortlist/evaluate intent split in the B2B panel).\n")
    ok_all = True
    for ds in datasets:
        own = primary_answers(ans, ds)
        p = Panel(unit_strata(own), n_boot=n_boot)
        pairs = within_pairs(own)
        half = placebo_halves(own)
        p.add("A", [(x, y) for x, y in pairs if half[x["item_id"]] == "A"])
        p.add("B", [(x, y) for x, y in pairs if half[x["item_id"]] == "B"])
        d = (p.est("A", "R") - p.est("A", "Pk")) - (p.est("B", "R") - p.est("B", "Pk"))
        lo, hi = d.ci()
        v = eq_verdict(lo, hi, PLA_BAND)
        ok = v in ("NULL", "NEGLIGIBLE")
        ok_all &= ok
        gap_a = p.est("A", "R") - p.est("A", "Pk")
        gap_b = p.est("B", "R") - p.est("B", "Pk")
        rep.data["h_pla"].append({"dataset": ds, "estimate": d.point, "lo": lo, "hi": hi,
                                  "gap_a": gap_a.point, "gap_b": gap_b.point,
                                  "p": p_tost(d, PLA_BAND), "verdict": v, "label": EQ_LABELS[v],
                                  "passed": ok})
        rep.say(f"- {ds}: {fmt_ci(d.point, lo, hi)} -> {EQ_LABELS[v]} (H1 gap on the two "
                f"halves: {gap_a.point:.2f} and {gap_b.point:.2f})"
                + ("" if ok else "  **WARNING: placebo not null or negligible**"))
    rep.say("")
    return ok_all


def holm_h1(rep: Report, panels: dict[str, Panel], datasets: list[str]) -> None:
    rep.say("## Stage 1 primary family: H1 (the shortlist beats position)\n")
    rep.say(f"R minus Pk within prompt, one-sided, H0: R - Pk <= {MARGIN:.2f}. Holm across "
            f"{len(datasets)} test(s) at family alpha {FAMILY_ALPHA}: p = share of bootstrap "
            "draws at or below 0.10; tests ranked by p; rank k uses the two-sided CI at level "
            f"1 - 2 x {FAMILY_ALPHA} / (m - k + 1).\n")
    rows, ests = [], {}
    for ds in datasets:
        r, e = run_suite(panels[ds], ds, tests=("H1",))
        rows.append(r[0])
        ests[ds] = e["H1"]
    m = len(rows)
    order = sorted(range(m), key=lambda k: rows[k]["p"])
    running, blocked = 0.0, False
    for rank, k in enumerate(order, start=1):
        row = rows[k]
        a_k = FAMILY_ALPHA / (m - rank + 1)
        lo, hi = ests[row["dataset"]].ci(2 * a_k)
        v = margin_verdict(lo, hi, MARGIN)
        running = max(running, min(1.0, (m - rank + 1) * row["p"]))
        row |= {"holm_rank": rank, "holm_alpha": a_k, "ci_level": 1 - 2 * a_k, "lo": lo,
                "hi": hi, "verdict": v, "label": MARGIN_LABELS[v], "p_holm": running,
                "lo_90": row["lo"], "hi_90": row["hi"]}
        if v == "SUPPORTED" and blocked:
            row["note"] = ("strict step-down would stop before this test: a better-ranked test "
                           "in the family was not supported")
        if v != "SUPPORTED":
            blocked = True
    rep.say("| Dataset | Estimate | Holm rank | CI level | CI | p | Holm p | Verdict |")
    rep.say("|---|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: r["holm_rank"]):
        rep.say(f"| {row['dataset']} | {fmt(row['estimate'])} | {row['holm_rank']} | "
                f"{row['ci_level']:.4f} | [{fmt(row['lo'])}, {fmt(row['hi'])}] | "
                f"{row['p']:.4f} | {row['p_holm']:.4f} | {row['label']} |")
        if row.get("note"):
            rep.say(f"|  | NOTE: {row['note']} | | | | | | |")
    rep.say("")
    rep.data["primary"] = rows


def secondary(rep: Report, panels: dict[str, Panel], datasets: list[str], section: str,
              title: str) -> None:
    rep.say(f"## {title}\n")
    for ds in datasets:
        p = panels[ds]
        rows, _ = run_suite(p, ds, tests=("H1", "H2", "H3", "H4", "H6", "H7")
                            if section == "generalization" else ("H2", "H3", "H4", "H6", "H7"))
        wp = p.est("within", "WP")
        rwp = p.est("within", "R") - wp
        extra = {"dataset": ds, "test": "WP", "estimate": wp.point, "lo": wp.ci()[0],
                 "hi": wp.ci()[1], "r_minus_wp": [rwp.point, *rwp.ci()]}
        note = " (underpowered: 27 prompts, 3 runs each)" if SPEC[ds].underpowered else ""
        rep.say(f"**{ds}**{note} ({p.sets['within'].n_pairs} within-prompt pairs)\n")
        for r in rows:
            rep.say(f"- {suite_line(r)}")
        rep.say(f"- WP (\"Where AI picks you\" as grouped today) within retention, an estimate: "
                f"{fmt_ci(wp.point, *wp.ci())}; R minus WP {fmt_ci(rwp.point, *rwp.ci())}")
        rep.say("")
        rep.data[section] += rows + [extra]


# ---------------------------------------------------------- descriptives


def held_share(panel: Panel, own: list[dict]) -> tuple[Est, float, float, int, dict]:
    """Share of shortlisted brand-prompt pairs shortlisted in >= 80% of a prompt's runs,
    plus the count of pairs by (runs shortlisted, runs of the prompt) for the figures."""
    n = len(panel.units)
    num, den = np.zeros(n), np.zeros(n)
    every = single = total = 0
    hist: Counter = Counter()
    groups = defaultdict(list)
    for a in own:
        groups[(a["item_id"], a["arm"])].append(a)
    for (item, _), runs in groups.items():
        cnt = Counter(b for a in runs for b in a["S"]["R"])
        for c in cnt.values():
            rate = c / len(runs)
            num[panel.idx[item]] += rate >= HELD_SHARE
            den[panel.idx[item]] += 1
            every += c == len(runs)
            single += c == 1
            total += 1
            hist[f"{c}/{len(runs)}"] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = (panel.W @ num) / (panel.W @ den)
    point = num.sum() / den.sum() if den.sum() else float("nan")
    return (Est(point, draws), every / total if total else float("nan"),
            single / total if total else float("nan"), total, dict(hist))


def dataset_descriptives(rep: Report, ds: str, panel: Panel, own: list[dict], n_boot: int
                         ) -> dict:
    out: dict = {}
    n_items = len({a["item_id"] for a in own})
    runs = Counter(a["item_id"] for a in own)
    rep.say(f"### {ds}: {SPEC[ds].label}\n")
    rep.say(f"{len(own)} answers evaluated (in this study), {n_items} prompts, runs per prompt "
            f"{min(runs.values())} to {max(runs.values())}; arm `{SPEC[ds].arm}`.\n")
    r = panel.est("within", "R")
    out["headline_R"] = [r.point, *r.ci()]
    rep.say(f"**Headline: shortlist (R) retention within prompt {fmt_ci(r.point, *r.ci())}.**\n")

    rep.say("| Status | Appearances | Within prompt | Between prompts (same category) | Cross "
            "category | Within minus between | Pair-mean Jaccard within |")
    rep.say("|---|---|---|---|---|---|---|")
    levels = {}
    for k in RETENTION_KEYS:
        cells = level_cells(panel, k)
        levels[k] = cells
        app = sum(len(a["S"][k]) for a in own)
        jac = jaccard_ci(panel, k, ("within", None), n_boot) if k in JACCARD_KEYS else None
        if jac is not None:
            cells["jaccard_within"] = jac
        if k == "C" and app < CAUTION_MIN:
            rep.say(f"| {STATUS_LABELS[k]} | {app} | fewer than {CAUTION_MIN} appearances | | | "
                    "| |")
            continue

        def c(name: str) -> str:
            return fmt_ci(*cells[name]) if name in cells else "n/a"

        rep.say(f"| {STATUS_LABELS[k]} | {app} | {c('within')} | {c('between')} | {c('cross')} "
                f"| {c('within_minus_between')} | {fmt_ci(*jac) if jac else ''} |")
    rep.say("")
    for k in ("T>R", "P1>R", "R>M"):
        e = panel.est("within", k)
        levels[k] = {"within": [e.point, *e.ci()]}
        rep.say(f"- {STATUS_LABELS[k]}: {fmt_ci(e.point, *e.ci())}")
    for a_, b_, label in (("R", "Rpos", "R minus position-only shortlist of the same size"),
                          ("R", "WP", "R minus WP")):
        d = panel.est("within", a_) - panel.est("within", b_)
        out[f"{a_}-{b_}"] = [d.point, *d.ci()]
        rep.say(f"- {label}: {fmt_ci(d.point, *d.ci())}")
    jr = jaccard_ci(panel, "R", ("within", "cross"), n_boot)
    out["jaccard_R_within_minus_cross"] = jr
    rep.say(f"- Pair-mean Jaccard of R, within minus cross: {fmt_ci(*jr)}")
    rep.data["levels"][ds] = levels

    held, every, single, n_bp, hist = held_share(panel, own)
    out["held_80"] = [held.point, *held.ci()]
    out["runs_shortlisted"] = hist
    rep.say(f"- Shortlisted brand-prompt pairs ({n_bp}) shortlisted in at least 80% of the "
            f"prompt's runs: {fmt_ci(held.point, *held.ci())}; in every run {pct(every)}; in "
            f"only one run {pct(single)}")
    shares = {
        "with_top_choice": np.mean([bool(a["S"]["T"]) for a in own]),
        "with_caution": np.mean([bool(a["S"]["C"]) for a in own]),
        "raw_top_demoted": np.mean([a["n_raw_top_items"] > 2 for a in own]),
        "R_differs_from_M": np.mean([a["S"]["R"] != a["S"]["M"] for a in own]),
        "lexicon_brands_per_answer": np.mean([len(a["order"]) for a in own]),
        "recommended_per_answer": np.mean([len(a["S"]["R"]) for a in own]),
        "no_lexicon_brand": np.mean([not a["order"] for a in own]),
    }
    out["answer_shape"] = shares
    rep.say(f"- Answers with a top choice {pct(shares['with_top_choice'])}; with a caution "
            f"against a lexicon brand {pct(shares['with_caution'])}; raw top choices demoted "
            f"(more than two) {pct(shares['raw_top_demoted'])}; shortlist differs from the "
            f"mentioned set {pct(shares['R_differs_from_M'])}; lexicon brands per answer "
            f"{shares['lexicon_brands_per_answer']:.1f}, recommended "
            f"{shares['recommended_per_answer']:.1f}")
    reasons, cautioned = Counter(), Counter()
    for a in own:
        for b in a["order"]:
            ts = a["caveat_types"].get(b, [])
            reasons.update(ts)
            if a["cats"][b] == "cautioned_against":
                cautioned.update(ts)
    out["caveat_reasons"] = dict(reasons)
    out["caveat_reasons_cautioned"] = dict(cautioned)
    tot = sum(reasons.values())
    if tot:
        rep.say(f"- Caveat reason mix ({tot} caveats on lexicon brands): " + ", ".join(
            f"{k} {pct(v / tot)}" for k, v in reasons.most_common()))
        ct = sum(cautioned.values())
        if ct:
            rep.say(f"  - on brands cautioned against ({ct}): " + ", ".join(
                f"{k} {pct(v / ct)}" for k, v in cautioned.most_common()))
    else:
        rep.say("- Caveat reason mix: no caveats on lexicon brands")
    rep.say("")
    return out


def cross_platform(rep: Report, ans: list[dict], n_boot: int) -> dict:
    sets = {ds: primary_answers(ans, ds) for ds in NEW_DATASETS}
    if not all(sets.values()):
        return {}
    rep.say("### Cross-platform shortlist agreement (same prompt, same wave)\n")
    items = sorted({a["item_id"] for v in sets.values() for a in v})
    p = Panel([items], n_boot=n_boot)
    out = {}
    rep.say("| Platforms | Pairs | Shortlist (R) | Top choice | Mentioned | Rank 1 |")
    rep.say("|---|---|---|---|---|---|")
    names = list(NEW_DATASETS)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a_, b_ = names[i], names[j]
            nm = f"{a_}|{b_}"
            p.add(nm, same_wave_pairs(sets[a_], sets[b_]))
            cells = {k: [p.est(nm, k).point, *p.est(nm, k).ci()] for k in ("R", "T", "M", "P1")}
            out[nm] = cells
            rep.say(f"| {SPEC[a_].label} vs {SPEC[b_].label} | {p.sets[nm].n_pairs} | "
                    + " | ".join(fmt_ci(*cells[k]) for k in ("R", "T", "M", "P1")) + " |")
    rep.say("")
    return out


def claude_arms(rep: Report, ans: list[dict], n_boot: int) -> dict:
    allc = [a for a in ans if a["dataset"] == "claude_b2b"]
    if not allc:
        return {}
    rep.say("### claude_b2b arms (ui_default vs ui_think vs opus55_plain)\n")
    p = Panel(unit_strata(allc), n_boot=n_boot)
    out = {}
    rep.say("| Comparison | Pairs | Shortlist (R) | Top choice | Rank 1 | Exact position |")
    rep.say("|---|---|---|---|---|---|")
    combos = [(f"{arm} within", within_pairs([a for a in allc if a["arm"] == arm]))
              for arm in CLAUDE_ARMS]
    combos += [(f"{x} vs {y}", cross_arm_pairs(allc, x, y))
               for x, y in (("ui_default", "ui_think"), ("ui_default", "opus55_plain"),
                            ("ui_think", "opus55_plain"))]
    for nm, pairs in combos:
        if not pairs:
            continue
        p.add(nm, pairs)
        cells = {k: [p.est(nm, k).point, *p.est(nm, k).ci()] for k in ("R", "T", "P1", "Pk")}
        out[nm] = cells
        rep.say(f"| {nm} | {len(pairs)} | " + " | ".join(fmt_ci(*cells[k])
                                                        for k in ("R", "T", "P1", "Pk")) + " |")
    rep.say("\nCross-arm pairs: same prompt, any wave (as in results/exploration.md).\n")
    return out


# ---------------------------------------------------------------- checks


def expect_checks(rep: Report, mode, meta: dict, passed: bool) -> list[tuple[str, bool, str]]:
    expect = json.loads((mode.raw / "planted_expect.json").read_text())
    checks = [("H_pos passes for every dataset", passed, "")]
    found = {}
    for sec in ("primary", "secondary", "generalization"):
        for r in rep.data[sec]:
            if "verdict" in r:
                found.setdefault((r["dataset"], r["test"]), (r["verdict"], r, sec))
    for ds, tests in expect.items():
        for t, want in tests.items():
            v, r, sec = found.get((ds, t), ("missing", {}, ""))
            checks.append((f"{ds} {t} in {want} ({sec or 'missing'})", v in want,
                           f"{fmt_ci(r.get('estimate'), r.get('lo'), r.get('hi'))} {v}"))
    checks.append(("firewall dropped the 480 synthetic tasks of waves 8 to 11",
                   meta.get("filtered_waves") == 480 and meta.get("max_new_wave") == 7,
                   f"filtered {meta.get('filtered_waves')}, max wave {meta.get('max_new_wave')}"))
    checks.append(("the planted refusal and empty answer are flagged and excluded",
                   meta.get("unusable") == {"chatgpt_b2b": 1, "gemini_b2b": 1},
                   str(meta.get("unusable"))))
    return checks


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_mode_args(ap)
    ap.add_argument("--expect", choices=("planted",), default=None,
                    help="assert the planted verdicts (synthetic only)")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    mode = mode_from_args(a)
    if a.expect and mode.kind != "synthetic":
        raise SystemExit("--expect is for synthetic worlds only")
    problems = analysis_gate(mode, a.n_boot)
    if problems:
        refuse(problems, "22_model.py")
    if mode.stage == 2:
        stage2(mode, a)
        return

    meta = json.loads(mode.meta_path.read_text())
    bf = load_bestfor(mode.bestfor)
    ans = load_answers(mode, bf=bf)
    if mode.kind != "explore":
        late = [x for x in ans if x["dataset"] in NEW_DATASETS
                and x["wave"] not in STAGE_WAVES[mode.stage]]
        if late:
            refuse([f"{len(late)} new-collection answers outside the Stage {mode.stage} waves"],
                   "22_model.py")
    datasets = [ds for ds in mode.datasets() if primary_answers(ans, ds)]
    primaries = [ds for ds in PRIMARY if ds in datasets]
    general = [ds for ds in datasets if SPEC[ds].role == "generalization"]

    rep = Report()
    rep.say(f"# Experiment 010: Stage {mode.stage} model results{mode.tag}\n")
    rep.say(f"Generated by `pipeline/22_model.py`. Seed {SEED}, {a.n_boot} bootstrap draws, "
            "90% percentile intervals, prompt-level cluster bootstrap, contrasts draw by draw. "
            "Retention = pooled Dice over answer pairs: the share of brand appearances with a "
            "status in one answer that keep it in the other. Aggregates only.\n")
    if bf is None:
        rep.say("Best-for files are missing, so WS and WP (and H7) are empty here.\n")
    panels = {ds: dataset_panel(ans, ds, n_boot=a.n_boot) for ds in datasets}

    passed = h_pos(rep, panels)
    pla_ok = None
    if passed:
        pla_ok = h_pla(rep, ans, primaries, a.n_boot)
        if primaries:
            holm_h1(rep, panels, primaries)
            secondary(rep, panels, primaries, "secondary",
                      "Stage 1 secondary (no multiplicity correction)")
        if general:
            secondary(rep, panels, general, "generalization",
                      "Generalization (no multiplicity correction): H1 to H4, H6, H7")
        rep.say("## Decision rules (spec §5, 90% CI)\n")
        rep.say(DECISION_TABLE + "\n")
        rep.say("H1's verdicts use the CI at each test's Holm-adjusted level (table above).\n")

        # Audit E caveat (spec §2): below 90%, R4 moves to the main text.
        second = load_answers(mode, rejudge=True, bf=bf)
        if second:
            e = audit_e(ans, second)
            rep.data["audit_e_agreement"] = e["agreement"]
            if e["agreement"] < AUDIT_E_MIN:
                rep.say(f"**Instrument-noise caveat:** judge test-retest agreement "
                        f"{pct(e['agreement'])} is below {AUDIT_E_MIN:.0%} (Audit E), so the "
                        "retention figures carry an instrument-noise caveat and robustness R4 "
                        "is promoted to the main text.\n")

        rep.say("## Stage 1 descriptives (no tests)\n")
        for ds in datasets:
            rep.data["descriptives"][ds] = dataset_descriptives(
                rep, ds, panels[ds], primary_answers(ans, ds), a.n_boot)
            rep.data["descriptives"][ds]["n_answers"] = len(primary_answers(ans, ds))
        rep.data["descriptives"]["cross_platform"] = cross_platform(rep, ans, a.n_boot)
        rep.data["descriptives"]["claude_arms"] = claude_arms(rep, ans, a.n_boot)

    out = mode.results
    out.mkdir(parents=True, exist_ok=True)
    rep.data["meta"] = {"seed": SEED, "n_boot": a.n_boot, "alpha": ALPHA,
                        "family_alpha": FAMILY_ALPHA, "mode": mode.kind, "world": mode.world,
                        "stage": mode.stage, "h_pos_passed": passed, "h_pla_ok": pla_ok,
                        "labels": {ds: SPEC[ds].label for ds in datasets},
                        "color_keys": {ds: SPEC[ds].color_key for ds in datasets},
                        "n_answers": {ds: len(primary_answers(ans, ds)) for ds in datasets},
                        "recommended": list(REC)}
    (out / f"stage{mode.stage}_model.json").write_text(
        json.dumps(jsonable(rep.data), indent=1) + "\n")
    text = "\n".join(rep.lines) + "\n"
    (out / f"stage{mode.stage}_model.md").write_text(text)
    print(text)
    print(f"wrote {out / f'stage{mode.stage}_model.md'} and .json")

    if not passed:
        sys.exit(1)
    if a.expect:
        checks = expect_checks(rep, mode, meta, passed)
        print(f"\ndry-run check ({a.expect}):")
        for name, ok, detail in checks:
            print(f"  {'OK  ' if ok else 'FAIL'} {name}: {detail}")
        print(f"  info (not asserted): H_pla null or negligible everywhere: {pla_ok}")
        if not all(ok for _, ok, _ in checks):
            sys.exit(2)


# ====================================================== Stage 2: over time

CURVE_KEYS = ("R", "T", "P1", "Pk", "WS")
CURVE_LABELS = {"R": "Shortlist (R)", "T": "Top choice (T)", "P1": "Rank 1 (P1)",
                "Pk": "Exact position (Pk)", "WS": "Best-for use case (WS)"}
EQ_ACCEPT = ("NULL", "NEGLIGIBLE")  # TOST rejects H0 (a drift of 0.05 or more)


def cell(e: Est) -> list[float]:
    return [e.point, *e.ci()]


def s2_h_pla(rep: Report, ans: list[dict], datasets: list[str], excluded: set,
             n_boot: int) -> bool:
    rep.say("## H_pla (placebo)\n")
    rep.say(f"H5 (far minus near shortlist retention) on one seeded random half of the prompts "
            f"minus H5 on the other half, TOST +/-{EQ_BAND:.2f}. Must be null or negligible. "
            "The halves are the Stage 1 halves, drawn within each intent stratum (spec "
            "deviation 4).\n")
    ok_all = True
    for ds in datasets:
        own = primary_answers(ans, ds)
        half = placebo_halves(own)
        p = h5_panel(own, ds, excluded=excluded, n_boot=n_boot, halves=half)
        ha, hb = h5_est(p, "R", "_A"), h5_est(p, "R", "_B")
        d = ha - hb
        lo, hi = d.ci()
        v = eq_verdict(lo, hi, EQ_BAND)
        ok = v in EQ_ACCEPT
        ok_all &= ok
        rep.data["h_pla"].append({"dataset": ds, "estimate": d.point, "lo": lo, "hi": hi,
                                  "h5_a": ha.point, "h5_b": hb.point, "p": p_tost(d, EQ_BAND),
                                  "verdict": v, "label": EQ_LABELS[v], "passed": ok})
        rep.say(f"- {ds}: {fmt_ci(d.point, lo, hi)} -> {EQ_LABELS[v]} (H5 on the two halves: "
                f"{ha.point:.2f} and {hb.point:.2f})"
                + ("" if ok else "  **WARNING: placebo not null or negligible**"))
    rep.say("")
    return ok_all


def s2_holm(rep: Report, panels: dict[str, Panel], datasets: list[str]) -> None:
    rep.say("## Stage 2 primary family: H5 (the shortlist does not drift)\n")
    rep.say(f"Shortlist (R) retention over within-prompt pairs {days_label((27, None))} apart "
            f"minus retention over pairs {days_label((1, 2))} apart, equivalence to 0 within "
            f"+/-{EQ_BAND:.2f} (TOST). Holm across {len(datasets)} test(s) at family alpha "
            f"{FAMILY_ALPHA}: p = the larger of the two tail shares of the bootstrap draws at "
            "the band edges; tests ranked by p; rank k uses the two-sided CI at level 1 - 2 x "
            f"{FAMILY_ALPHA} / (m - k + 1). Pairs per prompt from the schedule: 8 far, 11 near "
            "(the actual counts follow from the run dates and Audit A).\n")
    rows, ests = [], {}
    for ds in datasets:
        row, e = h5_row(panels[ds], ds, "R")
        rows.append(row)
        ests[ds] = e
    m = len(rows)
    order = sorted(range(m), key=lambda k: rows[k]["p"])
    running, blocked = 0.0, False
    for rank, k in enumerate(order, start=1):
        row = rows[k]
        a_k = FAMILY_ALPHA / (m - rank + 1)
        lo, hi = ests[row["dataset"]].ci(2 * a_k)
        v = eq_verdict(lo, hi, EQ_BAND)
        running = max(running, min(1.0, (m - rank + 1) * row["p"]))
        row |= {"holm_rank": rank, "holm_alpha": a_k, "ci_level": 1 - 2 * a_k, "lo": lo,
                "hi": hi, "verdict": v, "label": EQ_LABELS[v], "p_holm": running,
                "lo_90": row["lo"], "hi_90": row["hi"]}
        if v in EQ_ACCEPT and blocked:
            row["note"] = ("strict step-down would stop before this test: a better-ranked test "
                           "in the family did not reject H0")
        if v not in EQ_ACCEPT:
            blocked = True
    rep.say("| Dataset | Near pairs | Far pairs | R near | R far | Far minus near | Holm rank | "
            "CI level | CI | p | Holm p | Verdict |")
    rep.say("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: r["holm_rank"]):
        rep.say(f"| {row['dataset']} | {row['near_pairs']} | {row['far_pairs']} | "
                f"{fmt_ci(*row['near'])} | {fmt_ci(*row['far'])} | {fmt(row['estimate'])} | "
                f"{row['holm_rank']} | {row['ci_level']:.4f} | [{fmt(row['lo'])}, {fmt(row['hi'])}]"
                f" | {row['p']:.4f} | {row['p_holm']:.4f} | {row['label']} |")
        if row.get("note"):
            rep.say(f"|  | NOTE: {row['note']} | | | | | | | | | | |")
    rep.say("")
    rep.say("Unadjusted 90% intervals of the same contrasts: " + "; ".join(
        f"{r['dataset']} {fmt_ci(r['estimate'], r['lo_90'], r['hi_90'])}" for r in rows) + ".\n")
    rep.data["primary"] = rows


def s2_secondary(rep: Report, ans: list[dict], panels: dict[str, Panel], datasets: list[str],
                 n_boot: int) -> None:
    rep.say("## Stage 2 secondary (no multiplicity correction)\n")
    cons = primary_answers(ans, H5_CONSUMER)
    if cons:
        near_b, far_b = h5_bins_for(H5_CONSUMER)
        p = h5_panel(cons, H5_CONSUMER, excluded=set(), n_boot=n_boot)
        row, _ = h5_row(p, H5_CONSUMER, "R", test="H5 consumer")
        rep.data["secondary"].append(row)
        rep.say(f"**{H5_CONSUMER}** (holdout lags; {days_label(far_b)} vs {days_label(near_b)} "
                f"apart; {row['far_pairs']} far and {row['near_pairs']} near pairs): shortlist "
                f"retention far {fmt_ci(*row['far'])}, near {fmt_ci(*row['near'])}; far minus "
                f"near {fmt_ci(row['estimate'], row['lo'], row['hi'])} -> {row['label']}\n")
    rep.say("**H5 applied to the top choice (T) and the best-for use case (WS)**, far minus "
            f"near, TOST +/-{EQ_BAND:.2f}:\n")
    rep.say("| Dataset | Status | Appearances near / far | Near | Far | Far minus near [90% CI] "
            "| Verdict |")
    rep.say("|---|---|---|---|---|---|---|")
    for ds in datasets:
        for key, test in (("T", "H5 T"), ("WS", "H5 WS")):
            row, _ = h5_row(panels[ds], ds, key, test=test)
            rep.data["secondary"].append(row)
            rep.say(f"| {ds} | {CURVE_LABELS[key]} | {row['near_appearances']} / "
                    f"{row['far_appearances']} | {fmt_ci(*row['near'])} | {fmt_ci(*row['far'])} | "
                    f"{fmt_ci(row['estimate'], row['lo'], row['hi'])} | {row['label']} |")
    rep.say("")


def lag_curve(own: list[dict], n_boot: int) -> dict:
    """Retention by days apart (every within-prompt pair; Audit A's H5 rule does
    not apply here: the wave is kept everywhere but H5's bins)."""
    panel = Panel(unit_strata(own), n_boot=n_boot)
    pairs = within_pairs(own)
    lags = [lag_days(x, y) for x, y in pairs]
    out: dict = {"bins": [], "days": []}
    for lo, hi in CURVE_BINS:
        sel = [p for p, g in zip(pairs, lags) if lo <= g <= hi]
        if not sel:
            continue
        name = f"bin:{lo}-{hi}"
        panel.add(name, sel)
        out["bins"].append({"bin": [lo, hi], "label": days_label((lo, hi)), "pairs": len(sel),
                            "mean_lag": float(np.mean([g for g in lags if lo <= g <= hi])),
                            **{k: cell(panel.est(name, k)) for k in CURVE_KEYS}})
    for d in sorted(set(lags)):
        sel = [p for p, g in zip(pairs, lags) if g == d]
        name = f"day:{d}"
        panel.add(name, sel)
        out["days"].append({"days": d, "pairs": len(sel),
                            **{k: cell(panel.est(name, k)) for k in CURVE_KEYS}})
    return out


def s2_curve(rep: Report, ans: list[dict], datasets: list[str], n_boot: int) -> None:
    rep.say("### Retention by days apart (the curve)\n")
    rep.say("Within-prompt pairs grouped by the days between the two answers' run dates; every "
            "pair counts here (Audit A's 36-of-40 rule applies only to H5's bins). 90% "
            "intervals. The by-day shortlist table follows; every status by day is in the "
            "JSON.\n")
    for ds in [*datasets, H5_CONSUMER]:
        own = primary_answers(ans, ds)
        if not own:
            continue
        c = lag_curve(own, n_boot)
        rep.data["descriptives"].setdefault("curve", {})[ds] = c
        rep.say(f"**{ds}**\n")
        rep.say("| Days apart | Pairs | " + " | ".join(CURVE_LABELS[k] for k in CURVE_KEYS) + " |")
        rep.say("|---|---|" + "---|" * len(CURVE_KEYS))
        for b in c["bins"]:
            rep.say(f"| {b['label']} | {b['pairs']} | "
                    + " | ".join(fmt_ci(*b[k]) for k in CURVE_KEYS) + " |")
        rep.say("")
        rep.say("Shortlist (R) by day: " + "; ".join(
            f"{d['days']}: {fmt(d['R'][0])} ({d['pairs']})" for d in c["days"]) + "\n")


def s2_descriptive_suite(rep: Report, panels: dict[str, Panel], datasets: list[str],
                         mode) -> None:
    rep.say("### H1 to H4, H6, H7 on all 11 waves: DESCRIPTIVE ONLY\n")
    rep.say("Firewall rule 3: Stage 2 does not re-test Stage 1 hypotheses, so these are "
            "estimates and 90% intervals over every within-prompt pair of waves 1 to 11, with "
            "no verdicts. The Stage 1 verdicts (waves 1 to 7) stand as published.\n")
    s1 = {}
    s1_path = mode.results / "stage1_model.json"
    if s1_path.exists():
        r1 = json.loads(s1_path.read_text())
        for sec in ("primary", "secondary"):
            for r in r1.get(sec, []):
                if "estimate" in r and r.get("test", "").startswith("H"):
                    s1.setdefault((r["dataset"], r["test"]),
                                  [r["estimate"], r.get("lo_90", r["lo"]), r.get("hi_90", r["hi"])])
    rep.say("| Dataset | Within pairs | Shortlist (R) level | Test | Contrast | All 11 waves "
            "[90% CI] | Stage 1, waves 1 to 7 [90% CI] |")
    rep.say("|---|---|---|---|---|---|---|")
    for ds in datasets:
        p = panels[ds]
        rows, _ = run_suite(p, ds)
        r = p.est("within", "R")
        rep.data["descriptives"].setdefault("headline_R", {})[ds] = cell(r)
        for k, row in enumerate(rows):
            keep = {x: row[x] for x in ("test", "label_short", "estimate", "lo", "hi", "n_pairs",
                                        "dataset")}
            rep.data["descriptive_suite"].append(keep)
            prev = s1.get((ds, row["test"]))
            rep.say(f"| {ds if k == 0 else ''} | {p.sets['within'].n_pairs if k == 0 else ''} | "
                    f"{fmt_ci(*cell(r)) if k == 0 else ''} | {row['test']} | {row['label_short']}"
                    f" | {fmt_ci(row['estimate'], row['lo'], row['hi'])} | "
                    f"{fmt_ci(*prev) if prev else 'n/a'} |")
    rep.say("")


def s2_models(rep: Report, ans: list[dict], datasets: list[str]) -> None:
    rep.say("### The platform model on every wave\n")
    rep.say("| Dataset | " + " | ".join(f"W{w}" for w in range(1, 12)) + " |")
    rep.say("|---|" + "---|" * 11)
    out = {}
    for ds in datasets:
        own = primary_answers(ans, ds)
        by = {w: Counter(a.get("model") or "(not recorded)" for a in own if a["wave"] == w)
              for w in range(1, 12)}
        out[ds] = {w: dict(c) for w, c in by.items()}
        rep.say(f"| {ds} | " + " | ".join(
            ", ".join(f"{m}" + (f" ({n})" if len(c) > 1 else "") for m, n in c.most_common())
            or "none" for c in by.values()) + " |")
    rep.say("")
    rep.data["descriptives"]["models_by_wave"] = out


def v21_universe(mode) -> dict[str, set[str]] | None:
    """Lexicon v2.1 brands per category (kept rows), the lexicon 009's answers were
    built with; None outside the confirmatory data (one synthetic lexicon)."""
    if not mode.confirmatory:
        return None
    patterns, _, _ = brands009().frozen_lexicon()
    return {c: {canon for _, canon, keep in pats if keep} for c, pats in patterns.items()}


def restrict(a: dict, keep: set[str], bf) -> dict:
    x = dict(a)
    x["order"] = [b for b in a["order"] if b in keep]
    for k in ("cats", "best_for", "caveat_types"):
        x[k] = {b: v for b, v in a[k].items() if b in keep}
    return derive(x, bf)


def s2_claude_vs_009(rep: Report, ans: list[dict], mode, bf, n_boot: int) -> None:
    api = primary_answers(ans, "claude_api_b2b")
    old = [a for a in ans if a["dataset"] == "claude_b2b" and a["arm"] == "opus55_plain"]
    if not api or not old:
        return
    items = sorted({a["item_id"] for a in old})
    api = [a for a in api if a["item_id"] in items]
    rep.say("### claude_api_b2b against 009's opus55_plain answers (26 holdout prompts)\n")
    rep.say(f"The same request shape (009's arm opus55_plain). {len(old)} answers from 009 (3 "
            f"runs, {min(a['run_date'] for a in old)} to {max(a['run_date'] for a in old)}) "
            f"against {len(api)} new answers to the same {len(items)} prompts (waves 1 to 11); "
            "the 14 exploration prompts are left out. Cross pairs: one 009 answer and one new "
            "answer to the same prompt. The main rows count only brands in lexicon v2.1 (the "
            "lexicon 009's answers were built with) on both sides, so brands added in lexicon "
            "v3 cannot lower the cross-study figure; the as-built rows follow.\n")
    universe = v21_universe(mode)
    variants = [("lexicon v2.1 brands", universe)] if universe else []
    variants.append(("as built", None))
    keys = ("R", "T", "P1", "Pk", "M")
    out: dict = {"items": len(items), "answers_009": len(old), "answers_new": len(api)}
    notes: list[str] = []
    rep.say("| Brands | Pairs | Comparison | " + " | ".join(CURVE_LABELS.get(k, "Mentioned (M)")
                                                     for k in keys) + " |")
    rep.say("|---|---|---|" + "---|" * len(keys))
    for vname, uni in variants:
        A = [restrict(a, uni.get(a["category"], set()), bf) for a in api] if uni else api
        B = [restrict(b, uni.get(b["category"], set()), bf) for b in old] if uni else old
        p = Panel([items], n_boot=n_boot)
        by_b = defaultdict(list)
        for b in B:
            by_b[b["item_id"]].append(b)
        cross = [(x, y) for x in A for y in by_b[x["item_id"]]]
        p.add("cross", cross)
        p.add("new_within", within_pairs(A))
        p.add("009_within", within_pairs(B))
        res: dict = {}
        for nm, label in (("cross", "009 vs new (cross-study)"),
                          ("new_within", "new vs new (within)"),
                          ("009_within", "009 vs 009 (within)")):
            cells = {k: cell(p.est(nm, k)) for k in keys}
            res[nm] = cells | {"pairs": p.sets[nm].n_pairs}
            rep.say(f"| {vname} | {p.sets[nm].n_pairs} | {label} | "
                    + " | ".join(fmt_ci(*cells[k]) for k in keys) + " |")
        d = p.est("cross", "R") - p.est("new_within", "R")
        res["R_cross_minus_new_within"] = cell(d)
        lag_rows = []
        lags = [lag_days(x, y) for x, y in cross]
        for lo, hi in ((0, 6), (7, 13), (14, 20), (21, 27), (28, 34), (35, 99)):
            sel = [c for c, g in zip(cross, lags) if lo <= g <= hi]
            if sel:
                nm = f"cross:{lo}"
                p.add(nm, sel)
                lag_rows.append({"bin": [lo, hi], "pairs": len(sel), "R": cell(p.est(nm, "R"))})
        res["cross_R_by_days"] = lag_rows
        out[vname] = res
        notes.append(f"- {vname}: shortlist, cross-study minus new within {fmt_ci(*cell(d))}; "
                     "cross-study shortlist by days apart: " + ", ".join(
                         f"{days_label(tuple(r['bin']))} {fmt_ci(*r['R'])} ({r['pairs']} pairs)"
                         for r in lag_rows))
    rep.say("")
    rep.lines += notes
    rep.say("")
    rep.data["descriptives"]["claude_vs_009"] = out


def expect_checks_s2(rep: Report, mode, meta: dict, passed: bool, ans: list[dict],
                     excluded: set) -> list[tuple[str, bool, str]]:
    exp = json.loads((mode.raw / "planted_expect_stage2.json").read_text())
    checks = [("H_pos passes for every dataset", passed, "")]
    prim = {r["dataset"]: r for r in rep.data["primary"]}
    for ds, want in exp["H5"].items():
        r = prim.get(ds, {})
        checks.append((f"{ds} H5 (Holm) in {want}", r.get("verdict") in want,
                       f"{fmt_ci(r.get('estimate'), r.get('lo'), r.get('hi'))} {r.get('verdict')}"))
    cons = next((r for r in rep.data["secondary"] if r["test"] == "H5 consumer"), {})
    checks.append((f"{H5_CONSUMER} H5 in {exp['H5_consumer']}",
                   cons.get("verdict") in exp["H5_consumer"],
                   f"{fmt_ci(cons.get('estimate'), cons.get('lo'), cons.get('hi'))} "
                   f"{cons.get('verdict')}"))
    for ds, want in exp["pairs"].items():
        r = prim.get(ds, {})
        got = {"near": r.get("near_pairs"), "far": r.get("far_pairs")}
        checks.append((f"{ds} H5 pairs near/far = {want['near']}/{want['far']} (true run "
                       "dates, Audit A)", got == want, f"{got['near']}/{got['far']}"))
    checks.append(("Audit A leaves the short wave out of H5's bins",
                   sorted(map(list, excluded)) == exp["excluded"], str(sorted(excluded))))
    checks.append(("Stage 2 frame holds waves 1 to 11 (nothing dropped)",
                   meta.get("filtered_waves") == 0 and meta.get("max_new_wave") == 11,
                   f"filtered {meta.get('filtered_waves')}, max wave {meta.get('max_new_wave')}"))
    for ds, want in exp["r2_modal"].items():
        got = model_modal(primary_answers(ans, ds))
        checks.append((f"{ds} modal model (R2) is {want}", got == want, str(got)))
    n_s2 = len([a for a in read_jsonl(mode.rejudge_path)
                if a["wave"] in STAGE2_NEW_WAVES and a["dataset"] in H5_DATASETS])
    checks.append(("Stage 2 Audit E sample = 48 tasks of waves 8 to 11", n_s2 == 48, str(n_s2)))
    return checks


def stage2(mode, a) -> None:
    meta = json.loads(mode.meta_path.read_text())
    bf = load_stage_bestfor(mode)
    rows = read_jsonl(mode.answers_path)
    excluded = h5_excluded(rows)
    ans = load_answers(mode, bf=bf)
    late = [x for x in ans if x["dataset"] in NEW_DATASETS and x["wave"] not in STAGE_WAVES[2]]
    if late:
        refuse([f"{len(late)} new-collection answers outside the Stage 2 waves"], "22_model.py")
    datasets = [ds for ds in mode.datasets() if primary_answers(ans, ds)]
    h5_sets = [ds for ds in H5_DATASETS if ds in datasets]

    rep = Report()
    rep.data |= {"descriptive_suite": []}
    rep.say(f"# Experiment 010: Stage 2 model results{mode.tag}\n")
    rep.say(f"Generated by `pipeline/22_model.py --stage 2`. New-collection waves 1 to 11 and the "
            f"holdouts. Seed {SEED}, {a.n_boot} bootstrap draws, 90% percentile intervals, "
            "prompt-level cluster bootstrap, contrasts draw by draw. Retention = pooled Dice "
            "over answer pairs: the share of brand appearances with a status in one answer that "
            "keep it in the other. Lag = days between the two answers' run dates. Aggregates "
            "only.\n")
    if excluded:
        rep.say("Audit A: waves below 36 of 40 left out of H5's lag bins for their platform "
                "(kept everywhere else): " + ", ".join(f"{ds} wave {w}"
                                                        for ds, w in sorted(excluded)) + ".\n")
    else:
        rep.say("Audit A: no wave fell below 36 of 40, so every wave is in H5's lag bins.\n")
    if bf is None:
        rep.say("Best-for files are missing, so WS is empty here.\n")
    panels = {ds: dataset_panel(ans, ds, n_boot=a.n_boot) for ds in datasets}

    passed = h_pos(rep, panels)
    pla_ok = None
    if passed:
        h5_panels = {ds: h5_panel(primary_answers(ans, ds), ds, excluded=excluded,
                                  n_boot=a.n_boot) for ds in h5_sets}
        pla_ok = s2_h_pla(rep, ans, h5_sets, excluded, a.n_boot)
        if h5_sets:
            s2_holm(rep, h5_panels, h5_sets)
            s2_secondary(rep, ans, h5_panels, h5_sets, a.n_boot)
        rep.say("## Decision rules (spec §5, 90% CI)\n")
        rep.say(DECISION_TABLE + "\n")
        rep.say("H5's verdicts use the CI at each test's Holm-adjusted level (table above).\n")
        second = load_answers(mode, rejudge=True, bf=bf)
        s2_second = [x for x in second if x["dataset"] in NEW_DATASETS
                     and x["wave"] in STAGE2_NEW_WAVES]
        if s2_second:
            e = audit_e(ans, s2_second)
            rep.data["audit_e_agreement"] = e["agreement"]
            if e["agreement"] < AUDIT_E_MIN:
                rep.say(f"**Instrument-noise caveat:** judge test-retest agreement on the Stage 2 "
                        f"sample {pct(e['agreement'])} is below {AUDIT_E_MIN:.0%} (Audit E), so "
                        "the retention figures need an instrument-noise caveat and robustness "
                        "R4 is promoted to the main text.\n")
        rep.say("## Stage 2 descriptives (no tests)\n")
        s2_curve(rep, ans, h5_sets, a.n_boot)
        s2_descriptive_suite(rep, panels, h5_sets, mode)
        s2_models(rep, ans, h5_sets)
        s2_claude_vs_009(rep, ans, mode, bf, a.n_boot)

    out = mode.results
    out.mkdir(parents=True, exist_ok=True)
    rep.data["meta"] = {"seed": SEED, "n_boot": a.n_boot, "alpha": ALPHA,
                        "family_alpha": FAMILY_ALPHA, "eq_band": EQ_BAND, "mode": mode.kind,
                        "world": mode.world, "stage": 2, "h_pos_passed": passed,
                        "h_pla_ok": pla_ok, "h5_datasets": h5_sets,
                        "h5_excluded_waves": sorted(map(list, excluded)),
                        "labels": {ds: SPEC[ds].label for ds in datasets},
                        "color_keys": {ds: SPEC[ds].color_key for ds in datasets},
                        "n_answers": {ds: len(primary_answers(ans, ds)) for ds in datasets},
                        "recommended": list(REC)}
    (out / "stage2_model.json").write_text(json.dumps(jsonable(rep.data), indent=1) + "\n")
    text = "\n".join(rep.lines) + "\n"
    (out / "stage2_model.md").write_text(text)
    print(text)
    print(f"wrote {out / 'stage2_model.md'} and .json")

    if not passed:
        sys.exit(1)
    if a.expect:
        checks = expect_checks_s2(rep, mode, meta, passed, ans, excluded)
        print(f"\ndry-run check ({a.expect}, Stage 2 world {mode.world}):")
        for name, ok, detail in checks:
            print(f"  {'OK  ' if ok else 'FAIL'} {name}: {detail}")
        print(f"  info (not asserted): H_pla null or negligible everywhere: {pla_ok}")
        if not all(ok for _, ok, _ in checks):
            sys.exit(2)


if __name__ == "__main__":
    main()
