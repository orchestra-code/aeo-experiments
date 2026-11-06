"""Experiment 004 study pipeline: Gemini app markup stripping, the bootstrap TOST p and Holm
levels, the gap, H_pos, the pilot reproduction parser, power_sim's Stage 1 firewall, and one
end-to-end synthetic world in a temporary directory. Fake brands only (Acmeflow, Zentrik,
Quillo, Brightdesk; ``Zq...`` in the synthetic world)."""

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "004-api-vs-ui"
HARNESS, PIPELINE = EXP / "harness", EXP / "pipeline"
sys.path.insert(0, str(HARNESS))
SHADOWED = ("brands", "common", "synthetic", "01_frame", "02_audit", "03_model", "power_sim",
            "audit_d")


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


common, model, power, audit_d = _load_pipeline("common", "03_model", "power_sim", "audit_d")
answers = power.answers
m011 = common.m011

# ---------------------------------------------------------------- markup

PROSE = "## Shortlist\n\n1. **Acmeflow**: strong reporting.\n2. **Zentrik**: cheaper.\n\nPick one."


@pytest.mark.parametrize("markup", [
    '<ElicitationsGroup message="Want to go deeper?">\n<Elicitation label="Compare Quillo" '
    'query="quillo vs acmeflow"/>\n<Elicitation label="Pricing" query="pricing"/>\n</ElicitationsGroup>',
    '<FollowUp label="Tell me about Quillo" query="quillo review"/>',
    '<FollowUp>Should I compare Quillo next?</FollowUp>',
    '<Carousel>\n<Video component_placeholder_id="v1" count="3" query="Quillo demo" source="x"/>\n'
    '</Carousel>\n<FollowUp label="Quillo?" query="q"/>',
    '<Questionnaire>\n<FormStep selectionType="single" subtitle="s" title="Team size?">\n'
    '<ChipGroup label="Size">\n<Chip label="Quillo users" value="a"/>\n<Chip label="b" value="b"/>\n'
    '</ChipGroup>\n</FormStep>\n</Questionnaire>',
])
def test_strip_app_markup_shapes(markup):
    text = f"{PROSE}\n\n{markup}"
    stripped = answers.strip_app_markup(text)
    assert stripped == PROSE
    assert answers.app_markup_tags(stripped) == [] and answers.app_markup_tags(text)
    assert answers.strip_app_markup(stripped) == stripped  # idempotent
    assert answers.brand_text("gm_ui", text) == PROSE
    assert answers.brand_text("gm_ui", text, keep_markup=True) == text  # R6
    assert answers.brand_text("cg_ui", text) == text  # only the Gemini app is stripped


def test_strip_keeps_prose_and_unknown_tags():
    text = ("Acmeflow <b>bold</b> and a <Timeline><TimelineEvent>Zentrik 2024</TimelineEvent></Timeline> "
            'note.\n<FollowUp label="x" query="y"/>\n<ElicitationsGroup message="m">')
    out = answers.strip_app_markup(text)
    assert "<b>bold</b>" in out and "<Timeline>" in out and "Zentrik 2024" in out  # not stripped
    assert "FollowUp" not in out and "ElicitationsGroup" not in out  # a lone opening tag too
    assert answers.app_markup_tags(out) == ["Timeline", "TimelineEvent"]
    assert answers.strip_app_markup("") == "" and answers.strip_app_markup("no tags") == "no tags"


def test_stripping_changes_the_extracted_brands():
    patterns = [(re.compile(rf"(?<![\w&]){name}(?![\w&])", re.I), name, True)
                for name in ("Acmeflow", "Zentrik", "Quillo")]
    text = f'{PROSE}\n\n<FollowUp label="Tell me about Quillo" query="quillo"/>'
    assert common.extract(answers.brand_text("gm_ui", text), patterns) == ["Acmeflow", "Zentrik"]
    assert common.extract(text, patterns) == ["Acmeflow", "Zentrik", "Quillo"]


# ---------------------------------------------------------------- TOST and Holm


def test_bootstrap_tost_p_is_the_larger_tail():
    boot = m011.Boot(0.0, np.array([-0.2, -0.11, 0.0, 0.05, 0.12]), 40, 100, 0)
    assert boot.tost_p(0.10) == pytest.approx(0.4)  # 2 of 5 at or below -0.10 vs 1 of 5 at or above
    boot = m011.Boot(0.0, np.array([0.0, 0.01, 0.02, 0.15]), 40, 100, 0)
    assert boot.tost_p(0.10) == pytest.approx(0.25)


class _Ctx:
    def __init__(self, boots):
        self.boots = boots


def test_holm_levels_and_order():
    rng = np.random.default_rng(1)
    tight = m011.Boot(0.01, rng.normal(0.01, 0.02, 2000), 40, 240, 0)  # small p
    wide = m011.Boot(0.04, rng.normal(0.04, 0.04, 2000), 40, 240, 0)   # larger p
    rows = [{"p_tost": wide.tost_p(0.10)}, {"p_tost": tight.tost_p(0.10)}]
    m011.holm(_Ctx({"a": wide, "b": tight}), rows, ["a", "b"])
    assert rows[1]["holm_rank"] == 1 and rows[1]["ci_level"] == pytest.approx(0.95)
    assert rows[0]["holm_rank"] == 2 and rows[0]["ci_level"] == pytest.approx(0.90)
    lo95, hi95 = tight.ci(0.05)
    assert (rows[1]["lo"], rows[1]["hi"]) == (lo95, hi95)
    assert rows[1]["lo"] <= rows[1]["lo_unadjusted"] and rows[1]["hi"] >= rows[1]["hi_unadjusted"]
    assert (rows[0]["lo"], rows[0]["hi"]) == wide.ci(0.10)
    assert rows[0]["p_holm"] >= rows[1]["p_holm"]


@pytest.mark.parametrize("lo,hi,verdict", [(-0.05, 0.05, "NULL"), (0.01, 0.09, "NEGLIGIBLE"),
                                           (0.05, 0.15, "REAL"), (-0.12, 0.08, "INCONCLUSIVE")])
def test_decision_table(lo, hi, verdict):
    assert m011.verdict_of(lo, hi, 0.10).name == verdict
    assert m011.CONCLUSION[verdict]  # the spec's wording is attached to every verdict


# ---------------------------------------------------------------- gap and H_pos


def _frame(api_brands, n_items=12):
    """cg_ui identical across waves; cg_api_low draws ``api_brands``; categories in pairs."""
    rows = []
    for k in range(1, n_items + 1):
        item, cat = f"b2b_{k:02d}", f"cat{(k + 1) // 2:02d}"
        ui = [f"Acmeflow{cat}", f"Zentrik{cat}"]
        for wave in (1, 2, 3):
            for arm, brands in (("cg_ui", ui), ("cg_api_low", api_brands(cat, ui)),
                                ("cg_api_plain", ui)):
                rows.append({"arm": arm, "platform": "chatgpt", "item_id": item, "category": cat,
                             "wave": wave, "brands": brands, "cited_domains": [],
                             "evaluated_domains": [], "searched": True})
    return pd.DataFrame(rows)


def test_gap_and_h1_recover_a_planted_gap():
    df = _frame(lambda cat, ui: [ui[0], f"Quillo{cat}"])  # cross Jaccard 1/3, within 1
    ctx = model.Ctx(df, n_boot=200)
    row = model.gap_row(ctx, "cg_api_low", "H1", "H1")
    assert row["estimate"] == pytest.approx(2 / 3) and row["verdict"] == "REAL"
    assert row["n_pairs"] == 12 * 6
    eq = model.gap_row(ctx, "cg_api_plain", "H1", "H1")
    assert eq["estimate"] == pytest.approx(0.0) and eq["verdict"] in model.EQUIVALENT


def test_h_pos_fails_on_a_broken_join():
    df = _frame(lambda cat, ui: ui)
    gm = df.assign(arm=df["arm"].map({"cg_ui": "gm_ui", "cg_api_low": "gm_api_plain",
                                      "cg_api_plain": "gm_api_plain_x"}), platform="gemini")
    gm = gm[gm["arm"] != "gm_api_plain_x"]
    good = model.Ctx(pd.concat([df, gm], ignore_index=True), n_boot=200)
    assert model.h_pos(good) is True
    broken = df.copy()
    api = broken["arm"].isin(["cg_api_low", "cg_api_plain"])  # H_pos pools the platform's API arms
    broken.loc[api, "brands"] = broken.loc[api, "category"].map(lambda c: [f"Brightdesk{c}"])
    bad = model.Ctx(pd.concat([broken, gm], ignore_index=True), n_boot=200)
    assert model.h_pos(bad) is False
    row = next(r for r in bad.rows if r["test"] == "H_pos ChatGPT")
    assert not row["passed"] and "below" in row["reason"]


def test_pilot_report_parser_reads_the_tracked_gaps():
    got = model.pilot_expected()
    assert got == {"cg_api_low": (0.007, -0.068, 0.085), "cg_api_plain": (0.059, 0.005, 0.111),
                   "gm_api_plain": (0.101, 0.016, 0.187)}


# ---------------------------------------------------------------- Audit D


def _pat(alias, canon, keep):
    return (re.compile(rf"(?<![\w&]){re.escape(alias)}(?![\w&])", re.I), canon, keep)


def test_audit_d_hits_match_extraction_and_list_drops():
    patterns = [_pat("Acmeflow Billing", "acmeflow billing", False), _pat("Acmeflow", "acmeflow", True),
                _pat("Zentrik", "zentrik", True), _pat("Brightdesk", "brightdesk", False)]
    text = ("Try **Zentrik** or Acmeflow; connect [brightdesk.com](https://brightdesk.com/x) and "
            "Acmeflow Billing via Brightdesk.\n\nSources:\n- Quillo review")
    kept, dropped = audit_d.lexicon_hits(text, patterns)
    assert kept == common.extract(text, patterns) == ["zentrik", "acmeflow"]
    assert dropped == ["acmeflow billing", "brightdesk"]  # the longer drop alias shadows Acmeflow
    shown = audit_d.reading_text(text)
    assert "https://" not in shown and "brightdesk.com" not in shown and "Quillo" not in shown
    assert "**Zentrik**" in shown  # formatting kept for the reader


def _audit_files(tmp_path, rows):
    sheet, key = tmp_path / "sheet.csv", tmp_path / "key.csv"
    arms = list(common.ALL_ARMS)
    audit_d._write_csv(sheet, [{"audit_id": f"A{i:02d}", "category": "c", "extracted_brands": e,
                                "excluded_names_found": "", "missed_brands": m, "wrong_brands": w,
                                "reviewer_notes": ""} for i, (e, m, w) in enumerate(rows, 1)])
    audit_d._write_csv(key, [{"audit_id": f"A{i:02d}", "arm": arms[(i - 1) % 5], "item_id": "b2b_01",
                              "wave": 1} for i in range(1, len(rows) + 1)])
    return sheet, key


def test_audit_d_score_arithmetic(tmp_path):
    rows = [("Acmeflow; Zentrik; Quillo", "", "")] * 28 + [
        ("Acmeflow; Zentrik", "Brightdesk", "zentrik; Nope"), ("Acmeflow", "Quillo; Brightdesk", "")]
    s = audit_d.score(*_audit_files(tmp_path, rows), "abc")
    assert (s["true_positive"], s["false_positive"], s["false_negative"]) == (84 + 1 + 1, 1, 3)
    assert s["wrong_names_not_extracted"] == 1 and s["complete"] and s["lexicon_sha256"] == "abc"
    assert s["precision"] == pytest.approx(86 / 87) and s["recall"] == pytest.approx(86 / 89)
    assert s["passes"] and sum(v["answers"] for v in s["per_arm"].values()) == 30
    fail = audit_d.score(*_audit_files(tmp_path, [("Acmeflow", "Zentrik; Quillo", "")] * 30), "abc")
    assert fail["recall"] == pytest.approx(1 / 3) and not fail["passes"]
    short = audit_d.score(*_audit_files(tmp_path, rows[:29]), "abc")
    assert not short["complete"] and not short["passes"]  # 29 rows is not a finished sheet


def test_audit_d_real_sheet_waits_for_the_waves_and_the_pin():
    df = pd.DataFrame({"arm": ["cg_ui"]})
    ok = {"lexicon_sha256": common.STUDY_LEXICON_SHA256, "missing": []}
    assert audit_d.sheet_problems(df, ok, common.Mode()) == []
    probs = audit_d.sheet_problems(df, {"lexicon_sha256": "x", "missing": [{"arm": "cg_ui"}]},
                                   common.Mode())
    assert len(probs) == 2
    assert audit_d.sheet_problems(df, {}, common.Mode(synthetic="planted")) == []


def test_real_data_gate(tmp_path):
    df = pd.DataFrame({"synthetic": [0]})
    meta = {"lexicon_sha256": common.STUDY_LEXICON_SHA256}
    problems = model.preregistration_gate(df, meta, 2000, score_path=tmp_path / "none.json")
    assert problems == ["Audit D is not scored and signed (results/audit_d_score.json)"]
    score = tmp_path / "s.json"
    score.write_text(json.dumps({"passes": True, "signed_by": "Jim Wrubel",
                                 "lexicon_sha256": common.STUDY_LEXICON_SHA256}))
    assert model.preregistration_gate(df, meta, 2000, score_path=score) == []
    assert len(model.preregistration_gate(df, {"lexicon_sha256": "x"}, 500, score_path=score)) == 2


# ---------------------------------------------------------------- power_sim


def _write_010(raw: Path) -> None:
    """A fake 010 raw dir: a Stage 1 task and a Stage 2 task whose result file does not exist."""
    (raw / "responses_main_chatgpt" / "w1").mkdir(parents=True)
    good = raw / "responses_main_chatgpt" / "w1" / "t1.json"
    good.write_text(json.dumps({"model": "gpt-6", "markdown": "Acmeflow and Zentrik."}))
    stage2 = raw / "responses_main_chatgpt" / "w8" / "t8.json"  # never created: must not be read
    recs = [
        {"task_id": "t1", "wave": 1, "item_id": "b2b_01", "status": "submitted",
         "submitted_at": "2026-10-04T00:00:15+00:00"},
        {"task_id": "t1", "wave": 1, "item_id": "b2b_01", "status": "collected",
         "submitted_at": "2026-10-04T00:00:15+00:00", "collected_at": "2026-10-04T00:05:00+00:00",
         "result_path": str(good)},
        {"task_id": "t8", "wave": 8, "item_id": "b2b_01", "status": "collected",
         "submitted_at": "2026-10-11T00:00:15+00:00", "collected_at": "2026-10-11T00:05:00+00:00",
         "result_path": str(stage2)},
    ]
    (raw / "ledger_main_chatgpt.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")


def test_power_reads_stage1_only(tmp_path):
    _write_010(tmp_path)
    recs = power.stage1_records("chatgpt", tmp_path)
    assert {r["wave"] for r in recs} == {1}
    finals = power.stage1_finals("chatgpt", tmp_path)
    assert finals == {("b2b_01", 1): tmp_path / "responses_main_chatgpt" / "w1" / "t1.json"}


def test_power_refuses_a_stage1_record_outside_its_dates(tmp_path):
    _write_010(tmp_path)
    path = tmp_path / "ledger_main_chatgpt.jsonl"
    rec = {"task_id": "t2", "wave": 7, "item_id": "b2b_02", "status": "submitted",
           "submitted_at": "2026-11-06T15:00:00+00:00"}
    path.write_text(path.read_text() + json.dumps(rec) + "\n")
    with pytest.raises(AssertionError, match="Stage 1 task submitted"):
        power.stage1_finals("chatgpt", tmp_path)


def test_power_simulation_behaves():
    rng = np.random.default_rng(3)
    cube = np.full((40, 7, 7), np.nan)
    for p in range(40):
        base = rng.uniform(0.5, 0.8)
        for i in range(7):
            for j in range(i + 1, 7):
                cube[p, i, j] = cube[p, j, i] = np.clip(base + rng.normal(0, 0.05), 0, 1)
    spread = {"dev": rng.normal(0, 0.1, 20) - 0.0, "cross": rng.normal(0, 0.1, 20)}
    spread["dev"] -= spread["dev"].mean()
    spread["cross"] -= spread["cross"].mean()
    zero = power.simulate(cube, spread, "A", 0.0, 1, n_studies=100, n_boot=200)
    far = power.simulate(cube, spread, "A", 0.15, 1, n_studies=100, n_boot=200)
    assert zero["pass_95"] > 0.9 and far["pass_90"] == 0.0
    assert zero["half_width_95"] > zero["half_width_90"]
    exch = power.simulate(cube, spread, "C", 0.05, 2, n_studies=50, n_boot=100)
    assert exch["mean_estimate"] == pytest.approx(0.05, abs=0.02)


# ---------------------------------------------------------------- end to end


def _run(script: str, *args: str, root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, common.SYNTHETIC_ROOT_ENV: str(root)}
    return subprocess.run([sys.executable, str(PIPELINE / script), *args], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=600)


def test_synthetic_world_end_to_end(tmp_path):
    """The planted world through the real driver, 01, 02 and 03 (fewer draws for speed)."""
    for script, args in (("synthetic.py", ("--world", "planted")),
                         ("01_frame.py", ("--synthetic", "planted")),
                         ("02_audit.py", ("--synthetic", "planted")),
                         ("03_model.py", ("--synthetic", "planted", "--expect", "planted",
                                          "--n-boot", "400"))):
        res = _run(script, *args, root=tmp_path)
        assert res.returncode == 0, f"{script}: {res.stdout[-2000:]} {res.stderr[-2000:]}"
    assert "FAIL" not in res.stdout.split("dry-run check")[1]
    assert (tmp_path / "results" / "planted" / "model_report.md").exists()


def test_synthetic_audit_d_sheet_and_score(tmp_path):
    """The planted world's Audit D: arm-blind files, 6 per arm, protected input, a signed score."""
    for script, args in (("synthetic.py", ("--world", "planted")),
                         ("01_frame.py", ("--synthetic", "planted")),
                         ("02_audit.py", ("--synthetic", "planted", "--audit-d-sheet"))):
        res = _run(script, *args, root=tmp_path)
        assert res.returncode == 0, f"{script}: {res.stdout[-2000:]} {res.stderr[-2000:]}"
    raw = tmp_path / "interim" / "planted" / "raw"
    sheet, key, md = raw / "audit_d_sheet.csv", raw / "audit_d_key.csv", raw / "audit_d_answers.md"
    k = pd.read_csv(key)
    assert len(k) == 30 and set(k["arm"].value_counts()) == {6}
    for f in (sheet, md):
        text = f.read_text()
        assert not any(a in text for a in common.ALL_ARMS) and "b2b_" not in text
    edited = pd.read_csv(sheet, dtype=str).fillna("")
    edited.loc[0, "reviewer_notes"] = "checked"
    edited.to_csv(sheet, index=False)
    res = _run("02_audit.py", "--synthetic", "planted", "--audit-d-sheet", root=tmp_path)
    assert res.returncode == 0 and "already has reviewer input" in res.stdout
    res = _run("02_audit.py", "--synthetic", "planted", "--score-audit-d", "--signed-by", "Tester",
               root=tmp_path)
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    score = json.loads((tmp_path / "results" / "planted" / "audit_d_score.json").read_text())
    assert score["passes"] and score["signed_by"] == "Tester" and score["precision"] == 1.0
