"""Stage 23: Stage 1 robustness checks (spec §7) -> results/stage1_robustness.md (+ .json).

Every check re-runs the Stage 1 tests (H1, H2, H3, H4, H6, H7; unadjusted 90%
CIs, the spec §5 decision rules) on a variant of the data. Runs only after
22_model.py has passed H_pos (spec §7.1).

  R1  every brand the judge names: lexicon brands plus normalized untracked
      names, order = the judge's order of first appearance (no best-for, so
      no H7).
  R2  modal model only, per dataset and arm (Audit F): answers reporting any
      other model, or none, are dropped. ChatGPT reported gpt-5-6 in waves 1
      to 5 and gpt-6 in waves 6 and 7, so R2 for chatgpt_b2b is waves 1 to 5.
  R3  answers with no lexicon brand excluded (refusals and empty answers are
      already excluded everywhere, Audit A).
  R4  the judge's second pass on the Audit E sample: the tests with the
      re-judged answers swapped in, and the identical-text ceiling (retention
      between the two passes on the same answer text).
  R5  category-level clusters for the B2B datasets (the bootstrap resamples
      categories instead of prompts).
  R6  claude_b2b with ui_default and ui_think pooled (6 runs per prompt;
      within pairs = same prompt, different waves, either arm).
  R8  009's "shortlist" vs "evaluate" prompts, separately (B2B datasets).
  R7  is Stage 2 only.

Stage 2 (``--stage 2``) -> results/stage2_robustness.md (+ .json): every check
re-runs H5 (far minus near retention, TOST +/-0.05, unadjusted 90% CIs) for
the shortlist (R) and its secondary forms on the top choice (T) and the
best-for use case (WS), on the three new datasets (and chatgpt_consumer's
holdout lags where the check applies):

  R1  every brand the judge names (R and T; no best-for, so no WS).
  R2  modal model only (Audit F, over all 11 waves): for chatgpt_b2b the mode
      is now gpt-6 (waves 6 to 11), so its bins keep only the pairs between
      those waves; the kept pair counts are reported, empty bins as such.
  R3  answers with no lexicon brand excluded.
  R4  the judge's second pass (Stage 1 sample reused plus the Stage 2 sample)
      swapped in, and the identical-text ceiling.
  R5  category-level clusters (B2B).
  R6  claude_b2b with ui_default and ui_think pooled: no new data and no drift
      test, so the Stage 1 suite is repeated, labeled unchanged.
  R7  H5 with alternative bins: 0 to 6 vs 27 to 34 days apart; and a weighted
      regression of pair retention on lag (slope per 30 days, cluster
      bootstrap), every within-prompt pair.
  R8  shortlist vs evaluate prompts (B2B).

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/23_robustness.py --stage 1
  uv run python .../23_robustness.py --stage 1 --split explore | --synthetic planted
  uv run python .../23_robustness.py --stage 2 [--synthetic planted_stable]
"""

from __future__ import annotations

import argparse
import json

from common import (
    EQ_BAND,
    EQ_LABELS,
    H5_CONSUMER,
    H5_DATASETS,
    R7_FAR_DAYS,
    R7_NEAR_DAYS,
    days_label,
    eq_verdict,
    h5_excluded,
    h5_panel,
    h5_row,
    lag_regression,
    load_stage_bestfor,
    read_jsonl,
    ALL_BRAND_KEYS,
    B2B_DATASETS,
    N_BOOT,
    R6_ARMS,
    SPEC,
    Est,
    Panel,
    add_mode_args,
    analysis_gate,
    dataset_panel,
    fmt,
    fmt_ci,
    jsonable,
    load_answers,
    load_bestfor,
    model_modal,
    mode_from_args,
    primary_answers,
    refuse,
    run_suite,
    unit_strata,
    within_pairs,
)

SHORT = {"SUPPORTED": "supported", "SMALLER": "smaller than 0.10?", "NOT_SHOWN": "not shown",
         "NULL": "null", "NEGLIGIBLE": "negligible", "REAL": "real",
         "INCONCLUSIVE": "inconclusive", "NOT_SUPPORTED": "not supported", "NA": "n/a"}
TESTS = ("H1", "H2", "H3", "H4", "H6", "H7")


class Out:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.data: dict = {}

    def say(self, s: str = "") -> None:
        self.lines.append(s)

    def table_head(self) -> None:
        self.say("| Dataset | Answers | R within | " + " | ".join(TESTS) + " |")
        self.say("|---|---|---|" + "---|" * len(TESTS))

    def row(self, check: str, label: str, panel: Panel, n: int, keys: dict | None = None) -> None:
        rows, _ = run_suite(panel, label, keys=keys)
        by = {r["test"]: r for r in rows}
        rk = (keys or {}).get("R", "R")
        r = panel.est("within", rk)
        cells = []
        for t in TESTS:
            x = by.get(t)
            cells.append(f"{fmt_ci(x['estimate'], x['lo'], x['hi'])} {SHORT[x['verdict']]}"
                         if x else "")
        self.say(f"| {label} | {n} | {fmt_ci(r.point, *r.ci())} | " + " | ".join(cells) + " |")
        self.data.setdefault(check, []).append({"dataset": label, "answers": n,
                                                "R_within": [r.point, *r.ci()], "tests": rows})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_mode_args(ap)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    mode = mode_from_args(a)
    problems = analysis_gate(mode, a.n_boot)
    model_json = mode.results / f"stage{mode.stage}_model.json"
    if not model_json.exists():
        problems.append("run 22_model.py first (H_pos comes first, spec §7.1)")
    elif not json.loads(model_json.read_text())["meta"]["h_pos_passed"]:
        problems.append("H_pos failed in 22_model.py: the study stops (spec §7.1)")
    if problems:
        refuse(problems, "23_robustness.py")
    if mode.stage == 2:
        stage2(mode, a)
        return

    bf = load_bestfor(mode.bestfor)
    ans = load_answers(mode, bf=bf)
    second = load_answers(mode, rejudge=True, bf=bf)
    datasets = [ds for ds in mode.datasets() if primary_answers(ans, ds)]
    b2b = [ds for ds in datasets if ds in B2B_DATASETS]
    o = Out()
    o.say(f"# Experiment 010: Stage {mode.stage} robustness{mode.tag}\n")
    o.say("Generated by `pipeline/23_robustness.py`. Each cell: estimate [90% CI] and the spec "
          "§5 verdict, unadjusted (the Holm-adjusted primary verdicts are in stage1_model.md). "
          "Tests: H1 R - Pk, H2 R - T, H3 T - P1, H4 T->R, H6 R - M, H7 R - WS.\n")

    o.say("## R1: every brand the judge names\n")
    o.table_head()
    for ds in datasets:
        o.row("R1", ds, dataset_panel(ans, ds, n_boot=a.n_boot, with_baselines=False),
              len(primary_answers(ans, ds)), keys=ALL_BRAND_KEYS)
    o.say("")

    o.say("## R2: modal model only\n")
    o.table_head()
    notes = []
    for ds in datasets:
        own = primary_answers(ans, ds)
        modal = model_modal(own)
        sub = [x for x in own if x.get("model") == modal]
        o.row("R2", ds, dataset_panel(ans, ds, sub=sub, n_boot=a.n_boot, with_baselines=False),
              len(sub))
        waves = sorted({x["wave"] for x in sub}) if ds in B2B_DATASETS else []
        notes.append(f"- {ds}: modal `{modal}`, {len(sub)} of {len(own)} answers kept"
                     + (f" (waves {', '.join(map(str, waves))})" if waves else ""))
    o.say("")
    o.lines += notes
    o.say("")

    o.say("## R3: answers with no lexicon brand excluded\n")
    o.table_head()
    for ds in datasets:
        sub = [x for x in primary_answers(ans, ds) if x["order"]]
        o.row("R3", ds, dataset_panel(ans, ds, sub=sub, n_boot=a.n_boot, with_baselines=False),
              len(sub))
    o.say("")

    o.say("## R4: the judge's second pass (Audit E sample)\n")
    if not second:
        o.say("No second pass available.\n")
    else:
        swap = {x["task_id"]: x for x in second}
        o.say("Tests with the re-judged answers swapped in:\n")
        o.table_head()
        for ds in datasets:
            own = primary_answers(ans, ds)
            n_swapped = sum(x["task_id"] in swap for x in own)
            if not n_swapped:
                continue
            sub = [swap.get(x["task_id"], x) for x in own]
            o.row("R4", f"{ds} ({n_swapped} swapped)",
                  dataset_panel(ans, ds, sub=sub, n_boot=a.n_boot, with_baselines=False), len(sub))
        o.say("")
        o.say("Identical-text ceiling: retention between the two judge passes on the same "
              "answer (any status change here is the judge, not the AI).\n")
        keys = ("R", "T", "C", "M", "Pk", "WS", "WP")
        o.say("| Dataset | Answers | " + " | ".join(keys) + " |")
        o.say("|---|---|" + "---|" * len(keys))
        first = {x["task_id"]: x for x in ans}
        ceiling = {}
        for ds in [*datasets, "all"]:
            pairs = [(first[x["task_id"]], x) for x in second if x["task_id"] in first
                     and (ds == "all" or x["dataset"] == ds)]
            if not pairs:
                continue
            p = Panel(unit_strata([x for x, _ in pairs]), n_boot=a.n_boot)
            p.add("ceiling", pairs)
            cells = {k: [p.est("ceiling", k).point, *p.est("ceiling", k).ci()] for k in keys}
            ceiling[ds] = cells
            o.say(f"| {ds} | {len(pairs)} | " + " | ".join(fmt(cells[k][0]) for k in keys) + " |")
        o.data["R4_ceiling"] = ceiling
        o.say("")

    o.say("## R5: category-level clusters (B2B)\n")
    o.table_head()
    for ds in b2b:
        o.row("R5", ds, dataset_panel(ans, ds, n_boot=a.n_boot, by_category=True,
                                      with_baselines=False), len(primary_answers(ans, ds)))
    o.say("")

    o.say("## R6: claude_b2b with ui_default and ui_think pooled\n")
    pooled = [x for x in ans if x["dataset"] == "claude_b2b" and x["arm"] in R6_ARMS]
    if pooled:
        o.table_head()
        p = Panel(unit_strata(pooled), n_boot=a.n_boot)
        p.add("within", within_pairs(pooled, pool_arms=True))
        o.row("R6", "claude_b2b (ui_default + ui_think)", p, len(pooled))
        o.say("")
    else:
        o.say("No claude_b2b answers.\n")

    o.say("## R8: shortlist vs evaluate prompts (B2B)\n")
    o.table_head()
    for ds in b2b:
        for intent in ("shortlist", "evaluate"):
            sub = [x for x in primary_answers(ans, ds) if x["intent"] == intent]
            if sub:
                o.row("R8", f"{ds}, {intent}", dataset_panel(ans, ds, sub=sub, n_boot=a.n_boot,
                                                             with_baselines=False), len(sub))
    o.say("")
    o.say("R7 (alternative lag bins for H5) is Stage 2 only.\n")
    if any(SPEC[ds].underpowered for ds in datasets):
        o.say("chatgpt_agency is underpowered (27 prompts, 3 runs each).\n")

    mode.results.mkdir(parents=True, exist_ok=True)
    path = mode.results / f"stage{mode.stage}_robustness.md"
    path.write_text("\n".join(o.lines) + "\n")
    (mode.results / f"stage{mode.stage}_robustness.json").write_text(
        json.dumps(jsonable(o.data), indent=1) + "\n")
    print("\n".join(o.lines))
    print(f"wrote {path}")


# ====================================================== Stage 2: over time

H5_KEYS = (("R", "R"), ("T", "T"), ("WS", "WS"))


class Out2(Out):
    def h5_head(self) -> None:
        self.say("| Dataset | Answers | Near / far pairs | R near | R far | H5 R (far minus near) "
                 "| H5 T | H5 WS |")
        self.say("|---|---|---|---|---|---|---|---|")

    def h5(self, check: str, label: str, own: list[dict], ds: str, *, excluded: set,
           n_boot: int, keys: dict | None = None, bins: tuple | None = None,
           by_category: bool = False) -> dict:
        keys = keys or {}
        panel = h5_panel(own, ds, excluded=excluded, bins=bins, n_boot=n_boot,
                         by_category=by_category)
        rows, cells = [], []
        for name, default in H5_KEYS:
            k = keys.get(name, default)
            if k is None:
                cells.append("n/a")
                continue
            if not panel.sets["near"].n_pairs or not panel.sets["far"].n_pairs:
                cells.append("no pairs in a bin")
                continue
            r, _ = h5_row(panel, ds, k, test=f"H5 {name}")
            rows.append(r)
            cells.append(f"{fmt_ci(r['estimate'], r['lo'], r['hi'])} {SHORT[r['verdict']]}")
        rk = keys.get("R", "R")
        nn, nf = panel.sets["near"].n_pairs, panel.sets["far"].n_pairs
        near = fmt_ci(panel.est("near", rk).point, *panel.est("near", rk).ci()) if nn else "n/a"
        far = fmt_ci(panel.est("far", rk).point, *panel.est("far", rk).ci()) if nf else "n/a"
        self.say(f"| {label} | {len(own)} | {nn} / {nf} | {near} | {far} | " + " | ".join(cells)
                 + " |")
        rec = {"dataset": label, "answers": len(own), "near_pairs": nn, "far_pairs": nf,
               "tests": rows}
        self.data.setdefault(check, []).append(rec)
        return rec


def ceiling(o: Out, ans: list[dict], second: list[dict], datasets: list[str], n_boot: int
            ) -> dict:
    o.say("Identical-text ceiling: retention between the two judge passes on the same "
          "answer (any status change here is the judge, not the AI).\n")
    keys = ("R", "T", "C", "M", "Pk", "WS", "WP")
    o.say("| Dataset | Answers | " + " | ".join(keys) + " |")
    o.say("|---|---|" + "---|" * len(keys))
    first = {x["task_id"]: x for x in ans}
    out = {}
    for ds in [*datasets, "all"]:
        pairs = [(first[x["task_id"]], x) for x in second if x["task_id"] in first
                 and (ds == "all" or x["dataset"] == ds)]
        if not pairs:
            continue
        p = Panel(unit_strata([x for x, _ in pairs]), n_boot=n_boot)
        p.add("ceiling", pairs)
        cells = {k: [p.est("ceiling", k).point, *p.est("ceiling", k).ci()] for k in keys}
        out[ds] = cells
        o.say(f"| {ds} | {len(pairs)} | " + " | ".join(fmt(cells[k][0]) for k in keys) + " |")
    o.say("")
    return out


def stage2(mode, a) -> None:
    bf = load_stage_bestfor(mode)
    rows = read_jsonl(mode.answers_path)
    excluded = h5_excluded(rows)
    ans = load_answers(mode, bf=bf)
    second = load_answers(mode, rejudge=True, bf=bf)
    present = {x["dataset"] for x in ans}
    h5s = [ds for ds in H5_DATASETS if ds in present]
    with_cons = h5s + ([H5_CONSUMER] if H5_CONSUMER in present else [])
    nb = a.n_boot
    o = Out2()
    o.say(f"# Experiment 010: Stage 2 robustness{mode.tag}\n")
    o.say("Generated by `pipeline/23_robustness.py --stage 2`. Each cell: estimate [90% CI] and "
          f"the spec §5 equivalence verdict (TOST +/-{EQ_BAND:.2f}), unadjusted (the "
          "Holm-adjusted primary verdicts are in stage2_model.md). H5 = retention over pairs "
          f"{days_label((27, None))} apart minus retention over pairs {days_label((1, 2))} apart "
          f"(chatgpt_consumer: {days_label((15, None))} vs {days_label((0, 2))}), for the "
          "shortlist (R), the top choice (T) and the best-for use case (WS).\n")
    if excluded:
        o.say("Audit A: left out of H5's bins: " + ", ".join(f"{ds} wave {w}"
                                                            for ds, w in sorted(excluded)) + ".\n")

    o.say("## R1: every brand the judge names\n")
    o.h5_head()
    for ds in with_cons:
        o.h5("R1", ds, primary_answers(ans, ds), ds, excluded=excluded, n_boot=nb,
             keys={"R": "R_all", "T": "T_all", "WS": None})
    o.say("")

    o.say("## R2: modal model only\n")
    o.h5_head()
    notes = []
    for ds in with_cons:
        own = primary_answers(ans, ds)
        modal = model_modal(own)
        sub = [x for x in own if x.get("model") == modal]
        rec = o.h5("R2", ds, sub, ds, excluded=excluded, n_boot=nb)
        waves = sorted({x["wave"] for x in sub}) if ds in H5_DATASETS else []
        n_items = len({x["item_id"] for x in sub}) or 1
        notes.append(f"- {ds}: modal `{modal}`, {len(sub)} of {len(own)} answers kept"
                     + (f" (waves {', '.join(map(str, waves))})" if waves else "")
                     + f"; {rec['near_pairs']} near and {rec['far_pairs']} far pairs "
                       f"({rec['near_pairs'] / n_items:.1f} and {rec['far_pairs'] / n_items:.1f} "
                       "per prompt)"
                     + ("; a bin is empty, so H5 cannot be estimated under R2"
                        if not rec["near_pairs"] or not rec["far_pairs"] else ""))
    o.say("")
    o.lines += notes
    o.say("")

    o.say("## R3: answers with no lexicon brand excluded\n")
    o.h5_head()
    for ds in with_cons:
        sub = [x for x in primary_answers(ans, ds) if x["order"]]
        o.h5("R3", ds, sub, ds, excluded=excluded, n_boot=nb)
    o.say("")

    o.say("## R4: the judge's second pass (Audit E samples)\n")
    if not second:
        o.say("No second pass available.\n")
    else:
        swap = {x["task_id"]: x for x in second}
        o.say("H5 with the re-judged answers swapped in (Stage 1 sample reused, plus the Stage 2 "
              "sample of waves 8 to 11):\n")
        o.h5_head()
        for ds in with_cons:
            own = primary_answers(ans, ds)
            n_swapped = sum(x["task_id"] in swap for x in own)
            if n_swapped:
                o.h5("R4", f"{ds} ({n_swapped} swapped)", [swap.get(x["task_id"], x) for x in own],
                     ds, excluded=excluded, n_boot=nb)
        o.say("")
        o.data["R4_ceiling"] = ceiling(o, ans, second, with_cons, nb)

    o.say("## R5: category-level clusters (B2B)\n")
    o.h5_head()
    for ds in h5s:
        o.h5("R5", ds, primary_answers(ans, ds), ds, excluded=excluded, n_boot=nb,
             by_category=True)
    o.say("")

    o.say("## R6: claude_b2b with ui_default and ui_think pooled\n")
    pooled = [x for x in ans if x["dataset"] == "claude_b2b" and x["arm"] in R6_ARMS]
    if pooled:
        o.say("No new claude.ai data at Stage 2 and no drift test (3 runs over 4 days), so this "
              "repeats the Stage 1 suite, unchanged.\n")
        o.table_head()
        p = Panel(unit_strata(pooled), n_boot=nb)
        p.add("within", within_pairs(pooled, pool_arms=True))
        o.row("R6", "claude_b2b (ui_default + ui_think)", p, len(pooled))
        o.say("")
    else:
        o.say("No claude_b2b answers.\n")

    o.say("## R7: alternative lag bins, and a regression on lag\n")
    o.say(f"H5 with near = {days_label(R7_NEAR_DAYS)} apart and far = {days_label(R7_FAR_DAYS)} "
          "apart (new collection):\n")
    o.h5_head()
    for ds in h5s:
        o.h5("R7_bins", ds, primary_answers(ans, ds), ds, excluded=excluded, n_boot=nb,
             bins=(R7_NEAR_DAYS, R7_FAR_DAYS))
    o.say("")
    o.say("Weighted least-squares slope of pair retention on days apart, every within-prompt "
          "pair (each pair weighted by its two answers' appearances, the pooled-retention "
          "analogue), shown as the change over 30 days with its 90% cluster-bootstrap interval "
          f"and read against the H5 band +/-{EQ_BAND:.2f}:\n")
    o.say("| Dataset | Pairs | R: change per 30 days | T: change per 30 days | WS: change per "
          "30 days |")
    o.say("|---|---|---|---|---|")
    reg = {}
    for ds in with_cons:
        own = primary_answers(ans, ds)
        cells, out = [], {}
        n_pairs = 0
        for key in ("R", "T", "WS"):
            e, n_pairs = lag_regression(own, key, excluded=excluded, n_boot=nb)
            e30 = Est(30 * e.point, 30 * e.raw)
            lo, hi = e30.ci()
            v = eq_verdict(lo, hi, EQ_BAND)
            out[key] = {"slope_per_day": e.point, "per_30_days": [e30.point, lo, hi],
                        "verdict": v, "label": EQ_LABELS[v]}
            cells.append(f"{fmt_ci(e30.point, lo, hi, 3)} {SHORT[v]}")
        reg[ds] = out | {"pairs": n_pairs}
        o.say(f"| {ds} | {n_pairs} | " + " | ".join(cells) + " |")
    o.data["R7_regression"] = reg
    o.say("")

    o.say("## R8: shortlist vs evaluate prompts (B2B)\n")
    o.h5_head()
    for ds in h5s:
        for intent in ("shortlist", "evaluate"):
            sub = [x for x in primary_answers(ans, ds) if x["intent"] == intent]
            if sub:
                o.h5("R8", f"{ds}, {intent}", sub, ds, excluded=excluded, n_boot=nb)
    o.say("")

    mode.results.mkdir(parents=True, exist_ok=True)
    path = mode.results / "stage2_robustness.md"
    path.write_text("\n".join(o.lines) + "\n")
    (mode.results / "stage2_robustness.json").write_text(
        json.dumps(jsonable(o.data), indent=1) + "\n")
    print("\n".join(o.lines))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
