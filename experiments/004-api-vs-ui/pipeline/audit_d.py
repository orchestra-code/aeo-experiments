"""Audit D: extraction validity (spec §2), as in 011's ``02_audit.py``.

A 30-answer spot check, 6 per arm, drawn with the study seed from every answer in the frame
and shuffled into A01 to A30. Three files go to the mode's raw directory (gitignored in the
main checkout: they hold answer text and brand names):

- ``audit_d_sheet.csv``, which the reviewer edits: audit_id, category, the extracted brands,
  the lexicon's drop names found in the answer with their reasons, and the blank reviewer
  columns ``missed_brands``, ``wrong_brands`` and ``reviewer_notes``;
- ``audit_d_answers.md``, the reading file: per audit_id the same lists and the answer text
  as extraction reads it (the Gemini app's markup, citation links, labelled source blocks and
  link targets removed);
- ``audit_d_key.csv``: audit_id -> arm, item_id, wave, for the scorer only.

Neither reviewer file names the arm, prompt or wave. Drop names are listed because a reviewer
cannot otherwise tell a deliberate exclusion from a miss (010's audit, 2026-10-11).

The scorer counts every sheet row as reviewed (an empty row means the list was right). Per
row: E = extracted brands, W = ``wrong_brands`` that match an extracted name
(case-insensitive), M = ``missed_brands``. TP = |E| - |W|, FP = |W|, FN = |M|, pooled over
rows, overall and per arm through the key. It passes at precision >= 0.95 and recall >= 0.90
on a complete sheet, and records the lexicon's sha256; ``03_model`` checks that it is the
pinned study lexicon.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

import common
import numpy as np
import pandas as pd
from common import ALL_ARMS, SEED, Mode

AUDIT_D_N = 30
AUDIT_D_PRECISION = 0.95
AUDIT_D_RECALL = 0.90
REVIEWER_COLUMNS = ("missed_brands", "wrong_brands", "reviewer_notes")
SPLIT = re.compile(r"[;|\n]+")
INSTRUCTIONS = (
    "How to review: each answer below has an ID (A01 to A30) that matches a row in "
    "audit_d_sheet.csv.",
    "Read the answer text and compare it with the extracted brands listed above it.",
    "Excluded names are lexicon drop rows found in the answer (a deliberate exclusion, with "
    "the reason). Do not list them as missed unless you disagree with the exclusion; if you "
    "do, say so in reviewer_notes.",
    "missed_brands: brands in this category that the answer presents as options but the "
    "list missed. Write the names as the answer writes them, separated by \"; \".",
    "wrong_brands: listed brands that are not real in-category mentions in this answer. "
    "Copy the names exactly as listed, separated by \"; \".",
    "Leave both cells empty when the list is right. Use reviewer_notes for anything else.",
)


def paths(mode: Mode) -> dict[str, Path]:
    return {"sheet": mode.raw / "audit_d_sheet.csv", "answers": mode.raw / "audit_d_answers.md",
            "key": mode.raw / "audit_d_key.csv", "score": mode.results / "audit_d_score.json"}


def lexicon_path(mode: Mode) -> Path:
    return mode.raw / "lexicon.csv" if mode.synthetic else common.STUDY_LEXICON


# ------------------------------------------------------------------ text


def reading_text(text: str) -> str:
    """What the reviewer reads: extraction's input with link targets gone, formatting kept."""
    t = common.instrument010.strip_citation_links(text)
    return common.b9._MD_URL.sub(" ", common.b9.strip_sources(t)).strip()


def lexicon_hits(text: str, patterns: list) -> tuple[list[str], list[str]]:
    """(kept, dropped) canonicals in first-mention order, exactly as ``common.extract`` reads.

    The same preprocessing and span consumption as 009's ``lexicon_extract`` after 010's
    citation-link strip, so the kept list equals the frame's ``brands``.
    """
    b9 = common.b9
    t = common.instrument010.strip_citation_links(text)
    t = b9._MD_MARKUP.sub(" ", b9._MD_URL.sub(" ", b9.strip_sources(t)))
    taken = np.zeros(len(t) + 1, dtype=bool)
    first: dict[tuple[str, bool], int] = {}
    for pattern, canon, keep in patterns:
        for m in pattern.finditer(t):
            if taken[m.start():m.end()].any():
                continue
            taken[m.start():m.end()] = True
            k = (canon, bool(keep))
            if k not in first or m.start() < first[k]:
                first[k] = m.start()
    order = sorted(first, key=first.get)
    return [c for c, k in order if k], [c for c, k in order if not k]


def drop_reasons(path: Path) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], set[str]] = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            if r["decision"] == "drop":
                out.setdefault((r["category"], r["canonical"]), set()).add(r["reason"].strip())
    return {k: " / ".join(sorted(v)) for k, v in out.items()}


def answer_texts(mode: Mode, keys: list[tuple[str, str, int]]) -> dict[tuple[str, str, int], str]:
    """Brand text (``answers.brand_text``) per (arm, item_id, wave), read as 01_frame reads it."""
    frame = common._load("exp004_01_frame_for_audit_d", common.EXP / "pipeline" / "01_frame.py")
    frame.exp004.RAW = mode.raw
    waves = sorted({k[2] for k in keys})
    ui, _ = frame.load_ui(frame.exp004.STUDY, waves)
    api, _ = frame.load_api(frame.exp004.STUDY, waves, pilot=False)
    want = set(keys)
    out = {}
    for r in ui + api:
        k = (r["arm"], r["item_id"], int(r["wave"]))
        if k in want:
            out[k] = frame.answers.brand_text(r["arm"], r["norm"]["answer_text"])
    missing = want - set(out)
    if missing:
        raise SystemExit(f"Audit D: no answer text for {sorted(missing)[:3]}")
    return out


# ----------------------------------------------------------------- sheet


def picks(df: pd.DataFrame) -> list[pd.Series]:
    """30 answers, stratified across the arms, in the seeded shuffled order of A01 to A30."""
    rng = np.random.default_rng(SEED)
    arms = [a for a in ALL_ARMS if a in set(df["arm"])]
    base, extra = divmod(AUDIT_D_N, len(arms))
    bonus = set(rng.choice(arms, size=extra, replace=False)) if extra else set()
    out = []
    for arm in arms:
        sub = df[df["arm"] == arm].sort_values(["wave", "item_id"]).reset_index(drop=True)
        k = min(base + (arm in bonus), len(sub))
        out += [sub.iloc[i] for i in sorted(rng.choice(len(sub), size=k, replace=False))]
    return [out[i] for i in rng.permutation(len(out))]


def has_input(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(newline="") as f:
        return any((r.get(c) or "").strip() for r in csv.DictReader(f) for c in REVIEWER_COLUMNS)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def sheet_problems(df: pd.DataFrame, meta: dict, mode: Mode) -> list[str]:
    """Why the real sheet may not be drawn yet (synthetic worlds always may)."""
    if mode.synthetic:
        return []
    problems = []
    if meta.get("lexicon_sha256") != common.STUDY_LEXICON_SHA256:
        problems.append("the frame was not built with the pinned study lexicon")
    if meta.get("missing"):
        problems.append(f"{len(meta['missing'])} answers are still missing (all three waves first)")
    return problems


def make_sheet(df: pd.DataFrame, meta: dict, mode: Mode, *, force: bool = False) -> str:
    p = paths(mode)
    if has_input(p["sheet"]) and not force:
        return f"{p['sheet'].name} already has reviewer input; left unchanged (--force-new-sheet)"
    problems = sheet_problems(df, meta, mode)
    if problems:
        raise SystemExit("Audit D sheet not drawn: " + "; ".join(problems))
    lex = lexicon_path(mode)
    if common.sha256_file(lex) != meta["lexicon_sha256"]:
        raise SystemExit(f"{lex.name} is not the lexicon the frame was built with")
    patterns = common.b9.load_lexicon(lex)
    reasons = drop_reasons(lex)
    chosen = picks(df)
    texts = answer_texts(mode, [(r["arm"], r["item_id"], int(r["wave"])) for r in chosen])
    sheet, key, md = [], [], [*(f"- {line}" for line in INSTRUCTIONS), ""]
    for n, r in enumerate(chosen, start=1):
        audit_id = f"A{n:02d}"
        text = texts[(r["arm"], r["item_id"], int(r["wave"]))]
        kept, dropped = lexicon_hits(text, patterns.get(r["category"], []))
        if kept != list(r["brands"]):
            raise SystemExit(f"Audit D: re-extraction differs from the frame for {audit_id}; "
                             "rebuild the frame with this lexicon")
        listed = "; ".join(kept)
        excluded = "; ".join(f"{c} ({reasons.get((r['category'], c), 'drop')})" for c in dropped)
        sheet.append({"audit_id": audit_id, "category": r["category"], "extracted_brands": listed,
                      "excluded_names_found": excluded,
                      **{c: "" for c in REVIEWER_COLUMNS}})
        key.append({"audit_id": audit_id, "arm": r["arm"], "item_id": r["item_id"],
                    "wave": int(r["wave"])})
        md += [f"## {audit_id}: {r['category']}", "",
               f"**Extracted brands ({len(kept)}):** {listed or '(none)'}", "",
               f"**Excluded names found ({len(dropped)}):** {excluded or '(none)'}", "",
               "**Answer text:**", "", reading_text(text), "", "---", ""]
    _write_csv(p["sheet"], sheet)
    _write_csv(p["key"], key)
    p["answers"].write_text("\n".join(md))
    by_arm = pd.Series([k["arm"] for k in key]).value_counts().to_dict()
    return (f"wrote {p['sheet'].name}, {p['answers'].name} and {p['key'].name} "
            f"({len(sheet)} answers; per arm {by_arm})")


# ----------------------------------------------------------------- score


def _names(cell: str | None) -> list[str]:
    return [x.strip() for x in SPLIT.split(cell or "") if x.strip()]


def _pr(tp: int, fp: int, fn: int) -> tuple[float, float]:
    return (tp / (tp + fp) if tp + fp else float("nan"),
            tp / (tp + fn) if tp + fn else float("nan"))


def score(sheet_path: Path, key_path: Path, lexicon_sha256: str | None) -> dict:
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
    precision, recall = _pr(tp, fp, fn)
    per_arm = {}
    for arm in [a for a in ALL_ARMS if a in totals] + (["unknown"] if "unknown" in totals else []):
        a_tp, a_fp, a_fn, n = totals[arm]
        a_p, a_r = _pr(a_tp, a_fp, a_fn)
        per_arm[arm] = {"answers": n, "true_positive": a_tp, "false_positive": a_fp,
                        "false_negative": a_fn, "precision": a_p, "recall": a_r}
    complete = len(rows) == AUDIT_D_N and all(r["audit_id"] in arm_of for r in rows)
    passes = bool(complete and precision >= AUDIT_D_PRECISION and recall >= AUDIT_D_RECALL)
    return {"rows": len(rows), "complete": complete, "true_positive": tp, "false_positive": fp,
            "false_negative": fn, "wrong_names_not_extracted": unmatched,
            "precision": precision, "recall": recall, "per_arm": per_arm,
            "gate_precision": AUDIT_D_PRECISION, "gate_recall": AUDIT_D_RECALL,
            "passes": passes, "sheet_sha256": common.sha256_file(sheet_path),
            "key_sha256": common.sha256_file(key_path), "lexicon_sha256": lexicon_sha256,
            "scored_on": date.today().isoformat()}


def run(df: pd.DataFrame, meta: dict, mode: Mode, *, write_sheet: bool, do_score: bool,
        signed_by: str | None, force_sheet: bool) -> list[str]:
    """Audit D's report lines (aggregates only); writes the sheet and the score when asked."""
    p = paths(mode)
    out = [f"Arm-blind spot check: {AUDIT_D_N} answers, stratified across the "
           f"{df['arm'].nunique()} arms, drawn with seed {SEED} and shuffled into "
           f"A01-A{AUDIT_D_N}. The reviewer edits `{p['sheet'].name}` and reads "
           f"`{p['answers'].name}`; neither names the arm, prompt or wave, and both list the "
           f"lexicon's drop names found with their reasons. `{p['key'].name}` maps each row to "
           "its arm, item and wave for the scorer. All three are gitignored. Gate: precision "
           f">= {AUDIT_D_PRECISION}, recall >= {AUDIT_D_RECALL}, signed by Jim Wrubel; "
           "otherwise refine the lexicon, log it and re-check."]
    if write_sheet:
        print(f"  audit D: {make_sheet(df, meta, mode, force=force_sheet)}")
    result = None
    if do_score:
        if not p["sheet"].exists() or not p["key"].exists():
            raise SystemExit("no Audit D sheet to score (--audit-d-sheet first)")
        result = score(p["sheet"], p["key"], meta.get("lexicon_sha256"))
        if signed_by:
            result["signed_by"] = signed_by
        p["score"].parent.mkdir(parents=True, exist_ok=True)
        p["score"].write_text(json.dumps(common.jsonable(result), indent=1) + "\n")
        print(f"  audit D: wrote {p['score']}")
    elif p["score"].exists():
        result = json.loads(p["score"].read_text())
    if result:
        verdict = "PASS" if result["passes"] else "FAIL: refine the lexicon, log it, re-check"
        out.append(
            f"\nScore ({result['scored_on']}, {result['rows']} rows, lexicon "
            f"`{str(result.get('lexicon_sha256'))[:12]}`): precision {result['precision']:.3f}, "
            f"recall {result['recall']:.3f}; TP {result['true_positive']}, FP "
            f"{result['false_positive']}, FN {result['false_negative']}; wrong names that match no "
            f"extracted brand: {result['wrong_names_not_extracted']}. **{verdict}**"
            + (f", signed by {result['signed_by']}." if result.get("signed_by") else ", not yet signed."))
        out += ["\nPer arm:\n", common.md_table(pd.DataFrame(
            [{"arm": a, **v} for a, v in result["per_arm"].items()]))]
    elif p["sheet"].exists():
        out.append("\nSheet drawn, not scored yet. After review: `02_audit.py --score-audit-d "
                   "--signed-by \"<name>\"`.")
    else:
        out.append("\nNot drawn yet (`02_audit.py --audit-d-sheet`, after all three waves and the "
                   "lexicon freeze). 03_model refuses the real data until a signed pass exists.")
    return out
