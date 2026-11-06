"""Experiment 004 main study: one wave (spec.md §1, "Wave procedure").

Arms: ``cg_ui`` and ``gm_ui`` (DataForSEO, ``ui.py``), ``cg_api_low`` and
``cg_api_plain`` (``collect_openai.py``), ``gm_api_plain`` (``collect_gemini.py``), on
all 40 prompts (``exp004.load_prompts()``). The leak arms are not part of the study.

Orders. A generator seeded with ``[20261106, wave]`` (numpy ``SeedSequence``) draws, in
this sequence: which platform's UI batch is posted first, the order of the 40 tasks inside
each platform's batch (ChatGPT's drawn first, then Gemini's), one prompt order for the API
arms, and for each prompt in that order which ChatGPT arm runs first. DataForSEO takes a
platform's tasks in one POST, so "the order of the 80 UI tasks" is the two batches in the
drawn platform order, each in its drawn prompt order. Both API workers follow the same
prompt order. The orders are written to ``data/raw/main_state.json`` before any request
is sent.

Procedure (one call of this script, resumable):

1. Submit every UI task not yet submitted for the wave, tagged ``aeo-exp004-w<wave>``.
2. Run the API arms with two workers at the same time, one OpenAI (per prompt, the two
   ChatGPT arms back to back in the drawn order) and one Gemini. A failed call is
   retried in later passes over the wave, at most 3 attempts per (arm, prompt, wave). An
   empty answer counts as a failed attempt. An answer from a model other than the pin
   stops the wave: both workers stop, nothing more is sent, and the state file records
   why. A person decides what happens next and logs it.
3. Collect the UI tasks by ``task_get`` on our own task ids (never ``tasks_ready``). A
   task that failed or came back as the app's error message is resubmitted the same day,
   at most 3 submissions per prompt and wave.
4. Completeness per arm. An arm missing more than 4 answers is rerun for its missing
   prompts the next day with ``--rerun-missing``, which is logged as a deviation and
   gives those prompts a fresh allowance of 3 tries.

Files (main study only; the pilot's never mix in): ``ledger_main_api_openai.jsonl``,
``ledger_main_api_gemini.jsonl``, ``ledger_main_ui_chatgpt.jsonl``,
``ledger_main_ui_gemini.jsonl``, ``responses_main_api/``, ``responses_main_ui_<platform>/``,
``main_state.json`` and the log ``run_wave.log``, all in ``data/raw/``.

Cost guard: the study cap is $45 on main-study spend only (``exp004.main_spend``: pilot,
smoke and probe spend are not counted). A wave refuses to start if recorded main spend
plus the prior of everything the wave still has to request would pass the cap, and the
API workers stop if recorded spend passes it mid-wave.

Timing guards: a new wave starts only between 10:00 and 14:00 US Eastern (``--any-time``
overrides) and not on the day of, or the day after, an earlier wave (``--any-day``).

Usage (repo root):
    uv run python experiments/004-api-vs-ui/harness/run_wave.py --wave 1 --plan   # sends nothing
    nohup uv run python experiments/004-api-vs-ui/harness/run_wave.py --wave 1 > /dev/null 2>&1 &
    uv run python experiments/004-api-vs-ui/harness/run_wave.py --status
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import threading
import time
import traceback
from datetime import date, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answers  # noqa: E402
import collect_gemini  # noqa: E402
import collect_openai  # noqa: E402
import exp004  # noqa: E402
import ui  # noqa: E402

STUDY = exp004.STUDY
UI_POLL_S = 60
UI_MAX_WAIT_S = 45 * 60
WINDOW_ET = (10, 14)  # a wave starts between 10:00 and 14:00 US Eastern
INSTRUMENT_ARMS = {"openai": exp004.STUDY_OPENAI_ARMS, "gemini": exp004.STUDY_GEMINI_ARMS}


class WaveStopped(SystemExit):
    """A pinned-model mismatch (or another stop rule) ended the wave."""


def state_path() -> Path:
    return exp004.RAW / "main_state.json"


def log_path() -> Path:
    return exp004.RAW / "run_wave.log"


def log(msg: str) -> None:
    line = f"{exp004.now_iso()} {msg}"
    print(line, flush=True)
    log_path().parent.mkdir(parents=True, exist_ok=True)
    with log_path().open("a") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- orders


def draw_orders(wave: int, items: list[str], seed: int = exp004.STUDY_SEED) -> dict:
    """The wave's submit and run orders, drawn from ``[seed, wave]`` (module docstring)."""
    if wave not in exp004.STUDY_WAVES:
        raise SystemExit(f"wave must be one of {exp004.STUDY_WAVES}")
    items = sorted(items)
    rng = np.random.default_rng([seed, wave])
    platforms = [str(p) for p in rng.permutation(list(ui.PLATFORMS))]
    ui_order = {p: [str(x) for x in rng.permutation(items)] for p in ui.PLATFORMS}
    api_order = [str(x) for x in rng.permutation(items)]
    low, plain = exp004.STUDY_OPENAI_ARMS
    pair = {item: ([low, plain] if rng.integers(2) == 0 else [plain, low]) for item in api_order}
    return {"seed": [seed, wave], "ui_platform_order": platforms, "ui_order": ui_order,
            "api_order": api_order, "cg_pair_order": pair}


def openai_jobs(orders: dict) -> list[tuple[str, str]]:
    return [(arm, item) for item in orders["api_order"] for arm in orders["cg_pair_order"][item]]


def gemini_jobs(orders: dict) -> list[tuple[str, str]]:
    return [(arm, item) for item in orders["api_order"] for arm in exp004.STUDY_GEMINI_ARMS]


# ---------------------------------------------------------------- state


def load_state() -> dict:
    if state_path().exists():
        return json.loads(state_path().read_text())
    return {"seed": exp004.STUDY_SEED, "cap_usd": exp004.STUDY_COST_CAP_USD, "waves": {}}


def save_state(state: dict) -> None:
    state_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n")
    tmp.replace(state_path())


def today() -> str:
    return exp004.run_date()


def timing_problems(state: dict, wave: int, now_et: datetime | None = None) -> list[str]:
    """Reasons a NEW wave may not start now (spec §1: 10:00 to 14:00 ET, non-consecutive)."""
    from zoneinfo import ZoneInfo

    now_et = now_et or datetime.now(ZoneInfo("America/New_York"))
    problems = []
    if not WINDOW_ET[0] <= now_et.hour < WINDOW_ET[1]:
        problems.append(f"it is {now_et:%H:%M} ET; a wave starts between {WINDOW_ET[0]}:00 and "
                        f"{WINDOW_ET[1]}:00 ET (--any-time overrides)")
    day = now_et.date()
    for other, info in state["waves"].items():
        if int(other) == wave or not info.get("run_date"):
            continue
        ran = date.fromisoformat(info["run_date"])
        if abs((day - ran).days) <= 1:
            problems.append(f"wave {other} ran on {ran}; waves are on non-consecutive days "
                            "(--any-day overrides)")
    for earlier in range(1, wave):
        if str(earlier) not in state["waves"]:
            problems.append(f"wave {earlier} has not run")
    return problems


def tries_allowed(info: dict) -> int:
    """3 tries per (arm, prompt, wave), plus 3 for each logged next-day rerun."""
    return exp004.STUDY_MAX_TRIES * (1 + len(info.get("reruns", [])))


# ---------------------------------------------------------------- tallies


def ui_status(platform: str, wave: int) -> dict[str, dict]:
    """item -> {collected, submissions, pending, error_answers, failed} for one UI arm."""
    led = ui.ledger(platform, store=STUDY)
    tasks: dict[str, dict] = {}
    subs: dict[str, int] = {}
    for r in led.records():
        if int(r.get("wave", -1)) != wave:
            continue
        tasks.setdefault(r["task_id"], {}).update(r)
        if r.get("status") == "submitted":
            subs[r["item_id"]] = subs.get(r["item_id"], 0) + 1
    out: dict[str, dict] = {}
    for t in tasks.values():
        s = out.setdefault(t["item_id"], {"collected": False, "pending": 0, "error_answers": 0,
                                          "failed": 0})
        s["collected"] |= t["status"] == "collected"
        s["pending"] += t["status"] == "submitted"
        s["error_answers"] += t["status"] == "error_answer"
        s["failed"] += t["status"] == "failed"
    for item, n in subs.items():
        out.setdefault(item, {"collected": False, "pending": 0, "error_answers": 0, "failed": 0})
        out[item]["submissions"] = n
    return out


def api_status(instrument: str, wave: int) -> dict[tuple[str, str], dict]:
    """(arm, item) -> {collected, attempts, last_status} for one vendor's arms."""
    out: dict[tuple[str, str], dict] = {}
    for r in exp004.read_jsonl(STUDY.api_ledger(instrument)):
        if int(r.get("wave", -1)) != wave:
            continue
        s = out.setdefault((r["arm"], r["item_id"]), {"collected": False, "attempts": 0})
        s["attempts"] += 1
        s["collected"] |= r["status"] == "collected"
        s["last_status"] = r["status"]
    return out


def missing(wave: int, items: list[str]) -> dict[str, list[str]]:
    """arm -> prompts with no usable answer yet in this wave."""
    out = {}
    for platform in ui.PLATFORMS:
        st = ui_status(platform, wave)
        out[exp004.UI_ARM[platform]] = [i for i in items if not st.get(i, {}).get("collected")]
    for instrument, arms in INSTRUMENT_ARMS.items():
        st = api_status(instrument, wave)
        for arm in arms:
            out[arm] = [i for i in items if not st.get((arm, i), {}).get("collected")]
    return out


def remaining_plan(wave: int, items: list[str], arms=exp004.STUDY_ARMS) -> dict[str, int]:
    """arm -> answers this wave still has to request (the cost guard's prior)."""
    return {arm: len(m) for arm, m in missing(wave, items).items() if arm in arms and m}


# ---------------------------------------------------------------- API workers


def api_worker(instrument: str, jobs: list[tuple[str, str]], wave: int, run_day: str,
               max_tries: int, stop: threading.Event) -> dict:
    """Run one vendor's jobs in order; later passes retry what failed. Returns counts."""
    collector = collect_openai if instrument == "openai" else collect_gemini
    check = exp004.OPENAI_MODEL if instrument == "openai" else exp004.GEMINI_MODEL
    ledger = exp004.JsonlLedger(STUDY.api_ledger(instrument))
    prompts = exp004.load_prompts()
    counts = {"collected": 0, "failed": 0, "empty_answer": 0, "model_mismatch": 0}
    for pass_no in range(1, max_tries + 1):
        status = api_status(instrument, wave)
        todo = [(a, i) for a, i in jobs if not status.get((a, i), {}).get("collected")
                and status.get((a, i), {}).get("attempts", 0) < max_tries]
        if not todo:
            break
        if pass_no > 1:
            log(f"{instrument} w{wave}: retry pass {pass_no}, {len(todo)} answers")
        for arm, item in todo:
            if stop.is_set():
                return counts
            spent = exp004.main_spend()
            if spent > exp004.STUDY_COST_CAP_USD:
                stop.set()
                raise exp004.CostCapError(f"main-study spend ${spent:.2f} passed the "
                                          f"${exp004.STUDY_COST_CAP_USD:.2f} cap; stopping")
            n = status.get((arm, item), {}).get("attempts", 0) + 1
            rec = exp004.api_attempt(
                instrument=instrument, arm=arm, item=item, rnd=wave, text=prompts[item]["text"],
                build=collector.build, send=collector.send, normalize=normalizer(instrument),
                cost=collector.cost, check_model=check, ledger=ledger,
                path=STUDY.api_response(arm, item, wave), strict=True,
                extra={"wave": wave, "study": "main", "attempt": n, "wave_run_date": run_day})
            counts[rec["status"]] += 1
            note = rec.get("error") or "; ".join(rec.get("problems") or [])
            log(f"  {instrument} w{wave} {arm} {item} attempt {n}: {rec['status']}"
                f"{' ' + note[:200] if note else ''}")
            if rec["status"] == "model_mismatch":
                stop.set()
                raise WaveStopped(f"{arm} {item}: {note}; the pinned model check stops the wave")
    return counts


def normalizer(instrument: str):
    return answers.from_openai if instrument == "openai" else answers.from_gemini


def run_api(orders: dict, wave: int, run_day: str, max_tries: int, arms=exp004.STUDY_API_ARMS) -> None:
    """Both vendors at once, one worker each. The first exception stops the other worker."""
    stop = threading.Event()
    plan = {"openai": [j for j in openai_jobs(orders) if j[0] in arms],
            "gemini": [j for j in gemini_jobs(orders) if j[0] in arms]}
    errors = []
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(api_worker, inst, jobs, wave, run_day, max_tries, stop): inst
                   for inst, jobs in plan.items() if jobs}
        for fut in cf.as_completed(futures):
            inst = futures[fut]
            try:
                log(f"{inst} w{wave}: worker done {fut.result()}")
            except BaseException as e:  # noqa: BLE001 - re-raised below after both stop
                stop.set()
                errors.append(e)
                log(f"{inst} w{wave}: worker stopped: {e}")
    if errors:
        raise errors[0]


# ---------------------------------------------------------------- UI


def submit_ui(orders: dict, wave: int, max_tries: int, platforms=ui.PLATFORMS) -> int:
    n = 0
    for platform in orders["ui_platform_order"]:
        if platform in platforms:
            n += ui.submit(platform, orders["ui_order"][platform], wave, tag=exp004.study_tag(wave),
                           log=log, store=STUDY, max_submissions=max_tries)
    return n


def collect_ui(orders: dict, wave: int, max_tries: int, platforms=ui.PLATFORMS,
               wait_s: float = UI_POLL_S, max_wait_s: float = UI_MAX_WAIT_S) -> int:
    """Collect, then resubmit failed tasks and error answers, until none is left to resubmit."""
    for _ in range(max_tries):
        still = ui.collect(platforms, wait_s=wait_s, max_wait_s=max_wait_s, log=log, store=STUDY)
        if still:
            log(f"w{wave}: {still} UI tasks still pending after {max_wait_s / 60:.0f} min; a rerun "
                "of the driver keeps polling them")
            return still
        again = submit_ui(orders, wave, max_tries, platforms)
        if not again:
            return 0
        log(f"w{wave}: resubmitted {again} UI tasks (failed or the app's error message)")
    return 0


# ---------------------------------------------------------------- the wave


def start_wave(state: dict, wave: int, items: list[str], *, any_time: bool, any_day: bool,
               rerun_missing: bool) -> dict:
    """The wave's state entry, created (orders drawn and saved) before anything is sent."""
    key = str(wave)
    info = state["waves"].get(key)
    if info and info.get("stopped"):
        raise WaveStopped(f"wave {wave} was stopped: {info['stopped']}. A person decides what "
                          "happens next; to resume, log a deviation and remove 'stopped' from "
                          f"{state_path()}")
    if info is None:
        if rerun_missing:
            raise SystemExit(f"wave {wave} has not started; --rerun-missing is for a next-day rerun")
        problems = [] if (any_time and any_day) else timing_problems(state, wave)
        if any_time:
            problems = [p for p in problems if "ET; a wave starts" not in p]
        if any_day:
            problems = [p for p in problems if "non-consecutive" not in p]
        if problems:
            raise SystemExit("wave not started:\n  " + "\n  ".join(problems))
        info = {"wave": wave, "run_date": today(), "created_at": exp004.now_iso(),
                "tag": exp004.study_tag(wave), "items": items, **draw_orders(wave, items),
                "reruns": [], "complete": False}
        state["waves"][key] = info
        save_state(state)
        log(f"wave {wave}: orders drawn from seed {info['seed']} and saved to {state_path().name}")
        return info
    if info.get("complete"):
        return info
    if info["run_date"] != today() and today() not in [r["date"] for r in info["reruns"]]:
        if not rerun_missing:
            raise SystemExit(f"wave {wave} started on {info['run_date']}; finishing it today is a "
                             "next-day rerun: pass --rerun-missing (logged as a deviation)")
        miss = missing(wave, info["items"])
        arms = [a for a, m in miss.items() if len(m) > exp004.STUDY_RERUN_OVER]
        if not arms:
            raise SystemExit(f"wave {wave}: no arm misses more than {exp004.STUDY_RERUN_OVER} "
                             "answers; the missing ones are excluded and logged, not rerun")
        info["reruns"].append({"date": today(), "arms": arms,
                               "missing": {a: miss[a] for a in arms}, "at": exp004.now_iso()})
        save_state(state)
        log(f"wave {wave}: DEVIATION next-day rerun for {arms} ({ {a: len(miss[a]) for a in arms} } "
            "missing)")
    return info


def wave_arms(info: dict) -> tuple[str, ...]:
    """Arms this run touches: all of them, or on a rerun day only the rerun arms."""
    reruns = [r for r in info.get("reruns", []) if r["date"] == today()]
    return tuple(reruns[-1]["arms"]) if reruns else exp004.STUDY_ARMS


def check_effort(state: dict, info: dict) -> str:
    """cg_api_low's reasoning setting, the same for every wave (from the cached probe)."""
    effort = collect_openai.probe_effort()
    seen = {w.get("low_effort") for w in state["waves"].values() if w.get("low_effort")}
    if seen and seen != {effort}:
        raise WaveStopped(f"cg_api_low effort {effort!r} differs from earlier waves {seen}")
    info["low_effort"] = effort
    return effort


def run_wave(wave: int, *, any_time: bool = False, any_day: bool = False,
             rerun_missing: bool = False, ui_wait_s: float = UI_POLL_S,
             ui_max_wait_s: float = UI_MAX_WAIT_S) -> dict:
    prompts = exp004.load_prompts()
    items = sorted(prompts)
    if len(items) != exp004.STUDY_N_PROMPTS:
        raise SystemExit(f"expected {exp004.STUDY_N_PROMPTS} prompts, found {len(items)}")
    state = load_state()
    info = start_wave(state, wave, items, any_time=any_time, any_day=any_day,
                      rerun_missing=rerun_missing)
    if info.get("complete"):
        log(f"wave {wave}: already complete")
        return info
    arms = wave_arms(info)
    max_tries = tries_allowed(info)
    run_day = today()
    log(f"wave {wave}: start/resume on {run_day}; arms {list(arms)}; tries allowed {max_tries}")
    if any(exp004.ARMS[a].low_effort for a in arms):
        log(f"wave {wave}: cg_api_low effort {check_effort(state, info)!r}")
        save_state(state)
    STUDY.guard(remaining_plan(wave, items, arms))
    info.setdefault("started_at", exp004.now_iso())
    save_state(state)
    try:
        ui_platforms = tuple(p for p in ui.PLATFORMS if exp004.UI_ARM[p] in arms)
        submit_ui(info, wave, max_tries, ui_platforms)
        run_api(info, wave, run_day, max_tries, arms)
        collect_ui(info, wave, max_tries, ui_platforms, ui_wait_s, ui_max_wait_s)
    except WaveStopped as e:
        info["stopped"] = str(e)
        info["stopped_at"] = exp004.now_iso()
        save_state(state)
        log(f"wave {wave}: STOPPED: {e}")
        raise
    miss = missing(wave, items)
    pending = sum(s["pending"] for p in ui.PLATFORMS for s in ui_status(p, wave).values())
    info["missing"] = {a: m for a, m in miss.items() if m}
    info["finished_at"] = exp004.now_iso()
    info["complete"] = not info["missing"] and not pending
    rerun = [a for a, m in miss.items() if len(m) > exp004.STUDY_RERUN_OVER]
    info["rerun_needed"] = rerun if not pending else []
    save_state(state)
    counts = {a: f"{exp004.STUDY_N_PROMPTS - len(m)}/{exp004.STUDY_N_PROMPTS}" for a, m in miss.items()}
    log(f"wave {wave}: answers {counts}; UI pending {pending}; main spend ${exp004.main_spend():.4f}")
    if pending:
        log(f"wave {wave}: rerun the driver to keep polling the pending UI tasks")
    elif rerun:
        log(f"wave {wave}: {rerun} miss more than {exp004.STUDY_RERUN_OVER} answers; rerun them "
            f"tomorrow with --wave {wave} --rerun-missing (a deviation)")
    elif info["missing"]:
        log(f"wave {wave}: missing answers are excluded and logged: "
            f"{ {a: m for a, m in info['missing'].items()} }")
    return info


# ---------------------------------------------------------------- plan / status


def plan(wave: int) -> dict:
    """What ``--wave N`` would do now. Reads local files only and sends nothing."""
    prompts = exp004.load_prompts()
    items = sorted(prompts)
    state = load_state()
    info = state["waves"].get(str(wave))
    orders = info if info else draw_orders(wave, items)
    planned = remaining_plan(wave, items)
    probe = collect_openai.PROBE_PATH
    effort = json.loads(probe.read_text())["accepted"] if probe.exists() else None
    print(f"experiment 004 main study, wave {wave} (plan only; nothing is sent)")
    print(f"  prompts: {len(items)}; arms: {list(exp004.STUDY_ARMS)}; tag {exp004.study_tag(wave)}")
    print(f"  seed {exp004.STUDY_SEED} combined with wave {wave}: {orders['seed']}; "
          f"orders {'already recorded in ' + state_path().name if info else 'drawn now, recorded at start'}")
    print(f"  UI batches, in order: {orders['ui_platform_order']}")
    for p in orders["ui_platform_order"]:
        o = orders["ui_order"][p]
        print(f"    {p}: {len(o)} tasks, first {o[:5]} ... last {o[-1]}")
    o = orders["api_order"]
    print(f"  API prompt order (both workers): first {o[:5]} ... last {o[-1]}")
    first = [orders["cg_pair_order"][i][0] for i in o]
    print(f"  ChatGPT pair order: cg_api_low first on {first.count('cg_api_low')} prompts, "
          f"cg_api_plain first on {first.count('cg_api_plain')}; first three "
          f"{[(i, orders['cg_pair_order'][i]) for i in o[:3]]}")
    print(f"  OpenAI worker: {len(openai_jobs(orders))} calls; Gemini worker: "
          f"{len(gemini_jobs(orders))} calls; UI tasks: "
          f"{sum(len(v) for v in orders['ui_order'].values())}")
    print(f"  cg_api_low reasoning effort: {effort!r} "
          f"({'cached probe ' + probe.name if effort else 'not probed yet: the run would probe first'})")
    print("  files: " + ", ".join(p.name for p in (
        STUDY.api_ledger("openai"), STUDY.api_ledger("gemini"), STUDY.ui_ledger("chatgpt"),
        STUDY.ui_ledger("gemini"))) + f", {STUDY.api_response('x', 'y', wave).parents[2].name}/, "
          f"{STUDY.ui_responses('chatgpt').name}/, {STUDY.ui_responses('gemini').name}/")
    print(f"  still to request this wave: {planned or 'nothing'}")
    problems = timing_problems(state, wave) if not info else []
    print(f"  timing: {'OK to start now' if not problems else '; '.join(problems)}"
          if not info else f"  timing: wave started {info['run_date']}")
    total = STUDY.guard(planned)
    return {"orders": orders, "planned": planned, "projected_usd": total, "timing": problems}


def status() -> None:
    state = load_state()
    if not state["waves"]:
        print("no main-study wave yet")
    for key, info in sorted(state["waves"].items()):
        wave = int(key)
        miss = missing(wave, info["items"])
        line = {a: f"{len(info['items']) - len(m)}/{len(info['items'])}" for a, m in miss.items()}
        pending = sum(s["pending"] for p in ui.PLATFORMS for s in ui_status(p, wave).values())
        resub = {exp004.UI_ARM[p]: sum(max(s.get("submissions", 0) - 1, 0)
                                       for s in ui_status(p, wave).values()) for p in ui.PLATFORMS}
        fails = {inst: sum(s["attempts"] - s["collected"] for s in api_status(inst, wave).values())
                 for inst in INSTRUMENT_ARMS}
        print(f"wave {wave} ({info['run_date']}): answers {line}; UI pending {pending}; "
              f"UI resubmissions {resub}; API attempts that did not count {fails}; "
              f"complete {info.get('complete')}; reruns {[r['date'] for r in info.get('reruns', [])]}"
              + (f"; STOPPED: {info['stopped']}" if info.get("stopped") else ""))
    print(f"main-study spend recorded: ${exp004.main_spend():.4f} of ${exp004.STUDY_COST_CAP_USD:.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wave", type=int, choices=exp004.STUDY_WAVES)
    ap.add_argument("--plan", action="store_true", help="print the plan and the cost guard; send nothing")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--rerun-missing", action="store_true",
                    help="next-day rerun of an arm missing more than 4 answers (a deviation)")
    ap.add_argument("--any-time", action="store_true", help="skip the 10:00 to 14:00 ET start window")
    ap.add_argument("--any-day", action="store_true", help="skip the non-consecutive-day check")
    a = ap.parse_args()
    if a.status:
        status()
        return
    if a.wave is None:
        ap.error("--wave is required")
    if a.plan:
        plan(a.wave)
        return
    for name in ("OPENAI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "DATAFORSEO_API_KEY"):
        exp004.env_value(name)
    for attempt in range(1, 4):
        try:
            run_wave(a.wave, any_time=a.any_time, any_day=a.any_day, rerun_missing=a.rerun_missing)
            return
        except SystemExit:  # the cost cap, a stopped wave, a refused start: never retried
            raise
        except Exception:
            log(f"wave {a.wave}: attempt {attempt} raised:\n{traceback.format_exc()}")
            if attempt == 3:
                raise
            time.sleep(300)
            a.any_time = a.any_day = True  # the wave has started; the guards were checked once


if __name__ == "__main__":
    main()
