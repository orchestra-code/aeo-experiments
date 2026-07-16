#!/usr/bin/env python3
"""Submit and collect DataForSEO LLM-scraper tasks against a JSONL ledger.

Subcommands:
    submit   Post one wave of prompts (idempotent — already-submitted
             (intent, item_id, wave) triples are skipped, so re-running after
             a partial failure or to retry failed tasks is safe).
    collect  Poll pending task ids via task_get and write raw response JSON
             (one file per task). Re-run until `status` shows zero pending.
    status   Ledger summary: counts by status/wave, accumulated cost.

The prompts CSV must have columns: item_id, intent, text.

Never uses tasks_ready (shared with the Spyglasses production poller) — see
aeo_research.dataforseo module docs.

Usage:
    uv run python scripts/llm_scraper.py submit \
        --prompts experiments/002-prompt-consistency/data/raw/prompts.csv \
        --intent headphones --wave 1 \
        --ledger experiments/002-prompt-consistency/data/raw/ledger.jsonl \
        --env-file ../spyglasses/.env.local
    uv run python scripts/llm_scraper.py collect \
        --ledger experiments/002-prompt-consistency/data/raw/ledger.jsonl \
        --out-dir experiments/002-prompt-consistency/data/raw/responses \
        --env-file ../spyglasses/.env.local --wait 60
    uv run python scripts/llm_scraper.py status --ledger .../ledger.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from aeo_research.dataforseo import (
    Ledger,
    TaskSpec,
    get_task,
    ledger_stats,
    load_api_key,
    post_tasks,
)

DEFAULT_MAX_TOTAL_TASKS = 1500  # ~ $3.60 at the $0.0024 priority rate
STALE_AFTER = timedelta(hours=48)
POLL_SLEEP_S = 0.3


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def cmd_submit(a: argparse.Namespace) -> None:
    ledger = Ledger(a.ledger)
    prompts = pd.read_csv(a.prompts)
    missing = {"item_id", "intent", "text"} - set(prompts.columns)
    if missing:
        raise SystemExit(f"prompts CSV missing columns: {sorted(missing)}")

    rows = prompts[prompts["intent"] == a.intent]
    if rows.empty:
        raise SystemExit(f"no prompts with intent={a.intent!r} in {a.prompts}")
    if a.limit:
        rows = rows.head(a.limit)

    done = ledger.submitted_keys()
    todo = rows[[ (a.intent, r.item_id, a.wave) not in done for r in rows.itertuples() ]]
    skipped = len(rows) - len(todo)

    total_after = ledger_stats(ledger).total + len(todo)
    if total_after > a.max_total_tasks and not a.force:
        raise SystemExit(
            f"cost cap: ledger would grow to {total_after} tasks "
            f"(cap {a.max_total_tasks}). Pass --force to override."
        )

    tag = a.tag or f"{a.tag_prefix}-w{a.wave}"
    print(f"wave {a.wave} intent={a.intent}: {len(todo)} to submit, {skipped} already done, tag={tag}")
    if a.dry_run or todo.empty:
        if a.dry_run:
            print("dry run — nothing submitted")
        return

    api_key = load_api_key(a.env_file)
    specs = [
        TaskSpec(keyword=r.text, tag=tag, priority=a.priority) for r in todo.itertuples()
    ]
    submitted = post_tasks(api_key, specs)

    accepted = rejected = 0
    for row, sub in zip(todo.itertuples(), submitted):
        if sub.accepted:
            accepted += 1
            ledger.append(
                {
                    "task_id": sub.task_id,
                    "tag": tag,
                    "wave": a.wave,
                    "item_id": row.item_id,
                    "intent": a.intent,
                    "keyword_sha256": sha256(row.text),
                    "status": "submitted",
                    "submitted_at": now_iso(),
                    "cost": sub.cost,
                }
            )
        else:
            rejected += 1
            print(f"  REJECTED {row.item_id}: {sub.status_code} {sub.status_message}")
    print(f"submitted {accepted}, rejected {rejected}. Collect in ~5 minutes.")


def collect_once(a: argparse.Namespace, ledger: Ledger, api_key: str) -> int:
    """One sweep over pending tasks. Returns how many are still pending."""
    pending = ledger.pending()
    if pending.empty:
        return 0

    out_dir = Path(a.out_dir)
    still = 0
    for row in pending.itertuples():
        outcome = get_task(api_key, row.task_id)
        base = {
            "task_id": row.task_id,
            "tag": row.tag,
            "wave": row.wave,
            "item_id": row.item_id,
            "intent": row.intent,
            "keyword_sha256": row.keyword_sha256,
            "submitted_at": row.submitted_at,
            "cost": row.cost,
        }
        if outcome.state == "done":
            wave_dir = out_dir / f"w{row.wave}"
            wave_dir.mkdir(parents=True, exist_ok=True)
            result_path = wave_dir / f"{row.task_id}.json"
            result_path.write_text(json.dumps(outcome.result, indent=1))
            ledger.append(
                base
                | {
                    "status": "collected",
                    "collected_at": now_iso(),
                    "model": (outcome.result or {}).get("model"),
                    "result_path": str(result_path),
                }
            )
            print(f"  collected {row.item_id} w{row.wave} ({row.task_id})")
        elif outcome.state == "failed":
            ledger.append(
                base
                | {
                    "status": "failed",
                    "error": f"{outcome.status_code} {outcome.status_message}",
                }
            )
            print(f"  FAILED {row.item_id} w{row.wave}: {outcome.status_code} {outcome.status_message}")
        else:
            submitted_at = datetime.fromisoformat(row.submitted_at)
            if datetime.now(timezone.utc) - submitted_at > STALE_AFTER:
                ledger.append(base | {"status": "failed", "error": "stale >48h"})
                print(f"  STALE {row.item_id} w{row.wave} marked failed")
            else:
                still += 1
        time.sleep(POLL_SLEEP_S)
    return still


def cmd_collect(a: argparse.Namespace) -> None:
    ledger = Ledger(a.ledger)
    api_key = load_api_key(a.env_file)
    while True:
        still = collect_once(a, ledger, api_key)
        print(f"pending: {still}")
        if still == 0 or not a.wait:
            break
        print(f"sleeping {a.wait}s ...")
        time.sleep(a.wait)


def cmd_status(a: argparse.Namespace) -> None:
    ledger = Ledger(a.ledger)
    stats = ledger_stats(ledger)
    print(f"tasks: {stats.total}   cost: ${stats.cost:.4f}")
    for status, n in sorted(stats.by_status.items()):
        print(f"  {status}: {n}")
    df = ledger.frame()
    if not df.empty:
        print("\nby intent/wave:")
        pivot = df.pivot_table(
            index=["intent", "wave"], columns="status", values="task_id",
            aggfunc="count", fill_value=0,
        )
        print(pivot.to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="post one wave of prompts")
    s.add_argument("--prompts", required=True, help="CSV with item_id, intent, text")
    s.add_argument("--intent", required=True)
    s.add_argument("--wave", type=int, required=True)
    s.add_argument("--ledger", required=True)
    s.add_argument("--env-file", default=None)
    s.add_argument("--tag-prefix", default="aeo-exp002")
    s.add_argument("--tag", default=None, help="override the derived tag (e.g. smoke tests)")
    s.add_argument("--priority", type=int, default=2, choices=[1, 2],
                   help="2 = priority queue ~5min (default), 1 = standard ~45min, half cost")
    s.add_argument("--limit", type=int, default=None, help="submit only the first N prompts")
    s.add_argument("--max-total-tasks", type=int, default=DEFAULT_MAX_TOTAL_TASKS)
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_submit)

    c = sub.add_parser("collect", help="poll pending tasks, write raw JSON")
    c.add_argument("--ledger", required=True)
    c.add_argument("--out-dir", required=True)
    c.add_argument("--env-file", default=None)
    c.add_argument("--wait", type=int, default=0,
                   help="seconds between sweeps; 0 = single pass (default)")
    c.set_defaults(fn=cmd_collect)

    st = sub.add_parser("status", help="ledger summary")
    st.add_argument("--ledger", required=True)
    st.set_defaults(fn=cmd_status)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
