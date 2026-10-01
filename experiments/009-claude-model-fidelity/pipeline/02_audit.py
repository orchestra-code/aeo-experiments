"""Stage 02 — data-quality audits A-D (spec §2) -> results/audit_report.md.

A  degenerate responses, per arm x wave: failed or errored batch requests,
   ``pause_turn`` continuations, empty answers, zero searches, zero cited
   URLs, zero extracted brands, refusals (heuristic), plus the claude.ai
   ingest check (matched / duplicate / ambiguous / ignored chats, re-derived
   read-only from the exports), clarifying-question chats, collector notes,
   and wrong-setting exclusions. The no-search rule: an arm with more than
   30% no-search answers has its domain claims reported INCONCLUSIVE. The
   empty-vs-empty rate (pairs where both sets are empty, so Jaccard is NaN
   and the pair is excluded) per condition.
B  what the labels mean: the extraction code, quoted with its location.
C  independence: the prompt / category / wave structure and pair counts.
D  extraction validity. Writes a 30-answer spot-check sheet stratified across
   the 9 arms (seeded) to ``data/raw/audit_d_sheet.csv`` (gitignored: it holds
   answer text) for a person to fill; ``--score-audit-d`` scores the filled
   sheet (brand precision >= 0.95 and recall >= 0.90 against the manual
   read) and writes ``results/audit_d_score.json``. Plus the R4-style
   agreement between lexicon extraction and the Haiku candidates mapped
   through the lexicon, for the waves the candidate cache covers.

Nothing here computes a hypothesis metric (no Jaccard between answers of
different arms or waves). Tracked outputs hold aggregates only: no brand
names, domains, prompt text, answer text or queries.

Usage:
  uv run python experiments/009-claude-model-fidelity/pipeline/02_audit.py
  uv run python .../02_audit.py --score-audit-d --signed-by "Jim Wrubel"
  uv run python .../02_audit.py --synthetic planted
"""

from __future__ import annotations

import argparse
import csv
import inspect
import json
import re
import sys
from datetime import date
from pathlib import Path

import brands
import common
import numpy as np
import pandas as pd
from common import (
    ALL_ARMS,
    API_ARMS,
    AUDIT_D_N,
    AUDIT_D_PRECISION,
    AUDIT_D_RECALL,
    AUDIT_D_SCORE,
    AUDIT_D_SHEET,
    EXP,
    LEDGER,
    NO_SEARCH_MAX,
    PROMPTS_CSV,
    RAW,
    REFERENCE,
    SEED,
    SYNTHETIC_WORLDS,
    UI_ARMS,
    UI_WRONG_SETTING,
    WAVES,
    build_pairs,
    load_features,
    results_dir,
    sha256_file,
)

import aeo_research.claude_answers as claude_answers
from aeo_research.overlap import jaccard, token_set

HARNESS = EXP / "harness"
REVIEWER_COLUMNS = ("missed_brands", "wrong_brands", "reviewer_notes")
#: Audit D files (all gitignored under data/raw). The reviewer edits the sheet
#: and reads the answers file; neither names the arm, prompt or wave. The key
#: maps audit_id back to (arm, item_id, wave) for the scorer.
AUDIT_D_ANSWERS = RAW / "audit_d_answers.md"
AUDIT_D_KEY = RAW / "audit_d_key.csv"
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


def h(out: list[str], title: str) -> None:
    out.append(f"\n## {title}\n")


def md_table(df: pd.DataFrame, digits: int = 3) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        cells = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else f"{v:.{digits}f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def arm_order(df: pd.DataFrame, col: str = "arm") -> pd.DataFrame:
    """Rows in the spec's arm order, then by wave when there is one."""
    order = {a: i for i, a in enumerate(ALL_ARMS)}
    by = [col] + (["wave"] if "wave" in df.columns else [])
    return df.sort_values(by=by, key=lambda s: s.map(order) if s.name == col else s,
                          kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------ A


def ledger_status(synthetic: bool) -> pd.DataFrame | None:
    """Last status per batch task, counted per arm x wave."""
    if synthetic or not LEDGER.exists():
        return None
    last: dict[str, dict] = {}
    for line in LEDGER.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            last[r["task_id"]] = r
    recs = pd.DataFrame(last.values())
    recs = recs[recs["wave"].isin(WAVES)]
    table = recs.groupby(["arm", "wave", "status"]).size().unstack(fill_value=0).reset_index()
    return table


def ui_ingest_check(synthetic: bool) -> pd.DataFrame | None:
    """Re-run the ingest's matching on each wave's export, read-only."""
    if synthetic:
        return None
    sys.path.insert(0, str(HARNESS))
    try:
        import ingest_claude_export as ingest
    except ImportError as e:  # pragma: no cover - harness missing
        print(f"  ingest check skipped: {e}")
        return None
    with PROMPTS_CSV.open(newline="") as f:
        prompts = {r["item_id"]: r for r in csv.DictReader(f)}
    rows = []
    for wave in WAVES:
        export_dir = RAW / "ui_exports" / f"w{wave}"
        if not export_dir.exists():
            continue
        convs = ingest.load_conversations(export_dir)
        matched, duplicates, ambiguous, ignored = ingest.match(convs, prompts, wave, list(UI_ARMS))
        rows.append({
            "wave": wave, "conversations_in_export": len(convs),
            "expected": len(prompts) * len(UI_ARMS), "matched": len(matched),
            "matched_by_prompt_text": sum(1 for c in matched.values() if c.get("_matched_by")),
            "duplicated": len(duplicates), "ambiguous": len(ambiguous),
            "other_ignored": ignored,
        })
    return pd.DataFrame(rows)


def degenerate_table(df: pd.DataFrame) -> pd.DataFrame:
    g = df.assign(
        zero_search=df["n_searches"] == 0,
        zero_cited=df["n_cited"] == 0,
        zero_brands=df["n_brands"] == 0,
    ).groupby(["arm", "wave"])
    t = g.agg(
        answers=("item_id", "size"), empty=("empty_answer", "sum"), paused=("paused", "sum"),
        zero_search=("zero_search", "sum"), zero_cited=("zero_cited", "sum"),
        zero_brands=("zero_brands", "sum"), refusal=("refusal", "sum"),
        clarifying=("clarifying_questions", "sum"), notes=("collector_notes", "sum"),
        other_tools=("other_tools", "sum"),
    ).reset_index()
    for c in t.columns[2:]:
        t[c] = t[c].astype(int)
    return arm_order(t)


def no_search_rule(df: pd.DataFrame) -> pd.DataFrame:
    t = df.groupby("arm").agg(answers=("item_id", "size"),
                              no_search=("n_searches", lambda s: int((s == 0).sum())))
    t["no_search_rate"] = t["no_search"] / t["answers"]
    t["domain_claims"] = np.where(t["no_search_rate"] > NO_SEARCH_MAX,
                                  "INCONCLUSIVE (rule)", "eligible")
    return arm_order(t.reset_index())


def empty_pair_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Share of pairs per condition where both sets are empty (Jaccard NaN)."""
    pairs = build_pairs(df)
    keep = [c for c in pairs["condition"].unique()
            if c == f"within:{REFERENCE}" or (c.startswith("cross:") and REFERENCE in c)
            or c in ("within:ui_think", "within:sonnet5_leak_think", "within:sonnet5_leak_low",
                     "cross:sonnet5_leak_low|sonnet5_leak_think")]
    pairs = pairs[pairs["condition"].isin(keep)]
    rows = []
    for col, label in (("brands", "brands"), ("cited_domains", "cited"),
                       ("evaluated_domains", "evaluated")):
        empty = df[col].map(lambda v: not v).to_numpy()
        both = empty[pairs["i"].to_numpy()] & empty[pairs["j"].to_numpy()]
        rates = pd.Series(both).groupby(pairs["condition"].to_numpy()).agg(["size", "sum"])
        for cond, r in rates.iterrows():
            rows.append({"condition": cond, "metric": label, "pairs": int(r["size"]),
                         "both_empty": int(r["sum"]), "nan_rate": r["sum"] / r["size"]})
    t = pd.DataFrame(rows).pivot_table(index=["condition", "pairs"], columns="metric",
                                       values="nan_rate").reset_index()
    return t[["condition", "pairs", "brands", "cited", "evaluated"]]


def audit_a(df: pd.DataFrame, out: list[str], synthetic: bool) -> None:
    h(out, "Audit A: degenerate responses")
    status = ledger_status(synthetic)
    if status is not None:
        out.append("Batch ledger, last status per task (API arms):\n")
        out.append(md_table(arm_order(status)))
        failed = status.drop(columns=["arm", "wave", "collected", "submitted"],
                             errors="ignore").to_numpy().sum()
        out.append(f"\nFailed, errored or expired batch requests: {int(failed)}.")
    expected = df["item_id"].nunique()
    missing = []
    for arm in ALL_ARMS:
        for wave in WAVES:
            n = int(((df["arm"] == arm) & (df["wave"] == wave)).sum())
            if n != expected:
                missing.append(f"{arm} w{wave}: {n}/{expected}")
    out.append("Answers present per arm x wave: "
               + ("all complete." if not missing else "; ".join(missing)))

    out.append("\nPer arm x wave counts (answers; `paused` = a `pause_turn` "
               "continuation in the ledger; `refusal` = heuristic pattern near the start of "
               "the answer or a `refusal` stop reason; `clarifying` = claude.ai asked "
               "clarifying questions, first reply scored (deviation 1); `notes` = collector "
               "note on the sheet row (R7); `other_tools` = the chat used a claude.ai tool "
               "other than search):\n")
    out.append(md_table(degenerate_table(df)))

    out.append("\nNo-search rule (pooled over waves; more than "
               f"{NO_SEARCH_MAX:.0%} no-search answers makes the arm's domain claims "
               "INCONCLUSIVE whatever the CI):\n")
    out.append(md_table(no_search_rule(df)))

    out.append("\nEmpty-vs-empty pairs (both sets empty, so Jaccard is NaN and the pair is "
               "excluded), as a share of the condition's pairs:\n")
    out.append(md_table(empty_pair_rates(df)))

    ingest = ui_ingest_check(synthetic)
    if ingest is not None and not ingest.empty:
        out.append("\nclaude.ai ingest, re-derived read-only from each wave's export "
                   "(`other_ignored` = chats outside the protocol names, including voided "
                   "chats):\n")
        out.append(md_table(ingest))
    excluded = [f"{a}/{i}/w{w}" for a, i, w in UI_WRONG_SETTING]
    out.append(
        "\nUI chats run with the wrong model or reasoning setting (collector notes): "
        + (", ".join(excluded) if excluded else
           "none. Every wave's notes record Opus 5.5 with Medium reasoning (default) and no "
           "wrong-setting chat (common.UI_WRONG_SETTING).")
    )
    flagged = df[df["collector_notes"]]
    out.append(f"UI chats with a collector note (excluded in R7): {len(flagged)} "
               f"({flagged.groupby('arm').size().to_dict()}). Chats where claude.ai asked "
               f"clarifying questions: {int(df['clarifying_questions'].sum())}.")
    models = df.groupby("arm")["model"].agg(lambda s: sorted(set(map(str, s)))).to_dict()
    out.append(f"\nModel strings per arm: {models}")
    dates = df.groupby(["wave", "surface"])["run_date"].agg(lambda s: sorted(set(s))).to_dict()
    out.append(f"Run dates per wave x surface: {dates}")


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
        "- **brand named** = a keep-row alias of the frozen lexicon v2 (sha256 "
        f"`{brands.LEXICON_SHA256}`) matched in the answer text for the prompt's "
        "category, after the sources block, link targets, bare URLs and markup are "
        "stripped; longest alias first, word boundaries, matched spans consumed, "
        "first-mention order. For a claude.ai chat that asked clarifying questions the "
        "answer text is the first reply only (deviation 1).")
    for fn in (brands.strip_sources, brands.lexicon_extract, brands.load_lexicon):
        quote(fn, out)
    out.append(
        "\n- **domain cited** = registered domain of a normalized URL in a text block's "
        "`citations[]` (API) or `citations[].details.url` (claude.ai export); "
        "**domain evaluated** = registered domain of a `web_search_tool_result` item (API) "
        "or a search `tool_result` item (export).")
    quote(claude_answers.from_api_message, out,
          only=("citations", "citation[", "web_search_tool_result", "web_search_result",
                "evaluated.", "cited.append", "queries.append"))
    quote(claude_answers._export_citation_url, out)
    quote(claude_answers._export_result_urls, out)
    quote(claude_answers.from_claude_export, out,
          only=("citations", "_export_citation_url", "EXPORT_SEARCH_TOOLS", "evaluated.extend",
                "queries.append", "md_links", "cited_source"))
    for fn in (common.normalize_url, common.registered_domain, common.ordered_domains):
        quote(fn, out)
    out.append("\n- **grounding tokens** = stopword-filtered tokens of the search queries.")
    quote(token_set, out)
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
        [f"within:{a}" for a in ALL_ARMS] + [common.cross(a, REFERENCE) for a in API_ARMS]
        + [common.cross("ui_default", "ui_think"),
           common.cross("sonnet5_leak_think", "sonnet5_leak_low")])]
    out.append("\nSame-prompt pair counts per condition (within = different waves, cross = "
               "same wave):\n")
    out.append(md_table(show))
    out.append(
        "\nEvery answer joins several pairs, so pairs are not independent. All inference is "
        "a prompt-level cluster bootstrap (`aeo_research.overlap.cluster_boot` weights, "
        "resampling the 40 prompts); no pair-level standard errors. The two prompts of a "
        "category share vendors, so category is a coarser cluster: R6 resamples the 20 "
        "categories instead. Panel shares (`pipeline/shares.py`) resample categories, then "
        "prompts within each drawn category.")


# ------------------------------------------------------------------ D


def answer_ref(arm: str, item: str, wave: int) -> str:
    return f"responses/w{wave}/{arm}/{item}.json"


def sheet_has_input(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(newline="") as f:
        return any(any((r.get(c) or "").strip() for c in REVIEWER_COLUMNS + ("reviewed",))
                   for r in csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def audit_d_picks(df: pd.DataFrame) -> list[pd.Series]:
    """30 answers stratified across the 9 arms (3 each, 3 arms drawn for a 4th),
    in the seeded shuffled order that becomes A01..A30."""
    rng = np.random.default_rng(SEED)
    arms = [a for a in ALL_ARMS if a in set(df["arm"])]
    base, extra = divmod(AUDIT_D_N, len(arms))
    bonus = set(rng.choice(arms, size=extra, replace=False)) if extra else set()
    picks = []
    for arm in arms:
        sub = df[df["arm"] == arm].sort_values(["wave", "item_id"]).reset_index(drop=True)
        k = base + (arm in bonus)
        picks += [sub.iloc[i] for i in sorted(rng.choice(len(sub), size=k, replace=False))]
    return [picks[i] for i in rng.permutation(len(picks))]


def make_audit_d_sheet(df: pd.DataFrame, path: Path = AUDIT_D_SHEET, *,
                       answers_path: Path = AUDIT_D_ANSWERS, key_path: Path = AUDIT_D_KEY,
                       force: bool = False) -> str:
    """Write the arm-blind review sheet, the reading file and the key.

    Sheet (edited by the reviewer, one line per row): audit_id, category,
    extracted_brands and the blank reviewer columns. Reading file: per
    audit_id, the category, the extracted brands and the answer text as
    extraction reads it (sources block stripped). Key: audit_id -> arm,
    item_id, wave. Neither reviewer file names the arm, prompt or wave.
    """
    if sheet_has_input(path) and not force:
        return f"{path.name} already has reviewer input; left unchanged (--force-new-sheet)"
    sheet, key, md = [], [], [*(f"- {line}" for line in AUDIT_D_INSTRUCTIONS), ""]
    for n, r in enumerate(audit_d_picks(df), start=1):
        audit_id = f"A{n:02d}"
        ref = answer_ref(r["arm"], r["item_id"], int(r["wave"]))
        resp = json.loads((RAW / ref).read_text())
        text = brands.strip_sources(resp["normalized"].get("answer_text") or "")
        listed = "; ".join(r["brands"])
        sheet.append({"audit_id": audit_id, "category": r["category"],
                      "extracted_brands": listed, "missed_brands": "", "wrong_brands": "",
                      "reviewer_notes": ""})
        key.append({"audit_id": audit_id, "arm": r["arm"], "item_id": r["item_id"],
                    "wave": int(r["wave"])})
        md += [f"## {audit_id} — {r['category']}", "",
               f"**Extracted brands ({len(r['brands'])}):** {listed or '(none)'}", "",
               "**Answer text:**", "", text.strip(), "", "---", ""]
    _write_csv(path, sheet)
    _write_csv(key_path, key)
    answers_path.write_text("\n".join(md))
    by_arm = pd.Series([k["arm"] for k in key]).value_counts().to_dict()
    return (f"wrote {path.name}, {answers_path.name} and {key_path.name} "
            f"({len(sheet)} answers; per arm {by_arm})")


def _names(cell: str | None) -> list[str]:
    return [x.strip() for x in SPLIT.split(cell or "") if x.strip()]


def _precision_recall(tp: int, fp: int, fn: int) -> tuple[float, float]:
    return (tp / (tp + fp) if tp + fp else float("nan"),
            tp / (tp + fn) if tp + fn else float("nan"))


def score_audit_d(path: Path = AUDIT_D_SHEET, key_path: Path = AUDIT_D_KEY) -> dict:
    """Brand precision and recall of the extraction against the reviewer's read.

    Every sheet row counts as reviewed (an empty row means the extracted list
    was right), so score only a finished sheet. Per row: E = extracted brands;
    W = the reviewer's ``wrong_brands`` that match an extracted name
    (case-insensitive); M = ``missed_brands``. TP = |E| - |W|, FP = |W|,
    FN = |M|; precision and recall are pooled over rows (micro), overall and
    per arm via the key. Wrong names that match no extracted brand are counted
    and reported, not scored.
    """
    with path.open(newline="") as f:
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
        "passes": passes, "sheet_sha256": sha256_file(path),
        "key_sha256": sha256_file(key_path),
        "lexicon_sha256": brands.LEXICON_SHA256,
        "scored_on": date.today().isoformat(),
    }


def r4_agreement(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Coverage of the Haiku cache, and per-answer agreement where it exists."""
    has = df["brands_haiku"].map(lambda v: v is not None)
    cov = df.assign(has=has).groupby("wave").agg(answers=("item_id", "size"),
                                                  with_candidates=("has", "sum")).reset_index()
    cov["coverage"] = cov["with_candidates"] / cov["answers"]
    sub = df[has]
    if sub.empty:
        return cov, pd.DataFrame()
    j = [jaccard(set(a), set(b)) for a, b in zip(sub["brands"], sub["brands_haiku"])]
    sub = sub.assign(j=j, identical=[set(a) == set(b) for a, b in
                                     zip(sub["brands"], sub["brands_haiku"])],
                     n_haiku=sub["brands_haiku"].map(len))
    agree = sub.groupby("arm").agg(
        answers=("item_id", "size"), mean_jaccard=("j", "mean"),
        identical=("identical", "mean"), lexicon_brands=("n_brands", "mean"),
        haiku_brands=("n_haiku", "mean"), both_empty=("j", lambda s: int(s.isna().sum())),
    ).reset_index()
    total = {"arm": "all", "answers": len(sub), "mean_jaccard": np.nanmean(sub["j"]),
             "identical": sub["identical"].mean(), "lexicon_brands": sub["n_brands"].mean(),
             "haiku_brands": sub["n_haiku"].mean(), "both_empty": int(sub["j"].isna().sum())}
    return cov, pd.concat([arm_order(agree), pd.DataFrame([total])], ignore_index=True)


def audit_d(df: pd.DataFrame, out: list[str], synthetic: bool, *, score: bool,
            signed_by: str | None, force_sheet: bool) -> dict | None:
    h(out, "Audit D: extraction validity")
    result = None
    if synthetic:
        out.append("(synthetic frame: no spot-check sheet)")
    else:
        note = make_audit_d_sheet(df, AUDIT_D_SHEET, force=force_sheet)
        print(f"  audit D sheet: {note}")
        out.append(
            f"Arm-blind spot check, {AUDIT_D_N} answers stratified across the "
            f"{df['arm'].nunique()} arms, drawn with seed {SEED}, shuffled into A01-A{AUDIT_D_N}. "
            f"The reviewer edits `data/raw/{AUDIT_D_SHEET.name}` (audit_id, category, extracted "
            f"brands, reviewer columns) and reads `data/raw/{AUDIT_D_ANSWERS.name}` (each answer "
            "as extraction reads it, sources block stripped); neither names the arm, prompt or "
            f"wave. `data/raw/{AUDIT_D_KEY.name}` maps audit_id to arm, item and wave for the "
            "scorer. All three are gitignored. `missed_brands` = in-category brands the answer "
            "presents that extraction missed; `wrong_brands` = extracted brands that are not "
            "real in-category mentions in that answer (names separated by `; `).")
        if score:
            if not sheet_has_input(AUDIT_D_SHEET):
                raise SystemExit("the Audit D sheet has no reviewer input yet")
            result = score_audit_d(AUDIT_D_SHEET)
            if signed_by:
                result["signed_by"] = signed_by
            AUDIT_D_SCORE.parent.mkdir(parents=True, exist_ok=True)
            AUDIT_D_SCORE.write_text(json.dumps(result, indent=1) + "\n")
            print(f"  wrote {AUDIT_D_SCORE}")
        elif AUDIT_D_SCORE.exists():
            result = json.loads(AUDIT_D_SCORE.read_text())
        if result:
            out.append(
                f"\nScore ({result['scored_on']}, {result['rows']} rows): precision {result['precision']:.3f} (gate "
                f">= {AUDIT_D_PRECISION}), recall {result['recall']:.3f} (gate >= "
                f"{AUDIT_D_RECALL}); TP {result['true_positive']}, FP "
                f"{result['false_positive']}, FN {result['false_negative']}; wrong names that "
                f"match no extracted brand: {result['wrong_names_not_extracted']}. "
                f"**{'PASS' if result['passes'] else 'FAIL: refine the lexicon, log it, re-check'}**"
                + (f", signed by {result['signed_by']}." if result.get("signed_by") else
                   ", not yet signed."))
            if result.get("per_arm"):
                out.append("\nPer arm:\n")
                out.append(md_table(pd.DataFrame(
                    [{"arm": a, **v} for a, v in result["per_arm"].items()])))
        else:
            out.append("\nNot scored yet. After review: `02_audit.py --score-audit-d "
                       "--signed-by \"<name>\"`. 03_model refuses to run on real data until the "
                       "score passes and is signed.")

    cov, agree = r4_agreement(df)
    out.append("\nHaiku candidate cache coverage (R4 needs every wave; the extraction for "
               "waves 2 and 3 is `harness/lexicon_candidates.py --wave N`):\n")
    out.append(md_table(cov))
    if not agree.empty:
        out.append("\nAgreement, lexicon extraction vs Haiku candidates mapped through the "
                   "frozen lexicon (same answer; per-answer Jaccard, NaN when both are empty). "
                   "The lexicon was curated from the wave 1 candidates, so wave 1 agreement is "
                   "in-sample:\n")
        out.append(md_table(agree))
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

    df = load_features(synthetic=a.synthetic)
    synthetic = bool(df["synthetic"].max())
    out = [
        f"# Experiment 009: data-quality audits{f' (SYNTHETIC/{a.synthetic})' if synthetic else ''}",
        "",
        f"Generated {date.today().isoformat()} by `pipeline/02_audit.py` from "
        f"`data/interim/features.jsonl` ({len(df)} answers). Aggregates only: no brand, "
        "domain, prompt, answer or query text.",
    ]
    audit_a(df, out, synthetic)
    audit_b(out)
    audit_c(df, out)
    audit_d(df, out, synthetic, score=a.score_audit_d, signed_by=a.signed_by,
            force_sheet=a.force_new_sheet)

    results = results_dir(a.synthetic)
    results.mkdir(parents=True, exist_ok=True)
    path = results / "audit_report.md"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
