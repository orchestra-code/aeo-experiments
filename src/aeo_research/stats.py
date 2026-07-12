"""Statistical machinery for pre-registered equivalence studies.

Design notes (see any experiment spec for the full rationale):

- Null claims are made via TOST equivalence testing against a pre-registered
  SESOI, never via a non-significant p-value alone.
- Models are pooled logits with cluster-robust standard errors. Two-way
  clustering (e.g. by execution AND by video) uses the Cameron–Gelbach–Miller
  combination ``V = V_a + V_b − V_ab``, which statsmodels does not provide
  natively for logit. If the combined matrix is not positive semi-definite,
  negative eigenvalues are floored at zero (the standard CGM fix); the
  pre-registered fallback is the element-wise max of the two one-way SEs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as sps
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.proportion import proportion_confint


class Verdict(str, Enum):
    NULL = "NULL — practically equivalent to zero"
    NEGLIGIBLE = "detectable but NEGLIGIBLE (inside SESOI)"
    REAL = "REAL EFFECT — exceeds SESOI"
    INCONCLUSIVE = "INCONCLUSIVE — underpowered, do NOT claim a null"


@dataclass
class TostResult:
    var: str
    beta: float
    se: float
    odds_ratio: float
    or_lo: float
    or_hi: float
    p_nhst: float
    p_tost: float
    verdict: Verdict

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["verdict"] = self.verdict.value
        return d


def tost(
    params: pd.Series,
    bse: pd.Series,
    pvalues: pd.Series,
    var: str,
    *,
    sesoi_or: float = 1.10,
    alpha: float = 0.10,
) -> TostResult:
    """Two One-Sided Tests against an odds-ratio SESOI band.

    The (1−alpha) CI must sit entirely inside [1/sesoi_or, sesoi_or] to claim
    practical equivalence to zero. A wide CI containing 1.0 is INCONCLUSIVE —
    the row people cheat on; we do not.
    """
    sesoi = np.log(sesoi_or)
    z = sps.norm.ppf(1 - alpha / 2)

    b = float(params[var])
    se = float(bse[var])
    lo, hi = b - z * se, b + z * se

    p_lower = sps.norm.sf((b + sesoi) / se)   # H0: beta <= -SESOI
    p_upper = sps.norm.cdf((b - sesoi) / se)  # H0: beta >= +SESOI
    p_tost = max(p_lower, p_upper)

    equivalent = (lo > -sesoi) and (hi < sesoi)
    nonzero = (lo > 0) or (hi < 0)

    if equivalent and not nonzero:
        verdict = Verdict.NULL
    elif equivalent and nonzero:
        verdict = Verdict.NEGLIGIBLE
    elif nonzero:
        verdict = Verdict.REAL
    else:
        verdict = Verdict.INCONCLUSIVE

    return TostResult(
        var=var,
        beta=b,
        se=se,
        odds_ratio=float(np.exp(b)),
        or_lo=float(np.exp(lo)),
        or_hi=float(np.exp(hi)),
        p_nhst=float(pvalues[var]),
        p_tost=float(p_tost),
        verdict=verdict,
    )


@dataclass
class ClusteredLogitResult:
    """Coefficients with cluster-robust (co)variance, TOST-ready."""

    formula: str
    params: pd.Series
    cov: pd.DataFrame
    nobs: int
    cluster_cols: tuple[str, ...]
    cgm_floored: bool = False  # negative eigenvalues were floored (two-way only)

    @property
    def bse(self) -> pd.Series:
        return pd.Series(np.sqrt(np.diag(self.cov)), index=self.params.index)

    @property
    def pvalues(self) -> pd.Series:
        z = self.params / self.bse
        return pd.Series(2 * sps.norm.sf(np.abs(z)), index=self.params.index)

    def tost(self, var: str, **kw) -> TostResult:
        return tost(self.params, self.bse, self.pvalues, var, **kw)


def _oneway_cov(model, groups: pd.Series) -> pd.DataFrame:
    codes, _ = pd.factorize(groups)
    fit = model.fit(disp=False, cov_type="cluster", cov_kwds={"groups": codes})
    return pd.DataFrame(fit.cov_params(), index=fit.params.index, columns=fit.params.index)


def fit_clustered_logit(
    df: pd.DataFrame,
    formula: str,
    cluster_cols: list[str] | tuple[str, ...],
) -> ClusteredLogitResult:
    """Pooled logit with one- or two-way cluster-robust SEs.

    Point estimates are identical across covariance choices; only the
    uncertainty differs. Rows with NA in any model variable are dropped by
    patsy; cluster columns are aligned to the retained rows.
    """
    cluster_cols = tuple(cluster_cols)
    if not 1 <= len(cluster_cols) <= 2:
        raise ValueError("cluster_cols must name one or two columns")

    model = smf.logit(formula, data=df)
    # Rows patsy kept (NA handling) — align cluster labels to these.
    kept = model.data.row_labels
    base = model.fit(disp=False)
    params = pd.Series(base.params, index=base.params.index)

    if len(cluster_cols) == 1:
        cov = _oneway_cov(model, df.loc[kept, cluster_cols[0]])
        return ClusteredLogitResult(formula, params, cov, int(base.nobs), cluster_cols)

    a = df.loc[kept, cluster_cols[0]]
    b = df.loc[kept, cluster_cols[1]]
    both = pd.Series(list(zip(a, b)), index=kept)

    v = _oneway_cov(model, a) + _oneway_cov(model, b) - _oneway_cov(model, both)

    # CGM can produce a non-PSD matrix; floor negative eigenvalues at zero.
    eigval, eigvec = np.linalg.eigh(v.to_numpy())
    floored = bool((eigval < 0).any())
    if floored:
        eigval = np.clip(eigval, 0, None)
        v = pd.DataFrame(
            eigvec @ np.diag(eigval) @ eigvec.T, index=v.index, columns=v.columns
        )

    return ClusteredLogitResult(formula, params, v, int(base.nobs), cluster_cols, floored)


def wilson_interval(successes, n, alpha: float = 0.10):
    """Wilson score interval — correct near the 0/1 boundaries."""
    return proportion_confint(successes, n, alpha=alpha, method="wilson")


def collinearity_report(df: pd.DataFrame, cols: list[str]) -> dict:
    """Pairwise correlations + VIFs for a candidate predictor set.

    Encodes the one-size-variable-per-model rule: fitting two log-size
    predictors together roughly doubles each SE and destroys equivalence
    power. Report this in every write-up so readers see why models are
    fitted separately.
    """
    d = df[cols].dropna()
    x = np.column_stack([np.ones(len(d)), d.to_numpy()])
    vifs = {c: float(variance_inflation_factor(x, i + 1)) for i, c in enumerate(cols)}
    return {"corr": d.corr(), "vif": vifs}
