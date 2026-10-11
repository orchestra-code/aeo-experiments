"""Stage 21: data-quality audits (spec §2) -> results/stage1_audits.md (+ .json).

Run before the model. Reads the answer frame from 20_answers.py (flagged
answers included), the Audit E second pass, the best-for classifier passes
and, for Audit D, ``results/audit_d_score.json`` written by the harness's
spot-check script. Computes no retention metric.

- Audit A, completeness: per platform and wave of the new collection, tasks
  collected, non-empty and not refused (pass at 38 of 40; below 36 a wave
  leaves Stage 2's H5 lag bins); per holdout dataset and arm, the same counts.
- Audit B, labels: answers whose raw judge output had more than two top
  choices (demoted to one of many by the production post-processing), judge
  rows on the pinned judge, judge names mapped back to a lexicon brand.
- Audit C, independence: the bootstrap cluster (a note; R5 is in 23_).
- Audit D, lexicon v3 precision and recall: pass/fail from the score file.
- Audit E, judge test-retest: category agreement and Cohen's kappa on the
  seeded re-judge sample (pass at 90%).
- Audit F, model drift: the reported model per platform and wave, the modal
  model, and any change mid-collection (a finding; R2 restricts to the mode).
- Audit G, best-for classifier: segment test-retest on all distinct phrases
  (pass at 90%).

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/21_audits.py --stage 1
  uv run python .../21_audits.py --stage 1 --split explore | --synthetic planted
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict

from common import (
    AUDIT_A_H5_MIN,
    AUDIT_A_MIN,
    AUDIT_D_PRECISION,
    AUDIT_D_RECALL,
    AUDIT_E_MIN,
    AUDIT_G_MIN,
    EXPLORE_TAXONOMY_CATEGORIES,
    NEW_DATASETS,
    PROMPTS_PER_WAVE,
    SPEC,
    STAGE_WAVES,
    add_mode_args,
    audit_e,
    jsonable,
    load_bestfor,
    mode_from_args,
    pct,
    fmt,
    read_jsonl,
    usable,
)


def audit_a(rows: list[dict], stage: int, out: list[str]) -> dict:
    out.append("## Audit A: collection completeness\n")
    res: dict = {"new": [], "holdout": [], "passes": True}
    out.append(f"New collection: tasks per platform and wave (need at least {AUDIT_A_MIN} of "
               f"{PROMPTS_PER_WAVE} non-empty and not refused; below {AUDIT_A_H5_MIN} the wave "
               "would leave Stage 2's lag bins). Judge failures are listed separately.\n")
    out.append("| Dataset | Wave | Collected | Non-empty, not refused | Refusals | Empty | "
               "Judge failures | Pass |")
    out.append("|---|---|---|---|---|---|---|---|")
    for ds in NEW_DATASETS:
        sub = [r for r in rows if r["dataset"] == ds]
        if not sub:
            continue
        for w in STAGE_WAVES[stage]:
            g = [r for r in sub if r["wave"] == w]
            ok = sum(not r["empty"] and not r["refusal"] for r in g)
            rec = {"dataset": ds, "wave": w, "collected": len(g), "ok": ok,
                   "refusals": sum(r["refusal"] for r in g), "empty": sum(r["empty"] for r in g),
                   "judge_failures": sum(not r["judge_ok"] for r in g),
                   "passes": ok >= AUDIT_A_MIN, "h5_bins": ok >= AUDIT_A_H5_MIN}
            res["new"].append(rec)
            res["passes"] &= rec["passes"]
            out.append(f"| {ds} | {w} | {len(g)} | {ok} | {rec['refusals']} | {rec['empty']} | "
                       f"{rec['judge_failures']} | {'yes' if rec['passes'] else '**NO**'} |")
    out.append("")
    hold = [r for r in rows if r["dataset"] not in NEW_DATASETS]
    if hold:
        out.append("Holdout (or exploration) datasets, by arm:\n")
        out.append("| Dataset | Arm | Runs (study and wave) | Prompts | Answers | Refusals | Empty | "
                   "Judge failures |")
        out.append("|---|---|---|---|---|---|---|---|")
        groups = defaultdict(list)
        for r in hold:
            groups[(r["dataset"], r["arm"])].append(r)
        for (ds, arm), g in sorted(groups.items()):
            rec = {"dataset": ds, "arm": arm,
                   "runs": len({(r["source_exp"], r["wave"]) for r in g}),
                   "prompts": len({r["item_id"] for r in g}), "answers": len(g),
                   "refusals": sum(r["refusal"] for r in g), "empty": sum(r["empty"] for r in g),
                   "judge_failures": sum(not r["judge_ok"] for r in g)}
            res["holdout"].append(rec)
            out.append(f"| {ds} | {arm} | {rec['runs']} | {rec['prompts']} | {rec['answers']} | "
                       f"{rec['refusals']} | {rec['empty']} | {rec['judge_failures']} |")
        out.append("")
    out.append("Refusals (an apology-shaped refusal in the first 600 characters, 009's heuristic), "
               "empty answers and judge failures are excluded from every analysis.\n")
    return res


def audit_b(rows: list[dict], meta: dict, out: list[str]) -> dict:
    out.append("## Audit B: what the labels mean\n")
    out.append("Categories are the production judge's (top choice, one of many, generic mention, "
               "cautioned against). More than two raw top choices in one answer are demoted to "
               "one of many by the production post-processing; the raw output is kept.\n")
    out.append("| Dataset | Usable answers | Raw output with more than two top choices (demoted) | "
               "Post-processing over the cap | Judge names mapped back by the lexicon matcher | "
               "Judge names outside the lexicon per answer |")
    out.append("|---|---|---|---|---|---|")
    res = {}
    for ds in sorted({r["dataset"] for r in rows}, key=list(SPEC).index):
        g = [r for r in rows if r["dataset"] == ds and usable(r)]
        if not g:
            continue
        dem = sum(r["n_raw_top_items"] > 2 for r in g) / len(g)
        cap = sum((r["dropped"] or {}).get("overCap", 0) > 0 for r in g) / len(g)
        mapped = sum(r["fallback_mapped"] for r in g)
        unt = sum(r["untracked_names"] for r in g) / len(g)
        res[ds] = {"answers": len(g), "demoted": dem, "over_cap": cap, "fallback_mapped": mapped,
                   "untracked_per_answer": unt}
        out.append(f"| {ds} | {len(g)} | {pct(dem)} | {pct(cap)} | {mapped} | {unt:.1f} |")
    out.append("")
    off = meta.get("judge_rows_off_pin")
    out.append(f"Judge pin (`harness/judge_pin.json`) sha256 "
               f"`{(meta.get('judge_pin_sha256') or 'missing')[:12]}...`; judged rows on another "
               f"judge build: {off}.\n")
    res["judge_rows_off_pin"] = off
    return res


def audit_d(mode, out: list[str]) -> dict:
    out.append("## Audit D: lexicon v3 precision and recall\n")
    if mode.audit_d is None:
        out.append("Not applicable: the exploration split uses the frozen 005 and 009 lexicons.\n")
        return {"status": "n/a"}
    if not mode.audit_d.exists():
        out.append(f"**Not scored yet** (`{mode.audit_d.name}` missing). 22_model.py will refuse "
                   "the confirmatory data until it passes.\n")
        return {"status": "missing", "passes": False}
    s = json.loads(mode.audit_d.read_text())
    ok = bool(s.get("passes"))
    out.append(f"Precision {fmt(s.get('precision'))} (need {AUDIT_D_PRECISION}), recall "
               f"{fmt(s.get('recall'))} (need {AUDIT_D_RECALL}), signed by "
               f"{s.get('signed_by') or 'nobody'}: **{'PASS' if ok else 'FAIL'}**\n")
    return {"status": "scored", "passes": ok, **{k: s.get(k) for k in
                                                ("precision", "recall", "signed_by")}}


def audit_e_section(first: list[dict], second: list[dict], out: list[str]) -> dict:
    out.append("## Audit E: judge test-retest\n")
    if not second:
        out.append("**No second pass yet.** The seeded 10% sample must be judged twice "
                   "(20_answers.py --write-rejudge-sample, then judge_runner.mts --split "
                   "b2b_main_rejudge; the holdout sample is tasks_holdout_rejudge).\n")
        return {"status": "missing", "passes": False}
    first = [a for a in first if usable(a)]
    second = [a for a in second if usable(a)]
    out.append(f"Same answer text judged twice. Pass: category agreement at least "
               f"{AUDIT_E_MIN:.0%} over lexicon brand mentions.\n")
    out.append("| Group | Answers re-judged | Brand mentions | Category agreement | Cohen's kappa "
               "| Top choices kept as top choice |")
    out.append("|---|---|---|---|---|---|")
    res: dict = {"groups": {}}
    groups = [("all", lambda d: True), ("new collection", lambda d: d in NEW_DATASETS),
              ("old datasets", lambda d: d not in NEW_DATASETS)]
    groups += [(ds, (lambda d, ds=ds: d == ds)) for ds in SPEC]
    for name, keep in groups:
        e = audit_e([a for a in first if keep(a["dataset"])],
                    [a for a in second if keep(a["dataset"])])
        if not e["answers"]:
            continue
        e.pop("pairs")
        res["groups"][name] = e
        out.append(f"| {name} | {e['answers']} | {e['mentions']} | {pct(e['agreement'])} | "
                   f"{fmt(e['kappa'])} | {pct(e['top_kept'])} of {e['top_choices']} |")
    allg = res["groups"].get("all", {})
    res["passes"] = bool(allg) and allg["agreement"] >= AUDIT_E_MIN
    out.append("")
    out.append(f"Pooled agreement {pct(allg.get('agreement', float('nan')))}: "
               f"**{'PASS' if res['passes'] else 'FAIL: retention figures carry an instrument-noise caveat and R4 moves to the main text'}**\n")
    if allg.get("changes"):
        out.append("Category changes between passes (first -> second): " + "; ".join(
            f"{k}: {v}" for k, v in list(allg["changes"].items())[:8]) + "\n")
    return res


def audit_f(rows: list[dict], out: list[str]) -> dict:
    out.append("## Audit F: model drift\n")
    out.append("The model each answer reports (DataForSEO `model`; Anthropic model id; claude.ai "
               "answers are recorded as `claude.ai`; holdout ChatGPT from the source studies).\n")
    res = {}
    keys = sorted({(r["dataset"], r["arm"]) for r in rows},
                  key=lambda k: (list(SPEC).index(k[0]), k[1]))
    for ds, arm in keys:
        g = [r for r in rows if r["dataset"] == ds and r["arm"] == arm and usable(r)]
        if not g:
            continue
        overall = Counter(r.get("model") or "(not recorded)" for r in g)
        modal = overall.most_common(1)[0][0]
        by_wave = defaultdict(Counter)
        for r in g:
            by_wave[(r["source_exp"], r["wave"])][r.get("model") or "(not recorded)"] += 1
        changed = sorted(f"{e} w{w}" for (e, w), c in by_wave.items()
                         if c.most_common(1)[0][0] != modal)
        name = ds if arm == SPEC[ds].arm else f"{ds} ({arm})"
        res[name] = {"modal": modal, "models": dict(overall), "off_modal_share":
                     1 - overall[modal] / len(g), "runs_with_other_modal": changed}
        out.append(f"- **{name}**: modal `{modal}` ({pct(overall[modal] / len(g))} of answers); "
                   + ", ".join(f"`{m}` {n}" for m, n in overall.most_common()))
        if ds in NEW_DATASETS:
            out.append("  - by wave: " + "; ".join(
                f"w{w} " + "/".join(m for m, _ in by_wave[(e, w)].most_common())
                for (e, w) in sorted(by_wave)))
        if changed:
            out.append(f"  - **model change mid-collection** (a finding; R2 keeps `{modal}` "
                       f"only): runs whose model differs from the mode: {', '.join(changed)}")
    out.append("")
    return res


def audit_g(mode, out: list[str]) -> dict:
    out.append("## Audit G: best-for classifier\n")
    bf = load_bestfor(mode.bestfor)
    if bf is None:
        out.append(f"**Not available yet** (best-for files under `{mode.bestfor.name}/`).\n")
        return {"status": "missing", "passes": False}
    res: dict = {"groups": {}}
    out.append(f"Segment test-retest over every distinct phrase (two classifier passes). Pass: "
               f"at least {AUDIT_G_MIN:.0%}.\n")
    out.append("| Categories | Distinct phrases | Same segment both passes | Outside every "
               "segment (pass a) |\n|---|---|---|---|")
    groups = (("all", lambda c: True),
              ("B2B", lambda c: c not in EXPLORE_TAXONOMY_CATEGORIES),
              ("headphones and agencies", lambda c: c in EXPLORE_TAXONOMY_CATEGORIES))
    for name, keep in groups:
        tot = agree = other = 0
        for c, lst in bf.phrases.items():
            if not keep(c):
                continue
            for e in lst:
                p = e["phrase"]
                ga = bf.seg_a.get(c, {}).get(p)
                tot += 1
                agree += ga is not None and bf.seg_b.get(c, {}).get(p) == ga
                other += ga in (None, "other", "unassigned")
        if not tot:
            continue
        res["groups"][name] = {"phrases": tot, "agreement": agree / tot, "outside": other / tot}
        out.append(f"| {name} | {tot} | {pct(agree / tot)} | {pct(other / tot)} |")
    a = res["groups"].get("all", {}).get("agreement", 0.0)
    res["passes"] = a >= AUDIT_G_MIN
    out.append(f"\nTest-retest {pct(a)}: **{'PASS' if res['passes'] else 'FAIL'}**\n")
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_mode_args(ap)
    a = ap.parse_args()
    mode = mode_from_args(a)
    if not mode.answers_path.exists():
        raise SystemExit(f"no answer frame at {mode.answers_path}; run 20_answers.py first")
    rows = read_jsonl(mode.answers_path)
    second = read_jsonl(mode.rejudge_path) if mode.rejudge_path.exists() else []
    meta = json.loads(mode.meta_path.read_text())

    out = [f"# Experiment 010: Stage {mode.stage} data-quality audits{mode.tag}\n",
           "Generated by `pipeline/21_audits.py`. Aggregates only.\n"]
    out.append(f"Answers in the frame: {len(rows)} ({sum(usable(r) for r in rows)} usable). "
               f"Firewall: {meta.get('filtered_waves', 0)} new-collection tasks from waves after "
               f"{max(STAGE_WAVES[mode.stage])} dropped before any judge output was read.")
    if meta.get("lexicon_v3_sha256"):
        out.append(f"Lexicon v3 sha256 `{meta['lexicon_v3_sha256'][:12]}...`; B2B taxonomy sha256 "
                   f"`{(meta.get('taxonomy_b2b_sha256') or '')[:12]}...`.")
    out.append("")
    res = {"A": audit_a(rows, mode.stage, out), "B": audit_b(rows, meta, out)}
    out.append("## Audit C: independence\n")
    out.append("Pairs share prompts, so every interval resamples prompts (the cluster), never "
               "pairs. The two prompts of a B2B category share a market; robustness R5 "
               "(23_robustness.py) resamples categories instead.\n")
    res["D"] = audit_d(mode, out)
    res["E"] = audit_e_section(rows, second, out)
    res["F"] = audit_f(rows, out)
    res["G"] = audit_g(mode, out)
    out.append("## Summary\n")
    out.append("| Audit | Result |\n|---|---|")
    out.append(f"| A completeness | {'pass' if res['A']['passes'] else 'see table'} |")
    out.append("| B demotions | reported |")
    out.append(f"| D lexicon v3 | {res['D'].get('status')}"
               f"{', pass' if res['D'].get('passes') else ''} |")
    out.append(f"| E judge test-retest | {'pass' if res['E'].get('passes') else res['E'].get('status', 'FAIL')} |")
    out.append(f"| F model drift | {'change found' if any(v['runs_with_other_modal'] for v in res['F'].values()) else 'no change'} |")
    out.append(f"| G classifier | {'pass' if res['G'].get('passes') else res['G'].get('status', 'FAIL')} |")
    out.append("")
    mode.results.mkdir(parents=True, exist_ok=True)
    path = mode.results / f"stage{mode.stage}_audits.md"
    path.write_text("\n".join(out) + "\n")
    (mode.results / f"stage{mode.stage}_audits.json").write_text(
        json.dumps(jsonable(res), indent=1) + "\n")
    print("\n".join(out))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
