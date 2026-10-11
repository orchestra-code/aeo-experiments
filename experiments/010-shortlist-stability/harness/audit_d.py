"""Experiment 010, Audit D: lexicon v3 extraction precision and recall (spec §2).

A person reads 30 answers from new waves 1 and 2 and marks, against the
lexicon's extraction, the brands it got wrong and the brands it missed. Pass:
brand precision at least 0.95 and recall at least 0.90 (009's thresholds).

The sample is stratified by platform (10 per platform from ChatGPT, Gemini
and the Claude API; spec deviation 3), drawn with the frozen seed, and shown
platform-blind in a seeded shuffled order (A01 to A30). The draw depends only
on the seed and the task ids, not on the lexicon, so re-making the sheet after
a lexicon change keeps the same 30 answers.

Files (all gitignored under data/raw/audit_d/, they hold answer text and
brand names): ``sheet.csv`` (the reviewer edits it), ``answers.md`` (the
reading file), ``key.csv`` (audit_id -> dataset, item, wave). Scoring writes
``results/audit_d_score.json`` (counts and hashes only, no brand names).

Usage (repo root):
  uv run python experiments/010-shortlist-stability/harness/audit_d.py make --lexicon <csv>
  uv run python experiments/010-shortlist-stability/harness/audit_d.py score --lexicon <csv> --signed-by "Jim Wrubel"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
OUT = RAW / "audit_d"
SHEET, ANSWERS, KEY = OUT / "sheet.csv", OUT / "answers.md", OUT / "key.csv"
SCORE = EXP / "results" / "audit_d_score.json"
SRC_009 = EXP.parent / "009-claude-model-fidelity"
TASKS = RAW / "tasks_b2b_main.jsonl"

SEED = 20261003
DATASETS = ("chatgpt_b2b", "gemini_b2b", "claude_api_b2b")
PER_DATASET = 10
WAVES = (1, 2)
PRECISION_GATE, RECALL_GATE = 0.95, 0.90
REVIEWER_COLUMNS = ("missed_brands", "wrong_brands", "reviewer_notes")
SPLIT = re.compile(r"[;|\n]+")
INSTRUCTIONS = (
    "Each answer below has an ID (A01 to A30) that matches a row in sheet.csv. "
    "The platform, prompt and wave are hidden.",
    "Read the answer and compare it with the extracted brands listed above it. "
    "Count a brand when the answer presents it as an option in the prompt's category "
    "(recommended, compared, mentioned as an alternative, or warned against). Do not "
    "count the buyer's other systems, integrations, publishers or standards.",
    "missed_brands: in-category brands the list missed, written as the answer writes "
    "them, separated by \"; \".",
    "wrong_brands: listed brands that are not real in-category mentions in this answer, "
    "copied exactly as listed, separated by \"; \".",
    "Leave both cells empty when the list is right. Use reviewer_notes for anything else.",
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def brands_module():
    sys.path.insert(0, str(SRC_009 / "pipeline"))
    return _load(SRC_009 / "pipeline/brands.py", "exp009_brands")


def picks() -> list[dict]:
    tasks = [json.loads(line) for line in TASKS.read_text().splitlines() if line.strip()]
    rng = np.random.default_rng(SEED)
    chosen = []
    for ds in DATASETS:
        pool = sorted((t for t in tasks if t["dataset"] == ds and t["wave"] in WAVES),
                      key=lambda t: t["task_id"])
        chosen += [pool[i] for i in sorted(rng.choice(len(pool), PER_DATASET, replace=False))]
    return [chosen[i] for i in rng.permutation(len(chosen))]


def sheet_has_input() -> bool:
    if not SHEET.exists():
        return False
    with SHEET.open(newline="") as f:
        return any(any((r.get(c) or "").strip() for c in REVIEWER_COLUMNS)
                   for r in csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def make(lexicon: Path, force: bool) -> None:
    if sheet_has_input() and not force:
        raise SystemExit("sheet.csv already has reviewer input; pass --force to overwrite")
    b9 = brands_module()
    patterns = b9.load_lexicon(lexicon)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet, key, md = [], [], [*(f"- {line}" for line in INSTRUCTIONS), ""]
    for n, t in enumerate(picks(), start=1):
        aid = f"A{n:02d}"
        found = b9.lexicon_extract(t["answer"], patterns.get(t["category"], []))
        listed = "; ".join(found)
        sheet.append({"audit_id": aid, "category": t["category"], "extracted_brands": listed,
                      "missed_brands": "", "wrong_brands": "", "reviewer_notes": ""})
        key.append({"audit_id": aid, "task_id": t["task_id"], "dataset": t["dataset"],
                    "item_id": t["item_id"], "wave": t["wave"]})
        md += [f"## {aid}: {t['category']}", "",
               f"**Question:** {t['question']}", "",
               f"**Extracted brands ({len(found)}):** {listed or '(none)'}", "",
               "**Answer text:**", "", b9.strip_sources(t["answer"]).strip(), "", "---", ""]
    write_csv(SHEET, sheet)
    write_csv(KEY, key)
    ANSWERS.write_text("\n".join(md))
    (OUT / "lexicon_used.txt").write_text(f"{lexicon}\n{sha256_file(lexicon)}\n")
    print(f"wrote {len(sheet)} rows to {SHEET.relative_to(EXP)} with lexicon "
          f"{lexicon.name} ({sha256_file(lexicon)[:12]})")


def names(cell: str | None) -> list[str]:
    return [x.strip() for x in SPLIT.split(cell or "") if x.strip()]


def pr(tp: int, fp: int, fn: int) -> tuple[float, float]:
    return (tp / (tp + fp) if tp + fp else float("nan"),
            tp / (tp + fn) if tp + fn else float("nan"))


def score(lexicon: Path, signed_by: str | None) -> None:
    """TP = |extracted| - |wrong that match an extracted name|, FP = those wrong,
    FN = |missed|; pooled over rows, overall and per dataset. The sheet must
    have been made with the lexicon being scored."""
    used = (OUT / "lexicon_used.txt").read_text().split()
    if used[-1] != sha256_file(lexicon):
        raise SystemExit("the sheet was made with a different lexicon file; re-make it")
    with SHEET.open(newline="") as f:
        rows = list(csv.DictReader(f))
    with KEY.open(newline="") as f:
        ds_of = {r["audit_id"]: r["dataset"] for r in csv.DictReader(f)}
    tot: dict[str, list[int]] = {}
    unmatched = 0
    for r in rows:
        ext = {x.lower() for x in names(r["extracted_brands"])}
        wrong = {x.lower() for x in names(r.get("wrong_brands"))}
        hit = wrong & ext
        unmatched += len(wrong - ext)
        c = (len(ext) - len(hit), len(hit), len(names(r.get("missed_brands"))))
        for k in ("all", ds_of[r["audit_id"]]):
            t = tot.setdefault(k, [0, 0, 0, 0])
            for i, v in enumerate(c):
                t[i] += v
            t[3] += 1
    tp, fp, fn, n = tot["all"]
    p, rcl = pr(tp, fp, fn)
    per = {}
    for ds in DATASETS:
        a, b, c, m = tot.get(ds, [0, 0, 0, 0])
        dp, dr = pr(a, b, c)
        per[ds] = {"answers": m, "true_positive": a, "false_positive": b,
                   "false_negative": c, "precision": dp, "recall": dr}
    complete = n == PER_DATASET * len(DATASETS)
    out = {"rows": n, "complete": complete, "true_positive": tp, "false_positive": fp,
           "false_negative": fn, "wrong_names_not_extracted": unmatched,
           "precision": p, "recall": rcl, "per_dataset": per,
           "gate_precision": PRECISION_GATE, "gate_recall": RECALL_GATE,
           "passes": bool(complete and p >= PRECISION_GATE and rcl >= RECALL_GATE),
           "sheet_sha256": sha256_file(SHEET), "key_sha256": sha256_file(KEY),
           "lexicon_sha256": sha256_file(lexicon), "signed_by": signed_by,
           "scored_on": date.today().isoformat()}
    SCORE.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("rows", "precision", "recall", "passes")}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "score"])
    ap.add_argument("--lexicon", type=Path, required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--signed-by", default=None)
    a = ap.parse_args()
    make(a.lexicon, a.force) if a.cmd == "make" else score(a.lexicon, a.signed_by)


if __name__ == "__main__":
    main()
