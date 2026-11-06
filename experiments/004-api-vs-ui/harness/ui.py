"""DataForSEO LLM-scraper submit and collect for 004's UI arms (``cg_ui``, ``gm_ui``).

The settings are 010's, so 004's UI answers are collected the way 010 collected
them: US (location 2840), English, desktop, priority queue; ChatGPT with
``force_web_search`` true, Gemini without the field (its endpoint rejects it).
Built on ``aeo_research.dataforseo`` (``post_tasks``, ``get_task``, ``Ledger``), the
same code as ``scripts/llm_scraper.py``, with the same ledger records, so
``llm_scraper.py status --ledger ...`` reads 004's UI ledgers too.

HARD RULE: polling is ``task_get`` by our own stored task ids only. Never
``tasks_ready``: it is account-wide and shared with a production poller.

The key comes only from the main checkout's ``.env.local`` (``exp004.env_value``),
never from the process environment.

Ledgers: ``<prefix>ledger_ui_<platform>.jsonl``; ``wave`` = round (1..3) for the
pilot. Raw results: ``<prefix>responses_ui_<platform>/w<round>/<task_id>.json``.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answers  # noqa: E402
import exp004  # noqa: E402

from aeo_research.dataforseo import Ledger, TaskSpec, get_task, post_tasks  # noqa: E402

PLATFORMS = ("chatgpt", "gemini")
INTENT = "b2b"
STALE_AFTER = timedelta(hours=48)
#: Submissions per (prompt, round), first included. A task that fails or returns the
#: app's error message is resubmitted the same round up to this many times in all.
MAX_SUBMISSIONS = 3
POLL_SLEEP_S = 0.3


def ledger(platform: str, prefix: str = "") -> Ledger:
    return Ledger(exp004.ui_ledger(prefix, platform))


def out_dir(platform: str, prefix: str = "") -> Path:
    return exp004.RAW / f"{prefix}responses_ui_{platform}"


def _key() -> str:
    return exp004.env_value("DATAFORSEO_API_KEY")


def submit(platform: str, items: list[str], rnd: int, prefix: str = "", tag: str | None = None,
           log=print) -> int:
    """Submit one round; (intent, item, round) already submitted or collected is skipped."""
    led = ledger(platform, prefix)
    prompts = exp004.load_prompts()
    done = led.submitted_keys()
    tries = submissions(platform, prefix)
    capped = [i for i in items if (INTENT, i, rnd) not in done and tries.get((i, rnd), 0) >= MAX_SUBMISSIONS]
    if capped:
        log(f"ui {platform} r{rnd}: {len(capped)} prompts reached {MAX_SUBMISSIONS} submissions, not resubmitted")
    todo = [i for i in items if (INTENT, i, rnd) not in done and i not in capped]
    if not todo:
        log(f"ui {platform} r{rnd}: nothing to submit")
        return 0
    exp004.guard_cost({exp004.UI_ARM[platform]: len(todo)})
    tag = tag or f"{exp004.TAG}-{prefix.strip('_') or 'pilot'}-r{rnd}"
    specs = [TaskSpec(keyword=prompts[i]["text"], tag=tag, force_web_search=platform != "gemini")
             for i in todo]
    subs = post_tasks(_key(), specs, platform=platform)
    accepted = 0
    for item, sub in zip(todo, subs, strict=True):
        if sub.accepted:
            accepted += 1
            led.append({"task_id": sub.task_id, "tag": tag, "wave": rnd, "round": rnd,
                        "item_id": item, "intent": INTENT, "platform": platform,
                        "arm": exp004.UI_ARM[platform],
                        "keyword_sha256": exp004.sha256_text(prompts[item]["text"]),
                        "status": "submitted", "submitted_at": exp004.now_iso(), "cost": sub.cost})
        else:
            log(f"  REJECTED {platform} {item}: {sub.status_code} {sub.status_message}")
    log(f"ui {platform} r{rnd}: submitted {accepted}/{len(todo)} (tag {tag})")
    return accepted


def submissions(platform: str, prefix: str = "") -> dict[tuple[str, int], int]:
    """(item_id, round) -> number of tasks submitted for it."""
    out: dict[tuple[str, int], int] = {}
    for r in ledger(platform, prefix).records():
        if r.get("status") == "submitted":
            k = (r["item_id"], int(r["wave"]))
            out[k] = out.get(k, 0) + 1
    return out


def collect_once(platform: str, prefix: str = "", log=print) -> int:
    """One sweep over pending tasks via task_get. Returns how many are still pending."""
    led = ledger(platform, prefix)
    pending = led.pending()
    if pending.empty:
        return 0
    key, still = _key(), 0
    for row in pending.itertuples():
        base = {k: getattr(row, k) for k in ("task_id", "tag", "wave", "item_id", "intent",
                                             "keyword_sha256", "submitted_at", "cost")}
        base |= {"platform": platform, "round": int(row.wave), "arm": exp004.UI_ARM[platform]}
        try:
            outcome = get_task(key, row.task_id, platform=platform)
        except Exception as e:  # network trouble: leave pending, retry next sweep
            log(f"  poll error {platform} {row.item_id} r{row.wave}: {type(e).__name__}")
            still += 1
            continue
        if outcome.state == "done":
            d = out_dir(platform, prefix) / f"w{row.wave}"
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{row.task_id}.json"
            path.write_text(json.dumps(outcome.result, indent=1, ensure_ascii=False))
            error = answers.is_error_answer((outcome.result or {}).get("markdown") or "")
            led.append(base | {"status": "error_answer" if error else "collected",
                               "collected_at": exp004.now_iso(),
                               "model": (outcome.result or {}).get("model"),
                               "result_path": str(path)})
            log(f"  {'ERROR ANSWER' if error else 'collected'} {platform} {row.item_id} r{row.wave}")
        elif outcome.state == "failed":
            led.append(base | {"status": "failed",
                               "error": f"{outcome.status_code} {outcome.status_message}"})
            log(f"  FAILED {platform} {row.item_id} r{row.wave}: {outcome.status_code}")
        else:
            if datetime.now(timezone.utc) - datetime.fromisoformat(row.submitted_at) > STALE_AFTER:
                led.append(base | {"status": "failed", "error": "stale >48h"})
            else:
                still += 1
        time.sleep(POLL_SLEEP_S)
    return still


def collect(platforms=PLATFORMS, prefix: str = "", wait_s: int = 60, max_wait_s: int = 3600,
            log=print) -> int:
    """Sweep until nothing is pending or ``max_wait_s`` passes. Returns pending count."""
    deadline = time.monotonic() + max_wait_s
    while True:
        still = sum(collect_once(p, prefix, log) for p in platforms)
        if still == 0 or time.monotonic() > deadline:
            log(f"ui collect: {still} pending")
            return still
        time.sleep(wait_s)


def mark_error_answers(platform: str, prefix: str = "", log=print) -> int:
    """Re-check collected tasks; mark any app error message as ``error_answer``."""
    led, n = ledger(platform, prefix), 0
    for row in led.frame().itertuples():
        if row.status != "collected":
            continue
        result = json.loads(Path(row.result_path).read_text())
        if answers.is_error_answer(result.get("markdown") or ""):
            rec = {k: getattr(row, k) for k in row._fields if k != "Index"}
            led.append({k: v for k, v in rec.items() if v == v} | {"status": "error_answer"})
            n += 1
    if n:
        log(f"ui {platform}: {n} collected tasks were app error messages, marked error_answer")
    return n
