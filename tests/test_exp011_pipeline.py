"""Experiment 011 analysis pipeline: bootstrap, Holm, gates, audits, synthetic dry run.

The pipeline lives outside the installed package and its modules share names with other
experiments' pipelines (``brands``, ``common``, ``03_model``), which other test modules may
already have imported. ``_load`` loads 011's copies with those names swapped out of ``sys.modules`` and
restores them afterwards. The end-to-end dry run (spec §8 step 3) runs the stage scripts as
subprocesses with the synthetic worlds redirected to a temporary directory. Nothing here reads
real answers, and no fake data uses a real brand name.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aeo_research.claude_answers import from_api_message, from_claude_code_stream, from_claude_export
from aeo_research.overlap import cluster_boot

EXP = Path(__file__).resolve().parents[1] / "experiments" / "011-claude-code-fidelity"
PIPELINE = EXP / "pipeline"
#: Other experiments' tests leave modules with these names in ``sys.modules``, and 009's test
#: imports its own ``03_model`` and ``02_audit``, so each must be swapped out to load 011's.
SHADOWED = ("brands", "common", "shares", "01_features", "02_audit", "03_model")


def _load(*names: str) -> dict:
    saved = {n: sys.modules.pop(n) for n in SHADOWED if n in sys.modules}
    sys.path.insert(0, str(PIPELINE))
    try:
        return {n: importlib.import_module(n) for n in names}
    finally:
        sys.path.remove(str(PIPELINE))
        for n in SHADOWED:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


_mods = _load("brands", "common", "01_features", "02_audit", "03_model")
brands, common = _mods["brands"], _mods["common"]
features, audit, model = _mods["01_features"], _mods["02_audit"], _mods["03_model"]

_lex_spec = importlib.util.spec_from_file_location(
    "exp011_lexicon_candidates", EXP / "harness" / "lexicon_candidates.py")
lexicon_candidates = importlib.util.module_from_spec(_lex_spec)
sys.modules[_lex_spec.name] = lexicon_candidates
_lex_spec.loader.exec_module(lexicon_candidates)

LEXICON_ROWS = ("canonical,aliases,category,decision,reason,match,n_answers\n"
                "fakeone,Fakeone|Fakeone Cloud,crm,keep,in category,ci,3\n"
                "faketwo,Faketwo,crm,keep,in category,cs,1\n"
                "fakeledger,Fakeledger,crm,drop,out of category,ci,1\n")


@pytest.fixture
def patterns(tmp_path):
    lex = tmp_path / "lex.csv"
    lex.write_text(LEXICON_ROWS)
    return brands.load_lexicon(lex)


# ------------------------------------------------------------- constants


def test_design_constants_match_the_spec():
    assert common.SEED == 20261103
    assert common.WAVES == (1, 2, 3)
    assert (common.N_BOOT, common.ALPHA, common.SESOI) == (2000, 0.10, 0.10)
    assert (common.H_POS_MIN, common.RBO_P, common.TOP_K) == (0.10, 0.9, 10)
    assert common.REFERENCE == "ui_default"
    assert common.PRIMARY_ARMS == ("cc_stock_full", "sched_kit")
    assert common.SECONDARY_ARMS == ("cc_none_search", "opus55_plain")
    assert common.PROMPTS_CSV.parts[-4:] == ("009-claude-model-fidelity", "data", "raw", "prompts.csv")
    assert brands.LEXICON.name == "lexicon_v1_2.csv"


# ------------------------------------------------------------- bootstrap


def _toy_pairs(seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(30):
        base = rng.uniform(0.3, 0.8)
        for _ in range(3):
            rows.append(("within:ui_default", f"b2b_{p:02d}", base + rng.normal(0, 0.1)))
            rows.append(("cross:arm|ui_default", f"b2b_{p:02d}", base - 0.05 + rng.normal(0, 0.1)))
    df = pd.DataFrame(rows, columns=["condition", "cluster_i", "value"])
    df.loc[[4, 17], "value"] = np.nan
    df["cluster_j"] = df["cluster_i"]
    return df


def test_boot_combo_reproduces_cluster_boot_draw_for_draw():
    pairs = _toy_pairs()
    ref = cluster_boot(pairs, contrast=("within:ui_default", "cross:arm|ui_default"),
                       n_boot=400, seed=common.SEED)
    b = model.boot_combo(pairs, "value", {"within:ui_default": 1.0, "cross:arm|ui_default": -1.0},
                         n_boot=400, seed=common.SEED)
    assert b.estimate == pytest.approx(ref.estimate)
    assert b.ci(0.10) == pytest.approx((ref.lo, ref.hi))
    assert b.n_nan == ref.n_nan == 2


def test_boot_combo_handles_cross_cluster_pairs_like_cluster_boot():
    rng = np.random.default_rng(5)
    rows = [("a" if k % 2 else "b", f"p{rng.integers(10)}", f"p{rng.integers(10)}", rng.random())
            for k in range(300)]
    pairs = pd.DataFrame(rows, columns=["condition", "cluster_i", "cluster_j", "value"])
    ref = cluster_boot(pairs, contrast=("a", "b"), n_boot=200, seed=11)
    b = model.boot_combo(pairs, "value", {"a": 1.0, "b": -1.0}, n_boot=200, seed=11)
    assert b.ci(0.10) == pytest.approx((ref.lo, ref.hi))


def test_boot_combo_missing_condition_is_inconclusive_not_a_crash():
    b = model.boot_combo(_toy_pairs(), "value", {"within:ui_default": 1.0, "cross:none": -1.0}, n_boot=50)
    assert b.draws.size == 0 and np.isnan(b.estimate) and np.isnan(b.tost_p())
    assert model.verdict_of(*b.ci()) is model.Verdict.INCONCLUSIVE


def test_tost_p_is_the_larger_tail_at_the_band_edges():
    b = model.Boot(0.0, np.array([-0.2, -0.05, 0.0, 0.05, 0.12, 0.15]), 1, 1, 0)
    assert b.tost_p(0.10) == pytest.approx(2 / 6)


def test_verdict_mapping_follows_the_decision_table():
    V = model.Verdict
    assert model.verdict_of(-0.05, 0.05) is V.NULL
    assert model.verdict_of(0.01, 0.05) is V.NEGLIGIBLE
    assert model.verdict_of(0.05, 0.3) is V.REAL
    assert model.verdict_of(-0.2, 0.2) is V.INCONCLUSIVE
    assert model.verdict_of(-0.02, 0.12) is V.INCONCLUSIVE
    assert set(model.CONCLUSION) == {v.name for v in V}


# ------------------------------------------------------------------ Holm


def _holm_ctx(**normals):
    ctx = model.Ctx.__new__(model.Ctx)
    rng = np.random.default_rng(0)
    ctx.boots = {k: model.Boot(mu, rng.normal(mu, sd, 2000), 40, 1, 0) for k, (mu, sd) in normals.items()}
    keys = list(normals)
    rows = [{"p_tost": ctx.boots[k].tost_p()} for k in keys]
    model.holm(ctx, rows, keys)
    return dict(zip(keys, rows))


def test_holm_one_pass_one_fail():
    r = _holm_ctx(fails=(0.3, 0.03), passes=(0.0, 0.02))
    assert r["passes"]["holm_rank"] == 1 and r["fails"]["holm_rank"] == 2
    assert r["passes"]["ci_level"] == pytest.approx(0.95)
    assert r["fails"]["ci_level"] == pytest.approx(0.90)
    assert r["passes"]["verdict"] == "NULL" and r["fails"]["verdict"] == "REAL"
    assert "holm_stepdown_note" not in r["fails"]


def test_holm_both_pass_uses_95_then_90():
    r = _holm_ctx(close=(0.05, 0.028), closer=(0.0, 0.03))
    assert r["closer"]["p_tost"] < r["close"]["p_tost"]
    first, second = r["closer"], r["close"]
    assert (first["holm_rank"], second["holm_rank"]) == (1, 2)
    assert (first["ci_level"], second["ci_level"]) == pytest.approx((0.95, 0.90))
    # The first CI is wider than its own 90% CI; the second is its 90% CI.
    assert first["lo"] < first["lo_unadjusted"] and first["hi"] > first["hi_unadjusted"]
    assert (second["lo"], second["hi"]) == (second["lo_unadjusted"], second["hi_unadjusted"])
    assert all(x["verdict"] in ("NULL", "NEGLIGIBLE") for x in (first, second))
    assert first["p_holm"] == pytest.approx(2 * first["p_tost"])


def test_holm_tied_p_values_keep_the_spec_order():
    r = _holm_ctx(cc_stock_full=(0.02, 0.01), sched_kit=(0.0, 0.01))
    assert r["cc_stock_full"]["p_tost"] == r["sched_kit"]["p_tost"] == 0.0
    assert r["cc_stock_full"]["holm_rank"] == 1 and r["sched_kit"]["holm_rank"] == 2


def test_holm_step_down_is_flagged_when_only_the_higher_p_passes():
    """Rank 1 has the smaller p but fails at 95%; rank 2 passes at 90%. Reported, not hidden."""
    ctx = model.Ctx.__new__(model.Ctx)
    near = np.concatenate([np.full(1940, 0.02), np.full(40, 0.0999), np.full(20, 0.11)])
    fails95 = np.concatenate([np.full(1900, 0.05), np.full(90, 0.105), np.full(10, 0.2)])
    ctx.boots = {"b": model.Boot(0.02, near, 40, 1, 0), "c": model.Boot(0.05, fails95, 40, 1, 0)}
    rows = [{"p_tost": 0.001}, {"p_tost": 0.01}]
    model.holm(ctx, rows, ["c", "b"])
    assert rows[0]["holm_rank"] == 1 and rows[0]["verdict"] == "REAL"
    assert rows[1]["verdict"] in ("NULL", "NEGLIGIBLE") and "holm_stepdown_note" in rows[1]


def test_holm_sorts_a_missing_test_last():
    ctx = model.Ctx.__new__(model.Ctx)
    ctx.boots = {"gone": model.Boot(float("nan"), np.array([]), 0, 0, 0),
                 "ok": model.Boot(0.0, np.random.default_rng(1).normal(0, 0.02, 500), 40, 1, 0)}
    rows = [{"p_tost": float("nan")}, {"p_tost": 0.0}]
    model.holm(ctx, rows, ["gone", "ok"])
    assert rows[1]["holm_rank"] == 1 and rows[0]["holm_rank"] == 2
    assert rows[0]["verdict"] == "INCONCLUSIVE"


# ------------------------------------------------------------- contrasts


def _frame(arm_brands: dict, *, waves=(1, 2, 3), items=("b2b_01", "b2b_02"), category=None) -> pd.DataFrame:
    rows = []
    for arm, fn in arm_brands.items():
        for item in items:
            for wave in waves:
                rows.append({"arm": arm, "item_id": item, "wave": wave,
                             "category": (category or {}).get(item, "c"), "brands": fn(item, wave),
                             "cited_domains": [], "evaluated_domains": []})
    return pd.DataFrame(rows)


def test_build_pairs_conditions_and_counts():
    df = _frame({"ui_default": lambda i, w: [], "cc_stock_full": lambda i, w: [], "sched_kit": lambda i, w: []})
    pairs = common.build_pairs(df)
    counts = pairs["condition"].value_counts().to_dict()
    assert counts["within:ui_default"] == 6          # 3 wave pairs x 2 prompts
    assert counts["cross:cc_stock_full|ui_default"] == 6  # 3 waves x 2 prompts
    assert counts["cross:cc_stock_full|sched_kit"] == 6
    assert (pairs["cluster_i"] == pairs["cluster_j"]).all()
    assert len(pairs) == 3 * 6 + 3 * 6


def test_cross_pairs_are_same_wave_and_within_pairs_are_different_wave():
    df = _frame({"ui_default": lambda i, w: [], "cc_stock_full": lambda i, w: []}, items=("b2b_01",))
    pairs = common.build_pairs(df)
    waves = df["wave"].to_numpy()
    for row in pairs.itertuples():
        same = waves[row.i] == waves[row.j]
        assert same if row.condition.startswith("cross:") else not same


def test_h1_gap_h2_and_h3_contrasts_on_a_small_frame():
    def fixed(*names):
        return lambda item, wave: list(names)

    df = _frame({"ui_default": fixed("a", "b"),               # within:ui = 1.0
                 "cc_stock_full": fixed("a", "c"),            # J with ui = 1/3
                 "opus55_plain": fixed("a", "b", "c"),        # J with ui = 2/3
                 "sched_kit": fixed("x", "y"),                # J with ui = 0, with stock = 0
                 "cc_none_search": fixed("a", "b")})
    pairs = model.frame_pairs(df)

    def combo(coefs):
        return model.boot_combo(pairs, "brand_j", coefs, n_boot=20).estimate

    assert combo(model.gap_coefs("cc_stock_full")) == pytest.approx(1 - 1 / 3)
    assert combo(model.gap_coefs("sched_kit")) == pytest.approx(1.0)
    # gap(arm) - gap(plain): positive means the arm is further from claude.ai than the API is.
    assert combo(model.h2_coefs("cc_stock_full")) == pytest.approx((1 - 1 / 3) - (1 - 2 / 3))
    assert combo(model.h2_coefs("cc_none_search")) == pytest.approx(0 - (1 - 2 / 3))
    # H3: both floors are 1.0 and the cross overlap is 0.
    assert combo(model.h3_coefs(*common.H3_PAIR)) == pytest.approx(1.0)


def test_h_pos_pairs_pool_all_arms_same_wave_and_skip_same_category():
    category = {"b2b_01": "c1", "b2b_02": "c1", "b2b_03": "c2", "b2b_04": "c2"}
    df = _frame({a: (lambda i, w: [i]) for a in common.ALL_ARMS}, items=tuple(category),
                category=category)
    rel = model.relation_pairs(df)
    assert set(rel["condition"]) == {"same_prompt", "other_category"}
    n_same = 4 * 4 * 3        # arms x prompts x waves
    n_other = 4 * (4 * 2) * 3  # arms x (prompts x other-category prompts) x waves
    assert (rel["condition"] == "same_prompt").sum() == n_same
    assert (rel["condition"] == "other_category").sum() == n_other
    assert rel.loc[rel["condition"] == "same_prompt", "brand_j"].eq(1.0).all()
    assert rel.loc[rel["condition"] == "other_category", "brand_j"].eq(0.0).all()


def test_h_pos_reason_requires_size_and_a_ci_above_zero():
    assert model.h_pos_reason({"estimate": 0.2, "lo": 0.1, "hi": 0.3}) is None
    assert "below" in model.h_pos_reason({"estimate": 0.05, "lo": 0.01, "hi": 0.09})
    assert "includes 0" in model.h_pos_reason({"estimate": 0.2, "lo": -0.01, "hi": 0.4})
    assert model.h_pos_reason({"estimate": float("nan"), "lo": 0.0, "hi": 0.0}) == "no usable pairs"


def test_r4_is_skipped_unless_the_cache_covers_every_answer():
    df = pd.DataFrame({"brands": [["a"], ["b"]], "brands_all": [["a", "z"], None]})
    assert model.r4_frame(df) is None
    full = pd.DataFrame({"brands": [["a"], ["b"]], "brands_all": [["a", "z"], ["b"]]})
    assert list(model.r4_frame(full)["brands"]) == [["a", "z"], ["b"]]


def test_top10_metric_reads_the_first_ten_by_first_mention():
    twelve = [f"b{k}" for k in range(12)]
    df = _frame({"ui_default": lambda i, w: twelve,
                 "cc_stock_full": lambda i, w: [*twelve[:10], "x", "y"]}, items=("b2b_01",))
    pairs = model.frame_pairs(df)
    row = pairs[pairs["condition"] == common.cross("cc_stock_full", "ui_default")].iloc[0]
    assert row["top10_j"] == 1.0 and row["brand_j"] < 1.0


def test_usage_rows_pool_per_plan_and_imply_prompts_per_day():
    rows = []
    for wave in (1, 2):
        for k in range(10):
            rows.append({"arm": "cc_stock_full", "wave": wave, "started": f"t{k}",
                         "five_hour_first": 0.10 + 0.01 * k, "five_hour_last": 0.11 + 0.01 * k,
                         "seven_day_first": 0.20 + 0.001 * k, "seven_day_last": 0.201 + 0.001 * k})
    rows.append({"arm": "sched_kit", "wave": 1, "started": None, "five_hour_first": None,
                 "five_hour_last": None, "seven_day_first": None, "seven_day_last": None})
    out = model.usage_rows(pd.DataFrame(rows))
    pooled = next(r for r in out if r["arm"] == "all local")
    assert pooled["plan"] == "Max" and pooled["answers"] == 20
    assert pooled["seven_day_per_answer"] == pytest.approx(0.001)
    assert pooled["prompts_per_day_implied"] == pytest.approx(1 / (7 * 0.001))
    assert not any(r["arm"] == "sched_kit" for r in out)


# ------------------------------------------------------------- lexicon


def test_real_lexicon_refuses_when_not_frozen_missing_or_changed(tmp_path):
    lex = tmp_path / "lex.csv"
    lex.write_text(LEXICON_ROWS)
    with pytest.raises(SystemExit, match="not frozen"):
        brands.frozen_lexicon(lex, None)
    with pytest.raises(SystemExit, match="not found"):
        brands.frozen_lexicon(tmp_path / "absent.csv", "0" * 64)
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        brands.frozen_lexicon(lex, "0" * 64)
    _patterns, sha = brands.frozen_lexicon(lex, brands.sha256_file(lex))
    assert sha == brands.sha256_file(lex)


def test_synthetic_lexicon_is_the_only_way_past_the_hash(tmp_path):
    lex = tmp_path / "lex.csv"
    lex.write_text(LEXICON_ROWS)
    assert brands.synthetic_lexicon(lex)[1] == brands.sha256_file(lex)


def test_extraction_strips_sources_blocks_and_links_and_consumes_drop_rows(patterns):
    text = ("Try **Faketwo** then [Fakeone Cloud](https://fakeone.com/x). It syncs with Fakeledger.\n\n"
            "Sources:\n- [Some Vendor Fakethree](https://a.example)\n- [faketwo blog](https://faketwo.example)")
    assert brands.lexicon_extract(text, patterns["crm"]) == ["faketwo", "fakeone"]
    # Case-sensitive alias: only the exact casing counts.
    assert brands.lexicon_extract("faketwo", patterns["crm"]) == []


def test_unplaced_names_follow_the_pilot_rule(patterns):
    pats = patterns["crm"]
    names = ["Fakeone Enterprise", "Fakeledger", "Newvendor", " NEWVENDOR ", ""]
    # A plan tier of a known vendor and a drop row both count as placed.
    assert brands.unplaced_names(names, pats) == ["newvendor"]
    assert brands.with_unplaced(["fakeone"], names, pats) == ["fakeone", "newvendor"]


# ------------------------------------------------------------- features


PROMPT = {"item_id": "b2b_01", "category": "crm", "intent": "shortlist", "text": "x"}


def _row(arm: str, normalized: dict, patterns: dict, *, ledger=None, candidates=None, notes=None) -> dict:
    resp = {"arm": arm, "item_id": "b2b_01", "wave": 1, "normalized": normalized}
    return features.feature_row(resp, PROMPT, patterns, candidates or {}, ledger or {}, notes or {})


def test_sched_kit_search_comes_from_the_flag_not_a_count(patterns):
    base = {"answer_text": "Fakeone.", "cited_urls": [], "evaluated_urls": [], "n_searches": None}
    yes = _row("sched_kit", base | {"searched": True, "subagent_tool_uses": 4, "resolved_model": "m",
                                    "report_match": True, "instruction_exact": True}, patterns)
    assert yes["searched"] is True and yes["n_searches"] is None and yes["search_unknown"] is False
    assert yes["n_evaluated"] is None and yes["run_ok"] is True
    assert (yes["subagent_tool_uses"], yes["resolved_model"], yes["report_match"]) == (4, "m", True)
    assert yes["instruction_exact"] is True
    no = _row("sched_kit", base | {"searched": False}, patterns)
    assert no["searched"] is False and no["search_unknown"] is False
    unjoined = _row("sched_kit", base, patterns)
    assert unjoined["searched"] is False and unjoined["search_unknown"] is True


def test_only_sched_kit_may_lack_a_search_count(patterns):
    with pytest.raises(ValueError, match="no n_searches"):
        _row("cc_stock_full", {"answer_text": "x", "n_searches": None}, patterns)


def test_every_parser_output_fits_feature_row(patterns):
    stream = from_claude_code_stream([
        {"type": "system", "subtype": "init", "apiKeySource": "none", "tools": ["WebSearch"],
         "mcp_servers": [], "model": "m", "claude_code_version": "2.1.316"},
        {"type": "assistant", "message": {"model": "m", "content": [
            {"type": "tool_use", "name": "WebSearch", "input": {"query": "q"}}]}},
        {"type": "user", "tool_use_result": {"results": [{"content": [{"url": "https://e.example/1"}]}]}},
        {"type": "result", "result": "Fakeone [link](https://www.a.example/x).", "total_cost_usd": 0.3,
         "duration_ms": 5000},
    ])
    row = _row("cc_none_search", stream, patterns)
    assert (row["n_searches"], row["searched"], row["brands"]) == (1, True, ["fakeone"])
    assert row["claude_code_version"] == "2.1.316" and row["cited_domains"] == ["a.example"]
    assert row["evaluated_domains"] == ["e.example"] and row["cost_usd"] == 0.3
    assert row["duration_ms"] == 5000

    api = from_api_message({"model": "m", "stop_reason": "end_turn", "content": [
        {"type": "server_tool_use", "name": "web_search", "input": {"query": "q"}},
        {"type": "web_search_tool_result", "content": [
            {"type": "web_search_result", "url": "https://e.example/1"}]},
        {"type": "text", "text": "Faketwo.", "citations": [{"url": "https://c.example/1"}]}]})
    row = _row("opus55_plain", api, patterns)
    assert (row["n_searches"], row["brands"], row["cited_domains"]) == (1, ["faketwo"], ["c.example"])

    export = from_claude_export({"uuid": "u", "chat_messages": [
        {"sender": "human", "text": "x"},
        {"sender": "assistant", "content": [{"type": "text", "text": "Fakeone and Faketwo?"}]}]})
    row = _row("ui_default", export, patterns)
    assert row["searched"] is False and row["n_fetches"] is None


def test_a_local_answer_counts_only_if_its_last_ledger_record_is_ok(tmp_path, patterns):
    src = common.Sources(tmp_path, tmp_path / "prompts.csv")
    records = [{"wave": 1, "arm": "cc_stock_full", "item_id": "b2b_01", "status": "ok"},
               {"wave": 1, "arm": "cc_stock_full", "item_id": "b2b_01", "status": "failed", "problems": ["x"]},
               {"wave": 1, "arm": "cc_none_search", "item_id": "b2b_01", "status": "failed", "problems": ["x"]},
               {"wave": 1, "arm": "cc_none_search", "item_id": "b2b_01", "status": "ok"},
               {"wave": 0, "arm": "cc_stock_full", "item_id": "b2b_02", "status": "ok"},
               {"wave": 91, "arm": "cc_stock_full", "item_id": "b2b_03", "status": "ok"}]
    src.ledger_cc.write_text("".join(json.dumps(r) + "\n" for r in records))
    ledger = common.last_by_answer(common.ledger_records(src))
    assert set(k[2] for k in ledger) == {1}  # waves 0 and 91 are never read
    answer = {"answer_text": "Fakeone.", "n_searches": 1}
    assert _row("cc_stock_full", answer, patterns, ledger=ledger)["run_ok"] is False
    assert _row("cc_none_search", answer, patterns, ledger=ledger)["run_ok"] is True
    # A local or API answer with no ledger record is not accounted for, so it does not count.
    assert _row("cc_stock_full", answer, patterns, ledger={})["run_ok"] is False
    assert _row("opus55_plain", answer, patterns, ledger={})["run_ok"] is False
    assert _row("ui_default", answer, patterns, ledger={})["run_ok"] is True
    collected = {("opus55_plain", "b2b_01", 1): {"status": "collected", "cost_usd": 0.07}}
    row = _row("opus55_plain", answer, patterns, ledger=collected)
    assert row["run_ok"] is True and row["cost_usd"] == 0.07


def test_build_frame_reads_only_study_waves_and_arms(tmp_path):
    src = common.Sources(tmp_path, tmp_path / "prompts.csv")
    features.write_csv(src.prompts, [PROMPT])
    for wave, arm in ((1, "ui_default"), (0, "ui_default"), (91, "cc_stock_full"), (1, "cc_stock_search")):
        path = src.responses / f"w{wave}" / arm / "b2b_01.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"normalized": {"answer_text": "x", "n_searches": 0}}))
    # A raw stream file next to an answer is not an answer.
    (src.responses / "w1" / "ui_default" / "b2b_01.stream.jsonl").write_text("{}\n")
    frame = features.build_frame(src, {})
    assert list(zip(frame["arm"], frame["wave"])) == [("ui_default", 1)]


def test_collector_notes_and_coding_and_question_flags(tmp_path, patterns):
    sheets = tmp_path / "ui_sheets"
    features.write_csv(sheets / "w2.csv", [{"arm": "ui_default", "item_id": "b2b_01", "notes": "flag"},
                                           {"arm": "ui_default", "item_id": "b2b_02", "notes": " "}])
    notes = features.load_notes(sheets)
    assert notes == {("ui_default", "b2b_01", 2): True, ("ui_default", "b2b_02", 2): False}
    assert _row("ui_default", {"answer_text": "What is your budget?", "n_searches": 0}, patterns)["asks_back"]
    assert not _row("ui_default", {"answer_text": "Fakeone. Budget?", "n_searches": 0}, patterns)["asks_back"]
    assert _row("ui_default", {"answer_text": "I created a script for this.", "n_searches": 0}, patterns)["coding_flag"]


def test_candidate_cache_reads_pilot_and_study_records(tmp_path, patterns):
    cache = tmp_path / "brand_candidates.jsonl"
    sha = hashlib.sha256(b"Fakeone.").hexdigest()
    key = f"cc_stock_full|b2b_01|1|{sha}"
    cache.write_text(json.dumps({"key": "ab" * 32, "names": ["Pilotname"]}) + "\n"
                     + json.dumps({"key": key, "brands": ["Fakeone", "Newvendor"], "names": ["ignored"]}) + "\n")
    loaded = features.load_candidates(cache)
    assert loaded["ab" * 32] == ["Pilotname"] and loaded[key] == ["Fakeone", "Newvendor"]
    row = _row("cc_stock_full", {"answer_text": "Fakeone.", "n_searches": 1}, patterns, candidates=loaded)
    assert row["brands_all"] == ["fakeone", "newvendor"] and row["n_unplaced"] == 1
    other = _row("cc_stock_full", {"answer_text": "Changed.", "n_searches": 1}, patterns, candidates=loaded)
    assert other["brands_all"] is None


# ------------------------------------------------------------- lexicon_candidates


def test_new_cache_records_keep_the_pilot_reader_working(tmp_path, monkeypatch):
    r = {"arm": "sched_kit", "item_id": "b2b_01", "wave": 1, "answer_sha256": "a" * 64}
    rec = lexicon_candidates.cache_record(r, ["Fakeone"], {"input_tokens": 1}, 0.01, "m")
    assert rec["key"] == f"sched_kit|b2b_01|1|{'a' * 64}"
    assert rec["brands"] == rec["names"] == ["Fakeone"]  # pilot_report.py reads row["names"]
    cache = tmp_path / "c.jsonl"
    cache.write_text(json.dumps({"key": "ff" * 32, "names": ["Pilotname"]}) + "\n" + json.dumps(rec) + "\n")
    loaded = lexicon_candidates.load_cache(cache)
    assert lexicon_candidates.names_of(loaded["ff" * 32]) == ["Pilotname"]
    assert lexicon_candidates.names_of(loaded[rec["key"]]) == ["Fakeone"]


def test_load_answers_takes_the_wave_and_keeps_study_arms(tmp_path):
    prompts = tmp_path / "prompts.csv"
    features.write_csv(prompts, [PROMPT])
    for wave, arm in ((1, "sched_kit"), (1, "cc_stock_search"), (0, "cc_stock_search"), (2, "ui_default")):
        path = tmp_path / "responses" / f"w{wave}" / arm / "b2b_01.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"normalized": {"answer_text": "x"}}))
    (tmp_path / "responses" / "w1" / "sched_kit" / "b2b_01.stream.jsonl").write_text("{}\n")
    w1 = lexicon_candidates.load_answers(1, tmp_path / "responses", prompts)
    assert [r["arm"] for r in w1] == ["sched_kit"] and w1[0]["category"] == "crm"
    assert [r["arm"] for r in lexicon_candidates.load_answers(0, tmp_path / "responses", prompts)] == [
        "cc_stock_search"]


def test_key_comes_only_from_the_given_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-process-environment")
    env = tmp_path / ".env.local"
    with pytest.raises(SystemExit, match="only from this repo"):
        lexicon_candidates.require_repo_key(env)
    env.write_text("OTHER=1\nANTHROPIC_API_KEY=\n")
    with pytest.raises(SystemExit, match="only from this repo"):
        lexicon_candidates.require_repo_key(env)
    env.write_text('ANTHROPIC_API_KEY="fake-for-test"\n')
    assert lexicon_candidates.require_repo_key(env) == str(env)


def test_extractor_module_loads_without_network_or_data():
    code = ("import importlib.util as u, sys\n"
            f"spec = u.spec_from_file_location('lc', {str(EXP / 'harness' / 'lexicon_candidates.py')!r})\n"
            "m = u.module_from_spec(spec); sys.modules['lc'] = m; spec.loader.exec_module(m)\n"
            "e = m.extractor()\n"
            "assert all(hasattr(e, n) for n in ('extract_brands', 'cost_from_usage', 'EXTRACT_MODEL', "
            "'canonical_brand', 'EXCLUDE'))\n"
            "from anthropic_client import make_client\n")
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr[-1500:]


def test_missing_name_rate_uses_the_resolved_rule(tmp_path):
    lex = tmp_path / "lex.csv"
    lex.write_text(LEXICON_ROWS)
    pats = lexicon_candidates.brands.load_lexicon(lex)
    r = {"arm": "sched_kit", "item_id": "b2b_01", "wave": 1, "answer_sha256": "a", "category": "crm"}
    cache = {lexicon_candidates.key(r): {"brands": ["Fakeone Pro", "Newvendor", "newvendor ", "Faketwo"]}}
    assert lexicon_candidates.missing_rate([r], cache, pats) == {"sched_kit": (3, 1)}


# ------------------------------------------------------------- audits


def _audit_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"arm": arm, "item_id": f"b2b_{i:02d}", "wave": w, "category": "c", "brands": ["fakeone"],
         "run_ok": not (arm == "cc_stock_full" and i == 1 and w == 1)}
        for arm in common.ALL_ARMS for i in range(1, 11) for w in common.WAVES])


def test_audit_d_picks_are_stratified_seeded_and_only_counted_answers():
    df = _audit_frame()
    picks = audit.audit_d_picks(df)
    assert len(picks) == 30
    assert pd.Series([p["arm"] for p in picks]).value_counts().to_dict() == {a: 6 for a in common.ALL_ARMS}
    assert all(p["run_ok"] for p in picks)
    again = audit.audit_d_picks(df)
    assert [(p["arm"], p["item_id"], p["wave"]) for p in picks] == [
        (p["arm"], p["item_id"], p["wave"]) for p in again]
    # Shuffled, so sheet order does not reveal the arm.
    arms = [p["arm"] for p in picks]
    assert arms != sorted(arms, key=common.ALL_ARMS.index)


def test_audit_d_sheet_is_arm_blind_and_keeps_reviewer_input(tmp_path):
    src = common.Sources(tmp_path, tmp_path / "prompts.csv")
    df = _audit_frame()
    for r in df.itertuples():
        path = src.responses / f"w{r.wave}" / r.arm / f"{r.item_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"normalized": {
            "answer_text": "Fakeone is fine.\n\nSources:\n- [Hiddenblock](https://x.example)"}}))
    audit.make_audit_d_sheet(df, src)
    sheet, answers, key = src.audit_d_sheet.read_text(), src.audit_d_answers.read_text(), src.audit_d_key.read_text()
    with src.audit_d_sheet.open(newline="") as f:
        columns = csv.DictReader(f).fieldnames
    assert columns == ["audit_id", "category", "extracted_brands", "missed_brands", "wrong_brands",
                       "reviewer_notes"]
    for arm in common.ALL_ARMS:
        assert arm not in sheet and arm not in answers and arm in key
    assert "b2b_" not in sheet and "b2b_" not in answers
    assert "Hiddenblock" not in answers  # the reviewer reads what extraction reads
    assert len(key.strip().splitlines()) == 31

    src.audit_d_sheet.write_text(sheet.replace("fakeone,,,", "fakeone,Missed,,", 1))
    filled = src.audit_d_sheet.read_text()
    assert "already has reviewer input" in audit.make_audit_d_sheet(df, src)
    assert src.audit_d_sheet.read_text() == filled
    assert "wrote" in audit.make_audit_d_sheet(df, src, force=True)


def test_audit_d_reading_file_lists_deliberate_exclusions(tmp_path):
    lex = tmp_path / "lex.csv"
    lex.write_text("canonical,aliases,category,decision,reason,match,n_answers,change\n"
                   "fakeone,Fakeone,c,keep,in category,ci,,\n"
                   "otherco,Otherco,c,drop,out of category: billing,ci,,\n")
    src = common.Sources(tmp_path, tmp_path / "prompts.csv")
    df = _audit_frame()
    for r in df.itertuples():
        path = src.responses / f"w{r.wave}" / r.arm / f"{r.item_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"normalized": {"answer_text": "Fakeone syncs with Otherco."}}))
    audit.make_audit_d_sheet(df, src, lexicon=lex)
    answers = src.audit_d_answers.read_text()
    assert "**Excluded on purpose (1):** otherco (out of category: billing)" in answers
    with src.audit_d_sheet.open(newline="") as f:
        assert "otherco" not in next(csv.DictReader(f))["extracted_brands"]


def test_audit_d_scorer_joins_the_key_per_arm(tmp_path):
    sheet, key = tmp_path / "sheet.csv", tmp_path / "key.csv"
    rows = [{"audit_id": f"A{i:02d}", "category": "c", "extracted_brands": "A; B; C; D; E",
             "missed_brands": "", "wrong_brands": "", "reviewer_notes": ""} for i in range(1, 31)]
    rows[0]["wrong_brands"] = "b; Fakename"  # one real false positive, one unmatched name
    rows[1]["missed_brands"] = "F"
    features.write_csv(sheet, rows)
    features.write_csv(key, [{"audit_id": f"A{i:02d}", "arm": "ui_default" if i <= 2 else "sched_kit",
                              "item_id": "b2b_01", "wave": 1} for i in range(1, 31)])
    s = audit.score_audit_d(sheet, key, "lexsha")
    assert (s["true_positive"], s["false_positive"], s["false_negative"]) == (149, 1, 1)
    assert s["wrong_names_not_extracted"] == 1 and s["passes"] and s["lexicon_sha256"] == "lexsha"
    ui = s["per_arm"]["ui_default"]
    assert (ui["answers"], ui["true_positive"], ui["false_positive"], ui["false_negative"]) == (2, 9, 1, 1)
    features.write_csv(sheet, rows[:29])
    assert not audit.score_audit_d(sheet, key, "lexsha")["passes"]  # an incomplete sheet never passes
    for r in rows:
        r["wrong_brands"] = "a"
    features.write_csv(sheet, rows)
    assert not audit.score_audit_d(sheet, key, "lexsha")["passes"]


def test_ledger_table_separates_run_failures_from_audit_failures():
    records = [
        {"arm": "cc_stock_full", "wave": 1, "status": "failed", "problems": ["exit_1"]},
        {"arm": "cc_stock_full", "wave": 1, "status": "failed", "problems": ["apiKeySource=env"]},
        {"arm": "cc_stock_full", "wave": 1, "status": "ok", "problems": []},
        {"arm": "opus55_plain", "wave": 1, "status": "submitted"},
        {"arm": "opus55_plain", "wave": 1, "status": "failed", "error": "expired"},
    ]
    df = pd.DataFrame({"arm": ["cc_stock_full"], "wave": [1], "run_ok": [False]})
    t = audit.ledger_table(df, records).set_index("arm")
    assert t.loc["cc_stock_full", ["attempts", "failed_runs", "audit_failures", "not_counted"]].tolist() == [3, 1, 1, 1]
    assert t.loc["opus55_plain", ["attempts", "failed_runs", "audit_failures"]].tolist() == [1, 1, 0]


def test_scheduled_checks_report_copies_instruction_and_model():
    base = {"arm": "sched_kit", "wave": 1, "subagent_tool_uses": 4.0, "resolved_model": "claude-opus-5-5"}
    df = pd.DataFrame([
        base | {"searched": True, "search_unknown": False, "fetched": True, "report_match": True, "instruction_exact": True},
        base | {"searched": True, "search_unknown": False, "fetched": False, "report_match": False, "instruction_exact": True},
        base | {"searched": False, "search_unknown": True, "fetched": None, "report_match": None, "instruction_exact": None,
                "subagent_tool_uses": None, "resolved_model": None},
    ])
    row = audit.scheduled_checks(df).iloc[0]
    assert (row["answers"], row["searched"], row["no_join"], row["fetched"]) == (3, 2, 1, 1)
    assert (row["exact_instruction"], row["copies_checked"], row["exact_copies"]) == (2, 2, 1)
    assert row["report_match_rate"] == 0.5 and row["resolved_model"] == "claude-opus-5-5"


# ------------------------------------------------------------- gate


def test_model_gate_blocks_real_runs(tmp_path):
    df = pd.DataFrame({"synthetic": [0]})
    score = tmp_path / "score.json"
    problems = model.preregistration_gate(df, 300, score_path=score, lexicon_sha256="lexsha")
    assert any("--n-boot" in p for p in problems) and any("not scored" in p for p in problems)
    score.write_text(json.dumps({"passes": False, "lexicon_sha256": "lexsha"}))
    problems = model.preregistration_gate(df, common.N_BOOT, score_path=score, lexicon_sha256="lexsha")
    assert any("did not pass" in p for p in problems) and any("not signed" in p for p in problems)
    score.write_text(json.dumps({"passes": True, "signed_by": "A Reviewer", "lexicon_sha256": "old"}))
    problems = model.preregistration_gate(df, common.N_BOOT, score_path=score, lexicon_sha256="lexsha")
    assert problems == ["Audit D was scored against a different lexicon; re-check it"]
    score.write_text(json.dumps({"passes": True, "signed_by": "A Reviewer", "lexicon_sha256": "lexsha"}))
    assert model.preregistration_gate(df, common.N_BOOT, score_path=score, lexicon_sha256="lexsha") == []
    assert model.preregistration_gate(pd.DataFrame({"synthetic": [1]}), common.N_BOOT, score_path=score,
                                      lexicon_sha256="lexsha") == ["the real feature frame contains synthetic rows"]


# ------------------------------------------------------------- dry run


def _run(script: str, *args: str, root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, common.SYNTHETIC_ROOT_ENV: str(root)}
    return subprocess.run([sys.executable, str(PIPELINE / script), *args], env=env,
                          capture_output=True, text=True, timeout=900)


def _world(world: str, root: Path, *extra: str) -> subprocess.CompletedProcess:
    made = _run("01_features.py", "--synthetic", world, root=root)
    assert made.returncode == 0, made.stderr
    return _run("03_model.py", "--synthetic", world, "--n-boot", "500", *extra, root=root)


@pytest.mark.parametrize("world", ["planted", "planted_equiv"])
def test_synthetic_dry_run_recovers_planted_verdicts(world, tmp_path):
    made = _run("01_features.py", "--synthetic", world, root=tmp_path)
    assert made.returncode == 0, made.stderr
    audited = _run("02_audit.py", "--synthetic", world, root=tmp_path)
    assert audited.returncode == 0, audited.stderr
    res = _run("03_model.py", "--synthetic", world, "--expect", world, "--n-boot", "500", root=tmp_path)
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-3000:]
    assert "FAIL" not in res.stdout.split("dry-run check")[1].split("info")[0]

    results = json.loads((tmp_path / "results" / world / "model_results.json").read_text())
    rows = {r["test"]: r for r in results["rows"] if r.get("section") == "H1_primary"}
    levels = {r["holm_rank"]: round(r["ci_level"], 4) for r in rows.values()}
    assert levels == {1: 0.95, 2: 0.90}
    if world == "planted_equiv":
        assert all(r["verdict"] in ("NULL", "NEGLIGIBLE") for r in rows.values())
    else:
        assert rows["H1 sched_kit"]["verdict"] == "REAL"
        assert rows["H1 sched_kit"]["holm_rank"] == 2
        assert rows["H1 cc_stock_full"]["holm_rank"] == 1

    report = tmp_path / "results" / world / "audit_report.md"
    text = report.read_text()
    assert common.SYNTH_ANSWER_MARK not in text and "Zq" not in text
    assert "INCONCLUSIVE (rule)" in text and "exact_copies" in text


def test_synthetic_audit_d_sheet_and_score_path(tmp_path):
    assert _run("01_features.py", "--synthetic", "planted", root=tmp_path).returncode == 0
    assert _run("02_audit.py", "--synthetic", "planted", root=tmp_path).returncode == 0
    raw = tmp_path / "interim" / "planted" / "raw"
    with (raw / "audit_d_key.csv").open(newline="") as f:
        by_arm = pd.Series([r["arm"] for r in csv.DictReader(f)]).value_counts().to_dict()
    assert by_arm == {a: 6 for a in common.ALL_ARMS}
    with (raw / "audit_d_sheet.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0]["reviewer_notes"] = "reviewed"
    features.write_csv(raw / "audit_d_sheet.csv", rows)
    scored = _run("02_audit.py", "--synthetic", "planted", "--score-audit-d", "--signed-by", "A Reviewer",
                  root=tmp_path)
    assert scored.returncode == 0, scored.stderr
    score = json.loads((tmp_path / "results" / "planted" / "audit_d_score.json").read_text())
    assert score["passes"] and score["signed_by"] == "A Reviewer" and score["rows"] == 30


def test_synthetic_robustness_rows_and_report_shape(tmp_path):
    res = _world("planted", tmp_path)
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    results = json.loads((tmp_path / "results" / "planted" / "model_results.json").read_text())
    rows = results["rows"]
    for section, n in (("R1", 4), ("R2", 4), ("R3", 12), ("R4", 4), ("R5", 4), ("R6", 4), ("R7", 4)):
        assert sum(r.get("section") == section for r in rows) == n, section
    # R5 resamples categories, not prompts.
    assert next(r for r in rows if r.get("section") == "R5")["n_clusters"] == 20
    meta = results["meta"]
    assert meta["r6_excluded"] == 6  # 2 flagged prompts x 3 waves
    assert meta["r7_excluded"]["sched_kit"] == 3 and meta["r7_excluded"]["cc_none_search"] > 36
    assert meta["r4_coverage"] == {"1": 1.0, "2": 1.0, "3": 1.0}
    desc = {r["arm"]: r for r in results["descriptives"]["by_arm"]}
    assert desc["sched_kit"]["searches"] is None and desc["sched_kit"]["evaluated_urls"] is None
    assert desc["sched_kit"]["subagent_tool_uses"] > 0
    assert desc["cc_stock_full"]["searches"] > 0 and desc["ui_default"]["fetches"] is None
    assert desc["ui_default"]["usd_estimate"] is None and desc["opus55_plain"]["usd_estimate"] > 0
    usage = results["descriptives"]["usage"]
    assert {r["plan"] for r in usage} == {"Max"} and any(r["arm"] == "all local" for r in usage)
    # The placebo never gates: the stage finished, whatever its verdicts were.
    assert sum(r.get("section") == "H_pla" for r in rows) == 2
    assert all("verdict" not in r for r in rows if r.get("section") == "domain_gap")
    report = (tmp_path / "results" / "planted" / "model_report.md").read_text()
    assert report.startswith("# Experiment 011") and "Practically equivalent: passes" in report
    assert "Real gap: report its size" in report


def test_synthetic_broken_join_stops_on_h_pos_before_anything_else(tmp_path):
    res = _world("broken_join", tmp_path)
    assert res.returncode == 1, res.stdout[-2000:] + res.stderr[-2000:]
    assert "H_pos FAILED" in res.stdout and "FAIL: STOP" in res.stdout
    results = json.loads((tmp_path / "results" / "broken_join" / "model_results.json").read_text())
    assert {r["section"] for r in results["rows"]} == {"H_pos"}
    assert results["meta"]["h_pos_passed"] is False


def test_expect_must_name_the_world(tmp_path):
    res = _run("03_model.py", "--synthetic", "planted", "--expect", "planted_equiv", root=tmp_path)
    assert res.returncode != 0 and "--expect must name" in res.stderr
