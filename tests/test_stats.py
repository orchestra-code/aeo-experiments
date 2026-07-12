import numpy as np
import pandas as pd
import pytest

from aeo_research.stats import Verdict, collinearity_report, fit_clustered_logit, tost
from aeo_research.synthetic import synthesize


def _series(beta, se, p=0.5):
    return (
        pd.Series({"x": beta}),
        pd.Series({"x": se}),
        pd.Series({"x": p}),
    )


class TestTost:
    def test_null_when_tight_ci_inside_band(self):
        # 90% CI = 0 ± 1.645*0.03 = ±0.049, well inside ±log(1.10)=±0.0953
        r = tost(*_series(0.0, 0.03), "x")
        assert r.verdict is Verdict.NULL
        assert r.or_lo > 1 / 1.10 and r.or_hi < 1.10

    def test_inconclusive_when_wide_ci(self):
        r = tost(*_series(0.0, 0.20), "x")
        assert r.verdict is Verdict.INCONCLUSIVE

    def test_real_when_effect_exceeds_band(self):
        r = tost(*_series(0.30, 0.05), "x")
        assert r.verdict is Verdict.REAL

    def test_negligible_when_nonzero_but_inside_band(self):
        # CI = 0.05 ± 0.016 → excludes 0, inside the band
        r = tost(*_series(0.05, 0.01), "x")
        assert r.verdict is Verdict.NEGLIGIBLE

    def test_hand_computed_bounds(self):
        r = tost(*_series(0.1, 0.02), "x", sesoi_or=1.5, alpha=0.10)
        z = 1.6448536269514722
        assert r.or_lo == pytest.approx(np.exp(0.1 - z * 0.02))
        assert r.or_hi == pytest.approx(np.exp(0.1 + z * 0.02))


def prep(n=2000, true_effect=0.0, seed=7):
    d = synthesize(n=n, true_effect=true_effect, n_other_platforms=0, seed=seed)
    d["moment"] = d["timestamp_seconds"].notna().astype(int)
    d["log_subs"] = np.log10(d["audience_size"] + 1)
    d["log_duration"] = np.log10(d["duration_seconds"] + 1)
    for c in ["log_subs", "log_duration", "similarity"]:
        d[c] = (d[c] - d[c].mean()) / d[c].std()
    d["chapters"] = d["has_chapters"].astype(float)
    return d


@pytest.fixture(scope="module")
def df():
    return prep()


class TestClusteredLogit:

    FORMULA = "moment ~ similarity + chapters + log_duration + log_subs"

    def test_oneway_matches_statsmodels(self, df):
        import statsmodels.formula.api as smf

        res = fit_clustered_logit(df, self.FORMULA, ["execution_id"])
        codes, _ = pd.factorize(df["execution_id"])
        direct = smf.logit(self.FORMULA, data=df).fit(
            disp=False, cov_type="cluster", cov_kwds={"groups": codes}
        )
        assert np.allclose(res.params, direct.params)
        assert np.allclose(res.bse, direct.bse)

    def test_twoway_runs_and_is_sane(self, df):
        res2 = fit_clustered_logit(df, self.FORMULA, ["execution_id", "video_id"])
        res_a = fit_clustered_logit(df, self.FORMULA, ["execution_id"])
        assert np.all(np.isfinite(res2.bse))
        assert np.all(res2.bse > 0)
        # Two-way SEs should be within an order of magnitude of one-way.
        assert np.all(res2.bse < res_a.bse * 10)
        assert np.all(res2.bse > res_a.bse / 10)

    def test_positive_controls_detected(self, df):
        # Chapters and duration drive moment citation in the generator.
        res = fit_clustered_logit(df, self.FORMULA, ["execution_id"])
        for var in ["chapters", "log_duration"]:
            r = res.tost(var)
            assert r.beta > 0
            assert r.p_nhst < 0.01

    def test_null_effect_judged_null(self):
        d = prep(n=5400, true_effect=0.0, seed=42)
        res = fit_clustered_logit(d, self.FORMULA, ["execution_id"])
        assert res.tost("log_subs").verdict is Verdict.NULL

    def test_real_effect_detected(self):
        d = prep(n=5400, true_effect=0.30, seed=42)
        res = fit_clustered_logit(d, self.FORMULA, ["execution_id"])
        assert res.tost("log_subs").verdict is Verdict.REAL


def test_collinearity_report():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 500)
    df = pd.DataFrame({"a": a, "b": a * 0.95 + rng.normal(0, 0.3, 500)})
    rep = collinearity_report(df, ["a", "b"])
    assert rep["corr"].loc["a", "b"] > 0.9
    assert rep["vif"]["a"] > 4
