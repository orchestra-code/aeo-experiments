#!/usr/bin/env python3
"""Daily wave driver for experiment 002, run by launchd (io.spyglasses.aeo-exp002).

Ledger-derived state machine, safe to run any number of times per day:
- latest headphone wave already submitted today  -> collect-only sweep
- latest wave complete and < 7, not submitted today -> submit next wave,
  wait for the priority queue, collect
- all 7 waves collected -> post a completion notification, remove the
  launchd job (delete plist + bootout), never run again

Everything else (idempotent submission, cost cap, task_get-only polling) is
inherited from scripts/llm_scraper.py. Logs append to
data/raw/wave_runs.log via the launchd plist redirection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

EXP = Path(__file__).resolve().parent
REPO = EXP.parents[1]
LEDGER = EXP / "data" / "raw" / "ledger.jsonl"
PROMPTS = EXP / "data" / "raw" / "prompts.csv"
RESPONSES = EXP / "data" / "raw" / "responses"
ENV_FILE = "/Users/jcw/projects/spyglasses/.env.local"
UV = "/usr/local/bin/uv"
LABEL = "io.spyglasses.aeo-exp002"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
MAX_WAVE = 7
QUEUE_WAIT_S = 420  # priority queue turnaround ~5 min


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def notify(msg: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "AEO experiment 002"'],
            check=False, capture_output=True,
        )
    except OSError:
        pass


def cli(*args: str) -> int:
    return subprocess.run(
        [UV, "run", "python", "scripts/llm_scraper.py", *args], cwd=REPO
    ).returncode


def collect() -> int:
    return cli(
        "collect", "--ledger", str(LEDGER), "--out-dir", str(RESPONSES),
        "--env-file", ENV_FILE, "--wait", "90",
    )


def ledger_state() -> tuple[int, bool, bool]:
    """(max headphone wave, submitted today?, that wave fully collected?)"""
    sys.path.insert(0, str(REPO / "src"))
    from aeo_research.dataforseo import Ledger

    frame = Ledger(LEDGER).frame()
    hp = frame[(frame["intent"] == "headphones")]
    max_wave = int(hp["wave"].max())
    latest = hp[hp["wave"] == max_wave]
    today = date.today().isoformat()
    submitted_today = latest["submitted_at"].astype(str).str[:10].eq(today).any()
    # "Complete" = nothing pending; failed rows are resubmittable next day.
    complete = not (latest["status"] == "submitted").any()
    return max_wave, submitted_today, complete


def self_destruct() -> None:
    log("all 7 waves collected — removing launchd job")
    notify("All 7 waves collected. Ready for analysis (pipeline 01-05).")
    PLIST.unlink(missing_ok=True)  # gone even if bootout kills us mid-line
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
        check=False, capture_output=True,
    )


def main() -> None:
    max_wave, submitted_today, complete = ledger_state()
    log(f"state: max_wave={max_wave} submitted_today={submitted_today} complete={complete}")

    if submitted_today:
        log("latest wave already submitted today — collect-only sweep")
        collect()
        _, _, complete = ledger_state()
        if max_wave >= MAX_WAVE and complete:
            self_destruct()
        return

    if max_wave >= MAX_WAVE:
        collect()  # stragglers from wave 7, if any
        _, _, complete = ledger_state()
        if complete:
            self_destruct()
        return

    if not complete:
        log(f"wave {max_wave} has pending tasks — sweeping before the next wave")
        collect()

    wave = max_wave + 1
    log(f"submitting wave {wave} (143 headphone prompts)")
    rc = cli(
        "submit", "--prompts", str(PROMPTS), "--intent", "headphones",
        "--wave", str(wave), "--ledger", str(LEDGER), "--env-file", ENV_FILE,
    )
    if rc != 0:
        notify(f"Wave {wave} submission FAILED (rc={rc}) — check wave_runs.log")
        sys.exit(rc)
    log(f"waiting {QUEUE_WAIT_S}s for the priority queue")
    time.sleep(QUEUE_WAIT_S)
    rc = collect()
    _, _, complete = ledger_state()
    status = "collected" if complete else "collect incomplete — will resweep tomorrow"
    log(f"wave {wave}: {status}")
    notify(f"Wave {wave}/7 {status}.")
    if wave >= MAX_WAVE and complete:
        self_destruct()


if __name__ == "__main__":
    main()
