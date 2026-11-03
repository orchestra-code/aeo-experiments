"""Stage 01: normalized responses -> data/interim/features.jsonl (spec §3).

One row per answer (prompt x arm x wave), waves 1 to 3 only:

- ``brands``: canonical brands in first-mention order, frozen lexicon, over
  ``normalized.answer_text``. The lexicon's sha256 is checked before anything else is read.
- ``brands_all``: ``brands`` plus every Haiku name the lexicon cannot place (R4); null where
  the cache has no record for this exact answer.
- ``cited_domains`` / ``evaluated_domains``: registered domains, first-seen order.
- ``searched``: whether the answer used search. ``n_searches`` where the record counts them;
  on ``sched_kit`` the transcript has no count, so this is its ``searched`` flag and
  ``n_searches`` stays null. The same goes for evaluated URLs on that arm. A printed answer the
  ingest could not join to a subagent has no flag: it counts as not searched, and
  ``search_unknown`` marks it for Audit A.
- ``run_ok``: the ledger's last record for this answer says it counts. A local run that
  failed the instrument audit (``collect_cc.audit``) still leaves a response file, so a file
  on disk is not enough. Rows with ``run_ok`` false stay in the frame for Audit A, and stage
  03 drops them.

The interim frame holds brand names and domains, so it stays under the gitignored
``data/interim/``. It holds no answer text and no query text.

``--synthetic {planted,planted_equiv,broken_join}`` builds the spec §8 step 3 dry-run worlds:
fake answers, ledgers, collector sheets, Haiku cache and lexicon are written to disk under
``data/interim/synthetic/<world>/raw`` in the real layout, then read back through the same
``build_frame`` and ``feature_row`` as real data.

- ``planted``: ``ui_default``, ``cc_stock_full`` and ``opus55_plain`` share one per-prompt
  profile, so their gaps are 0 by construction. ``sched_kit`` draws from a reshuffled profile
  in the same category (a large real gap, and a large H3). ``cc_none_search`` mixes the two
  and skips search on 40% of answers, above the Audit A limit.
- ``planted_equiv``: the same, except ``sched_kit`` shares the profile too, so both primary
  arms pass and the Holm 95% and 90% levels are both exercised on a passing arm.
- ``broken_join``: ``planted`` with every non-reference answer filed under another prompt,
  the join bug H_pos exists to catch, so 03_model must stop on H_pos.

Usage (repo root):
  uv run python experiments/011-claude-code-fidelity/pipeline/01_features.py
  uv run python .../01_features.py --synthetic planted
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from brands import frozen_lexicon, lexicon_extract, synthetic_lexicon, unplaced_names, with_unplaced
from common import (
    ALL_ARMS,
    ANCHOR,
    EVALUATED_ARMS,
    LOCAL_ARMS,
    REFERENCE,
    SCHEDULED,
    SEED,
    SURFACE,
    SYNTH_ANSWER_MARK,
    SYNTH_QUERY_MARK,
    SYNTHETIC_WORLDS,
    WAVES,
    Sources,
    features_path,
    last_by_answer,
    ledger_records,
    ordered_domains,
    sources,
    write_features,
)

ET = ZoneInfo("America/New_York")

#: Coding behavior flags, from the pilot (pipeline/pilot_report.py). A person reads whatever
#: these flag; Audit A reports the counts and nothing is excluded on them.
OFFER_RE = re.compile(
    r"(?i)\b(?:i can|i could|want me to|would you like me to|shall i|let me)\b[^.?!\n]{0,60}"
    r"\b(?:file|script|code|repo|repository|commit|directory)\b"
)
BUILD_RE = re.compile(r"(?i)\b(?:i (?:wrote|created|saved|edited)|your (?:codebase|repository))\b")

#: Ledger status that makes an answer count, per ledger.
OK_STATUS = {**{a: "ok" for a in LOCAL_ARMS}, ANCHOR: "collected"}


# ------------------------------------------------------------- loaders


def load_prompts(path: Path) -> dict[str, dict]:
    with path.open(newline="") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def load_notes(sheets_dir: Path) -> dict[tuple[str, str, int], bool]:
    """(arm, item_id, wave) -> the collector wrote a note on that sheet row (R6)."""
    out: dict[tuple[str, str, int], bool] = {}
    for wave in WAVES:
        path = sheets_dir / f"w{wave}.csv"
        if not path.exists():
            continue
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                out[(r["arm"], r["item_id"], wave)] = bool((r.get("notes") or "").strip())
    return out


def load_candidates(path: Path) -> dict[str, list[str]]:
    """Haiku candidate cache: key -> names.

    Study records are keyed ``arm|item_id|wave|answer_sha256``. The pilot's records hold a bare
    hash key and a ``names`` list; they can never match a study key and are harmless here.
    """
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            names = rec.get("brands")
            out[rec["key"]] = rec.get("names", []) if names is None else names
    return out


# ------------------------------------------------------------- features


def run_date_of(resp: dict, led: dict | None) -> str:
    if led and led.get("run_date"):
        return str(led["run_date"])
    if resp.get("run_date"):
        return str(resp["run_date"])
    stamp = (led or {}).get("started") or (resp.get("normalized") or {}).get("created_at")
    if stamp:
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ET).date().isoformat()
        except ValueError:
            return str(stamp)[:10]
    return ""


def search_fields(arm: str, n: dict) -> tuple[int | None, bool, bool]:
    """(n_searches, searched, search_unknown).

    Only ``sched_kit`` may lack a count. Its flag can be missing too, when a printed answer has
    no subagent result to join to; R7 and Audit A then treat that answer as not searched.
    """
    count = n.get("n_searches")
    if count is not None:
        return int(count), int(count) > 0, False
    if arm != SCHEDULED:
        raise ValueError(f"{arm}: record has no n_searches")
    if isinstance(n.get("searched"), bool):
        return None, n["searched"], False
    return None, False, True


def asks_back(text: str, brand_list: list[str]) -> bool:
    """A reply that only asks a question: no brands, and its last line is a question."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return bool(lines) and not brand_list and lines[-1].rstrip(" *_").endswith("?")


def window(led: dict | None, edge: str, name: str) -> float | None:
    marks = (led or {}).get("rate_limits") or {}
    return (marks.get(edge) or {}).get(name)


def feature_row(resp: dict, prompt: dict, patterns: dict, candidates: dict[str, list[str]],
                ledger: dict, notes: dict, *, synthetic: int = 0) -> dict:
    """The spec §3 row for one normalized response (real or synthetic)."""
    n = resp["normalized"]
    arm, item, wave = resp["arm"], resp["item_id"], int(resp["wave"])
    category = prompt["category"]
    text = n.get("answer_text") or ""
    sha = hashlib.sha256(text.encode()).hexdigest()
    cited_urls = n.get("cited_urls") or []
    eval_urls = n.get("evaluated_urls") or []
    cat_patterns = patterns.get(category, [])
    brand_list = lexicon_extract(text, cat_patterns)

    raw_names = candidates.get(f"{arm}|{item}|{wave}|{sha}")
    led = ledger.get((arm, item, wave))
    n_searches, searched, search_unknown = search_fields(arm, n)
    cited = ordered_domains(cited_urls)
    ok_status = OK_STATUS.get(arm)
    cost = None
    if led:
        cost = led.get("cost_usd") if arm == ANCHOR else led.get("total_cost_usd")
    if cost is None:
        cost = n.get("total_cost_usd")
    return {
        "item_id": item,
        "category": category,
        "intent": prompt["intent"],
        "arm": arm,
        "surface": SURFACE.get(arm, "unknown"),
        "wave": wave,
        "run_date": run_date_of(resp, led),
        "model": n.get("model"),
        "resolved_model": n.get("resolved_model"),
        "claude_code_version": n.get("claude_code_version")
        or (n.get("init") or {}).get("claude_code_version"),
        "answer_sha256": sha,
        "chars": len(text),
        "empty_answer": not text.strip(),
        "asks_back": asks_back(text, brand_list),
        "coding_flag": bool(OFFER_RE.search(text) or BUILD_RE.search(text)),
        "stop_reason": n.get("stop_reason"),
        "brands": brand_list,
        "n_brands": len(brand_list),
        "brands_all": None if raw_names is None else with_unplaced(brand_list, raw_names, cat_patterns),
        "n_unplaced": None if raw_names is None else len(unplaced_names(raw_names, cat_patterns)),
        "n_links": len(cited_urls),
        "cited_urls_source": n.get("cited_urls_source") or "citations",
        "cited_domains": cited,
        "n_cited_domains": len(cited),
        "evaluated_domains": ordered_domains(eval_urls),
        "n_evaluated": len(eval_urls) if arm in EVALUATED_ARMS else None,
        "n_searches": n_searches,
        "searched": searched,
        "search_unknown": search_unknown,
        "fetched": n.get("fetched"),
        "n_fetches": n.get("n_fetches"),
        "n_backend_searches": n.get("n_backend_searches"),
        "subagent_tool_uses": n.get("subagent_tool_uses"),
        "subagent_ms": n.get("subagent_ms"),
        "report_match": n.get("report_match"),
        "instruction_exact": n.get("instruction_exact"),
        "clarifying_questions": bool(n.get("clarifying_questions")),
        "collector_notes": bool(notes.get((arm, item, wave), False)),
        "n_warnings": len(n.get("warnings") or []),
        "ledger_status": led.get("status") if led else None,
        "run_ok": ok_status is None or bool(led and led.get("status") == ok_status),
        "cost_usd": float(cost) if cost is not None else None,
        "duration_ms": (led or {}).get("duration_ms", n.get("duration_ms")),
        "started": (led or {}).get("started"),
        "five_hour_first": window(led, "first", "five_hour"),
        "five_hour_last": window(led, "last", "five_hour"),
        "seven_day_first": window(led, "first", "seven_day"),
        "seven_day_last": window(led, "last", "seven_day"),
        "synthetic": synthetic,
    }


def build_frame(src: Sources, patterns: dict, *, synthetic: int = 0) -> pd.DataFrame:
    """Every study answer on disk, waves 1 to 3, this study's arms only."""
    prompts = load_prompts(src.prompts)
    ledger = last_by_answer(ledger_records(src))
    notes = load_notes(src.ui_sheets)
    candidates = load_candidates(src.candidates)
    rows = []
    for wave in WAVES:
        for arm in ALL_ARMS:
            for path in sorted((src.responses / f"w{wave}" / arm).glob("*.json")):
                resp = json.loads(path.read_text())
                resp |= {"arm": arm, "item_id": path.stem, "wave": wave}
                rows.append(feature_row(resp, prompts[path.stem], patterns, candidates, ledger,
                                        notes, synthetic=synthetic))
    return pd.DataFrame(rows)


def build_real() -> tuple[pd.DataFrame, list[str]]:
    patterns, sha = frozen_lexicon()  # refuses before any answer is read
    return build_frame(sources(), patterns), [f"lexicon sha256 {sha} (verified)"]


# ------------------------------------------------------------- synthetic

N_CATEGORIES = 20
BRANDS_PER_CATEGORY = 14
DOMAINS_PER_CATEGORY = 16
SHARED_PUBLISHERS = 12
N_PROMPTS = 2 * N_CATEGORIES

#: Arm behavior: which profile, and the share of answers that skip search.
SYNTH_ARMS = {
    "ui_default": ("same", 0.10),
    "cc_stock_full": ("same", 0.0),
    "sched_kit": ("divergent", 0.0),
    "cc_none_search": ("mix", 0.40),
    "opus55_plain": ("same", 0.0),
}
#: The answers dry-run bookkeeping is planted on: one local run that ended on a failed audit,
#: one local run retried after a failure, one API task that never collected (no answer file).
FAILED_RUN = ("cc_stock_full", "b2b_05", 2)
RETRIED_RUN = ("cc_stock_full", "b2b_06", 1)
FAILED_TASK = ("opus55_plain", "b2b_07", 3)
#: ``sched_kit`` transcript facts: two subagents that skipped search, one printed answer with no
#: subagent to join to, one retyped copy that differs, one instruction that differs.
SCHED_NO_SEARCH = {("b2b_09", 1), ("b2b_10", 2)}
SCHED_NO_JOIN = ("b2b_11", 3)
SCHED_COPY_DIFFERS = ("b2b_12", 1)
SCHED_INSTRUCTION_DIFFERS = ("b2b_13", 2)


def synth_prompts() -> dict[str, dict]:
    prompts = {}
    for i in range(1, N_PROMPTS + 1):
        c = (i - 1) // 2 + 1
        prompts[f"b2b_{i:02d}"] = {"item_id": f"b2b_{i:02d}", "category": f"category {c:02d}",
                                   "intent": "shortlist" if i % 2 else "evaluate",
                                   "text": f"synthetic prompt {i}"}
    return prompts


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def write_lexicon(path: Path) -> None:
    """Invented brand tokens (``Zq0307`` = category 3, brand 7), one drop row per category and
    one case-sensitive row, so the dry run needs no real data and leaks none."""
    rows = []
    for c in range(1, N_CATEGORIES + 1):
        cat = f"category {c:02d}"
        for k in range(1, BRANDS_PER_CATEGORY + 1):
            name = f"Zq{c:02d}{k:02d}"
            rows.append({"canonical": name.lower(), "aliases": f"{name}|{name} Cloud" if k == 1 else name,
                         "category": cat, "decision": "keep", "reason": "in category",
                         "match": "cs" if k == 2 else "ci", "n_answers": 0})
        rows.append({"canonical": f"ledgerx{c:02d}", "aliases": f"LedgerX{c:02d}", "category": cat,
                     "decision": "drop", "reason": "out of category", "match": "ci", "n_answers": 0})
    write_csv(path, rows)


def synth_profiles(rng: np.random.Generator) -> dict:
    """Per prompt: inclusion probabilities over the category's brands and domains.

    The divergent profile puts the same probabilities on a reshuffled order, so a divergent
    arm names as many brands but largely different ones.
    """
    levels = np.array([0.95, 0.92, 0.9, 0.85, 0.8, 0.6, 0.35, 0.15, 0.08, 0.05, 0.03, 0.02,
                       0.02, 0.01])
    dom_levels = np.array([0.9, 0.85, 0.8, 0.7, 0.55, 0.4, 0.25, 0.15, 0.1, 0.05, 0.05, 0.03,
                           0.02, 0.02, 0.01, 0.01])
    out = {}
    for i in range(1, N_PROMPTS + 1):
        brand_p, dom_p = rng.permutation(levels), rng.permutation(dom_levels)
        out[f"b2b_{i:02d}"] = {"brands": brand_p, "brands_div": rng.permutation(brand_p),
                               "domains": dom_p, "domains_div": rng.permutation(dom_p)}
    return out


def synth_answer(c: int, brand_idx: list[int], arm: str, rng: np.random.Generator) -> str:
    lines = [f"Here is a shortlist. {SYNTH_ANSWER_MARK}"]
    for k in brand_idx:
        name = f"Zq{c:02d}{k + 1:02d}"
        if k == 0 and rng.random() < 0.5:
            name += " Cloud"
        lines.append(f"- **{name}**: a fit for teams like yours ([site](https://{name.lower().replace(' ', '')}.com/x)).")
    lines.append(f"It also syncs with LedgerX{c:02d}, your accounting system.")
    if SURFACE[arm] in ("local", "scheduled"):
        # A sources block naming a brand that is not in the answer: strip_sources must drop it.
        lines += ["", "Sources:", f"- [Zq{c:02d}14 blog](https://zq{c:02d}14.com/blog)", "- [a review site](https://pub01.org/r)"]
    return "\n".join(lines)


def synth_normalized(arm: str, item: str, wave: int, c: int, text: str, cited: list[str],
                     evaluated: list[str], searched: bool, rng: np.random.Generator) -> dict:
    """A record shaped like the arm's real parser output (claude_answers, ingest_routine)."""
    base = {"answer_text": text, "cited_urls": cited, "warnings": []}
    queries = [f"best category {c} tools {SYNTH_QUERY_MARK}", "pricing comparison"] if searched else []
    n_searches = int(rng.integers(1, 4)) if searched else 0
    if arm == SCHEDULED:
        record = base | {"cited_urls_source": "answer_links", "evaluated_urls": [],
                         "search_queries": [], "n_searches": None,
                         "source": "claude_code_scheduled_task", "report_match": None}
        if (item, wave) == SCHED_NO_JOIN:
            return record
        searched = (item, wave) not in SCHED_NO_SEARCH
        return record | {
            "searched": searched, "fetched": bool(searched and rng.random() < 0.5),
            "instruction_exact": (item, wave) != SCHED_INSTRUCTION_DIFFERS,
            "report_match": (item, wave) != SCHED_COPY_DIFFERS,
            "subagent_tool_uses": int(rng.integers(1, 9)) if searched else 0,
            "subagent_ms": int(rng.integers(30_000, 90_000)),
            "subagent_tokens": int(rng.integers(10_000, 40_000)),
            "resolved_model": "claude-opus-5-5",
        }
    if arm == REFERENCE:
        return base | {"cited_urls_source": "citations", "evaluated_urls": evaluated,
                       "search_queries": queries, "n_searches": len(queries),
                       "stop_reason": None, "model": "claude-opus-5-5",
                       "source": "claude_ai_export", "created_at": f"2026-11-{2 * wave + 3:02d}T15:00:00Z"}
    if arm == ANCHOR:
        return base | {"evaluated_urls": evaluated, "search_queries": queries,
                       "n_searches": n_searches, "fetched_urls": [], "n_fetches": 0,
                       "stop_reason": "end_turn", "model": "claude-opus-5-5", "source": "api"}
    return base | {
        "cited_urls_source": "answer_links", "evaluated_urls": evaluated, "fetched_urls": [],
        "search_queries": queries, "n_searches": n_searches,
        "n_fetches": int(rng.integers(0, 3)) if searched and arm == "cc_stock_full" else 0,
        "n_backend_searches": n_searches * 2, "stop_reason": "end_turn",
        "model": "claude-opus-5-5", "main_models": ["claude-opus-5-5"], "source": "claude_code",
        "init": {"apiKeySource": "none", "tools": ["WebSearch"], "mcp_servers": [],
                 "model": "claude-opus-5-5", "claude_code_version": "2.1.316"},
    }


def filing_map(prompts: dict, rng: np.random.Generator) -> dict[str, str]:
    """A permutation of the prompts with no fixed point, for the broken join."""
    items = list(prompts)
    while True:
        shuffled = [str(x) for x in rng.permutation(items)]
        if all(a != b for a, b in zip(items, shuffled)):
            return dict(zip(items, shuffled))


def write_world(world: str) -> Sources:
    """Write one fake world to disk in the real layout."""
    rng = np.random.default_rng(SEED)
    src = sources(world)
    shutil.rmtree(src.raw, ignore_errors=True)
    src.raw.mkdir(parents=True)
    prompts = synth_prompts()
    write_csv(src.prompts, list(prompts.values()))
    write_lexicon(src.raw / "lexicon_synthetic.csv")
    profiles = synth_profiles(rng)
    publishers = [f"https://pub{j:02d}.org/review" for j in range(1, SHARED_PUBLISHERS + 1)]
    arms = dict(SYNTH_ARMS)
    if world == "planted_equiv":
        arms["sched_kit"] = ("same", 0.0)

    cc_ledger, anchor_ledger, candidates = [], [], []
    for wave in WAVES:
        sheet_rows = []
        used = {"five_hour": 0.05, "seven_day": 0.20, "clock": 0}
        for arm, (profile, no_search) in arms.items():
            filed_as = filing_map(prompts, rng) if world == "broken_join" and arm != REFERENCE else {}
            for item, prompt in prompts.items():
                c = int(prompt["category"].split()[-1])
                prof = profiles[item]
                use_div = profile == "divergent" or (profile == "mix" and rng.random() < 0.5)
                bp = prof["brands_div"] if use_div else prof["brands"]
                dp = prof["domains_div"] if use_div else prof["domains"]
                order = [int(k) for k in rng.permutation(
                    [k for k in range(BRANDS_PER_CATEGORY) if rng.random() < bp[k]])]
                searched = bool(rng.random() >= no_search)
                cited = [f"https://www.d{c:02d}x{k + 1:02d}.com/page?utm_source=x"
                         for k in range(DOMAINS_PER_CATEGORY) if rng.random() < dp[k]]
                evaluated = []
                if searched:
                    cited += [p for p in publishers if rng.random() < 0.08]
                    evaluated = cited + [p for p in publishers if rng.random() < 0.3]
                else:
                    cited = []
                text = synth_answer(c, order, arm, rng)
                filed = filed_as.get(item, item)
                norm = synth_normalized(arm, item, wave, c, text, cited, evaluated, searched, rng)
                if arm == REFERENCE and item == "b2b_28":
                    norm["clarifying_questions"] = True

                key = (arm, filed, wave)
                if key != FAILED_TASK:
                    out = src.responses / f"w{wave}" / arm / f"{filed}.json"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(json.dumps({"source": norm["source"], "arm": arm, "item_id": filed,
                                               "wave": wave, "normalized": norm}))
                    sha = hashlib.sha256(text.encode()).hexdigest()
                    names = [f"Zq{c:02d}{k + 1:02d}" for k in order]
                    if rng.random() < 0.5:
                        names.append(f"Unlisted{c:02d}{int(rng.integers(1, 6))}")
                    candidates.append({"key": f"{arm}|{filed}|{wave}|{sha}", "arm": arm, "item_id": filed,
                                       "wave": wave, "answer_sha256": sha, "brands": names, "names": names})

                if arm in LOCAL_ARMS:
                    used["clock"] += 1
                    first = {k: round(used[k], 2) for k in ("five_hour", "seven_day")}
                    used["five_hour"] += 0.0035
                    used["seven_day"] += 0.00025
                    last = {k: round(used[k], 2) for k in ("five_hour", "seven_day")}
                    tick = used["clock"]
                    rec = {"wave": wave, "arm": arm, "item_id": filed, "status": "ok", "problems": [],
                           "started": f"2026-11-{2 * wave + 3:02d}T14:{tick // 60:02d}:{tick % 60:02d}+00:00",
                           "total_cost_usd": float(rng.uniform(0.2, 0.5)),
                           "duration_ms": int(rng.integers(40_000, 120_000)),
                           "rate_limits": {"first": first, "last": last}}
                    if key == RETRIED_RUN:
                        cc_ledger.append(rec | {"status": "failed", "problems": ["exit_1"]})
                    if key == FAILED_RUN:
                        rec |= {"status": "failed", "problems": ["tools=['WebSearch', 'Bash']"]}
                    cc_ledger.append(rec)
                elif arm == ANCHOR:
                    base = {"task_id": f"{arm}|{filed}|{wave}", "wave": wave, "arm": arm, "item_id": filed,
                            "run_date": f"2026-11-{2 * wave + 3:02d}"}
                    anchor_ledger.append(base | {"status": "submitted"})
                    if key == FAILED_TASK:
                        anchor_ledger.append(base | {"status": "failed", "error": "expired"})
                    else:
                        anchor_ledger.append(base | {"status": "collected",
                                                     "cost_usd": float(rng.uniform(0.06, 0.09))})
                elif arm == REFERENCE:
                    note = "asked a clarifying question" if item in ("b2b_28", "b2b_36") else ""
                    sheet_rows.append({"arm": arm, "item_id": filed, "notes": note})
        write_csv(src.ui_sheets / f"w{wave}.csv", sheet_rows)

    for path, recs in ((src.ledger_cc, cc_ledger), (src.ledger_anchor, anchor_ledger),
                       (src.candidates, candidates)):
        path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return src


def build_synthetic(world: str) -> tuple[pd.DataFrame, list[str]]:
    src = write_world(world)
    patterns, _sha = synthetic_lexicon(src.raw / "lexicon_synthetic.csv")
    return (build_frame(src, patterns, synthetic=1),
            [f"SYNTHETIC world '{world}' (fake lexicon, no real data)"])


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    a = ap.parse_args()

    df, notes = build_synthetic(a.synthetic) if a.synthetic else build_real()
    if df.empty:
        raise SystemExit("no responses found")
    path = features_path(a.synthetic)
    write_features(df, path)

    tag = f"SYNTHETIC/{a.synthetic} " if a.synthetic else ""
    print(f"wrote {len(df)} {tag}answers -> {path}")
    for line in notes:
        print(f"  {line}")
    counts = df.groupby(["arm", "wave"]).size().unstack(fill_value=0)
    print(counts.reindex([x for x in ALL_ARMS if x in counts.index]).to_string())
    print(f"answers that do not count (run_ok false): {int((~df['run_ok']).sum())}")
    print(f"answers without Haiku candidates (R4): {int(df['brands_all'].isna().sum())}")


if __name__ == "__main__":
    main()
