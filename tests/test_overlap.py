"""Overlap metrics + cluster-bootstrap TOST, incl. the mandated power sim."""

import numpy as np
import pandas as pd
import pytest

from aeo_research.overlap import (
    cluster_boot,
    condition_pairs,
    jaccard,
    pair_values,
    permutation_pvalue,
    rbo,
    tfidf_cosine,
    token_set,
)
from aeo_research.stats import Verdict


# ---------------------------------------------------------------- metrics


def test_jaccard():
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert jaccard({"a"}, {"a"}) == 1.0
    assert jaccard({"a"}, set()) == 0.0
    assert np.isnan(jaccard(set(), set()))


def test_rbo_bounds_and_order_sensitivity():
    assert rbo(["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1.0)
    assert rbo(["a", "b"], ["c", "d"]) == 0.0
    assert np.isnan(rbo([], []))
    # Same sets, different order: top-weightedness => reversal scores < 1.
    same_top = rbo(["a", "b", "c"], ["a", "c", "b"])
    reversed_ = rbo(["a", "b", "c"], ["c", "b", "a"])
    assert 0 < reversed_ < same_top < 1.0


def test_token_set_normalization():
    ts = token_set(["Best noise-cancelling headphones for TRAVEL?", "headphones travel"])
    assert ts == {"noise", "cancelling", "headphones", "travel"}


def test_tfidf_cosine():
    sims = tfidf_cosine(
        ["the sony headphones are great", "the sony headphones are great",
         "coffee shop branding agency", ""]
    )
    assert sims[0, 1] == pytest.approx(1.0, abs=1e-9)
    assert sims[0, 2] == pytest.approx(0.0, abs=1e-9)
    assert sims[3, 3] == 0.0  # empty text has no self-similarity


# ---------------------------------------------------- pair enumeration


def make_responses(n_prompts=4, waves=2, intent="headphones", prefix="h"):
    rows = []
    for p in range(n_prompts):
        for w in range(1, waves + 1):
            rows.append({"item_id": f"{prefix}{p:03d}", "intent": intent, "wave": w})
    return pd.DataFrame(rows)


def test_condition_pairs_counts():
    df = pd.concat(
        [make_responses(4, 2), make_responses(3, 1, intent="coffee", prefix="c")],
        ignore_index=True,
    )
    pairs = condition_pairs(df, primary_intent="headphones", contrast_intent="coffee")
    counts = pairs["condition"].value_counts().to_dict()
    # within: 4 prompts x C(2,2 waves)=1 pair each; between: 2 waves x C(4,2)=6;
    # cross: wave1 only (coffee has 1 wave) = 4 x 3.
    assert counts == {"within_prompt": 4, "between_prompt": 12, "cross_intent": 12}
    within = pairs[pairs["condition"] == "within_prompt"]
    assert (within["cluster_i"] == within["cluster_j"]).all()


def test_pair_values_applies_metric():
    df = make_responses(2, 2)
    values = [{"a"}, {"a"}, {"a"}, {"b"}]
    pairs = condition_pairs(df, primary_intent="headphones")
    got = pair_values(pairs, values, jaccard)
    assert set(got.unique()) <= {0.0, 1.0}


# ---------------------------------------------------- bootstrap + TOST


def synth_pairs(delta: float, n_prompts: int = 60, noise: float = 0.05, seed: int = 7):
    """Within/between pairs whose true mean difference is exactly delta."""
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_prompts):
        base = rng.uniform(0.4, 0.6)
        for _ in range(6):
            rows.append(
                {"condition": "within_prompt", "cluster_i": f"p{p}", "cluster_j": f"p{p}",
                 "value": np.clip(base + delta + rng.normal(0, noise), 0, 1)}
            )
        for q in range(p + 1, min(p + 6, n_prompts)):
            rows.append(
                {"condition": "between_prompt", "cluster_i": f"p{p}", "cluster_j": f"p{q}",
                 "value": np.clip(base + rng.normal(0, noise), 0, 1)}
            )
    return pd.DataFrame(rows)


def test_power_sim_null_when_delta_zero():
    res = cluster_boot(
        synth_pairs(0.0), contrast=("within_prompt", "between_prompt"),
        sesoi=0.10, n_boot=500,
    )
    assert res.verdict in (Verdict.NULL, Verdict.NEGLIGIBLE)
    assert abs(res.estimate) < 0.05


def test_power_sim_real_when_delta_exceeds_sesoi():
    res = cluster_boot(
        synth_pairs(0.30), contrast=("within_prompt", "between_prompt"),
        sesoi=0.10, n_boot=500,
    )
    assert res.verdict == Verdict.REAL
    assert res.estimate == pytest.approx(0.30, abs=0.05)


def test_inconclusive_when_underpowered():
    res = cluster_boot(
        synth_pairs(0.0, n_prompts=4, noise=0.4),
        contrast=("within_prompt", "between_prompt"), sesoi=0.10, n_boot=300,
    )
    assert res.verdict == Verdict.INCONCLUSIVE


def test_level_contrast_and_nan_exclusion():
    pairs = synth_pairs(0.2)
    pairs.loc[pairs.index[:10], "value"] = np.nan
    res = cluster_boot(pairs, contrast=("between_prompt", None), n_boot=300)
    assert 0.3 < res.estimate < 0.7
    assert res.verdict is None
    assert res.n_nan > 0


def test_permutation_pvalue_detects_signal_and_null():
    def null_stats(rng):
        return float(rng.normal(0, 1))

    p_signal = permutation_pvalue(5.0, null_stats, n_perm=500)
    p_null = permutation_pvalue(0.0, null_stats, n_perm=500)
    assert p_signal < 0.01
    assert p_null > 0.3


def test_cluster_boot_requires_pairs():
    with pytest.raises(ValueError):
        cluster_boot(
            pd.DataFrame(columns=["condition", "cluster_i", "cluster_j", "value"]),
            contrast=("within_prompt", "between_prompt"),
        )
