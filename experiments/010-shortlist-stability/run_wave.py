#!/usr/bin/env python3
"""Wave driver for experiment 010's B2B collection: ChatGPT, Gemini, Claude.

Run daily at 20:00 by launchd (io.spyglasses.aeo-exp010). Schedule-driven and
safe to run any number of times per day:

- every run first collects: DataForSEO tasks on ChatGPT and Gemini, ended
  Claude batches;
- every run re-submits FAILED tasks of already-submitted waves (both
  collectors skip anything submitted or collected, so this only retries);
- if the next wave's scheduled date has arrived and it is not yet submitted,
  it is submitted on all three platforms, Claude first (its batch can take
  hours), then ChatGPT and Gemini (40 prompts each); the driver waits for the
  DataForSEO priority queue and collects. Claude batch results are collected
  by the next run. A wave submitted after its date is logged LATE (a spec
  deviation to record);
- when waves 1 to 7 are collected on all platforms: one notification that
  Stage 1 data are complete;
- when all 11 waves are collected on all platforms: notify, delete the plist,
  boot the job out.

The schedule is fixed at freeze in ``collection_schedule.json`` (committed):
waves 1 to 7 daily from the start date, then waves 8 to 11 weekly (start
date plus 13, 20, 27 and 34 days).

ChatGPT and Gemini go through scripts/llm_scraper.py (task_get polling only,
never tasks_ready), one ledger per platform because that ledger dedupes on
(intent, item, wave), not platform. Claude goes through experiment 009's
collector (``harness/collect_anthropic.py``), arm ``opus55_plain`` (Opus 5.5,
effort medium, no system prompt, Pittsburgh user location: the request shape
Spyglasses tracks Claude with), Batches API.

Usage:
  uv run python experiments/010-shortlist-stability/run_wave.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta
from pathlib import Path

EXP = Path(__file__).resolve().parent
REPO = EXP.parents[1]
RAW = EXP / "data" / "raw"
PROMPTS = RAW / "prompts_b2b.csv"
SCHEDULE_FILE = EXP / "collection_schedule.json"
STAGE1_MARKER = RAW / "stage1_complete_notified"
ENV_FILE = str((REPO.parent / "spyglasses" / ".env.local").resolve())
UV = shutil.which("uv") or "/opt/homebrew/bin/uv"
CLAUDE_COLLECTOR = "experiments/009-claude-model-fidelity/harness/collect_anthropic.py"
LABEL = "io.spyglasses.aeo-exp010"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DFS_PLATFORMS = ("chatgpt", "gemini")
PLATFORMS = ("claude", *DFS_PLATFORMS)  # Claude first: its batch takes longest
CLAUDE_ARM = "opus55_plain"
CLAUDE_MAX_COST = "50"  # 440 calls at ~$0.07 plus the collector's pending-batch prior
TAG = "main"
QUEUE_WAIT_S = 420
WAVE_DAY_OFFSETS = (0, 1, 2, 3, 4, 5, 6, 13, 20, 27, 34)
STAGE1_FINAL_WAVE = 7
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


def run(script: str, *args: str) -> int:
    return subprocess.run([UV, "run", "python", script, *args], cwd=REPO).returncode


def collect(platform: str) -> int:
    if not ledger(platform).exists():
        return 0
    if platform == "claude":
        return run(CLAUDE_COLLECTOR, "collect", "--prompts", str(PROMPTS),
                   "--ledger", str(ledger(platform)), "--out-dir", str(responses(platform)),
                   "--env-file", ENV_FILE)
    return run("scripts/llm_scraper.py", "collect", "--ledger", str(ledger(platform)),
               "--out-dir", str(responses(platform)), "--env-file", ENV_FILE, "--wait", "90")


def submit(platform: str, wave: int) -> int:
    if platform == "claude":
        return run(CLAUDE_COLLECTOR, "submit", "--wave", str(wave), "--arms", CLAUDE_ARM,
                   "--prompts", str(PROMPTS), "--ledger", str(ledger(platform)),
                   "--out-dir", str(responses(platform)), "--max-cost", CLAUDE_MAX_COST,
                   "--env-file", ENV_FILE)
    return run("scripts/llm_scraper.py", "submit", "--prompts", str(PROMPTS), "--intent", "b2b",
               "--wave", str(wave), "--ledger", str(ledger(platform)), "--platform", platform,
               "--tag-prefix", "aeo-exp010", "--max-total-tasks", str(MAX_TASKS_PER_LEDGER),
               "--env-file", ENV_FILE)


def records(platform: str) -> dict[str, dict]:
    """Latest state per task id (both ledgers are append-only)."""
    recs: dict[str, dict] = {}
    if ledger(platform).exists():
        for line in ledger(platform).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                recs.setdefault(r["task_id"], {}).update(r)
    return recs


#: When a (prompt, wave) has several task records (a DataForSEO retry gets a
#: new task id), the best status wins.
STATUS_RANK = {"collected": 3, "submitted": 2, "failed": 1}


def n_prompts() -> int:
    return sum(1 for line in PROMPTS.read_text().splitlines()[1:] if line.strip())


def state(platform: str) -> dict:
    best: dict[tuple[str, int], str] = {}
    for r in records(platform).values():
        k = (r["item_id"], int(r["wave"]))
        st = r.get("status", "failed")
        if STATUS_RANK.get(st, 0) > STATUS_RANK.get(best.get(k, ""), 0):
            best[k] = st
    waves = sorted({w for _, w in best})
    expected = n_prompts()
    collected = {w for w in waves
                 if sum(1 for (_, ww), st in best.items() if ww == w and st == "collected")
                 == expected}
    failed = {w for (_, w), st in best.items() if st == "failed"}
    return {"top": max(waves, default=0), "collected": collected, "failed": failed}


def all_collected(states: dict, through: int) -> bool:
    return all(set(range(1, through + 1)) <= s["collected"] for s in states.values())


def self_destruct() -> None:
    log("all 11 waves collected on all platforms; removing launchd job")
    notify("All 11 waves collected. Stage 2 (over time) is ready to analyze.")
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

    if not args.dry_run:
        for p in PLATFORMS:
            collect(p)
        for p in PLATFORMS:
            for w in sorted(state(p)["failed"]):
                log(f"{p}: retrying failed tasks of wave {w}")
                submit(p, w)
    states = {p: state(p) for p in PLATFORMS}
    log("state: " + "; ".join(f"{p} top={s['top']} collected={sorted(s['collected'])} "
                              f"failed={sorted(s['failed'])}" for p, s in states.items()))

    if all_collected(states, STAGE1_FINAL_WAVE) and not STAGE1_MARKER.exists() \
            and not args.dry_run:
        STAGE1_MARKER.write_text(datetime.now().isoformat())
        notify("Stage 1 data complete (waves 1 to 7). Ready for the run-to-run analysis.")
        log("Stage 1 data complete")
    if all_collected(states, final):
        if not args.dry_run:
            self_destruct()
        return

    nxt = min(s["top"] for s in states.values()) + 1
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
        if states[p]["top"] >= nxt:
            continue
        rc = submit(p, nxt)
        if rc != 0:
            notify(f"Wave {nxt} {p} submission FAILED (rc={rc}); check wave_runs.log")
            log(f"{p}: submission failed rc={rc}")
    log(f"waiting {QUEUE_WAIT_S}s for the DataForSEO priority queue")
    time.sleep(QUEUE_WAIT_S)
    for p in DFS_PLATFORMS:
        collect(p)
    states = {p: state(p) for p in PLATFORMS}
    dfs_ok = all(nxt in states[p]["collected"] for p in DFS_PLATFORMS)
    msg = (f"Wave {nxt}/{final}: ChatGPT and Gemini "
           f"{'collected' if dfs_ok else 'incomplete, will resweep'}; Claude batch submitted")
    log(msg + (" (LATE)" if late else ""))
    notify(msg)


if __name__ == "__main__":
    main()
