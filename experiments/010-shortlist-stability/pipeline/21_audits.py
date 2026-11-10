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

Stage 2 (``--stage 2``, waves 1 to 11): Audit A per wave including 8 to 11,
with the 36-of-40 rule applied (a wave below it leaves H5's lag bins for
that platform) and the H5 bin pair counts from the true run dates, including
any pair a late task moved across a bin edge; Audit E on the Stage 2 sample
(waves 8 to 11; pass at 90% there), with the reused Stage 1 sample and the
pooled figure alongside; Audit F per wave with model counts and run dates;
Audit G on every distinct phrase Stage 2 uses (Stage 1 classifications
reused for the phrases Stage 1 saw, the rest classified at Stage 2).

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/21_audits.py --stage 1
  uv run python .../21_audits.py --stage 1 --split explore | --synthetic planted
  uv run python .../21_audits.py --stage 2 [--synthetic planted_stable]
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
    H5_CONSUMER,
    H5_CONSUMER_FAR,
    H5_CONSUMER_NEAR,
    H5_FAR,
    H5_NEAR,
    NEW_DATASETS,
    PROMPTS_PER_WAVE,
    R7_FAR_DAYS,
    R7_NEAR_DAYS,
    SPEC,
    STAGE2_NEW_WAVES,
    STAGE_WAVES,
    add_mode_args,
    audit_e,
    bin_pairs,
    days_label,
    h5_excluded,
    in_days,
    jsonable,
    lag_days,
    load_stage_bestfor,
    mode_from_args,
    nominal_lag,
    pct,
    fmt,
    primary_answers,
    read_jsonl,
    refuse,
    usable,
    within_pairs,
)


def audit_a(rows: list[dict], stage: int, out: list[str]) -> dict:
    out.append("## Audit A: collection completeness\n")
    res: dict = {"new": [], "holdout": [], "passes": True}
    out.append(f"New collection: tasks per platform and wave (need at least {AUDIT_A_MIN} of "
               f"{PROMPTS_PER_WAVE} non-empty and not refused; below {AUDIT_A_H5_MIN} the wave "
               "would leave Stage 2's lag bins). Judge failures are listed separately.\n")
    s2 = stage == 2
    if s2:
        out.append("| Dataset | Wave | Collected | Non-empty, not refused | Refusals | Empty | "
                   "Judge failures | Pass | In H5's lag bins |")
        out.append("|---|---|---|---|---|---|---|---|---|")
    else:
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
            line = (f"| {ds} | {w} | {len(g)} | {ok} | {rec['refusals']} | {rec['empty']} | "
                    f"{rec['judge_failures']} | {'yes' if rec['passes'] else '**NO**'} |")
            if s2:
                line += " yes |" if rec["h5_bins"] else " **NO: left out of H5's bins** |"
            out.append(line)
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


def lag_bins(rows: list[dict], out: list[str]) -> dict:
    """Stage 2: the pairs H5 and R7 use, from the true run dates (spec §3)."""
    out.append("### H5 lag bins from the true run dates\n")
    excluded = h5_excluded(rows)
    res: dict = {"excluded_waves": sorted([list(k) for k in excluded]), "datasets": {}}
    if excluded:
        out.append("Waves below 36 of 40 left out of H5's lag bins (kept everywhere else): "
                   + ", ".join(f"{ds} wave {w}" for ds, w in sorted(excluded)) + ".\n")
    else:
        out.append("No wave fell below 36 of 40, so every wave is in H5's lag bins.\n")
    out.append("Usable within-prompt answer pairs (same prompt, same platform) in each bin. Lag = "
               "days between the two answers' run dates. The schedule (days 0 to 6, 13, 20, 27, "
               "34) gives 11 near pairs (1 to 2 days apart) and 8 far pairs (27 days or more) "
               "per prompt; R7's bins are 0 to 6 and 27 to 34 days apart.\n")
    out.append("| Dataset | Prompts | Near (1 to 2 days) | Far (27+ days) | Near per prompt | Far "
               "per prompt | R7 near (0 to 6) | R7 far (27 to 34) | Pairs moved by run dates |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    us = [r for r in rows if usable(r)]
    bins = (("near", H5_NEAR), ("far", H5_FAR), ("r7_near", R7_NEAR_DAYS), ("r7_far", R7_FAR_DAYS))
    for ds in NEW_DATASETS:
        own = primary_answers(us, ds)
        if not own:
            continue
        pairs = within_pairs(own)
        n_items = len({a["item_id"] for a in own})
        cnt = {k: len(bin_pairs(pairs, b, excluded)) for k, b in bins}
        moved = []
        for x, y in pairs:
            lag, nom = lag_days(x, y), nominal_lag(x, y)
            if lag == nom:
                continue
            changes = [f"{'enters' if in_days(lag, b) else 'leaves'} {k}" for k, b in bins
                       if in_days(lag, b) != in_days(nom, b)]
            if changes:
                x, y = sorted((x, y), key=lambda a: a["wave"])
                moved.append({"item_id": x["item_id"], "waves": [x["wave"], y["wave"]],
                              "scheduled_lag": nom, "true_lag": lag, "bins_changed": changes})
        per = {k: cnt[k] / n_items for k in cnt}
        res["datasets"][ds] = {"prompts": n_items, **cnt,
                               "per_prompt": per, "moved": moved}
        out.append(f"| {ds} | {n_items} | {cnt['near']} | {cnt['far']} | {per['near']:.2f} | "
                   f"{per['far']:.2f} | {cnt['r7_near']} | {cnt['r7_far']} | {len(moved)} |")
    out.append("")
    for ds, d in res["datasets"].items():
        for m in d["moved"]:
            out.append(f"- {ds} {m['item_id']} waves {m['waves'][0]} and {m['waves'][1]}: "
                       f"scheduled {days_label((m['scheduled_lag'],) * 2)} apart, ran "
                       f"{days_label((m['true_lag'],) * 2)} apart, so the pair {' and '.join(m['bins_changed'])} (true lag used)")
    if any(d["moved"] for d in res["datasets"].values()):
        out.append("")
    cons = primary_answers(us, H5_CONSUMER)
    if cons:
        pairs = within_pairs(cons)
        near, far = bin_pairs(pairs, H5_CONSUMER_NEAR), bin_pairs(pairs, H5_CONSUMER_FAR)
        lags = [lag_days(x, y) for x, y in pairs]
        res["datasets"][H5_CONSUMER] = {"near": len(near), "far": len(far),
                                        "lag_range": [min(lags), max(lags)]}
        out.append(f"{H5_CONSUMER} (secondary H5, holdout lags {min(lags)} to {max(lags)} days): "
                   f"{len(near)} pairs {days_label(H5_CONSUMER_NEAR)} apart, {len(far)} pairs "
                   f"{days_label(H5_CONSUMER_FAR)} apart.\n")
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


def audit_e_stage2(first: list[dict], second: list[dict], out: list[str]) -> dict:
    out.append("## Audit E: judge test-retest\n")
    s2 = [a for a in second if a["dataset"] in NEW_DATASETS and a["wave"] in STAGE2_NEW_WAVES]
    if not s2:
        out.append("**No Stage 2 second pass yet.** The seeded 10% sample of waves 8 to 11 must be "
                   "judged twice (20_answers.py --stage 2 --write-rejudge-sample, then "
                   "judge_runner.mts --split b2b_main_rejudge_s2).\n")
        return {"status": "missing", "passes": False}
    first = [a for a in first if usable(a)]
    second = [a for a in second if usable(a)]
    out.append("Same answer text judged twice. The Stage 2 sample is a seeded 10% of waves 8 to "
               "11 (spec §2: the Stage 1 sample is reused). Pass: category agreement at least "
               f"{AUDIT_E_MIN:.0%} over lexicon brand mentions in the Stage 2 sample; the reused "
               "Stage 1 sample and the pooled figure are shown alongside.\n")
    out.append("| Group | Answers re-judged | Brand mentions | Category agreement | Cohen's kappa "
               "| Top choices kept as top choice |")
    out.append("|---|---|---|---|---|---|")

    def is_s2(a: dict) -> bool:
        return a["dataset"] in NEW_DATASETS and a["wave"] in STAGE2_NEW_WAVES

    groups = [("Stage 2 sample (waves 8 to 11)", is_s2)]
    groups += [(f"{ds}, waves 8 to 11", (lambda a, ds=ds: is_s2(a) and a["dataset"] == ds))
               for ds in NEW_DATASETS]
    groups += [("Stage 1 sample (waves 1 to 7, reused)",
                lambda a: a["dataset"] in NEW_DATASETS and not is_s2(a)),
               ("new collection, both samples", lambda a: a["dataset"] in NEW_DATASETS),
               ("all, with the holdout samples", lambda a: True)]
    res: dict = {"groups": {}}
    for name, keep in groups:
        e = audit_e([a for a in first if keep(a)], [a for a in second if keep(a)])
        if not e["answers"]:
            continue
        e.pop("pairs")
        res["groups"][name] = e
        out.append(f"| {name} | {e['answers']} | {e['mentions']} | {pct(e['agreement'])} | "
                   f"{fmt(e['kappa'])} | {pct(e['top_kept'])} of {e['top_choices']} |")
    main = res["groups"].get("Stage 2 sample (waves 8 to 11)", {})
    res["passes"] = bool(main) and main["agreement"] >= AUDIT_E_MIN
    res["agreement"] = main.get("agreement")
    out.append("")
    out.append(f"Stage 2 sample agreement {pct(main.get('agreement', float('nan')))}: "
               f"**{'PASS' if res['passes'] else 'FAIL: the retention figures need an instrument-noise caveat and R4 moves to the main text'}**\n")
    if main.get("changes"):
        out.append("Category changes between passes in the Stage 2 sample (first -> second): "
                   + "; ".join(f"{k}: {v}" for k, v in list(main["changes"].items())[:8]) + "\n")
    return res


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


def audit_f_stage2(rows: list[dict], out: list[str]) -> dict:
    """Stage 2: the reported model and run dates of every wave (a model change is a finding)."""
    out.append("## Audit F: model drift\n")
    out.append("The model each answer reports, per wave (DataForSEO `model`; Anthropic model id), "
               "and the answers' run dates (DataForSEO dates are UTC, so ChatGPT and Gemini "
               "answers are dated the day after the 20:00 local submission; Claude's is the local "
               "batch submission date; spec deviation 2).\n")
    res: dict = {}
    for ds in NEW_DATASETS:
        g = [r for r in rows if r["dataset"] == ds and usable(r)]
        if not g:
            continue
        overall = Counter(r.get("model") or "(not recorded)" for r in g)
        modal = overall.most_common(1)[0][0]
        out.append(f"**{ds}**: modal `{modal}` ({pct(overall[modal] / len(g))} of answers); "
                   + ", ".join(f"`{m}` {n}" for m, n in overall.most_common()) + "\n")
        out.append("| Wave | Answers | Models | Run dates |")
        out.append("|---|---|---|---|")
        waves = {}
        for w in sorted({r["wave"] for r in g}):
            gw = [r for r in g if r["wave"] == w]
            mc = Counter(r.get("model") or "(not recorded)" for r in gw)
            dc = Counter(r.get("run_date") for r in gw)
            waves[w] = {"answers": len(gw), "models": dict(mc), "run_dates": dict(sorted(dc.items()))}
            out.append(f"| {w} | {len(gw)} | " + ", ".join(f"`{m}` {n}" for m, n in mc.most_common())
                       + " | " + ", ".join(f"{d} ({n})" for d, n in sorted(dc.items())) + " |")
        changed = [w for w, v in waves.items() if Counter(v["models"]).most_common(1)[0][0] != modal]
        minority = [w for w, v in waves.items() if len(v["models"]) > 1]
        res[ds] = {"modal": modal, "models": dict(overall), "waves": waves,
                   "off_modal_share": 1 - overall[modal] / len(g),
                   "waves_with_other_modal": changed, "waves_with_two_models": minority}
        out.append("")
        if changed:
            out.append(f"- **model change mid-collection** (a finding; R2 keeps `{modal}` only): "
                       f"waves whose model differs from the mode: {', '.join(map(str, changed))}")
        if minority:
            out.append(f"- waves with more than one reported model: {', '.join(map(str, minority))}")
        if changed or minority:
            out.append("")
    hold = [r for r in rows if r["dataset"] not in NEW_DATASETS]
    if hold:
        out.append("Holdout datasets (unchanged from Stage 1):\n")
        res |= audit_f(hold, out, header=False)
    return res


def audit_f(rows: list[dict], out: list[str], header: bool = True) -> dict:
    if header:
        out.append("## Audit F: model drift\n")
        out.append("The model each answer reports (DataForSEO `model`; Anthropic model id; "
                   "claude.ai answers are recorded as `claude.ai`; holdout ChatGPT from the "
                   "source studies).\n")
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
    bf = load_stage_bestfor(mode)
    if bf is None:
        out.append(f"**Not available yet** (best-for files under `{mode.bestfor.name}/`).\n")
        return {"status": "missing", "passes": False}
    res: dict = {"groups": {}}
    out.append(f"Segment test-retest over every distinct phrase (two classifier passes). Pass: "
               f"at least {AUDIT_G_MIN:.0%}.\n")
    groups = [("all", lambda c, p: True),
              ("B2B", lambda c, p: c not in EXPLORE_TAXONOMY_CATEGORIES),
              ("headphones and agencies", lambda c, p: c in EXPLORE_TAXONOMY_CATEGORIES)]
    if mode.stage == 2:
        new = json.loads((mode.bestfor / "phrases.json").read_text())
        fresh = {(c, e["phrase"]) for c, lst in new.items() for e in lst}
        out.append("Stage 2: every distinct phrase the Stage 2 frame uses. Phrases Stage 1 had "
                   "classified keep their two Stage 1 passes (reused); the rest were classified "
                   "twice at Stage 2 with the same frozen taxonomies.\n")
        groups += [("classified at Stage 1 (reused)", lambda c, p: (c, p) not in fresh),
                   ("classified at Stage 2 (new phrases)", lambda c, p: (c, p) in fresh)]
    out.append("| Categories | Distinct phrases | Same segment both passes | Outside every "
               "segment (pass a) |\n|---|---|---|---|")
    for name, keep in groups:
        tot = agree = other = 0
        for c, lst in bf.phrases.items():
            for e in lst:
                p = e["phrase"]
                if not keep(c, p):
                    continue
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
    if mode.stage == 2:
        # The Stage 2 frame exists only once 20_answers.py --stage 2 has passed
        # its input gate (every wave 8 to 11 task and the Stage 2 sample judged).
        if not mode.meta_path.exists():
            refuse([f"no {mode.meta_path.name}; run 20_answers.py --stage 2 first"],
                   "21_audits.py")
        m2 = json.loads(mode.meta_path.read_text())
        if (m2.get("mode"), m2.get("stage"), m2.get("stage2_inputs_complete")) != (
                mode.kind, 2, True):
            refuse([f"{mode.answers_path.name} is not a complete Stage 2 frame for this mode"],
                   "21_audits.py")
    if not mode.answers_path.exists():
        raise SystemExit(f"no answer frame at {mode.answers_path}; run 20_answers.py first")
    rows = read_jsonl(mode.answers_path)
    second = read_jsonl(mode.rejudge_path) if mode.rejudge_path.exists() else []
    meta = json.loads(mode.meta_path.read_text())

    out = [f"# Experiment 010: Stage {mode.stage} data-quality audits{mode.tag}\n",
           "Generated by `pipeline/21_audits.py`. Aggregates only.\n"]
    if mode.stage == 2:
        out.append(f"Answers in the frame: {len(rows)} ({sum(usable(r) for r in rows)} usable). "
                   f"Stage 2 frame: new-collection waves 1 to {max(STAGE_WAVES[2])} "
                   f"({meta.get('filtered_waves', 0)} tasks dropped), built only after every "
                   "wave 8 to 11 task and the Stage 2 re-judge sample were judged OK.")
    else:
        out.append(f"Answers in the frame: {len(rows)} ({sum(usable(r) for r in rows)} usable). "
                   f"Firewall: {meta.get('filtered_waves', 0)} new-collection tasks from waves "
                   f"after {max(STAGE_WAVES[mode.stage])} dropped before any judge output was "
                   "read.")
    if meta.get("lexicon_v3_sha256"):
        out.append(f"Lexicon v3 sha256 `{meta['lexicon_v3_sha256'][:12]}...`; B2B taxonomy sha256 "
                   f"`{(meta.get('taxonomy_b2b_sha256') or '')[:12]}...`.")
    out.append("")
    res = {"A": audit_a(rows, mode.stage, out)}
    if mode.stage == 2:
        res["A"]["lag_bins"] = lag_bins(rows, out)
    res["B"] = audit_b(rows, meta, out)
    out.append("## Audit C: independence\n")
    out.append("Pairs share prompts, so every interval resamples prompts (the cluster), never "
               "pairs. The two prompts of a B2B category share a market; robustness R5 "
               "(23_robustness.py) resamples categories instead.\n")
    res["D"] = audit_d(mode, out)
    if mode.stage == 2:
        res["E"] = audit_e_stage2(rows, second, out)
        res["F"] = audit_f_stage2(rows, out)
    else:
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
    changed = any(v.get("runs_with_other_modal") or v.get("waves_with_other_modal")
                  for v in res["F"].values())
    out.append(f"| F model drift | {'change found' if changed else 'no change'} |")
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
