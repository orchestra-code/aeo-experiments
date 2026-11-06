"""Experiment 004 harness: parsers for the four instruments, the gap, the cost guard,
idempotent collection and the pilot's arm order. All fixtures are synthetic, with
made-up brands (Acmeflow, Zentrik, Brightdesk, Quillo)."""

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "004-api-vs-ui"
sys.path.insert(0, str(EXP / "harness"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exp004 = _load("exp004", EXP / "harness" / "exp004.py")
answers = _load("answers", EXP / "harness" / "answers.py")
run_pilot = _load("exp004_run_pilot", EXP / "harness" / "run_pilot.py")
report = _load("exp004_pilot_report", EXP / "pipeline" / "pilot_report.py")

# ---------------------------------------------------------------- parsers


def test_dataforseo_parser():
    raw = {
        "model": "gpt-6",
        "markdown": "Try **Acmeflow** ([acmeflow.com](https://www.acmeflow.com/p?utm_source=x)) "
                    "or Zentrik.",
        "sources": [{"url": "https://www.review.example.com/a", "domain": "review.example.com"},
                    {"url": "https://zentrik.io/pricing"}],
        "search_results": [{"url": "https://a.example.co.uk/x"}, {"url": "https://zentrik.io/"}],
        "fan_out_queries": ["best crm tools", "acmeflow vs zentrik"],
    }
    n = answers.from_dataforseo(raw)
    assert n["model"] == "gpt-6"
    assert n["n_searches"] == 2 and n["search_queries"][1] == "acmeflow vs zentrik"
    assert n["cited_domains"] == ["example.com", "zentrik.io", "acmeflow.com"]
    assert n["evaluated_domains"] == ["example.co.uk", "zentrik.io"]
    # Gemini UI: no fan-out, no search_results
    g = answers.from_dataforseo({"model": "3.5 Flash-Lite", "markdown": "Quillo.",
                                 "sources": [{"url": "https://quillo.app/"}]})
    assert g["n_searches"] == 0 and g["evaluated_domains"] == ["quillo.app"]


def test_openai_parser():
    raw = {
        "model": "gpt-6-luna", "status": "completed", "reasoning": {"effort": "none"},
        "output": [
            {"type": "web_search_call", "action": {"type": "search", "query": "best helpdesk",
                                                   "sources": [{"url": "https://brightdesk.com/x"},
                                                               {"url": "https://g.example.org/"}]}},
            {"type": "web_search_call", "action": {"type": "search", "queries": ["a", "b"]}},
            {"type": "web_search_call", "action": {"type": "open_page", "url": "https://quillo.app/"}},
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": "Brightdesk leads.",
                                             "annotations": [{"type": "url_citation",
                                                              "url": "https://brightdesk.com/x"}]}]},
        ],
    }
    n = answers.from_openai(raw)
    assert n["answer_text"] == "Brightdesk leads."
    assert n["model"] == "gpt-6-luna" and n["reasoning_effort"] == "none"
    assert n["n_web_search_calls"] == 3 and n["n_searches"] == 2
    assert n["search_queries"] == ["best helpdesk", "a", "b"]
    assert n["cited_domains"] == ["brightdesk.com"]
    assert n["evaluated_domains"] == ["brightdesk.com", "example.org", "quillo.app"]


def test_gemini_parser_domains_from_title():
    redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbC"
    raw = {
        "modelVersion": "gemini-3.5-flash-lite",
        "candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [{"text": "thinking", "thought": True},
                                  {"text": "Acmeflow and "}, {"text": "Zentrik."}]},
            "groundingMetadata": {
                "webSearchQueries": ["crm for startups", "acmeflow pricing"],
                "groundingChunks": [{"web": {"uri": redirect + "1", "title": "acmeflow.com"}},
                                    {"web": {"uri": redirect + "2", "title": "www.reviews.co.uk"}},
                                    {"web": {"uri": redirect + "3", "title": "A page title"}}],
                "groundingSupports": [{"groundingChunkIndices": [1, 0]}, {"groundingChunkIndices": [1]}],
            },
        }],
    }
    n = answers.from_gemini(raw)
    assert n["answer_text"] == "Acmeflow and Zentrik."
    assert n["model"] == "gemini-3.5-flash-lite" and n["n_searches"] == 2
    assert n["cited_domains"] == ["reviews.co.uk", "acmeflow.com"]
    assert n["evaluated_domains"] == ["acmeflow.com", "reviews.co.uk"]
    assert n["n_chunks_no_domain"] == 1 and n["domain_source"] == "web.title"


def test_error_answer_detection():
    assert answers.is_error_answer("Sorry, something went wrong. Please try your request again.")
    assert answers.is_error_answer("   ")
    assert answers.is_error_answer("I encountered an error doing what you asked. Could you try again?")
    assert not answers.is_error_answer("Something went wrong with legacy tools, so try Acmeflow. " * 10)
    assert not answers.is_error_answer("Acmeflow and Zentrik are the usual picks.")


# ---------------------------------------------------------------- gap


def _frame(rows):
    return pd.DataFrame([{"arm": a, "item_id": i, "round": r, "brands": b,
                          "answer_text": t[0] if (t := rest) else " and ".join(b) + "."}
                         for a, i, r, b, *rest in rows])


def test_planted_gap():
    """UI identical across rounds (within = 1); the arm shares 1 of 3 brands (cross = 1/3)."""
    rows = []
    for item in ("b2b_01", "b2b_06", "b2b_09", "b2b_14"):
        for rnd in (1, 2, 3):
            rows.append(("cg_ui", item, rnd, ["Acmeflow", "Zentrik"]))
        rows.append(("cg_api_plain", item, 1, ["Acmeflow", "Quillo"]))
    res, data = report.brand_gap(_frame(rows), "cg_api_plain", "cg_ui")
    assert Counter(data.condition) == {"within": 12, "cross": 12}
    assert res.estimate == pytest.approx(1 - 1 / 3)
    assert res.lo == pytest.approx(res.estimate) and res.hi == pytest.approx(res.estimate)


def test_gap_zero_when_arm_matches_ui_noise():
    rows = []
    sets = (["Acmeflow", "Zentrik"], ["Acmeflow", "Quillo"], ["Acmeflow", "Zentrik"])
    for item in ("b2b_01", "b2b_06", "b2b_09"):
        for rnd, s in enumerate(sets, 1):
            rows.append(("gm_ui", item, rnd, s))
        rows.append(("gm_api_plain", item, 1, ["Acmeflow", "Zentrik"]))
    res, _ = report.brand_gap(_frame(rows), "gm_api_plain", "gm_ui")
    within = (1 / 3 + 1 + 1 / 3) / 3
    cross = (1 + 1 / 3 + 1) / 3
    assert res.estimate == pytest.approx(within - cross)


def test_gap_drops_app_error_answers():
    """An app error message is a missing answer, not an empty brand set."""
    rows = []
    for item in ("b2b_01", "b2b_06", "b2b_09"):
        for rnd in (1, 2, 3):
            rows.append(("gm_ui", item, rnd, ["Acmeflow", "Zentrik"]))
        rows.append(("gm_api_plain", item, 1, ["Acmeflow", "Zentrik"]))
    rows[0] = ("gm_ui", "b2b_01", 1, [], "I encountered an error doing what you asked. Could you try again?")
    res, data = report.brand_gap(_frame(rows), "gm_api_plain", "gm_ui")
    assert Counter(data.condition) == {"within": 7, "cross": 8}
    assert res.estimate == pytest.approx(0.0)


# ---------------------------------------------------------------- cost


def test_cost_guard_refuses_past_cap():
    assert exp004.guard_cost({"cg_api_plain": 10}, spent=1.0) == pytest.approx(2.0)
    with pytest.raises(exp004.CostCapError):
        exp004.guard_cost({"cg_api_low": 10}, spent=7.0)  # 7 + 10 x 0.35 > 10


def test_total_spend_reads_every_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(exp004, "RAW", tmp_path)
    exp004.JsonlLedger(tmp_path / "ledger_api_openai.jsonl").append(
        {"arm": "cg_api_plain", "item_id": "b2b_01", "round": 1, "status": "collected", "cost_usd": 0.5})
    exp004.JsonlLedger(tmp_path / "smoke_ledger_api_gemini.jsonl").append(
        {"arm": "gm_api_plain", "item_id": "b2b_01", "round": 1, "status": "failed", "cost_usd": 9.0})
    led = exp004.JsonlLedger(tmp_path / "ledger_ui_chatgpt.jsonl")
    led.append({"task_id": "t1", "status": "submitted", "cost": 0.0024})
    led.append({"task_id": "t1", "status": "collected", "cost": 0.0024})
    (tmp_path / "low_effort_probe.json").write_text(json.dumps({"cost_usd": 0.001}))
    assert exp004.total_spend() == pytest.approx(0.5 + 0.0024 + 0.001)
    with pytest.raises(exp004.CostCapError):
        exp004.guard_cost({"cg_api_plain": 95})


def test_api_costs():
    usage = {"input_tokens": 10_000, "output_tokens": 2_000,
             "input_tokens_details": {"cached_tokens": 1_000, "cache_write_tokens": 4_000}}
    c = exp004.openai_cost(usage, 3)
    assert c["input"] == pytest.approx(5_000 * 0.10 / 1e6)
    assert c["total"] == pytest.approx(5e-4 + 1e-5 + 5e-4 + 1e-3 + 0.03)
    g = exp004.gemini_cost({"promptTokenCount": 1000, "candidatesTokenCount": 500,
                            "thoughtsTokenCount": 500}, 2)
    assert g["total"] == pytest.approx(1000 * 0.30 / 1e6 + 1000 * 2.50 / 1e6 + 2 * 0.014)


# ---------------------------------------------------------------- collection


def test_api_runner_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(exp004, "RAW", tmp_path)
    monkeypatch.setattr(exp004, "load_prompts", lambda: {
        "b2b_01": {"text": "made-up prompt one", "category": "CRM"},
        "b2b_06": {"text": "made-up prompt two", "category": "CRM"}})
    calls = []

    def send(body):
        calls.append(body)
        if body["input"].endswith("two") and len(calls) == 2:
            return exp004.HttpResult(503, None, "HTTP 503", 4)
        return exp004.HttpResult(200, {"model": "gpt-6-luna", "usage": {}, "output": [
            {"type": "web_search_call", "action": {"type": "search", "query": "q"}},
            {"type": "message", "content": [{"type": "output_text", "text": "Acmeflow."}]}]}, None, 1)

    kw = dict(instrument="openai", arms=["cg_api_plain"], items=["b2b_01", "b2b_06"], rnd=1,
              prefix="", build=lambda arm, text: ({"model": "gpt-6-luna", "input": text}, {}),
              send=send, normalize=answers.from_openai,
              cost=lambda raw, norm: exp004.openai_cost(raw.get("usage"), 1),
              check_model="gpt-6-luna", workers=1, log=lambda m: None)
    first = exp004.run_api_jobs(**kw)
    assert first == {"ok": 1, "failed": 1, "skipped": 0}
    second = exp004.run_api_jobs(**kw)  # only the failed one is retried
    assert second == {"ok": 1, "failed": 0, "skipped": 1}
    third = exp004.run_api_jobs(**kw)
    assert third["ok"] == 0 and len(calls) == 3
    recs = exp004.JsonlLedger(tmp_path / "ledger_api_openai.jsonl").records()
    assert all("made-up" not in json.dumps(r) for r in recs)  # no prompt text in the ledger
    saved = json.loads(exp004.response_path("", "cg_api_plain", "b2b_01", 1).read_text())
    assert saved["normalized"]["n_web_search_calls"] == 1


def test_pilot_order_uses_every_api_arm_once():
    order = run_pilot.draw_order()
    assert order == run_pilot.draw_order(exp004.SEED)
    flat = [a for arms in order.values() for a in arms]
    assert sorted(flat) == sorted(exp004.API_ARMS)
    assert sorted(len(v) for v in order.values()) == [1, 2, 2]
    assert set(order) == set(exp004.UI_ROUNDS)


def test_pilot_items():
    assert exp004.PILOT_ITEMS == ("b2b_01", "b2b_06", "b2b_09", "b2b_14", "b2b_17", "b2b_22",
                                  "b2b_25", "b2b_30", "b2b_33", "b2b_38")


def test_selection_rule():
    assert report.select_arm({}) is None
    assert report.select_arm({"cg_api_plain": 0.12, "cg_api_leak": 0.10}) == "cg_api_plain"
    assert report.select_arm({"cg_api_plain": 0.14, "cg_api_leak": 0.10}) == "cg_api_leak"
    assert report.select_arm({"cg_api_low": 0.05, "cg_api_leak": 0.08}) == "cg_api_low"
    assert report.select_arm({"gm_api_plain": 0.13, "gm_api_leak": 0.10}) == "gm_api_plain"


def test_question_back_flag():
    assert report.question_only({"answer_text": "What size is your team?", "brands": []})
    assert not report.question_only({"answer_text": "Acmeflow fits. Want more?", "brands": ["Acmeflow"]})
