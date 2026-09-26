"""Experiment 009 per-category share test (H1s / H1d): statistic, bootstrap, power."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PIPELINE = (
    Path(__file__).resolve().parents[1] / "experiments" / "009-claude-model-fidelity" / "pipeline"
)
sys.path.insert(0, str(PIPELINE))
shares = importlib.import_module("shares")


def test_null_abs_diff_exact_values():
    assert shares.null_abs_diff(0.0, 6, 6) == 0.0
    assert shares.null_abs_diff(1.0, 6, 6) == 0.0
    assert shares.null_abs_diff(0.5, 1, 1) == pytest.approx(0.5)
    # Matches a brute-force simulation of two binomial draws.
    rng = np.random.default_rng(1)
    sim = np.abs(rng.binomial(6, 0.4, 200_000) / 6 - rng.binomial(6, 0.4, 200_000) / 6).mean()
    assert shares.null_abs_diff(0.4, 6, 6) == pytest.approx(sim, abs=0.003)


def test_prompt_multisets_sum_to_one():
    for n in (1, 2, 3):
        ms = shares._prompt_multisets(n)
        assert sum(p for _, p in ms) == pytest.approx(1.0)
    assert len(shares._prompt_multisets(2)) == 3


def frame(ui_sets, arm_sets, category="CRM"):
    rows = []
    for who, sets in (("ui_default", ui_sets), ("arm", arm_sets)):
        for i, s in enumerate(sets):
            rows.append({"arm": who, "category": category, "item_id": f"p{i // 3}",
                         "wave": i % 3 + 1, "brands": s})
    return pd.DataFrame(rows)


def test_build_cells_and_point_estimate():
    ui = [{"a", "b"}, {"a"}, {"a", "c"}, {"a"}, {"b"}, {"a"}]  # a 5/6, b 2/6, c 1/6
    arm = [{"a"}, {"a"}, {"a"}, {"a"}, {"a"}, set()]           # a 5/6, b 0
    cells = shares.build_cells(frame(ui, arm), "arm")
    assert len(cells) == 1 and cells[0].ref.shape == (2, 3, 3)
    est = shares.share_excess(cells)
    assert est["basket_size"] == 2  # a and b (c is below 1/3)
    assert est["mad"] == pytest.approx((0 + 2 / 6) / 2)
    null = (shares.null_abs_diff(5 / 6, 6, 6) + shares.null_abs_diff(2 / 6, 6, 6)) / 2
    assert est["excess"] == pytest.approx(est["mad"] - null)


def test_identical_panels_have_negative_excess_and_pass():
    ui = [{"a", "b"}, {"a"}, {"a", "b"}, {"a"}, {"b"}, {"a"}]
    frames = [frame(ui, ui, category=f"c{k}") for k in range(20)]
    cells = shares.build_cells(pd.concat(frames), "arm")
    res = shares.share_test(cells, n_boot=500)
    assert res.mad == 0.0 and res.excess < 0 and res.passes


def test_disjoint_panels_fail():
    ui = [{"a", "b"}] * 6
    arm = [{"x"}] * 6
    frames = [frame(ui, arm, category=f"c{k}") for k in range(20)]
    res = shares.share_test(shares.build_cells(pd.concat(frames), "arm"), n_boot=500)
    assert res.mad == pytest.approx(1.0) and not res.passes and res.lower > 0.5


def test_power_brackets_sesoi():
    pool = [np.array([0.9, 0.7, 0.5, 0.4, 0.2, 0.1])] * 5
    near = shares.power(pool, 0.0, reps=20, n_boot=300)
    far = shares.power(pool, 0.20, reps=20, n_boot=300)
    assert far["p_pass"] == 0.0
    assert near["basket_mean"] > far["basket_mean"] * 0.5
    assert near["p_pass"] >= far["p_pass"]


def test_rmsd_is_unbiased_without_prompt_effects():
    rng = np.random.default_rng(3)
    pool = [np.array([0.8, 0.6, 0.5, 0.4])] * 200
    est = []
    for _ in range(20):
        cells = shares.simulate_cells(pool, 0.10, rng=rng)
        est.append(shares.share_excess(cells, basket_on="pooled")["rmsd"])
    assert np.mean(est) == pytest.approx(0.10, abs=0.02)


def test_share_test_rejects_unknown_statistic():
    with pytest.raises(ValueError):
        shares.share_test([], statistic="median")
