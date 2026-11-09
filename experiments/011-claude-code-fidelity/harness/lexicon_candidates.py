"""Wave brand candidates for extending the lexicon (spec §5; 009/harness/lexicon_rules.md).

Runs 009's Haiku extractor (``pilot_report.extract_brands``, same system prompt and schema) over
every normalized answer in ``data/raw/responses/w<wave>/``, caching one record per
(arm, item_id, wave, answer_sha256) in ``data/raw/brand_candidates.jsonl`` so a rerun costs
nothing. Then pools the candidates per (prompt category, canonical name) and compares them with
the current lexicon:

- ``v0_status``: ``keep`` / ``drop`` when a raw name is already an alias in that category,
  ``canonical`` when only the canonical key matches a row there, otherwise ``absent``;
- ``other_categories``: the same canonical key in other categories of the lexicon.

Writes ``data/raw/lexicon_w<wave>_candidates.csv`` (gitignored: brand names from AI answers) and
prints coverage: names the lexicon cannot place, against the spec's 2% limit, and answers per
category with a candidate the lexicon has no alias for.

The lexicon compared against is ``brands.LEXICON`` (now ``data/raw/lexicon_v1_2.csv``) once it exists, and until then 010's
frozen v3, the spec's starting point, with its hash checked. ``--lexicon`` overrides.

The cache also holds the pilot's records (a bare hash key and ``names``). ``pilot_report.py``
reads ``names`` on every row, so new records hold the list under both ``brands`` and ``names``.

The key comes only from this repo's ``.env.local``. Nothing runs without it, and nothing falls
back to the process environment or another repo.

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/harness/lexicon_candidates.py --wave 1
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import importlib.util
import json
import sys
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
RAW = EXP / "data" / "raw"
RESPONSES = RAW / "responses"
EXP009 = EXP.parent / "009-claude-model-fidelity"
PROMPTS = EXP009 / "data" / "raw" / "prompts.csv"
CACHE = RAW / "brand_candidates.jsonl"
ENV_FILE = ROOT / ".env.local"

LEXICON_V3 = EXP.parent / "010-shortlist-stability" / "data" / "raw" / "lexicon_v3" / "lexicon_v3.csv"
LEXICON_V3_SHA256 = "6084f47ca1831474de9cb64d79425d522b75ac409d2b5080b24653ec9905cf5d"

#: Arms read in the study waves. Other waves (the pilot) read whatever is on disk.
STUDY_ARMS = frozenset({"ui_default", "cc_stock_full", "sched_kit", "cc_none_search", "opus55_plain"})
STUDY_WAVES = (1, 2, 3)
MISSING_NAMES_MAX = 0.02  # spec §5: above this, extend the lexicon under the same rules


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: Loaded by path, since 009's harness puts 009's own ``brands`` on the import path.
brands = _load("exp011_brands", EXP / "pipeline" / "brands.py")


def extractor():
    """009's extraction module, imported only when needed: it changes ``sys.path``."""
    harness = str(EXP009 / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    import pilot_report

    return pilot_report


def load_answers(wave: int, responses: Path = RESPONSES, prompts: Path = PROMPTS) -> list[dict]:
    with prompts.open(newline="") as f:
        category = {r["item_id"]: r["category"] for r in csv.DictReader(f)}
    rows = []
    for path in sorted((responses / f"w{wave}").glob("*/*.json")):
        arm = path.parent.name
        if wave in STUDY_WAVES and arm not in STUDY_ARMS:
            continue
        text = json.loads(path.read_text())["normalized"].get("answer_text") or ""
        rows.append({"arm": arm, "item_id": path.stem, "wave": wave, "category": category[path.stem],
                     "answer_text": text, "answer_sha256": hashlib.sha256(text.encode()).hexdigest()})
    return rows


def key(r: dict) -> str:
    return f"{r['arm']}|{r['item_id']}|{r['wave']}|{r['answer_sha256']}"


def load_cache(path: Path = CACHE) -> dict[str, dict]:
    if not path.exists():
        return {}
    recs = (json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return {r["key"]: r for r in recs}


def cache_record(r: dict, names: list[str], usage: dict, cost: float, model: str) -> dict:
    """One cache row. ``names`` keeps it readable by pilot_report.py."""
    return {"key": key(r), **{k: r[k] for k in ("arm", "item_id", "wave", "answer_sha256")},
            "model": model, "brands": names, "names": names, "usage": usage, "cost_usd": cost,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def require_repo_key(path: Path = ENV_FILE) -> str:
    """This repo's ``.env.local``, or stop. The key is never printed."""
    has_key = path.exists() and any(
        line.strip().startswith("ANTHROPIC_API_KEY=") and line.split("=", 1)[1].strip().strip("\"'")
        for line in path.read_text().splitlines()
    )
    if not has_key:
        raise SystemExit(f"no ANTHROPIC_API_KEY in {path}; keys come only from this repo's .env.local")
    return str(path)


def fill_cache(rows: list[dict], ext) -> None:
    cache = load_cache()
    todo = [r for r in rows if key(r) not in cache and r["answer_text"]]
    if not todo:
        print(f"brand candidates: all {len(rows)} answers cached")
        return
    from anthropic_client import make_client

    api = make_client(require_repo_key())
    lock, spent = threading.Lock(), [0.0]

    def work(r):
        names, usage = ext.extract_brands(api, r["answer_text"], r["category"])
        cost = ext.cost_from_usage(ext.EXTRACT_MODEL, usage)["total"]
        rec = cache_record(r, names, usage, cost, ext.EXTRACT_MODEL)
        with lock:
            with CACHE.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            spent[0] += cost

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, todo))
    print(f"brand candidates: extracted {len(todo)} answers (${spent[0]:.4f})")


def lexicon_index(path: Path):
    """(category, canonical) -> decision, and canonical -> {category: decision}."""
    by_pair, by_canon = {}, defaultdict(dict)
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            by_pair[(row["category"], row["canonical"])] = row["decision"]
            by_canon[row["canonical"]][row["category"]] = row["decision"]
    return by_pair, by_canon


def default_lexicon() -> Path:
    if brands.LEXICON.exists():
        return brands.LEXICON
    brands.verify_lexicon(LEXICON_V3, LEXICON_V3_SHA256)
    return LEXICON_V3


def names_of(record: dict) -> list[str]:
    names = record.get("brands")
    return record.get("names", []) if names is None else names


def missing_rate(rows: list[dict], cache: dict[str, dict], patterns: dict) -> dict[str, tuple[int, int]]:
    """Per arm: (Haiku names, names the lexicon's own matcher cannot place)."""
    out: dict[str, list[int]] = {}
    for r in rows:
        names = names_of(cache.get(key(r), {}))
        tally = out.setdefault(r["arm"], [0, 0])
        tally[0] += len({n.strip().lower() for n in names if n.strip()})
        tally[1] += len(brands.unplaced_names(names, patterns.get(r["category"], [])))
    return {arm: (n, m) for arm, (n, m) in out.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--lexicon", default=None)
    a = ap.parse_args()

    lexicon = Path(a.lexicon) if a.lexicon else default_lexicon()
    ext = extractor()
    rows = load_answers(a.wave)
    fill_cache(rows, ext)
    cache = load_cache()
    amap = brands.lexicon_alias_map(lexicon)
    patterns = brands.load_lexicon(lexicon)
    by_pair, by_canon = lexicon_index(lexicon)

    names: dict[tuple, set] = defaultdict(set)
    answers: dict[tuple, set] = defaultdict(set)
    arms: dict[tuple, set] = defaultdict(set)
    status: dict[tuple, str] = {}
    gap_answers: Counter = Counter()
    per_cat: Counter = Counter()
    for r in rows:
        cat = r["category"]
        per_cat[cat] += 1
        unmatched = False
        for name in names_of(cache.get(key(r), {})):
            canon = ext.canonical_brand(name)
            if canon in ext.EXCLUDE:
                continue
            k = (cat, canon)
            names[k].add(name)
            answers[k].add((r["arm"], r["item_id"]))
            arms[k].add(r["arm"])
            hit = amap.get((cat, name.strip().lower()))
            if hit:
                status[k] = "keep" if hit[1] else "drop"
            elif k not in status and k in by_pair:
                status[k] = "canonical"
            if not hit:
                unmatched = True
        gap_answers[cat] += unmatched

    out = RAW / f"lexicon_w{a.wave}_candidates.csv"
    ordered = sorted(names, key=lambda k: (k[0], -len(answers[k]), k[1]))
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "canonical", "raw_names", "n_answers", "arms_seen",
                    "v0_status", "other_categories"])
        for k in ordered:
            others = {c: d for c, d in by_canon.get(k[1], {}).items() if c != k[0]}
            w.writerow([k[0], k[1], "|".join(sorted(names[k])), len(answers[k]),
                        "|".join(sorted(arms[k])), status.get(k, "absent"),
                        "|".join(f"{c}={d}" for c, d in sorted(others.items()))])

    st = Counter(status.get(k, "absent") for k in names)
    print(f"{out.name}: {len(names)} (category, brand) rows; status {dict(st)}; lexicon {lexicon.name}")
    print(f"names the lexicon cannot place, per arm (limit {MISSING_NAMES_MAX:.0%}, spec §5):")
    for arm, (n, m) in sorted(missing_rate(rows, cache, patterns).items()):
        share = m / n if n else 0.0
        print(f"  {arm:18} {m:>4}/{n:<5} {share:6.1%}{'  OVER LIMIT' if share > MISSING_NAMES_MAX else ''}")
    print("answers with a candidate the lexicon has no alias for, per category:")
    for cat in sorted(per_cat):
        print(f"  {cat:32} {gap_answers[cat]:>3}/{per_cat[cat]}")


if __name__ == "__main__":
    main()
