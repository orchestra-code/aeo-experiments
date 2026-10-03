#!/usr/bin/env python3
"""Wave driver for experiment 010's B2B collection (ChatGPT + Gemini via DataForSEO).

Run daily by launchd (io.spyglasses.aeo-exp010). Schedule-driven and safe to
run any number of times per day:

- every run first sweeps pending tasks on both platforms (collect);
- if the next wave's scheduled date has arrived (today or earlier) and it is
  not yet submitted, submit it on BOTH platforms (40 prompts each), wait for
  the priority queue, collect. A wave submitted after its scheduled date is
  logged as LATE (a spec deviation to record);
- once wave 11 is fully collected on both platforms: notify, delete the
  plist, boot the job out.

The schedule is fixed at freeze in ``collection_schedule.json`` (committed):
waves 1 to 7 daily from the start date, waves 8 to 11 on days 14, 21, 28 and
35. Submission, the cost cap and task_get-only polling come from
scripts/llm_scraper.py (never tasks_ready). One ledger per platform, because
the ledger dedupes on (intent, item, wave), not platform.

Usage:
  uv run python experiments/010-shortlist-stability/run_wave.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

EXP = Path(__file__).resolve().parent
REPO = EXP.parents[1]
RAW = EXP / "data" / "raw"
PROMPTS = RAW / "prompts_b2b.csv"
SCHEDULE_FILE = EXP / "collection_schedule.json"
ENV_FILE = str((REPO.parent / "spyglasses" / ".env.local").resolve())
UV = shutil.which("uv") or "/opt/homebrew/bin/uv"
LABEL = "io.spyglasses.aeo-exp010"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
PLATFORMS = ("chatgpt", "gemini")
TAG = "main"
QUEUE_WAIT_S = 420
WAVE_DAY_OFFSETS = (0, 1, 2, 3, 4, 5, 6, 13, 20, 27, 34)
MAX_TASKS_PER_LEDGER = 40 * len(WAVE_DAY_OFFSETS) + 40  # one wave of headroom for retries


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def notify(msg: str) -> None:
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{msg}" with title "AEO experiment 010"'],
                       check=False, capture_output=True)
    except OSError:
        pass


def schedule() -> dict[int, date]:
    start = date.fromisoformat(json.loads(SCHEDULE_FILE.read_text())["start"])
    return {i + 1: start + timedelta(days=d) for i, d in enumerate(WAVE_DAY_OFFSETS)}


def ledger(platform: str) -> Path:
    return RAW / f"ledger_{TAG}_{platform}.jsonl"


def responses(platform: str) -> Path:
    return RAW / f"responses_{TAG}_{platform}"


def cli(*args: str) -> int:
    return subprocess.run([UV, "run", "python", "scripts/llm_scraper.py", *args],
                          cwd=REPO).returncode


def collect(platform: str) -> int:
    if not ledger(platform).exists():
        return 0
    return cli("collect", "--ledger", str(ledger(platform)), "--out-dir",
               str(responses(platform)), "--env-file", ENV_FILE, "--wait", "90")


def state(platform: str) -> tuple[int, bool]:
    """(highest wave submitted, that wave has no pending tasks)."""
    if not ledger(platform).exists():
        return 0, True
    recs: dict[str, dict] = {}
    for line in ledger(platform).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            recs.setdefault(r["task_id"], {}).update(r)
    waves = [int(r["wave"]) for r in recs.values()]
    if not waves:
        return 0, True
    top = max(waves)
    pending = any(int(r["wave"]) == top and r.get("status") == "submitted"
                  for r in recs.values())
    return top, not pending


def self_destruct() -> None:
    log("all 11 waves collected on both platforms; removing launchd job")
    notify("All 11 waves collected. Ready for lexicon v3 and analysis.")
    PLIST.unlink(missing_ok=True)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
                   check=False, capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sched = schedule()
    final = max(sched)
    today = date.today()

    for p in PLATFORMS:
        if not args.dry_run:
            collect(p)
    states = {p: state(p) for p in PLATFORMS}
    log(f"state: {states}")

    if all(w >= final and done for w, done in states.values()):
        if not args.dry_run:
            self_destruct()
        return

    nxt = min(w for w, _ in states.values()) + 1
    if nxt > final:
        log("final wave submitted; waiting for stragglers")
        return
    due = sched[nxt]
    if today < due:
        log(f"wave {nxt} is scheduled for {due}; nothing to submit today")
        return
    late = today > due
    log(f"submitting wave {nxt} (scheduled {due}{', LATE' if late else ''}) on {PLATFORMS}")
    if args.dry_run:
        return
    for p in PLATFORMS:
        if states[p][0] >= nxt:
            continue
        rc = cli("submit", "--prompts", str(PROMPTS), "--intent", "b2b", "--wave", str(nxt),
                 "--ledger", str(ledger(p)), "--platform", p,
                 "--tag-prefix", "aeo-exp010", "--max-total-tasks", str(MAX_TASKS_PER_LEDGER),
                 "--env-file", ENV_FILE)
        if rc != 0:
            notify(f"Wave {nxt} {p} submission FAILED (rc={rc}); check wave_runs.log")
            sys.exit(rc)
    log(f"waiting {QUEUE_WAIT_S}s for the priority queue")
    time.sleep(QUEUE_WAIT_S)
    for p in PLATFORMS:
        collect(p)
    states = {p: state(p) for p in PLATFORMS}
    ok = all(done for _, done in states.values())
    msg = f"Wave {nxt}/{final} {'collected' if ok else 'incomplete, will resweep'}"
    log(msg + (" (LATE)" if late else ""))
    notify(msg)
    if nxt == final and ok:
        self_destruct()


if __name__ == "__main__":
    main()
