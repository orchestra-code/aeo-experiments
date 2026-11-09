"""Experiment 011 release stage (pipeline/05_release.py).

Two layers. The fake-frame tests run anywhere: they build a tiny frame with made-up brand
and domain names and check the coding rules, the seed and the gate. The real-release tests
read the released CSV and datasheet (and, for the lexicon scan and the rebuild, the
gitignored lexicon and feature frame); each skips when its inputs are not on disk.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aeo_research import release_dataset
from aeo_research.anonymize import FORBIDDEN_SUBSTRINGS, MAX_TEXT_LEN, Datasheet

EXP = Path(__file__).resolve().parents[1] / "experiments" / "011-claude-code-fidelity"
PIPELINE = EXP / "pipeline"
SHADOWED = ("brands", "common", "shares", "01_features", "02_audit", "03_model", "05_release")


def _load(name: str):
    saved = {n: sys.modules.pop(n) for n in SHADOWED if n in sys.modules}
    sys.path.insert(0, str(PIPELINE))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(PIPELINE))
        for n in SHADOWED:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


release = _load("05_release")

PUBLIC_CSV = release.PUBLIC / f"{release.SLUG}.csv"
PUBLIC_SHEET = release.PUBLIC / f"{release.SLUG}.datasheet.md"
LEXICON = EXP / "data" / "raw" / "lexicon_v1_2.csv"
FEATURES = EXP / "data" / "interim" / "features.jsonl"

FAKE_NAMES = [("Fakeone", False), ("Zorbix & Co", False), ("Quillo", True)]
FAKE_CLASSES = {"newsdesk.com": "publisher", "fakeone.com": "vendor",
                "quillo-reviews.com": "publisher", "zorbixandco.com": "publisher",
                "reviewhall.com": "review marketplace"}


def fake_frame() -> pd.DataFrame:
    rows = []
    for arm in release.ALL_ARMS:
        for wave in (1, 2):
            sched = arm == "sched_kit"
            rows.append({
                "item_id": "b2b_01", "category": "CRM", "intent": "shortlist", "arm": arm,
                "surface": {"ui_default": "claude.ai", "opus55_plain": "api",
                            "sched_kit": "scheduled"}.get(arm, "local"),
                "wave": wave, "run_date": "" if sched else f"2026-11-0{wave + 2}",
                "model": None if arm in ("ui_default", "sched_kit") else "claude-opus-5-5",
                "resolved_model": "claude-opus-5-5" if sched else None,
                "claude_code_version": "2.1.316" if arm.startswith("cc_") else None,
                "brands": ["fakeone", "zorbix & co"] if wave == 1 else ["quillo"],
                "n_brands": 2 if wave == 1 else 1,
                "searched": True, "n_searches": None if sched else 3.0,
                "n_backend_searches": 3.0 if arm.startswith("cc_") else None,
                "n_fetches": None if sched or arm == "ui_default" else 0.0,
                "subagent_tool_uses": 4.0 if sched else None,
                "fetched": False if sched else None,
                "report_match": True if sched else None,
                "instruction_exact": True if sched else None,
                "cited_urls_source": "citations" if arm in ("ui_default", "opus55_plain")
                else "answer_links",
                "n_links": 4,
                "cited_domains": ["newsdesk.com", "fakeone.com", "quillo-reviews.com",
                                  "zorbixandco.com", "unmapped.io"],
                "n_cited_domains": 5,
                "evaluated_domains": [] if sched else ["reviewhall.com", "fakeone.com"],
                "n_evaluated": None if sched else 2.0,
                "chars": 4000, "coding_flag": False, "clarifying_questions": False,
                "collector_notes": False,
            })
    return pd.DataFrame(rows)


FIRE = {1: "2026-11-03", 2: "2026-11-04"}


def build(seed: int = release.SEED):
    return release.build_release(fake_frame(), FAKE_CLASSES, FAKE_NAMES, FIRE, seed=seed)


# ------------------------------------------------------------ fake frame


def test_codes_stable_under_the_seed():
    a, ba, sa = build()
    b, bb, sb = build()
    assert ba == bb and sa == sb
    pd.testing.assert_frame_equal(a, b)
    _, bc, sc = build(seed=release.SEED + 1)
    assert set(bc) == set(ba) and set(sc) == set(sa)


def test_code_map_is_a_seeded_permutation():
    values = {f"v{i}" for i in range(50)}
    m1 = release.code_map(values, "b", np.random.default_rng(7))
    m2 = release.code_map(values, "b", np.random.default_rng(7))
    m3 = release.code_map(values, "b", np.random.default_rng(8))
    assert m1 == m2 and m1 != m3
    assert sorted(m1.values()) == [f"b{i:04d}" for i in range(1, 51)]


def test_domains_coded_by_class_coverage_and_name():
    out, _, site = build()
    # vendor, unmapped, a brand name inside a publisher domain, and '&' spelled 'and'
    assert set(site) == {"fakeone.com", "unmapped.io", "quillo-reviews.com", "zorbixandco.com"}
    clear = {t for v in out["cited_domains"] for t in v.split("|") if not t.startswith("site_")}
    assert clear == {"newsdesk.com"}
    classes = out["cited_domain_classes"].iloc[0].split("|")
    assert classes == ["publisher", "vendor", "publisher", "publisher", "unclassified"]


def test_sched_kit_unknowns_are_empty_and_dates_filled():
    out, _, _ = build()
    s = out[out["arm"] == "sched_kit"]
    assert s["n_searches"].isna().all() and s["n_evaluated_urls"].isna().all()
    assert s["evaluated_domains"].isna().all() and s["n_evaluated_domains"].isna().all()
    assert set(s["run_date"]) == set(FIRE.values())
    assert set(out[out["arm"] == "ui_default"]["model_version"]) == {"claude.ai"}


def test_fake_release_passes_the_gate_and_the_scans(tmp_path):
    out, _, _ = build()
    patterns = release.name_patterns(FAKE_NAMES)
    release.scan_frame(out, patterns, release.normed_names(FAKE_NAMES))
    paths = release_dataset(out, release.COLUMNS, tmp_path,
                            Datasheet(title="t", dataset_slug="x", study="011", unit="answers"))
    text = paths["csv"].read_text() + paths["datasheet"].read_text()
    for name, _ in FAKE_NAMES:
        assert name.lower() not in text.lower()


def test_scanners_catch_names():
    patterns = release.name_patterns(FAKE_NAMES)
    assert release.lexicon_hits("we suggest Fakeone here", patterns)
    assert release.lexicon_hits("the Zorbix & Co add-on", patterns)
    assert not release.lexicon_hits("quillo in lower case", patterns)  # cs alias
    with pytest.raises(SystemExit):
        release.scan_text("try fakeone", patterns, "x")
    normed = release.normed_names(FAKE_NAMES)
    assert release.brand_named_domain("zorbixandco.com", normed)
    assert release.brand_named_domain("getfakeone.io", normed)
    assert not release.brand_named_domain("newsdesk.com", normed)


def test_no_column_name_is_forbidden():
    for spec in release.COLUMNS:
        assert not any(bad in spec.name.lower() for bad in FORBIDDEN_SUBSTRINGS), spec.name
        assert not spec.synthetic_study_text


# ------------------------------------------------------------ real release

needs_public = pytest.mark.skipif(not PUBLIC_CSV.exists(), reason="no released CSV on disk")
needs_lexicon = pytest.mark.skipif(not LEXICON.exists(), reason="lexicon is gitignored")


@pytest.fixture(scope="module")
def public() -> pd.DataFrame:
    return pd.read_csv(PUBLIC_CSV, dtype=str, keep_default_na=False)


@needs_public
def test_public_csv_shape_and_columns(public):
    assert list(public.columns) == [c.name for c in release.COLUMNS]
    assert len(public) == 600
    assert public.groupby("arm").size().to_dict() == {a: 120 for a in release.ALL_ARMS}
    assert "opus55_plain" in set(public["arm"])


@needs_public
def test_public_csv_passes_the_gate_again(public, tmp_path):
    release_dataset(public, release.COLUMNS, tmp_path,
                    Datasheet(title="t", dataset_slug="x", study="011", unit="answers"))


@needs_public
def test_public_csv_has_no_forbidden_content(public):
    free = {c.name for c in release.COLUMNS if not c.public_fact}
    for col in public.columns:
        assert not any(bad in col.lower() for bad in FORBIDDEN_SUBSTRINGS)
        if col in free:
            assert public[col].str.len().max() <= MAX_TEXT_LEN, col
    for col in ("brand_codes",):
        tokens = {t for v in public[col] for t in v.split("|") if t}
        assert all(len(t) == 5 and t.startswith("b") and t[1:].isdigit() for t in tokens)
    for col in ("cited_domains", "evaluated_domains"):
        tokens = {t for v in public[col] for t in v.split("|") if t}
        assert not any("/" in t or " " in t for t in tokens), col  # no URLs, no text


@needs_public
@needs_lexicon
def test_no_lexicon_name_in_csv_or_datasheet(public):
    names = release.lexicon_names(LEXICON)
    patterns = release.name_patterns(names)
    normed = release.normed_names(names)
    release.scan_frame(public.replace("", np.nan), patterns, normed)
    assert not release.lexicon_hits(PUBLIC_SHEET.read_text(), patterns)
    # Every canonical name, whatever its match mode, as a whole token of a domain or a value.
    tokens = {t.lower() for col in public.columns for v in public[col].unique()
              for t in str(v).split("|")}
    labels = {t.rsplit(".", 1)[0] for t in tokens if "." in t}
    canon = set(pd.read_csv(LEXICON, dtype=str)["canonical"].str.lower())
    assert not (canon & tokens) and not (canon & labels)


@needs_public
@pytest.mark.skipif(not (FEATURES.exists() and LEXICON.exists()), reason="raw inputs gitignored")
def test_public_csv_rebuilds_byte_for_byte():
    df = release.load_features()
    out, _, _ = release.build_release(df, release.load_classes(),
                                      release.lexicon_names(LEXICON), release.sched_fire_dates())
    assert out.to_csv(index=False) == PUBLIC_CSV.read_text()
