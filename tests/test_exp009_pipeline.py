"""Experiment 009 analysis pipeline: bootstrap, Holm, gates, audits, synthetic dry run.

The pipeline lives outside the installed package and its modules share names
with other experiments' pipelines (``brands``, ``common``), which other test
modules may already have imported. ``pipeline_modules`` loads 009's copies
with those names swapped out of ``sys.modules`` and restores them afterwards.
The end-to-end dry run (spec §8 step 3) runs the stage scripts as
subprocesses with the synthetic worlds redirected to a temporary directory.
"""

from __future__ import annotations

import csv
import importlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aeo_research.overlap import cluster_boot

PIPELINE = (
    Path(__file__).resolve().parents[1] / "experiments" / "009-claude-model-fidelity" / "pipeline"
)
SHADOWED = ("brands", "common", "shares")


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


_mods = _load("brands", "common", "03_model", "02_audit", "02b_domain_map")
brands, common = _mods["brands"], _mods["common"]
model, audit, domain_map = _mods["03_model"], _mods["02_audit"], _mods["02b_domain_map"]


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
                       n_boot=400, seed=20260926)
    b = model.boot_combo(pairs, "value", {"within:ui_default": 1.0, "cross:arm|ui_default": -1.0},
                         n_boot=400, seed=20260926)
    lo, hi = b.ci(0.10)
    assert b.estimate == pytest.approx(ref.estimate)
    assert (lo, hi) == pytest.approx((ref.lo, ref.hi))
    assert b.n_nan == ref.n_nan == 2
    lvl = cluster_boot(pairs, contrast=("within:ui_default", None), n_boot=300, seed=7)
    bl = model.boot_combo(pairs, "value", {"within:ui_default": 1.0}, n_boot=300, seed=7)
    assert bl.ci(0.10) == pytest.approx((lvl.lo, lvl.hi))


def test_boot_combo_handles_cross_cluster_pairs_like_cluster_boot():
    rng = np.random.default_rng(5)
    rows = [("a" if k % 2 else "b", f"p{rng.integers(10)}", f"p{rng.integers(10)}", rng.random())
            for k in range(300)]
    pairs = pd.DataFrame(rows, columns=["condition", "cluster_i", "cluster_j", "value"])
    ref = cluster_boot(pairs, contrast=("a", "b"), n_boot=200, seed=11)
    b = model.boot_combo(pairs, "value", {"a": 1.0, "b": -1.0}, n_boot=200, seed=11)
    assert b.ci(0.10) == pytest.approx((ref.lo, ref.hi))


def test_tost_p_is_the_larger_tail_at_the_band_edges():
    b = model.Boot(0.0, np.array([-0.2, -0.05, 0.0, 0.05, 0.12, 0.15]), 1, 1, 0)
    assert b.tost_p(0.10) == pytest.approx(2 / 6)


def test_verdict_mapping():
    V = model.Verdict
    assert model.verdict_of(-0.05, 0.05) is V.NULL
    assert model.verdict_of(0.01, 0.05) is V.NEGLIGIBLE
    assert model.verdict_of(0.05, 0.3) is V.REAL
    assert model.verdict_of(-0.2, 0.2) is V.INCONCLUSIVE


def test_holm_orders_by_p_and_widens_the_ci():
    ctx = model.Ctx.__new__(model.Ctx)
    rng = np.random.default_rng(0)
    ctx.boots = {"a": model.Boot(0.0, rng.normal(0.0, 0.02, 2000), 40, 1, 0),
                 "b": model.Boot(0.3, rng.normal(0.3, 0.03, 2000), 40, 1, 0),
                 "c": model.Boot(0.05, rng.normal(0.05, 0.03, 2000), 40, 1, 0)}
    rows = [{"p_tost": ctx.boots[k].tost_p()} for k in "abc"]
    model.holm(ctx, rows, list("abc"))
    assert [r["holm_rank"] for r in rows] == [1, 3, 2]
    assert rows[0]["holm_alpha"] == pytest.approx(0.10 / 3)
    assert rows[2]["holm_alpha"] == pytest.approx(0.10 / 2)
    assert rows[1]["holm_alpha"] == pytest.approx(0.10)
    assert rows[0]["verdict"] == "NULL" and rows[1]["verdict"] == "REAL"
    # The Holm CI is at least as wide as the unadjusted one.
    assert rows[0]["lo"] <= rows[0]["lo_unadjusted"] and rows[0]["hi"] >= rows[0]["hi_unadjusted"]


# ------------------------------------------------------------- frames


def test_build_pairs_conditions_and_counts():
    rows = [{"arm": arm, "item_id": item, "wave": w, "category": "c"}
            for arm in ("ui_default", "sonnet5_plain", "haiku45_leak")
            for item in ("b2b_01", "b2b_02") for w in (1, 2, 3)]
    pairs = common.build_pairs(pd.DataFrame(rows))
    counts = pairs["condition"].value_counts().to_dict()
    assert counts["within:ui_default"] == 6        # 3 wave pairs x 2 prompts
    assert counts["cross:sonnet5_plain|ui_default"] == 6  # 3 waves x 2 prompts
    assert counts["cross:haiku45_leak|sonnet5_plain"] == 6
    assert (pairs["cluster_i"] == pairs["cluster_j"]).all()
    assert len(pairs) == 3 * 6 + 3 * 6


def test_lexicon_hash_check_refuses_a_changed_file(tmp_path):
    lex = tmp_path / "lex.csv"
    lex.write_text("canonical,aliases,category,decision,reason,match,n_answers\n"
                   "acme,Acme,CRM,keep,in category,ci,1\n")
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        brands.verify_lexicon(lex, "0" * 64)
    assert brands.verify_lexicon(lex, brands.sha256_file(lex)) == brands.sha256_file(lex)


def test_shared_canonical_across_cs_and_ci_rows(tmp_path):
    """Lexicon v2 folds a case-sensitive alias row and a case-insensitive row
    into one canonical; either alias must count as that single brand."""
    lex = tmp_path / "lex.csv"
    lex.write_text(
        "canonical,aliases,category,decision,reason,match,n_answers\n"
        "acme,Acme Cloud|acmecloud,CRM,keep,in category,ci,3\n"
        "acme,ACME,CRM,keep,in category; cs alias row,cs,1\n"
        "zed,Zed,CRM,keep,in category,ci,2\n"
    )
    pats = brands.load_lexicon(lex)
    assert brands.lexicon_extract("Try ACME or Zed.", pats["CRM"]) == ["acme", "zed"]
    assert brands.lexicon_extract("Zed, then acmecloud, then ACME.", pats["CRM"]) == ["zed", "acme"]
    # The cs row does not match other casings; the ci row does.
    assert brands.lexicon_extract("acme is a word here.", pats["CRM"]) == []
    assert brands.lexicon_extract("ACME CLOUD wins.", pats["CRM"]) == ["acme"]
    amap = brands.lexicon_alias_map(lex)
    assert amap[("CRM", "acme")] == ("acme", True) and amap[("CRM", "acme cloud")] == ("acme", True)
    assert brands.haiku_via_lexicon(["ACME", "Acme Cloud", "Zed"], "CRM", amap) == ["acme", "zed"]
    keys = domain_map.lexicon_keys(lex)
    assert keys["acmecloud"] == "acme" and keys["acme"] == "acme"


def test_frozen_lexicon_is_v2():
    assert brands.LEXICON.name == "lexicon_v2_1.csv"
    assert brands.LEXICON_SHA256.startswith("9756071e")


# ------------------------------------------------------------- panel


def test_share_ranking_orders_by_share_then_position_then_name():
    lists = [["b", "a", "c"], ["a", "b"], ["d", "c"]]
    order, share = model.share_ranking(lists)
    # a, b and c all have share 2/3. a and b both average position 0.5, so the
    # name breaks that tie; c averages position 1.5 and comes after them.
    assert share == {"a": 2 / 3, "b": 2 / 3, "c": 2 / 3, "d": 1 / 3}
    assert order == ["a", "b", "c", "d"]
    assert model.share_ranking([["x", "y"], ["y", "x"], ["y"]])[0] == ["y", "x"]


def test_category_panel_statistics():
    same = model.category_panel([["a", "b"], ["a", "b"], ["a"]], [["a", "b"], ["a", "b"], ["a"]])
    assert same["panel_rbo"] == pytest.approx(1.0)
    assert same["panel_jaccard_third"] == 1.0 and same["panel_jaccard_all"] == 1.0
    apart = model.category_panel([["a", "b"]] * 3, [["c", "d"]] * 3)
    assert apart["panel_rbo"] == 0.0 and apart["panel_jaccard_all"] == 0.0
    # Only "a" reaches 1/3 in both arms; "z" is named once of 6 in one arm.
    mixed = model.category_panel([["a"], ["a"], ["a"], ["z"], [], []],
                                 [["a"], ["a"], ["b"], ["b"], [], []])
    assert mixed["panel_jaccard_third"] == pytest.approx(1 / 2)
    assert mixed["panel_jaccard_all"] == pytest.approx(1 / 3)


def test_category_mean_interval_surrounds_estimate():
    rng = np.random.default_rng(2)
    values = np.append(rng.uniform(0.2, 0.9, 20), np.nan)
    est, lo, hi, n = model.category_mean_ci(values, 2000)
    assert n == 20 and lo <= est <= hi
    assert est == pytest.approx(np.nanmean(values))


def test_pilot_report_reexports_the_pipeline_extraction():
    harness = PIPELINE.parent / "harness"
    if str(harness) not in sys.path:
        sys.path.insert(0, str(harness))
    pilot_report = importlib.import_module("pilot_report")
    assert pilot_report.lexicon_extract.__module__ == "exp009_brands"
    assert pilot_report.registered_domain("https://news.bbc.co.uk/x") == "bbc.co.uk"


def test_audit_d_scorer_joins_the_key_per_arm(tmp_path):
    sheet, key = tmp_path / "sheet.csv", tmp_path / "key.csv"
    fields = ["audit_id", "category", "extracted_brands", "missed_brands", "wrong_brands",
              "reviewer_notes"]
    rows = [{"audit_id": f"A{i:02d}", "category": "c", "extracted_brands": "A; B; C; D; E",
             "missed_brands": "", "wrong_brands": "", "reviewer_notes": ""} for i in range(1, 31)]
    rows[0]["wrong_brands"] = "b; Zed"   # one real false positive, one unmatched name
    rows[1]["missed_brands"] = "F"

    def write(path, fieldnames, data):
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(data)

    write(sheet, fields, rows)
    write(key, ["audit_id", "arm", "item_id", "wave"],
          [{"audit_id": f"A{i:02d}", "arm": "ui_default" if i <= 2 else "haiku45_leak",
            "item_id": "b2b_01", "wave": 1} for i in range(1, 31)])
    s = audit.score_audit_d(sheet, key)
    assert (s["true_positive"], s["false_positive"], s["false_negative"]) == (149, 1, 1)
    assert s["wrong_names_not_extracted"] == 1
    assert s["passes"]
    ui = s["per_arm"]["ui_default"]
    assert (ui["answers"], ui["true_positive"], ui["false_positive"], ui["false_negative"]) == (
        2, 9, 1, 1)
    assert s["per_arm"]["haiku45_leak"]["precision"] == 1.0
    write(sheet, fields, rows[:29])
    assert not audit.score_audit_d(sheet, key)["passes"]   # an incomplete sheet never passes


def test_domain_map_suggestions():
    seed = {"reviews.example": "review marketplace"}
    lex = {"acme": "acme", "widgetco": "widgetco"}
    assert domain_map.suggest("reviews.example", seed, lex)[0] == "review marketplace"
    assert domain_map.suggest("acme.com", seed, lex)[:2] == ("vendor", "lexicon name match")
    assert domain_map.suggest("getacme.io", seed, lex)[0] == "vendor"
    assert domain_map.suggest("state.gov", seed, lex)[0] == "other"
    assert domain_map.suggest("somenews.com", seed, lex)[0] == "publisher"


def test_model_gate_blocks_real_runs_without_audit_d_and_frozen_map():
    df = pd.DataFrame({"synthetic": [0], "cited_classes": [None]})
    problems = model.preregistration_gate(df, 300)
    assert any("--n-boot" in p for p in problems)
    if common.DOMAIN_MAP_SHA256 is None:
        assert any("domain map is not frozen" in p for p in problems)


# ------------------------------------------------------------- dry run


def _run(script: str, *args: str, root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, common.SYNTHETIC_ROOT_ENV: str(root)}
    return subprocess.run([sys.executable, str(PIPELINE / script), *args], env=env,
                          capture_output=True, text=True, timeout=600)


def test_synthetic_dry_run_recovers_planted_arms(tmp_path):
    feats = _run("01_features.py", "--synthetic", "planted", root=tmp_path)
    assert feats.returncode == 0, feats.stderr
    assert (tmp_path / "interim" / "planted" / "features.jsonl").exists()
    res = _run("03_model.py", "--synthetic", "planted", "--expect", "planted",
               "--n-boot", "300", root=tmp_path)
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-3000:]
    assert "FAIL" not in res.stdout.split("dry-run check")[1].split("info")[0]
    assert (tmp_path / "results" / "planted" / "model_results.json").exists()
    fig = _run("04_figures.py", "--synthetic", "planted", root=tmp_path)
    assert fig.returncode == 0, fig.stderr
    assert (tmp_path / "results" / "planted" / "figures" / "gap-vs-cost.png").exists()


def test_synthetic_broken_join_stops_on_h_pos(tmp_path):
    assert _run("01_features.py", "--synthetic", "broken_join", root=tmp_path).returncode == 0
    res = _run("03_model.py", "--synthetic", "broken_join", "--n-boot", "200", root=tmp_path)
    assert res.returncode == 1, res.stdout[-2000:] + res.stderr[-2000:]
    assert "FAIL: STOP" in res.stdout
