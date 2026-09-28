"""Wave brand candidates for extending the lexicon (lexicon_rules.md, step 1).

Runs the pilot's Haiku extractor (``pilot_report.extract_brands``, same system
prompt and schema) over every normalized answer in
``data/raw/responses/w<wave>/`` (API and UI arms), caching one record per
(arm, item_id, wave, answer_sha256) in ``data/raw/brand_candidates.jsonl`` so
a rerun costs nothing. Then pools the candidates per (prompt category,
canonical name) and compares them with the current lexicon:

- ``v0_status``: ``keep`` / ``drop`` when a raw name is already an alias in
  that category, ``canonical`` when only the canonical key matches a row there,
  otherwise ``absent``;
- ``other_categories``: the same canonical key in other categories of the
  lexicon (a hint for suites and cross-category vendors).

Writes ``data/raw/lexicon_w<wave>_candidates.csv`` (gitignored: brand names
from AI answers) and prints coverage: per category, how many answers have a
Haiku candidate the lexicon does not match.

Usage (repo root):
    uv run python experiments/009-claude-model-fidelity/harness/lexicon_candidates.py --wave 1
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pilot_report import (
    EXCLUDE,
    EXTRACT_MODEL,
    RAW,
    canonical_brand,
    cost_from_usage,
    extract_brands,
    lexicon_alias_map,
)

CACHE = RAW / "brand_candidates.jsonl"
DEFAULT_LEXICON = RAW / "lexicon_v0.csv"


def load_answers(wave: int) -> list[dict]:
    with (RAW / "prompts.csv").open(newline="") as f:
        category = {r["item_id"]: r["category"] for r in csv.DictReader(f)}
    rows = []
    for path in sorted((RAW / "responses" / f"w{wave}").glob("*/*.json")):
        text = json.loads(path.read_text())["normalized"].get("answer_text") or ""
        rows.append({"arm": path.parent.name, "item_id": path.stem, "wave": wave,
                     "category": category[path.stem], "answer_text": text,
                     "answer_sha256": hashlib.sha256(text.encode()).hexdigest()})
    return rows


def key(r: dict) -> str:
    return f"{r['arm']}|{r['item_id']}|{r['wave']}|{r['answer_sha256']}"


def load_cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    recs = (json.loads(line) for line in CACHE.read_text().splitlines() if line.strip())
    return {r["key"]: r for r in recs}


def fill_cache(rows: list[dict], env_file: str | None) -> None:
    cache = load_cache()
    todo = [r for r in rows if key(r) not in cache and r["answer_text"]]
    if not todo:
        print(f"brand candidates: all {len(rows)} answers cached")
        return
    from anthropic_client import DEFAULT_ENV_FILE, make_client

    client = make_client(env_file or DEFAULT_ENV_FILE)
    lock, spent = threading.Lock(), [0.0]

    def work(r):
        brands, usage = extract_brands(client, r["answer_text"], r["category"])
        cost = cost_from_usage(EXTRACT_MODEL, usage)["total"]
        rec = {"key": key(r), **{k: r[k] for k in ("arm", "item_id", "wave", "answer_sha256")},
               "model": EXTRACT_MODEL, "brands": brands, "usage": usage, "cost_usd": cost,
               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--lexicon", default=str(DEFAULT_LEXICON))
    ap.add_argument("--env-file", default=None)
    a = ap.parse_args()

    rows = load_answers(a.wave)
    fill_cache(rows, a.env_file)
    cache = load_cache()
    amap = lexicon_alias_map(Path(a.lexicon))
    by_pair, by_canon = lexicon_index(Path(a.lexicon))

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
        for name in cache.get(key(r), {}).get("brands", []):
            canon = canonical_brand(name)
            if canon in EXCLUDE:
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
    print(f"{out.name}: {len(names)} (category, brand) rows; v0 status {dict(st)}")
    print("answers with a candidate the lexicon has no alias for, per category:")
    for cat in sorted(per_cat):
        print(f"  {cat:32} {gap_answers[cat]:>3}/{per_cat[cat]}")


if __name__ == "__main__":
    main()
