#!/usr/bin/env python3
"""Daily wave driver for experiment 005, run by launchd (io.spyglasses.aeo-exp005).

Ledger-derived state machine, safe to run any number of times per day:
- spec not frozen (no data/raw/FROZEN marker) -> log and exit; nothing
  submits before the spec review freeze
- latest wave already submitted today -> collect-only sweep
- latest wave complete and < 5, not submitted today -> submit next wave,
  wait for the priority queue, collect
- all 5 waves collected -> post a completion notification, remove the
  launchd job (delete plist + bootout), never run again

Wave 1 submits the coffee floor (40 prompts, `--intent coffee`) alongside
the 238 headphone-panel prompts (hum + mat + neu2); later waves are
headphones only. Everything else (idempotent submission, cost cap,
task_get-only polling) is inherited from scripts/llm_scraper.py. Logs
append to data/raw/wave_runs.log via the launchd plist redirection.
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
FROZEN = EXP / "data" / "raw" / "FROZEN"
LEDGER = EXP / "data" / "raw" / "ledger.jsonl"
PROMPTS = EXP / "data" / "raw" / "prompts.csv"
RESPONSES = EXP / "data" / "raw" / "responses"
ENV_FILE = "/Users/jcw/projects/spyglasses/.env.local"
UV = "/usr/local/bin/uv"
LABEL = "io.spyglasses.aeo-exp005"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
MAX_WAVE = 5
QUEUE_WAIT_S = 420  # priority queue turnaround ~5 min
TAG_PREFIX = "aeo-exp005"


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def notify(msg: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "AEO experiment 005"'],
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


def submit(intent: str, wave: int) -> int:
    return cli(
        "submit", "--prompts", str(PROMPTS), "--intent", intent,
        "--wave", str(wave), "--ledger", str(LEDGER), "--env-file", ENV_FILE,
        "--tag-prefix", TAG_PREFIX,
    )


def ledger_state() -> tuple[int, bool, bool]:
    """(max headphone-panel wave, submitted today?, that wave fully collected?)"""
    if not LEDGER.exists():
        return 0, False, True

    sys.path.insert(0, str(REPO / "src"))
    from aeo_research.dataforseo import Ledger

    frame = Ledger(LEDGER).frame()
    hp = frame[(frame["intent"] == "headphones")]
    if hp.empty:
        return 0, False, True
    max_wave = int(hp["wave"].max())
    latest = hp[hp["wave"] == max_wave]
    today = date.today().isoformat()

    def local_date(iso: str) -> str:
        # submitted_at is UTC; compare calendar days in LOCAL time (002's
        # wave-3 bug) or evening submissions skip the next day's wave.
        return datetime.fromisoformat(iso).astimezone().date().isoformat()

    submitted_today = latest["submitted_at"].astype(str).map(local_date).eq(today).any()
    # "Complete" = nothing pending; failed rows are resubmittable next day.
    complete = not (latest["status"] == "submitted").any()
    return max_wave, submitted_today, complete


def self_destruct() -> None:
    log(f"all {MAX_WAVE} waves collected — removing launchd job")
    notify(f"All {MAX_WAVE} waves collected. Ready for analysis (pipeline 01-05).")
    PLIST.unlink(missing_ok=True)  # gone even if bootout kills us mid-line
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
        check=False, capture_output=True,
    )


def main() -> None:
    if not FROZEN.exists():
        log("spec not frozen (data/raw/FROZEN missing) — nothing submitted")
        return

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
        collect()  # stragglers from the final wave, if any
        _, _, complete = ledger_state()
        if complete:
            self_destruct()
        return

    if max_wave and not complete:
        log(f"wave {max_wave} has pending tasks — sweeping before the next wave")
        collect()

    wave = max_wave + 1
    log(f"submitting wave {wave} (238 headphone-panel prompts: hum+mat+neu2)")
    rc = submit("headphones", wave)
    if rc == 0 and wave == 1:
        log("wave 1: submitting the coffee floor (40 prompts)")
        rc = submit("coffee", 1)
    if rc != 0:
        notify(f"Wave {wave} submission FAILED (rc={rc}) — check wave_runs.log")
        sys.exit(rc)
    log(f"waiting {QUEUE_WAIT_S}s for the priority queue")
    time.sleep(QUEUE_WAIT_S)
    rc = collect()
    _, _, complete = ledger_state()
    status = "collected" if complete else "collect incomplete — will resweep tomorrow"
    log(f"wave {wave}: {status}")
    notify(f"Wave {wave}/{MAX_WAVE} {status}.")
    if wave >= MAX_WAVE and complete:
        self_destruct()


if __name__ == "__main__":
    main()
