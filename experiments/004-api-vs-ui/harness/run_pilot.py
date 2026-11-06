"""Experiment 004 feasibility run, one day (sketch, "Feasibility run").

10 prompts (``exp004.PILOT_ITEMS``), three rounds about ``--gap-min`` minutes apart.
Each round:

1. submit the DataForSEO ChatGPT (``force_web_search`` true) and Gemini UI tasks
   for the 10 prompts (``ledger_ui_<platform>.jsonl``, wave = round);
2. run that round's API arms (``ledger_api_openai.jsonl``, ``ledger_api_gemini.jsonl``);
3. collect the UI tasks by ``task_get`` (never ``tasks_ready``). A task that
   failed or came back with the app's error message is resubmitted the same round,
   at most ``ui.MAX_SUBMISSIONS`` submissions per prompt and round.

The 5 API arms run exactly once over the 3 rounds (2, 2 and 1 arms), in an order
drawn from seed 20261105 and recorded in ``data/raw/pilot_state.json`` before
anything is sent. The leak files are adapted once for the run date, which is
fixed at the first start and kept in the state file.

Resumable and safe to leave unattended: every step is idempotent on its ledger,
so a rerun picks up where the last one stopped (a round already done is
skipped; round r+1 starts ``--gap-min`` after round r actually started). A round
that raises is logged and retried after a pause. The cost guard refuses to start
if the recorded 004 spend plus the remaining run's prior would pass $10, and
runs again before every batch. Log: ``data/raw/run_pilot.log``.

Usage (repo root):
    uv run python experiments/004-api-vs-ui/harness/run_pilot.py --plan    # print, send nothing
    nohup uv run python experiments/004-api-vs-ui/harness/run_pilot.py > /dev/null 2>&1 &
    uv run python experiments/004-api-vs-ui/harness/run_pilot.py --status
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_gemini  # noqa: E402
import collect_openai  # noqa: E402
import exp004  # noqa: E402
import leaks  # noqa: E402
import ui  # noqa: E402

STATE = exp004.RAW / "pilot_state.json"
LOG = exp004.RAW / "run_pilot.log"
PREFIX = ""  # pilot ledgers; the smoke test used "smoke_"
ROUND_SIZES = (2, 2, 1)
UI_MAX_WAIT_S = 45 * 60
UI_POLL_S = 60
ROUND_RETRIES = 3
RETRY_PAUSE_S = 300


def log(msg: str) -> None:
    line = f"{exp004.now_iso()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def draw_order(seed: int = exp004.SEED) -> dict[int, list[str]]:
    """API arms -> rounds: shuffle the 5 arms, then the round sizes (2, 2, 1)."""
    rng = random.Random(seed)
    arms = list(exp004.API_ARMS)
    rng.shuffle(arms)
    sizes = list(ROUND_SIZES)
    rng.shuffle(sizes)
    out, i = {}, 0
    for rnd, n in zip(exp004.UI_ROUNDS, sizes, strict=True):
        out[rnd] = arms[i:i + n]
        i += n
    return out


def load_state(gap_min: float) -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    state = {"run_date": exp004.run_date(), "created_at": exp004.now_iso(), "seed": exp004.SEED,
             "gap_min": gap_min, "items": list(exp004.PILOT_ITEMS),
             "api_order": {str(k): v for k, v in draw_order().items()}, "rounds": {}}
    save_state(state)
    return state


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1) + "\n")


def ensure_leaks(run_day: str) -> None:
    manifest = leaks.LEAKS / "adapt_manifest.json"
    if not (leaks.LEAKS / "fetch_manifest.json").exists():
        leaks.cmd_fetch(None)
    if not manifest.exists() or json.loads(manifest.read_text()).get("run_date") != run_day:
        leaks.cmd_adapt(argparse.Namespace(date=run_day))
    m = json.loads(manifest.read_text())
    log(f"leaks adapted for {m['run_date']}: chatgpt {m['chatgpt']['sha256'][:12]}, "
        f"gemini {m['gemini']['sha256'][:12]}")


def remaining_plan(state: dict) -> dict[str, int]:
    """arm -> answers still to request over the whole run (UI and API)."""
    items = state["items"]
    plan: dict[str, int] = {}
    for platform in ui.PLATFORMS:
        done = ui.ledger(platform, PREFIX).submitted_keys()
        n = sum((ui.INTENT, i, r) not in done for r in exp004.UI_ROUNDS for i in items)
        plan[exp004.UI_ARM[platform]] = n
    done = (exp004.JsonlLedger(exp004.api_ledger(PREFIX, "openai")).done()
            | exp004.JsonlLedger(exp004.api_ledger(PREFIX, "gemini")).done())
    for rnd, arms in state["api_order"].items():
        for arm in arms:
            plan[arm] = plan.get(arm, 0) + sum((arm, i, int(rnd)) not in done for i in items)
    return plan


def ui_round_complete(rnd: int, items: list[str]) -> bool:
    for platform in ui.PLATFORMS:
        led = ui.ledger(platform, PREFIX)
        df = led.frame()
        got = set(df[(df.status == "collected") & (df.wave == rnd)].item_id) if not df.empty else set()
        tries = ui.submissions(platform, PREFIX)
        for item in items:
            if item not in got and tries.get((item, rnd), 0) < ui.MAX_SUBMISSIONS:
                return False
        if not led.pending().empty and (led.pending().wave == rnd).any():
            return False
    return True


def api_round_complete(state: dict, rnd: int) -> bool:
    arms = state["api_order"][str(rnd)]
    done = (exp004.JsonlLedger(exp004.api_ledger(PREFIX, "openai")).done()
            | exp004.JsonlLedger(exp004.api_ledger(PREFIX, "gemini")).done())
    return all((a, i, rnd) in done for a in arms for i in state["items"])


def run_api(arms: list[str], items: list[str], rnd: int) -> None:
    for arm in arms:
        log(f"round {rnd}: API arm {arm}")
        if exp004.ARMS[arm].instrument == "openai":
            collect_openai.run([arm], items, rnd, PREFIX, log=log)
        else:
            collect_gemini.run([arm], items, rnd, PREFIX, log=log)


def collect_ui(rnd: int, items: list[str]) -> None:
    for _ in range(ui.MAX_SUBMISSIONS):
        still = ui.collect(ui.PLATFORMS, PREFIX, wait_s=UI_POLL_S, max_wait_s=UI_MAX_WAIT_S, log=log)
        if still:
            log(f"round {rnd}: {still} UI tasks still pending after {UI_MAX_WAIT_S // 60} min; "
                "a rerun of the driver will keep polling them")
            return
        resubmitted = sum(ui.submit(p, items, rnd, PREFIX, log=log) for p in ui.PLATFORMS)
        if not resubmitted:
            return
        log(f"round {rnd}: resubmitted {resubmitted} UI tasks (failed or app error message)")


def do_round(state: dict, rnd: int) -> None:
    items = state["items"]
    log(f"round {rnd}: start; API arms {state['api_order'][str(rnd)]}")
    for platform in ui.PLATFORMS:
        ui.submit(platform, items, rnd, PREFIX, log=log)
    run_api(state["api_order"][str(rnd)], items, rnd)
    if not api_round_complete(state, rnd):
        log(f"round {rnd}: retrying failed API answers once")
        run_api(state["api_order"][str(rnd)], items, rnd)
    collect_ui(rnd, items)
    log(f"round {rnd}: done (UI complete {ui_round_complete(rnd, items)}, "
        f"API complete {api_round_complete(state, rnd)}); total 004 spend "
        f"${exp004.total_spend():.4f}")


def wait_until(when: datetime) -> None:
    while True:
        left = (when - datetime.now(timezone.utc)).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 60))


def status(state: dict | None) -> None:
    if not state:
        print("no pilot state yet")
        return
    print(json.dumps({k: state[k] for k in ("run_date", "seed", "gap_min", "api_order", "rounds")},
                     indent=1))
    for rnd in exp004.UI_ROUNDS:
        print(f"round {rnd}: UI complete {ui_round_complete(rnd, state['items'])}, "
              f"API complete {api_round_complete(state, rnd)}")
    print(f"remaining plan: {remaining_plan(state)}")
    print(f"total 004 spend recorded: ${exp004.total_spend():.4f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gap-min", type=float, default=60.0, help="minutes between round starts")
    ap.add_argument("--plan", action="store_true", help="print the plan and the cost guard; send nothing")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status:
        status(json.loads(STATE.read_text()) if STATE.exists() else None)
        return
    if a.plan:
        print(f"API order (seed {exp004.SEED}): {draw_order()}")
        state = json.loads(STATE.read_text()) if STATE.exists() else {
            "items": list(exp004.PILOT_ITEMS), "api_order": {str(k): v for k, v in draw_order().items()}}
        exp004.guard_cost(remaining_plan(state))
        return

    prompts = exp004.load_prompts()
    missing = [i for i in exp004.PILOT_ITEMS if i not in prompts]
    if missing:
        raise SystemExit(f"pilot prompts missing: {missing}")
    for name in ("OPENAI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "DATAFORSEO_API_KEY"):
        exp004.env_value(name)
    state = load_state(a.gap_min)
    gap = timedelta(minutes=state.get("gap_min", a.gap_min))
    log(f"pilot start/resume: run date {state['run_date']}, gap {gap}, order {state['api_order']}")
    ensure_leaks(state["run_date"])
    if any(exp004.ARMS[x].low_effort for arms in state["api_order"].values() for x in arms):
        log(f"cg_api_low effort: {collect_openai.probe_effort()!r} (low_effort_probe.json)")
    exp004.guard_cost(remaining_plan(state))

    prev_start: datetime | None = None
    for rnd in exp004.UI_ROUNDS:
        info = state["rounds"].setdefault(str(rnd), {})
        if info.get("complete"):
            prev_start = datetime.fromisoformat(info["started_at"])
            continue
        if "started_at" not in info:
            if prev_start is not None:
                when = prev_start + gap
                log(f"round {rnd}: waiting until {when.isoformat(timespec='seconds')}")
                wait_until(when)
            info["started_at"] = exp004.now_iso()
            save_state(state)
        for attempt in range(1, ROUND_RETRIES + 1):
            try:
                do_round(state, rnd)
                break
            except exp004.CostCapError:
                raise
            except Exception:
                log(f"round {rnd}: attempt {attempt} raised:\n{traceback.format_exc()}")
                if attempt == ROUND_RETRIES:
                    raise
                time.sleep(RETRY_PAUSE_S)
        info["complete"] = ui_round_complete(rnd, state["items"]) and api_round_complete(state, rnd)
        info["finished_at"] = exp004.now_iso()
        save_state(state)
        prev_start = datetime.fromisoformat(info["started_at"])
        if not info["complete"]:
            log(f"round {rnd}: incomplete; rerun the driver later to finish it")
    for rnd in exp004.UI_ROUNDS:  # catch-up pass, same day: finish any incomplete round
        info = state["rounds"][str(rnd)]
        if not info.get("complete"):
            log(f"round {rnd}: catch-up pass")
            try:
                do_round(state, rnd)
            except exp004.CostCapError:
                raise
            except Exception:
                log(f"round {rnd}: catch-up raised:\n{traceback.format_exc()}")
            info["complete"] = ui_round_complete(rnd, state["items"]) and api_round_complete(state, rnd)
            save_state(state)
    incomplete = [r for r in exp004.UI_ROUNDS if not state["rounds"][str(r)].get("complete")]
    if incomplete:
        log(f"rounds still incomplete: {incomplete}; rerun the driver to keep polling")
    log(f"pilot finished; total 004 spend ${exp004.total_spend():.4f}. "
        "Next: uv run python experiments/004-api-vs-ui/pipeline/pilot_report.py")


if __name__ == "__main__":
    main()
