"""Stage 02: data-quality audits A to D (spec §2) -> results/audit_report.md.

A  degenerate responses, per arm x wave: failed runs and audit failures (ledgers), empty
   answers, zero searches, zero links, zero extracted brands, replies that only ask a question
   back, coding behavior. The no-search rule: more than 30% of an arm's answers with no search
   makes its domain claims INCONCLUSIVE. For ``sched_kit`` the no-search count uses the record's
   ``searched`` flag, since the transcript has no search count; search depth is its tool count.
   Audit A also compares every answer with its subagent's report (``report_match``), checks the
   instruction each subagent received (``instruction_exact``), and reports ``resolved_model``.
B  what the labels mean: the extraction code, quoted with its location.
C  independence: the prompt, category and wave structure and pair counts.
D  extraction validity. Writes a 30-answer spot-check sheet, stratified across the arms and
   arm-blind, to ``data/raw/audit_d_sheet.csv`` with its reading file and key (all gitignored:
   they hold answer text); ``--score-audit-d`` scores the filled sheet (precision at least 0.95,
   recall at least 0.90) and writes ``results/audit_d_score.json``.

Nothing here computes a hypothesis metric. Tracked outputs hold aggregates only: no brand names,
domains, prompt text, answer text or queries.

Usage (repo root):
  uv run python experiments/011-claude-code-fidelity/pipeline/02_audit.py
  uv run python .../02_audit.py --score-audit-d --signed-by "Jim Wrubel"
  uv run python .../02_audit.py --synthetic planted
"""

from __future__ import annotations

import argparse
import csv
import inspect
import json
import re
from datetime import date
from pathlib import Path

import brands
import common
import numpy as np
import pandas as pd
from common import (
    ALL_ARMS,
    AUDIT_D_N,
    AUDIT_D_PRECISION,
    AUDIT_D_RECALL,
    COMPARE_ARMS,
    EVALUATED_ARMS,
    EXP,
    H3_PAIR,
    NO_SEARCH_MAX,
    REFERENCE,
    SCHEDULED,
    SEED,
    SYNTHETIC_WORLDS,
    WAVES,
    Sources,
    arm_order,
    build_pairs,
    cross,
    ledger_records,
    load_features,
    md_table,
    results_dir,
    sha256_file,
    sources,
    within,
)

import aeo_research.claude_answers as claude_answers

REVIEWER_COLUMNS = ("missed_brands", "wrong_brands", "reviewer_notes")
AUDIT_D_INSTRUCTIONS = (
    "How to review: each answer below has an ID (A01 to A30) that matches a row in "
    "audit_d_sheet.csv.",
    "Read the answer text and compare it with the extracted brands listed above it.",
    "missed_brands: brands in this category that the answer presents as options but the "
    "list missed. Write the names as the answer writes them, separated by \"; \".",
    "wrong_brands: listed brands that are not real in-category mentions in this answer. "
    "Copy the names exactly as listed, separated by \"; \".",
    "Leave both cells empty when the list is right. Use reviewer_notes for anything else.",
)
SPLIT = re.compile(r"[;|\n]+")
#: Ledger problem codes that mean the run itself failed. Anything else is an instrument audit
#: failure (collect_cc.audit): wrong tools, an API key, MCP servers, the wrong model.
RUN_FAILURE = re.compile(r"^(exit_|no_answer|no_result_event|result_is_error|empty_answer)")


def h(out: list[str], title: str) -> None:
    out.append(f"\n## {title}\n")


# ------------------------------------------------------------------ A


def ledger_table(df: pd.DataFrame, records: list[dict]) -> pd.DataFrame:
    """Per arm x wave: attempts, failures by kind, and answers that ended up not counting."""
    rows: dict[tuple[str, int], dict] = {}
    for r in records:
        if r.get("status") == "submitted":
            continue
        row = rows.setdefault((r["arm"], int(r["wave"])), {"attempts": 0, "failed_runs": 0,
                                                           "audit_failures": 0})
        row["attempts"] += 1
        problems = r.get("problems") or []
        if r.get("status") not in ("ok", "collected"):
            if any(not RUN_FAILURE.match(str(p)) for p in problems):
                row["audit_failures"] += 1
            else:
                row["failed_runs"] += 1
    if not rows:
        return pd.DataFrame()
    not_counted = df[~df["run_ok"]].groupby(["arm", "wave"]).size().to_dict()
    table = pd.DataFrame([{"arm": a, "wave": w, **v, "not_counted": not_counted.get((a, w), 0)}
                          for (a, w), v in rows.items()])
    return arm_order(table)


def degenerate_table(df: pd.DataFrame) -> pd.DataFrame:
    g = df.assign(
        no_search=~df["searched"].astype(bool),
        zero_links=df["n_links"] == 0,
        zero_brands=df["n_brands"] == 0,
    ).groupby(["arm", "wave"])
    t = g.agg(
        answers=("item_id", "size"), empty=("empty_answer", "sum"),
        no_search=("no_search", "sum"), zero_links=("zero_links", "sum"),
        zero_brands=("zero_brands", "sum"), asks_back=("asks_back", "sum"),
        coding_flag=("coding_flag", "sum"), clarifying=("clarifying_questions", "sum"),
        notes=("collector_notes", "sum"), warned=("n_warnings", lambda s: int((s > 0).sum())),
    ).reset_index()
    for c in t.columns[2:]:
        t[c] = t[c].astype(int)
    return arm_order(t)


def no_search_rule(df: pd.DataFrame) -> pd.DataFrame:
    t = df.groupby("arm").agg(answers=("item_id", "size"),
                              no_search=("searched", lambda s: int((~s.astype(bool)).sum())))
    t["no_search_rate"] = t["no_search"] / t["answers"]
    t["domain_claims"] = np.where(t["no_search_rate"] > NO_SEARCH_MAX,
                                  "INCONCLUSIVE (rule)", "eligible")
    return arm_order(t.reset_index())


def empty_pair_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Share of pairs per condition where both sets are empty (Jaccard NaN)."""
    pairs = build_pairs(df)
    conditions = {within(REFERENCE): (REFERENCE,)}
    conditions |= {cross(a, REFERENCE): (a, REFERENCE) for a in COMPARE_ARMS}
    conditions |= {within(a): (a,) for a in H3_PAIR}
    conditions[cross(*H3_PAIR)] = H3_PAIR
    pairs = pairs[pairs["condition"].isin(conditions)]
    rows = []
    for cond, g in pairs.groupby("condition"):
        row = {"condition": cond, "pairs": len(g)}
        i, j = g["i"].to_numpy(), g["j"].to_numpy()
        for col, label in (("brands", "brands"), ("cited_domains", "cited"),
                           ("evaluated_domains", "evaluated")):
            if label == "evaluated" and not all(a in EVALUATED_ARMS for a in conditions[cond]):
                row[label] = float("nan")
                continue
            empty = df[col].map(lambda v: not v).to_numpy()
            row[label] = float((empty[i] & empty[j]).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def scheduled_checks(df: pd.DataFrame) -> pd.DataFrame:
    """``sched_kit`` per wave: what the transcript records about each subagent (spec §6)."""
    sub = df[df["arm"] == SCHEDULED]
    rows = []
    for wave, g in sub.groupby("wave"):
        checked = g["report_match"].dropna().astype(bool)
        rows.append({
            "wave": int(wave), "answers": len(g), "searched": int(g["searched"].astype(bool).sum()),
            "no_join": int(g["search_unknown"].astype(bool).sum()),
            "fetched": int(g["fetched"].eq(True).sum()),
            "exact_instruction": int(g["instruction_exact"].eq(True).sum()),
            "copies_checked": len(checked), "exact_copies": int(checked.sum()),
            "report_match_rate": float(checked.mean()) if len(checked) else float("nan"),
            "resolved_model": ", ".join(sorted(set(g["resolved_model"].dropna().astype(str)))) or "none",
            "tool_uses_per_answer": float(pd.to_numeric(g["subagent_tool_uses"]).mean()),
        })
    return pd.DataFrame(rows)


def audit_a(df: pd.DataFrame, src: Sources, out: list[str]) -> None:
    h(out, "Audit A: degenerate responses")
    table = ledger_table(df, ledger_records(src))
    if not table.empty:
        out.append("Ledgers, local and API arms (`attempts` = finished attempts including reruns; "
                   "`failed_runs` = the run itself failed; `audit_failures` = the instrument check "
                   "in `collect_cc.audit` failed; `not_counted` = answers whose last ledger record "
                   "is not a success, dropped before the model):\n")
        out.append(md_table(table))
    expected = df["item_id"].nunique()
    missing = []
    for arm in ALL_ARMS:
        for wave in WAVES:
            n = int(((df["arm"] == arm) & (df["wave"] == wave) & df["run_ok"]).sum())
            if n != expected:
                missing.append(f"{arm} w{wave}: {n}/{expected}")
    out.append("\nCounted answers per arm x wave: "
               + ("all complete." if not missing else "; ".join(missing)))

    out.append("\nPer arm x wave counts (`no_search` for `sched_kit` is the record's `searched` "
               "flag; `asks_back` = no brands and the reply ends on a question; `coding_flag` = "
               "offers or claims file or code work, to be read by a person; `clarifying` = claude.ai "
               "asked clarifying questions, first reply scored; `notes` = collector note, excluded "
               "in R6; `warned` = the parser or ingest recorded a warning):\n")
    out.append(md_table(degenerate_table(df)))

    out.append(f"\nNo-search rule, pooled over waves (more than {NO_SEARCH_MAX:.0%} makes the "
               "arm's domain claims INCONCLUSIVE):\n")
    out.append(md_table(no_search_rule(df)))

    out.append("\nEmpty-vs-empty pairs (Jaccard NaN, pair excluded), share of the condition's "
               "pairs. Evaluated URLs are not observed on `sched_kit`:\n")
    out.append(md_table(empty_pair_rates(df)))

    sched = scheduled_checks(df)
    if not sched.empty:
        out.append(f"\n`{SCHEDULED}` per wave, from each transcript. `no_join` = a printed answer "
                   "with no subagent result to join to, counted as not searched; `exact_instruction` "
                   "= the subagent received the frozen instruction; `exact_copies` = the printed "
                   "answer equals the subagent's report. The transcript records whether a subagent "
                   "searched and its total tool count, not the number of searches, so search depth "
                   "is reported as a tool count. The cloud's Claude Code version cannot be read:\n")
        out.append(md_table(sched))
        out.append(f"\nInstruction mismatches or missing joins: "
                   f"{int((sched['answers'] - sched['exact_instruction']).sum())}. Copies that differ "
                   f"from the report: {int((sched['copies_checked'] - sched['exact_copies']).sum())}.")

    models = df.groupby("arm")["model"].agg(lambda s: sorted(set(map(str, s)))).to_dict()
    out.append(f"\nModel strings per arm: {models}")
    versions = (df.dropna(subset=["claude_code_version"]).groupby(["arm", "wave"])["claude_code_version"]
                .agg(lambda s: sorted(set(s))).to_dict())
    out.append(f"Claude Code version per arm x wave: { {f'{a} w{w}': v for (a, w), v in versions.items()} }")
    dates = df.groupby(["wave", "surface"])["run_date"].agg(lambda s: sorted(set(s) - {""})).to_dict()
    out.append(f"Run dates per wave x surface: { {f'w{w} {s}': v for (w, s), v in dates.items()} }")


# ------------------------------------------------------------------ B


def location(fn) -> str:
    path = Path(inspect.getsourcefile(fn)).resolve()
    try:
        rel = path.relative_to(EXP.parents[1])
    except ValueError:
        rel = path
    lines, start = inspect.getsourcelines(fn)
    return f"`{rel}::{fn.__qualname__}` (lines {start}-{start + len(lines) - 1})"


def quote(fn, out: list[str], *, only: tuple[str, ...] = ()) -> None:
    out.append(f"\n{location(fn)}\n")
    src = inspect.getsource(fn).rstrip().split("\n")
    if only:
        src = [ln for ln in src if any(k in ln for k in only)]
    out.append("```python\n" + "\n".join(src) + "\n```")


def audit_b(out: list[str]) -> None:
    h(out, "Audit B: what the labels mean (quoted from code)")
    out.append(
        f"- **brand named** = a keep-row alias of the frozen lexicon (sha256 "
        f"`{brands.LEXICON_SHA256}`) matched in the answer text for the prompt's category, after "
        "labelled sources blocks, link targets, bare URLs and markup are stripped; longest alias "
        "first, word boundaries, matched spans consumed, first-mention order.")
    for fn in (brands.strip_sources, brands.lexicon_extract, brands.load_lexicon):
        quote(fn, out)
    out.append(
        "\n- **link in answer** (Claude Code) = a URL in the answer text. Claude Code has no "
        "citation objects, so this differs from `citations[]` on claude.ai and the API, and domain "
        "results are descriptive. **evaluated** = a link in a `WebSearch` result, local arms; a "
        "subagent's searches are not in the pulled transcript, so `sched_kit` has none.")
    quote(claude_answers._links_in_text, out)
    quote(claude_answers.from_claude_code_stream, out,
          only=("_links_in_text", "WebSearch", "evaluated.append", "queries.append",
                '"n_searches"', '"n_backend_searches"'))
    out.append("\n- **cited** (claude.ai, API) = citation objects in the answer's text blocks.")
    quote(claude_answers._export_citation_url, out)
    quote(claude_answers.from_api_message, out,
          only=("citations", "citation[", "cited.append"))
    for fn in (common.normalize_url, common.registered_domain, common.ordered_domains):
        quote(fn, out)
    out.append("\n- Pair metrics (stage 03): Jaccard with empty-vs-empty = NaN "
               "(`aeo_research.overlap.jaccard`), truncated normalized RBO at p = 0.9 "
               "(`aeo_research.overlap.rbo`).")


# ------------------------------------------------------------------ C


def audit_c(df: pd.DataFrame, out: list[str]) -> None:
    h(out, "Audit C: independence")
    per_cat = df.groupby("category")["item_id"].nunique()
    out.append(
        f"{df['item_id'].nunique()} prompts in {df['category'].nunique()} categories "
        f"(prompts per category: {sorted(per_cat.value_counts().to_dict().items())}); "
        f"intents {sorted(df['intent'].unique())}; waves {sorted(int(w) for w in df['wave'].unique())}; "
        f"{df['arm'].nunique()} arms; {len(df)} answers.")
    pairs = build_pairs(df)
    counts = pairs.groupby("condition").agg(pairs=("i", "size"),
                                            prompts=("cluster_i", "nunique")).reset_index()
    show = counts[counts["condition"].isin(
        [within(a) for a in ALL_ARMS] + [cross(a, REFERENCE) for a in COMPARE_ARMS]
        + [cross(*H3_PAIR)])]
    out.append("\nSame-prompt pair counts per condition (within = different waves, cross = same "
               "wave):\n")
    out.append(md_table(show))
    out.append(
        "\nEvery answer joins several pairs, so pairs are not independent. All inference is a "
        "prompt-level cluster bootstrap (`aeo_research.overlap.cluster_boot` weights), with no "
        "pair-level standard errors. The two prompts of a category share vendors, so category is "
        "a coarser cluster: R5 resamples categories instead.")


# ------------------------------------------------------------------ D


def sheet_has_input(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(newline="") as f:
        return any(any((r.get(c) or "").strip() for c in REVIEWER_COLUMNS) for r in csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def audit_d_picks(df: pd.DataFrame) -> list[pd.Series]:
    """30 counted answers stratified across the arms, in the seeded shuffled order that becomes
    A01 to A30."""
    rng = np.random.default_rng(SEED)
    counted = df[df["run_ok"]]
    arms = [a for a in ALL_ARMS if a in set(counted["arm"])]
    base, extra = divmod(AUDIT_D_N, len(arms))
    bonus = set(rng.choice(arms, size=extra, replace=False)) if extra else set()
    picks = []
    for arm in arms:
        sub = counted[counted["arm"] == arm].sort_values(["wave", "item_id"]).reset_index(drop=True)
        k = base + (arm in bonus)
        picks += [sub.iloc[i] for i in sorted(rng.choice(len(sub), size=k, replace=False))]
    return [picks[i] for i in rng.permutation(len(picks))]


def make_audit_d_sheet(df: pd.DataFrame, src: Sources, *, force: bool = False) -> str:
    """Write the arm-blind review sheet, the reading file and the key.

    Sheet (edited by the reviewer): audit_id, category, extracted_brands and the blank reviewer
    columns. Reading file: per audit_id, the category, the extracted brands and the answer text
    as extraction reads it (sources block stripped). Key: audit_id -> arm, item_id, wave. Neither
    reviewer file names the arm, prompt or wave.
    """
    if sheet_has_input(src.audit_d_sheet) and not force:
        return f"{src.audit_d_sheet.name} already has reviewer input; left unchanged (--force-new-sheet)"
    sheet, key, md = [], [], [*(f"- {line}" for line in AUDIT_D_INSTRUCTIONS), ""]
    for n, r in enumerate(audit_d_picks(df), start=1):
        audit_id = f"A{n:02d}"
        path = src.responses / f"w{int(r['wave'])}" / r["arm"] / f"{r['item_id']}.json"
        text = brands.strip_sources(json.loads(path.read_text())["normalized"].get("answer_text") or "")
        listed = "; ".join(r["brands"])
        sheet.append({"audit_id": audit_id, "category": r["category"], "extracted_brands": listed,
                      "missed_brands": "", "wrong_brands": "", "reviewer_notes": ""})
        key.append({"audit_id": audit_id, "arm": r["arm"], "item_id": r["item_id"],
                    "wave": int(r["wave"])})
        md += [f"## {audit_id}: {r['category']}", "",
               f"**Extracted brands ({len(r['brands'])}):** {listed or '(none)'}", "",
               "**Answer text:**", "", text.strip(), "", "---", ""]
    _write_csv(src.audit_d_sheet, sheet)
    _write_csv(src.audit_d_key, key)
    src.audit_d_answers.write_text("\n".join(md))
    by_arm = pd.Series([k["arm"] for k in key]).value_counts().to_dict()
    return (f"wrote {src.audit_d_sheet.name}, {src.audit_d_answers.name} and {src.audit_d_key.name} "
            f"({len(sheet)} answers; per arm {by_arm})")


def _names(cell: str | None) -> list[str]:
    return [x.strip() for x in SPLIT.split(cell or "") if x.strip()]


def _precision_recall(tp: int, fp: int, fn: int) -> tuple[float, float]:
    return (tp / (tp + fp) if tp + fp else float("nan"),
            tp / (tp + fn) if tp + fn else float("nan"))


def score_audit_d(sheet_path: Path, key_path: Path, lexicon_sha256: str | None) -> dict:
    """Brand precision and recall of the extraction against the reviewer's read.

    Every sheet row counts as reviewed (an empty row means the extracted list was right), so
    score only a finished sheet. Per row: E = extracted brands; W = the reviewer's
    ``wrong_brands`` that match an extracted name (case-insensitive); M = ``missed_brands``.
    TP = |E| - |W|, FP = |W|, FN = |M|, pooled over rows, overall and per arm via the key.
    """
    with sheet_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    with key_path.open(newline="") as f:
        arm_of = {r["audit_id"]: r["arm"] for r in csv.DictReader(f)}
    totals: dict[str, list[int]] = {}
    unmatched = 0
    for r in rows:
        extracted = {x.lower() for x in _names(r["extracted_brands"])}
        wrong = {x.lower() for x in _names(r.get("wrong_brands"))}
        hit = wrong & extracted
        unmatched += len(wrong - extracted)
        counts = (len(extracted) - len(hit), len(hit), len(_names(r.get("missed_brands"))))
        for k in ("all", arm_of.get(r["audit_id"], "unknown")):
            t = totals.setdefault(k, [0, 0, 0, 0])
            for i, v in enumerate(counts):
                t[i] += v
            t[3] += 1
    tp, fp, fn, _ = totals.get("all", [0, 0, 0, 0])
    precision, recall = _precision_recall(tp, fp, fn)
    per_arm = {}
    for arm in [a for a in ALL_ARMS if a in totals] + (["unknown"] if "unknown" in totals else []):
        a_tp, a_fp, a_fn, n = totals[arm]
        a_p, a_r = _precision_recall(a_tp, a_fp, a_fn)
        per_arm[arm] = {"answers": n, "true_positive": a_tp, "false_positive": a_fp,
                        "false_negative": a_fn, "precision": a_p, "recall": a_r}
    complete = len(rows) == AUDIT_D_N and all(r["audit_id"] in arm_of for r in rows)
    passes = bool(complete and precision >= AUDIT_D_PRECISION and recall >= AUDIT_D_RECALL)
    return {
        "rows": len(rows), "complete": complete,
        "true_positive": tp, "false_positive": fp, "false_negative": fn,
        "wrong_names_not_extracted": unmatched,
        "precision": precision, "recall": recall, "per_arm": per_arm,
        "gate_precision": AUDIT_D_PRECISION, "gate_recall": AUDIT_D_RECALL,
        "passes": passes, "sheet_sha256": sha256_file(sheet_path),
        "key_sha256": sha256_file(key_path),
        "lexicon_sha256": lexicon_sha256,
        "scored_on": date.today().isoformat(),
    }


def candidate_coverage(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """R4's inputs: cache coverage by wave and unplaced names per answer by arm."""
    has = df["brands_all"].map(lambda v: v is not None)
    cov = df.assign(has=has).groupby("wave").agg(answers=("item_id", "size"),
                                                 with_candidates=("has", "sum")).reset_index()
    cov["coverage"] = cov["with_candidates"] / cov["answers"]
    unplaced = (df[has].groupby("arm").agg(answers=("item_id", "size"),
                                           unplaced_per_answer=("n_unplaced", "mean")).reset_index()
                if has.any() else pd.DataFrame())
    return cov, arm_order(unplaced) if not unplaced.empty else unplaced


def audit_d(df: pd.DataFrame, src: Sources, score_path: Path, out: list[str], *, score: bool,
            signed_by: str | None, force_sheet: bool, lexicon_sha256: str | None) -> dict | None:
    h(out, "Audit D: extraction validity")
    note = make_audit_d_sheet(df, src, force=force_sheet)
    print(f"  audit D sheet: {note}")
    out.append(
        f"Arm-blind spot check, {AUDIT_D_N} answers stratified across the {df['arm'].nunique()} arms, "
        f"drawn with seed {SEED}, shuffled into A01-A{AUDIT_D_N}. The reviewer edits "
        f"`{src.audit_d_sheet.name}` and reads `{src.audit_d_answers.name}`; neither names the arm, "
        f"prompt or wave. `{src.audit_d_key.name}` maps audit_id to arm, item and wave for the "
        "scorer. All three are gitignored. `missed_brands` = in-category brands the answer presents "
        "that extraction missed; `wrong_brands` = extracted brands that are not real in-category "
        "mentions in that answer (names separated by `; `).")
    result = None
    if score:
        if not sheet_has_input(src.audit_d_sheet):
            raise SystemExit("the Audit D sheet has no reviewer input yet")
        result = score_audit_d(src.audit_d_sheet, src.audit_d_key, lexicon_sha256)
        if signed_by:
            result["signed_by"] = signed_by
        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps(result, indent=1) + "\n")
        print(f"  wrote {score_path}")
    elif score_path.exists():
        result = json.loads(score_path.read_text())
    if result:
        out.append(
            f"\nScore ({result['scored_on']}, {result['rows']} rows): precision "
            f"{result['precision']:.3f} (gate >= {AUDIT_D_PRECISION}), recall {result['recall']:.3f} "
            f"(gate >= {AUDIT_D_RECALL}); TP {result['true_positive']}, FP {result['false_positive']}, "
            f"FN {result['false_negative']}; wrong names that match no extracted brand: "
            f"{result['wrong_names_not_extracted']}. "
            f"**{'PASS' if result['passes'] else 'FAIL: refine the lexicon, log it, re-check'}**"
            + (f", signed by {result['signed_by']}." if result.get("signed_by") else ", not yet signed."))
        if result.get("per_arm"):
            out.append("\nPer arm:\n")
            out.append(md_table(pd.DataFrame([{"arm": a, **v} for a, v in result["per_arm"].items()])))
    else:
        out.append("\nNot scored yet. After review: `02_audit.py --score-audit-d --signed-by "
                   "\"<name>\"`. 03_model refuses to run on real data until the score passes and is "
                   "signed.")

    cov, unplaced = candidate_coverage(df)
    out.append("\nHaiku candidate cache coverage (R4 needs every answer; "
               "`harness/lexicon_candidates.py --wave N`):\n")
    out.append(md_table(cov))
    if not unplaced.empty:
        out.append("\nNames the lexicon cannot place, per answer (R4 adds these to both sides):\n")
        out.append(md_table(unplaced))
    return result


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    ap.add_argument("--score-audit-d", action="store_true",
                    help="score the filled Audit D sheet and write results/audit_d_score.json")
    ap.add_argument("--signed-by", default=None, help="Audit D sign-off name (with --score-audit-d)")
    ap.add_argument("--force-new-sheet", action="store_true",
                    help="regenerate the Audit D sheet even if it has reviewer input")
    a = ap.parse_args()

    lexicon_sha = None if a.synthetic else brands.verify_lexicon()
    df = load_features(synthetic=a.synthetic)
    src = sources(a.synthetic)
    results = results_dir(a.synthetic)
    tag = f" (SYNTHETIC/{a.synthetic})" if a.synthetic else ""
    out = [
        f"# Experiment 011: data-quality audits{tag}",
        "",
        f"Generated {date.today().isoformat()} by `pipeline/02_audit.py` ({len(df)} answers). "
        "Aggregates only: no brand, domain, prompt, answer or query text.",
    ]
    audit_a(df, src, out)
    audit_b(out)
    audit_c(df, out)
    audit_d(df, src, results / "audit_d_score.json", out, score=a.score_audit_d,
            signed_by=a.signed_by, force_sheet=a.force_new_sheet, lexicon_sha256=lexicon_sha)

    results.mkdir(parents=True, exist_ok=True)
    path = results / "audit_report.md"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
