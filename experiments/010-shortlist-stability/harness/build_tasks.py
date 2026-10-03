"""Experiment 010: the exploration split and the judge's task list (sketch.md).

Two outputs:

- ``split.csv`` (committed; ids only): every prompt of the three datasets with
  its split, ``explore`` or ``holdout``. Seeded and deterministic, so it can be
  regenerated and checked at any time.
- ``data/raw/tasks_<split>.jsonl`` (gitignored: it holds prompts and answers):
  one judge task per answer, with the question, the answer text, and the
  lexicon brands the source study's frozen matcher finds in it, in first-
  mention order. Those brands become the judge's ``trackedPresent``.

Sources, read in place from the source experiments' gitignored raw data:

- ``chatgpt_consumer`` / ``chatgpt_agency``: 002, 003 and 005 (``hum`` and
  ``coffee`` prompts; identical texts across the three studies). Answer =
  the DataForSEO ``markdown`` field. Brands = 005's lexicon, which is
  identical to 002's and 003's (checked 2026-10-03).
- ``claude_b2b``: 009 arms ``ui_default``, ``ui_think``, ``opus55_plain``.
  Answer = ``normalized.answer_text`` (first reply only when claude.ai asked
  clarifying questions, 009 deviation 1). Brands = 009's frozen lexicon v2.1,
  hash-checked by 009's own loader.

Building holdout tasks needs ``--allow-holdout``: the holdout stays
unclassified until a confirmatory spec is frozen.

``--rejudge N`` writes ``tasks_<split>_rejudge.jsonl``: a seeded sample of N
of the split's tasks, judged a second time to measure the judge's own
test-retest agreement on identical text (the instrument's noise floor).

Usage:
  uv run python experiments/010-shortlist-stability/harness/build_tasks.py
  uv run python .../build_tasks.py --rejudge 200
  uv run python .../build_tasks.py --check   # verify split.csv, write nothing
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
EXPERIMENTS = EXP.parent
RAW = EXP / "data" / "raw"
SPLIT_CSV = EXP / "split.csv"

SEED = "20261003"
SRC_002 = EXPERIMENTS / "002-prompt-consistency"
SRC_003 = EXPERIMENTS / "003-synthetic-prompt-coverage"
SRC_005 = EXPERIMENTS / "005-subintent-matched-panels"
SRC_009 = EXPERIMENTS / "009-claude-model-fidelity"

#: dataset -> (source arm/intent, number of exploration units)
CHATGPT = {
    "chatgpt_consumer": ("headphones", 48),
    "chatgpt_agency": ("coffee", 13),
}
CLAUDE_ARMS = ("ui_default", "ui_think", "opus55_plain")
CLAUDE_EXPLORE_CATEGORIES = 7


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def rank_key(unit: str) -> str:
    return hashlib.sha256(f"{SEED}:{unit}".encode()).hexdigest()


def pick(units: list[str], n: int) -> set[str]:
    return set(sorted(units, key=rank_key)[:n])


def same_prompt(sent: str, text: str) -> bool:
    """DataForSEO decodes "+" in a keyword as a space (seen on 3 agency prompts
    in 002 to 005; spec deviation 1), so that one substitution is allowed."""
    sent, text = sent.strip(), text.strip()
    return sent == text or sent == text.replace("+", " ")


def read_csv(path: Path) -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ split


def build_split() -> list[dict]:
    rows = []
    prompts = read_csv(SRC_002 / "data/raw/prompts.csv")
    for dataset, (intent, n) in CHATGPT.items():
        items = [p["item_id"] for p in prompts if p["intent"] == intent]
        if intent == "coffee":
            # Only the 40 agency prompts 003 and 005 re-ran have repeat runs.
            rerun = {p["item_id"] for p in read_csv(SRC_003 / "data/raw/prompts.csv")
                     if p["arm"] == "coffee"}
            items = [i for i in items if i in rerun]
        chosen = pick(items, n)
        rows += [{"dataset": dataset, "unit": i, "item_id": i,
                  "split": "explore" if i in chosen else "holdout"} for i in sorted(items)]

    claude = read_csv(SRC_009 / "data/raw/prompts.csv")
    cats = sorted({p["category"] for p in claude})
    chosen = pick(cats, CLAUDE_EXPLORE_CATEGORIES)
    rows += [{"dataset": "claude_b2b", "unit": p["category"], "item_id": p["item_id"],
              "split": "explore" if p["category"] in chosen else "holdout"}
             for p in sorted(claude, key=lambda p: p["item_id"])]
    return rows


def write_split(rows: list[dict]) -> None:
    with SPLIT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "unit", "item_id", "split"])
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ tasks


def chatgpt_tasks(split: dict[tuple[str, str], str], wanted: set[str]) -> list[dict]:
    brands = _load(SRC_005 / "pipeline/brands.py", "exp005_brands")
    texts = {p["item_id"]: p["text"] for p in read_csv(SRC_002 / "data/raw/prompts.csv")}
    out = []
    for src, exp in ((SRC_002, "002"), (SRC_003, "003"), (SRC_005, "005")):
        for r in read_csv(src / "data/interim/responses.csv"):
            intent = r["intent"]
            arm = r.get("arm") or ("hum" if intent == "headphones" else "coffee")
            if arm not in ("hum", "coffee"):
                continue
            dataset = "chatgpt_consumer" if intent == "headphones" else "chatgpt_agency"
            s = split.get((dataset, r["item_id"]))
            if s not in wanted:
                continue
            wave = int(r["wave"])
            raw = json.loads((src / "data/raw/responses" / f"w{wave}" /
                              f"{r['task_id']}.json").read_text())
            answer = raw.get("markdown") or ""
            if not same_prompt(raw.get("keyword", ""), texts[r["item_id"]]):
                raise SystemExit(f"prompt mismatch: {exp} {r['task_id']}")
            found = brands.extract_brands(answer, intent)
            lex = brands.LEXICONS[intent]
            out.append({
                "task_id": f"{dataset}|{exp}|{arm}|{r['item_id']}|w{wave}",
                "dataset": dataset, "source_exp": exp, "arm": "chatgpt",
                "item_id": r["item_id"], "category": intent, "split": s,
                "wave": wave, "run_date": r["run_date"], "platform": "openai",
                "question": texts[r["item_id"]], "answer": answer,
                "brands": found,
                "tracked": [{"canonical": b, "aliases": lex[b]} for b in found],
            })
    return out


def claude_tasks(split: dict[tuple[str, str], str], wanted: set[str]) -> list[dict]:
    sys.path.insert(0, str(SRC_009 / "pipeline"))
    b9 = _load(SRC_009 / "pipeline/brands.py", "exp009_brands")
    patterns, _alias_map, _sha = b9.frozen_lexicon()
    rows_by_cat = b9.lexicon_categories(b9.LEXICON)
    aliases = {}
    for cat, rows in rows_by_cat.items():
        for row in rows:
            if row["decision"] == "keep":
                aliases.setdefault((cat, row["canonical"]), set()).update(
                    a.strip() for a in row["aliases"].split("|") if a.strip())
    prompts = {p["item_id"]: p for p in read_csv(SRC_009 / "data/raw/prompts.csv")}
    out = []
    for wave in (1, 2, 3):
        for arm in CLAUDE_ARMS:
            for path in sorted((SRC_009 / "data/raw/responses" / f"w{wave}" / arm).glob("*.json")):
                item = path.stem
                s = split.get(("claude_b2b", item))
                if s not in wanted:
                    continue
                resp = json.loads(path.read_text())
                p = prompts[item]
                answer = (resp.get("normalized") or {}).get("answer_text") or ""
                found = b9.lexicon_extract(answer, patterns.get(p["category"], []))
                out.append({
                    "task_id": f"claude_b2b|009|{arm}|{item}|w{wave}",
                    "dataset": "claude_b2b", "source_exp": "009", "arm": arm,
                    "item_id": item, "category": p["category"], "split": s,
                    "wave": wave, "run_date": None, "platform": "claude",
                    "question": p["text"], "answer": answer,
                    "brands": found,
                    "tracked": [{"canonical": b,
                                 "aliases": sorted(aliases.get((p["category"], b), set()))}
                                for b in found],
                })
    return out


COLLECTION_PLATFORMS = ("chatgpt", "gemini", "claude")
CLAUDE_COLLECTION_ARM = "opus55_plain"


def collection_tasks(tag: str) -> list[dict]:
    """Judge tasks for 010's own B2B collection: ChatGPT and Gemini (DataForSEO),
    Claude (Anthropic API, 009's collector, arm ``opus55_plain``).

    One ledger and one response tree per platform: ``ledger_<tag>_<platform>.jsonl``
    and ``responses_<tag>_<platform>/w<wave>/<task_id>.json`` (Claude:
    ``w<wave>/opus55_plain/<item_id>.json``). Brands = 009's
    frozen lexicon over the prompt's category rows (the lexicon protocol in
    spec.md extends it before any confirmatory metric).
    """
    sys.path.insert(0, str(SRC_009 / "pipeline"))
    b9 = _load(SRC_009 / "pipeline/brands.py", "exp009_brands")
    patterns, _alias_map, _sha = b9.frozen_lexicon()
    aliases = {}
    for cat, rows in b9.lexicon_categories(b9.LEXICON).items():
        for row in rows:
            if row["decision"] == "keep":
                aliases.setdefault((cat, row["canonical"]), set()).update(
                    a.strip() for a in row["aliases"].split("|") if a.strip())
    prompts = {p["item_id"]: p for p in read_csv(RAW / "prompts_b2b.csv")}
    out = []
    for platform in COLLECTION_PLATFORMS:
        ledger = RAW / f"ledger_{tag}_{platform}.jsonl"
        if not ledger.exists():
            continue
        recs = {}
        for line in ledger.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                recs.setdefault(r["task_id"], {}).update(r)
        for tid, r in sorted(recs.items()):
            if r.get("status") != "collected":
                continue
            p = prompts[r["item_id"]]
            if platform == "claude":
                path = (RAW / f"responses_{tag}_{platform}" / f"w{r['wave']}"
                        / CLAUDE_COLLECTION_ARM / f"{r['item_id']}.json")
                resp = json.loads(path.read_text())
                if r.get("keyword_sha256") != hashlib.sha256(p["text"].encode()).hexdigest():
                    raise SystemExit(f"prompt mismatch: {platform} {tid}")
                answer = (resp.get("normalized") or {}).get("answer_text") or ""
                run_date = r.get("run_date") or (r.get("submitted_at") or "")[:10]
                model = (resp.get("normalized") or {}).get("model")
            else:
                path = RAW / f"responses_{tag}_{platform}" / f"w{r['wave']}" / f"{tid}.json"
                if not path.exists():
                    continue
                resp = json.loads(path.read_text())
                if not same_prompt(resp.get("keyword") or "", p["text"]):
                    raise SystemExit(f"prompt mismatch: {platform} {tid}")
                answer = resp.get("markdown") or ""
                run_date = (resp.get("datetime") or "")[:10]
                model = resp.get("model")
            found = b9.lexicon_extract(answer, patterns.get(p["category"], []))
            dataset = "claude_api_b2b" if platform == "claude" else f"{platform}_b2b"
            out.append({
                "task_id": f"{dataset}|010|{platform}|{r['item_id']}|w{r['wave']}",
                "dataset": dataset, "source_exp": "010", "arm": platform,
                "item_id": r["item_id"], "category": p["category"], "split": tag,
                "wave": int(r["wave"]), "run_date": run_date, "model": model,
                "platform": {"chatgpt": "openai"}.get(platform, platform),
                "question": p["text"], "answer": answer, "brands": found,
                "tracked": [{"canonical": b,
                             "aliases": sorted(aliases.get((p["category"], b), set()))}
                            for b in found],
            })
    return out


def claude_run_dates() -> dict[tuple[str, str, int], str]:
    """(arm, item, wave) -> run_date from 009's interim features."""
    out = {}
    with (SRC_009 / "data/interim/features.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            out[(r["arm"], r["item_id"], int(r["wave"]))] = r["run_date"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["explore", "holdout", "all"], default="explore")
    ap.add_argument("--allow-holdout", action="store_true")
    ap.add_argument("--check", action="store_true", help="verify split.csv only")
    ap.add_argument("--collection", default=None, metavar="TAG",
                    help="build tasks for 010's own collection (smoke | main) instead")
    ap.add_argument("--rejudge", type=int, default=0,
                    help="also write a seeded sample of N exploration tasks to re-judge")
    args = ap.parse_args()

    rows = build_split()
    if SPLIT_CSV.exists():
        committed = read_csv(SPLIT_CSV)
        if committed != [{k: str(v) for k, v in r.items()} for r in rows]:
            raise SystemExit("split.csv differs from the seeded split; refusing")
    elif args.check:
        raise SystemExit("split.csv missing")
    else:
        write_split(rows)
    if args.check:
        print("split.csv matches the seeded split")
        return
    if args.collection:
        tasks = collection_tasks(args.collection)
        out = RAW / f"tasks_b2b_{args.collection}.jsonl"
        with out.open("w") as f:
            for t in tasks:
                f.write(json.dumps(t) + "\n")
        print(f"wrote {len(tasks)} tasks to {out.relative_to(EXP)}")
        return

    if args.split != "explore" and not args.allow_holdout:
        raise SystemExit("holdout tasks need --allow-holdout (freeze the spec first)")
    wanted = {"explore", "holdout"} if args.split == "all" else {args.split}
    split = {(r["dataset"], r["item_id"]): r["split"] for r in rows}

    tasks = chatgpt_tasks(split, wanted) + claude_tasks(split, wanted)
    dates = claude_run_dates()
    for t in tasks:
        if t["dataset"] == "claude_b2b":
            t["run_date"] = dates[(t["arm"], t["item_id"], t["wave"])]
    ids = [t["task_id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate task ids")

    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / f"tasks_{args.split}.jsonl"
    with out.open("w") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")
    if args.rejudge:
        sample = sorted(tasks, key=lambda t: rank_key("rejudge:" + t["task_id"]))[:args.rejudge]
        with (RAW / f"tasks_{args.split}_rejudge.jsonl").open("w") as f:
            for t in sample:
                f.write(json.dumps(t) + "\n")
        print(f"wrote {len(sample)} re-judge tasks")
    by = {}
    for t in tasks:
        by[t["dataset"]] = by.get(t["dataset"], 0) + 1
    print(f"wrote {len(tasks)} tasks to {out.relative_to(EXP)}: {by}")


if __name__ == "__main__":
    main()
