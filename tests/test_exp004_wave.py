"""Experiment 004 main-study wave driver: orders, plan, ledger separation, cost guard, retries,
resubmissions and the pinned-model stop. Every transport is a fake from the pipeline's synthetic
world (``pipeline/synthetic.py``), so nothing is sent anywhere. Fake brands only."""

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "004-api-vs-ui"
HARNESS, PIPELINE = EXP / "harness", EXP / "pipeline"
sys.path.insert(0, str(HARNESS))
#: Other experiments' tests leave modules with these names in ``sys.modules``.
SHADOWED = ("brands", "common", "synthetic", "01_frame", "02_audit", "03_model", "power_sim")


def _load_pipeline(*names):
    saved = {n: sys.modules.pop(n) for n in SHADOWED if n in sys.modules}
    sys.path.insert(0, str(PIPELINE))
    try:
        return [importlib.import_module(n) for n in names]
    finally:
        sys.path.remove(str(PIPELINE))
        for n in SHADOWED:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


(synthetic,) = _load_pipeline("synthetic")
run_wave, ui = synthetic.run_wave, synthetic.ui
collect_openai, collect_gemini = synthetic.collect_openai, synthetic.collect_gemini
exp004 = run_wave.exp004
ITEMS = synthetic.ITEMS
#: Every exp004 module object the driver's modules hold (another test may have reloaded it).
EXP004_MODULES = {m.exp004 for m in (run_wave, ui, collect_openai, collect_gemini, synthetic,
                                     synthetic.common)}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake collection world in ``tmp_path``: real driver, fake transports."""
    prompts = synthetic.write_inputs(tmp_path)
    w = synthetic.World("planted")
    original = exp004.load_prompts
    for mod in EXP004_MODULES:
        monkeypatch.setattr(mod, "RAW", tmp_path)
        monkeypatch.setattr(mod, "load_prompts", lambda path=None: original(prompts))
    monkeypatch.setattr(collect_openai, "PROBE_PATH", tmp_path / "low_effort_probe.json")
    monkeypatch.setattr(collect_openai, "send", w.openai_send)
    monkeypatch.setattr(collect_gemini, "send", w.gemini_send)
    monkeypatch.setattr(ui, "_key", lambda: "synthetic")
    monkeypatch.setattr(ui, "post_tasks", w.post_tasks)
    monkeypatch.setattr(ui, "get_task", w.get_task)
    monkeypatch.setattr(ui, "POLL_SLEEP_S", 0)
    return w


def _run(w, wave, **kw):
    w.wave = wave
    return run_wave.run_wave(wave, any_time=True, any_day=True, ui_wait_s=0, ui_max_wait_s=0, **kw)


# ---------------------------------------------------------------- orders


def test_orders_are_seeded_per_wave_and_cover_everything():
    a, b = run_wave.draw_orders(1, ITEMS), run_wave.draw_orders(1, list(reversed(ITEMS)))
    assert a == b and a["seed"] == [20261106, 1]
    c = run_wave.draw_orders(2, ITEMS)
    assert c["api_order"] != a["api_order"] and c["ui_order"] != a["ui_order"]
    for o in (a, c):
        assert sorted(o["ui_platform_order"]) == ["chatgpt", "gemini"]
        assert all(sorted(v) == ITEMS for v in o["ui_order"].values())
        assert sorted(o["api_order"]) == ITEMS
        assert all(sorted(p) == ["cg_api_low", "cg_api_plain"] for p in o["cg_pair_order"].values())
        firsts = {p[0] for p in o["cg_pair_order"].values()}
        assert firsts == {"cg_api_low", "cg_api_plain"}
    jobs = run_wave.openai_jobs(a)
    assert len(jobs) == 80 and jobs[0][1] == jobs[1][1] == a["api_order"][0]  # back to back
    assert [i for _a, i in run_wave.gemini_jobs(a)] == a["api_order"]
    with pytest.raises(SystemExit):
        run_wave.draw_orders(4, ITEMS)


def test_plan_sends_nothing_and_writes_nothing(world, tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("plan must not send")

    for target, name in ((collect_openai, "send"), (collect_gemini, "send"), (ui, "post_tasks"),
                         (ui, "get_task")):
        monkeypatch.setattr(target, name, boom)
    before = sorted(p.name for p in tmp_path.iterdir())
    out = run_wave.plan(1)
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert out["planned"] == {a: 40 for a in exp004.STUDY_ARMS}
    assert "nothing is sent" in capsys.readouterr().out


def test_orders_are_saved_before_the_first_request(world, monkeypatch):
    seen = []

    def first_post(key, specs, **kw):
        state = json.loads(run_wave.state_path().read_text())
        seen.append(state["waves"]["1"]["api_order"])
        return world.post_tasks(key, specs, **kw)

    monkeypatch.setattr(ui, "post_tasks", first_post)
    _run(world, 1)
    assert seen and seen[0] == run_wave.draw_orders(1, ITEMS)["api_order"]
    first_ui = json.loads(run_wave.state_path().read_text())["waves"]["1"]["ui_platform_order"][0]
    recs = exp004.read_jsonl(exp004.STUDY.ui_ledger(first_ui))
    order = run_wave.draw_orders(1, ITEMS)["ui_order"][first_ui]
    assert [r["item_id"] for r in recs if r["status"] == "submitted"][:40] == order
    assert all(r["tag"] == "aeo-exp004-w1" for r in recs)


# ---------------------------------------------------------------- the wave


def test_wave_collects_retries_and_resubmits(world, tmp_path):
    info = _run(world, 1)
    assert info["complete"] and not info["missing"]
    # The planted Gemini app error answer was resubmitted once; nothing else was.
    subs = {exp004.UI_ARM[p]: run_wave.ui_status(p, 1) for p in ui.PLATFORMS}
    assert subs["gm_ui"]["b2b_05"]["submissions"] == 2 and subs["gm_ui"]["b2b_05"]["error_answers"] == 1
    assert sum(s["submissions"] for s in subs["cg_ui"].values()) == 40
    # Wave files are the main study's own; no pilot-named file was written.
    names = {p.name for p in tmp_path.iterdir()}
    assert {"ledger_main_api_openai.jsonl", "ledger_main_api_gemini.jsonl", "ledger_main_ui_chatgpt.jsonl",
            "ledger_main_ui_gemini.jsonl", "responses_main_api", "responses_main_ui_chatgpt",
            "responses_main_ui_gemini", "main_state.json", "run_wave.log"} <= names
    assert not [n for n in names if n.startswith(("ledger_api_", "ledger_ui_", "responses_ui_"))
                or n == "responses"]
    # API records hold the wave, the attempt and the low-effort setting.
    recs = exp004.read_jsonl(exp004.STUDY.api_ledger("openai"))
    assert len(recs) == 80 and all(r["wave"] == 1 and r["study"] == "main" for r in recs)
    assert {r["effort_requested"] for r in recs if r["arm"] == "cg_api_low"} == {"none"}


def test_resume_is_idempotent(world, monkeypatch):
    _run(world, 1)
    calls = []
    monkeypatch.setattr(collect_openai, "send", lambda body: calls.append(body))
    monkeypatch.setattr(ui, "post_tasks", lambda *a, **k: calls.append(a))
    info = _run(world, 1)
    assert info["complete"] and calls == []


def test_api_failures_stop_after_three_attempts(world):
    _run(world, 1)
    info = _run(world, 2)
    st = run_wave.api_status("gemini", 2)
    assert st[("gm_api_plain", "b2b_33")] == {"collected": False, "attempts": 3, "last_status": "failed"}
    assert info["missing"] == {"gm_api_plain": ["b2b_33"]} and not info["complete"]
    assert info["rerun_needed"] == []  # 1 missing is excluded and logged, not rerun
    retried = run_wave.api_status("openai", 2)
    assert all(s["collected"] for s in retried.values())


def test_model_mismatch_stops_the_wave(world, monkeypatch):
    def wrong_model(body):
        res = world.openai_send(body)
        res.body["model"] = "gpt-6-sol"
        return res

    monkeypatch.setattr(collect_openai, "send", wrong_model)
    with pytest.raises(run_wave.WaveStopped):
        _run(world, 1)
    state = json.loads(run_wave.state_path().read_text())
    assert "pinned model" in state["waves"]["1"]["stopped"]
    recs = exp004.read_jsonl(exp004.STUDY.api_ledger("openai"))
    assert len(recs) == 1 and recs[0]["status"] == "model_mismatch"
    gm = exp004.read_jsonl(exp004.STUDY.api_ledger("gemini"))
    assert len(gm) < 40  # the other worker stopped too
    with pytest.raises(run_wave.WaveStopped):  # a rerun refuses until a person clears it
        _run(world, 1)


def test_cost_guard_counts_main_spend_only(world, tmp_path):
    # Pilot-era spend far over the study cap does not count against it ...
    exp004.JsonlLedger(tmp_path / "ledger_api_openai.jsonl").append(
        {"arm": "cg_api_low", "item_id": "b2b_01", "round": 1, "status": "collected", "cost_usd": 500.0})
    assert exp004.main_spend() == 0.0
    assert exp004.total_spend() == pytest.approx(500.0)
    # ... and main-study spend does not count against the pilot's.
    exp004.JsonlLedger(exp004.STUDY.api_ledger("gemini")).append(
        {"arm": "gm_api_plain", "item_id": "b2b_01", "wave": 1, "status": "failed", "cost_usd": 30.0})
    exp004.JsonlLedger(exp004.STUDY.ui_ledger("chatgpt")).append(
        {"task_id": "t", "status": "submitted", "cost": 0.5})
    (tmp_path / "brand_candidates_main.jsonl").write_text(json.dumps({"cost_usd": 0.25}) + "\n")
    assert exp004.main_spend() == pytest.approx(30.75)
    assert exp004.total_spend() == pytest.approx(500.0)
    # 30.75 + a full wave's prior (about $20.59) passes $45: the wave refuses to start.
    with pytest.raises(exp004.CostCapError):
        _run(world, 1)
    assert not exp004.STUDY.ui_ledger("gemini").exists()


def test_timing_guards():
    from datetime import datetime

    state = {"waves": {"1": {"run_date": "2026-11-06"}}}
    late = datetime(2026, 11, 8, 15, 0)
    probs = run_wave.timing_problems(state, 2, late)
    assert len(probs) == 1 and "14:00" in probs[0]
    assert run_wave.timing_problems(state, 2, datetime(2026, 11, 8, 11, 0)) == []
    assert any("non-consecutive" in p for p in run_wave.timing_problems(state, 2, datetime(2026, 11, 7, 11)))
    assert any("wave 2 has not run" in p for p in run_wave.timing_problems(state, 3, datetime(2026, 11, 10, 11)))


def test_next_day_rerun_needs_the_flag_and_a_large_miss(world, monkeypatch):
    _run(world, 1)
    _run(world, 2)
    monkeypatch.setattr(run_wave, "today", lambda: "2026-12-01")
    with pytest.raises(SystemExit, match="--rerun-missing"):
        _run(world, 2)
    with pytest.raises(SystemExit, match="excluded and logged"):
        _run(world, 2, rerun_missing=True)  # only 1 answer missing: no rerun


def test_strict_attempt_marks_empty_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(exp004, "RAW", tmp_path)
    led = exp004.JsonlLedger(tmp_path / "l.jsonl")
    body = {"model": "gpt-6-luna", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": "  ", "annotations": []}]}]}
    common = dict(instrument="openai", arm="cg_api_plain", item="b2b_01", rnd=1, text="Prompt",
                  build=lambda arm, text: ({"model": "gpt-6-luna"}, {}),
                  send=lambda b: exp004.HttpResult(200, body, None, 1),
                  normalize=synthetic.run_wave.answers.from_openai,
                  cost=lambda raw, norm: {"total": 0.01}, check_model="gpt-6-luna", ledger=led,
                  path=tmp_path / "r.json")
    assert exp004.api_attempt(**common)["status"] == "collected"  # the pilot's rule
    assert exp004.api_attempt(**common, strict=True)["status"] == "empty_answer"
