#!/usr/bin/env python3
"""Daily wave driver for experiment 008, run by launchd (io.spyglasses.aeo-exp008).

Allocation C (frozen): 10 daily waves of the 96 core items, plus two extra
replicate sets on wave 1 only (rep1/rep2), spaced by the launchd triggers
(10:30 / 14:30 / 18:30 local). The collector is the direct OpenAI Responses
API (synchronous), so each trigger submits and finishes in one pass.

Ledger-derived state machine, safe to run any number of times per day:
- no data/raw/FROZEN marker, or before the start date it records -> exit
- wave 1 day: first trigger runs `core`, second `rep1`, third `rep2`
- waves 2-10: first trigger of the day runs `core`; later triggers retry
  only failed/missing rows (idempotent) and otherwise no-op
- after wave 10 is fully collected -> notify, remove the launchd job

Logs append to data/raw/wave_runs.log via the plist redirection.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

EXP = Path(__file__).resolve().parent
REPO = EXP.parents[1]
FROZEN = EXP / "data" / "raw" / "FROZEN"
LEDGER = EXP / "data" / "raw" / "ledger_direct.jsonl"
PROMPTS = EXP / "data" / "raw" / "prompts.csv"
RESPONSES = EXP / "data" / "raw" / "responses_direct"
UV = "/usr/local/bin/uv"
LABEL = "io.spyglasses.aeo-exp008"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
MAX_WAVE = 10
WAVE_INTENTS = {1: ["core", "rep1", "rep2"]}  # every other wave: ["core"]


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def notify(msg: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "AEO experiment 008"'],
            check=False, capture_output=True,
        )
    except OSError:
        pass


def start_date() -> date | None:
    if not FROZEN.exists():
        return None
    for line in FROZEN.read_text().splitlines():
        if line.startswith("start_date="):
            return date.fromisoformat(line.split("=", 1)[1].strip())
    return None


def run_intent(intent: str, wave: int) -> int:
    return subprocess.run(
        [UV, "run", "python",
         str(EXP / "harness" / "collect_openai.py"),
         "--prompts", str(PROMPTS), "--intent", intent, "--wave", str(wave),
         "--ledger", str(LEDGER), "--out-dir", str(RESPONSES)],
        cwd=REPO,
    ).returncode


def ledger_frame():
    sys.path.insert(0, str(REPO / "src"))
    from aeo_research.dataforseo import Ledger
    frame = Ledger(LEDGER).frame() if LEDGER.exists() else None
    if frame is None or frame.empty:
        return None
    return frame[frame["intent"].isin(["core", "rep1", "rep2"])]


def done_intents(frame, wave: int) -> set[str]:
    """Intents fully collected for this wave (no missing, no failed rows)."""
    if frame is None:
        return set()
    import pandas as pd  # noqa: F401 — via ledger frame

    import csv as _csv
    with PROMPTS.open() as f:
        wanted = {}
        for row in _csv.DictReader(f):
            wanted.setdefault(row["intent"], set()).add(row["item_id"])

    done = set()
    sub = frame[frame["wave"] == wave]
    for intent, items in wanted.items():
        got = set(sub[(sub["intent"] == intent)
                      & (sub["status"] == "collected")]["item_id"])
        if items <= got:
            done.add(intent)
    return done


def self_destruct() -> None:
    log(f"all {MAX_WAVE} waves collected — removing launchd job")
    notify(f"All {MAX_WAVE} waves collected. Ready for audits + analysis.")
    PLIST.unlink(missing_ok=True)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
                   check=False, capture_output=True)


def main() -> None:
    start = start_date()
    if start is None:
        log("spec not frozen (data/raw/FROZEN with start_date= missing) — exit")
        return
    today = datetime.now().astimezone().date()
    wave = (today - start).days + 1
    if wave < 1:
        log(f"start date {start} not reached — exit")
        return
    if wave > MAX_WAVE:
        wave = MAX_WAVE  # straggler sweeps only

    frame = ledger_frame()
    intents = WAVE_INTENTS.get(wave, ["core"])
    done = done_intents(frame, wave)
    log(f"wave {wave}/{MAX_WAVE}: intents {intents}, done {sorted(done)}")

    todo = [i for i in intents if i not in done]
    if todo:
        intent = todo[0]  # one intent per trigger — that's the spacing
        log(f"running intent {intent} for wave {wave}")
        rc = run_intent(intent, wave)
        if rc != 0:
            notify(f"Wave {wave} intent {intent} FAILED (rc={rc}) — see wave_runs.log")
            sys.exit(rc)
        done = done_intents(ledger_frame(), wave)

    if wave >= MAX_WAVE and set(WAVE_INTENTS.get(MAX_WAVE, ["core"])) <= done:
        self_destruct()


if __name__ == "__main__":
    main()
