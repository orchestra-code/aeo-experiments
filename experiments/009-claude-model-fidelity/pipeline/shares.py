"""Per-category panel-share test for experiment 009 (H1s brands, H1d domains).

Why per category: the panel has 20 software categories with 2 prompts each,
so a vendor sold in one category appears in at most 2 of 40 prompts. Shares
pooled over the whole panel all sit near or below 0.05 and a pooled MAD
below 0.05 would pass by construction. Shares are therefore computed within
each category.

Construction (spec §4 H1s / H1d, §5):

- **Share.** For arm a, category c and item k (a canonical brand, or a
  registered domain the answer cites): the fraction of arm a's answers in
  category c (2 prompts x waves, 6 answers at the confirmatory design) whose
  item set contains k.
- **Basket.** Cells (c, k) with share at least ``threshold`` (1/3 by default:
  2 of 6 answers). ``basket_on="ref"`` selects on the reference arm's share
  (``ui_default``); ``basket_on="pooled"`` selects on the mean of both arms'
  shares, which does not inflate their difference through selection.
- **Statistic ``excess``** (first proposal): MAD over the basket of
  |share_arm - share_ref| minus the MAD expected from sampling alone, i.e.
  per cell E|X/n_ref - Y/n_arm| with X ~ Bin(n_ref, p), Y ~ Bin(n_arm, p) at
  p = the reference share, computed exactly (the limit of a parametric
  bootstrap of two independent draws at the reference shares).
- **Statistic ``rmsd``** (alternative): noise-corrected root-mean-square
  difference, signed sqrt of the basket mean of
  (s_arm - s_ref)^2 - s_arm(1 - s_arm)/(n_arm - 1) - s_ref(1 - s_ref)/(n_ref - 1),
  an unbiased estimate of the squared difference of the true shares.
- **Test.** Two-stage cluster bootstrap: resample categories with
  replacement, then prompts within each drawn category with replacement
  (every wave and both arms of a drawn prompt travel together); basket and
  noise terms are recomputed in every draw, with a prompt drawn twice
  counted at its effective sample size. Pass (equivalent) when the one-sided
  upper bound (the 1 - alpha/2 quantile, 95th percentile at alpha = 0.10,
  matching a 90% two-sided CI) is below ``sesoi`` (0.05).

Power (pilot-scale shares, 40 prompts, 3 waves; ``pilot_report.py``): with
6 answers per arm per category a single cell's share difference has a
sampling SD near 0.27. ``excess`` passes when the arms agree but is
attenuated (absolute differences of noisy shares respond weakly to small
true differences), so a true 0.05 difference still passes often. ``rmsd``
is unbiased but its upper bound cannot reach 0.05 at this sample size. See
spec §5 for the resulting decision.

The bootstrap is exact in the prompt stage: each category's possible prompt
multisets are enumerated with their multinomial probabilities, so a draw
only picks categories and one multiset per category. That keeps 2,000 draws
cheap enough for the power simulation.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.stats import binom

THRESHOLD = 1 / 3
SESOI = 0.05
ALPHA = 0.10
_EPS = 1e-9


@lru_cache(maxsize=None)
def _null_abs_diff(p_key: float, n_ref: int, n_arm: int) -> float:
    if n_ref == 0 or n_arm == 0:
        return float("nan")
    p = min(max(p_key, 0.0), 1.0)
    x = np.arange(n_ref + 1)
    y = np.arange(n_arm + 1)
    px = binom.pmf(x, n_ref, p)
    py = binom.pmf(y, n_arm, p)
    diff = np.abs(x[:, None] / n_ref - y[None, :] / n_arm)
    return float((px[:, None] * py[None, :] * diff).sum())


def null_abs_diff(p: float, n_ref: int, n_arm: int) -> float:
    """E|X/n_ref - Y/n_arm|, X ~ Bin(n_ref, p), Y ~ Bin(n_arm, p)."""
    return _null_abs_diff(round(float(p), 9), int(n_ref), int(n_arm))


# ------------------------------------------------------------ data layout


@dataclass
class CategoryCells:
    """One category's answers as indicator arrays.

    ``ref`` and ``arm`` have shape (prompts, answers_per_prompt, items); a
    missing answer is a row of NaN. ``items`` names the item axis.
    """

    category: str
    items: list
    ref: np.ndarray
    arm: np.ndarray


def build_cells(
    df: pd.DataFrame,
    arm: str,
    ref: str = "ui_default",
    col: str = "brands",
    *,
    arm_col: str = "arm",
    category_col: str = "category",
    prompt_col: str = "item_id",
    wave_col: str = "wave",
) -> list[CategoryCells]:
    """Indicator arrays per category from a frame with one row per answer.

    ``df[col]`` holds an iterable of items per answer (canonical brands, or
    cited registered domains). Only categories where both arms have answers
    are kept.
    """
    sub = df[df[arm_col].isin([arm, ref])]
    out: list[CategoryCells] = []
    for cat, g in sub.groupby(category_col, sort=True):
        if not ((g[arm_col] == arm).any() and (g[arm_col] == ref).any()):
            continue
        prompts = sorted(g[prompt_col].unique())
        waves = sorted(g[wave_col].unique())
        items = sorted({x for s in g[col] for x in s})
        index = {k: i for i, k in enumerate(items)}
        arrays = {}
        for who in (ref, arm):
            a = np.full((len(prompts), len(waves), len(items)), np.nan)
            for r in g[g[arm_col] == who].itertuples():
                pi = prompts.index(getattr(r, prompt_col))
                wi = waves.index(getattr(r, wave_col))
                a[pi, wi, :] = 0.0
                for x in getattr(r, col):
                    a[pi, wi, index[x]] = 1.0
            arrays[who] = a
        out.append(CategoryCells(str(cat), items, arrays[ref], arrays[arm]))
    return out


# ------------------------------------------------------------ statistic


def _prompt_multisets(n_prompts: int) -> list[tuple[tuple[int, ...], float]]:
    """All prompt multisets of size n drawn with replacement, with probabilities."""
    out = []
    for combo in itertools.combinations_with_replacement(range(n_prompts), n_prompts):
        counts = np.bincount(combo, minlength=n_prompts)
        prob = math.factorial(n_prompts) / np.prod([math.factorial(c) for c in counts])
        out.append((combo, prob / n_prompts**n_prompts))
    return out


#: Per-category sums kept for every prompt multiset (columns of the tables).
_ABS, _NULL, _D2, _SIZE, _PROB = range(5)


def _cell_sums(ref: np.ndarray, arm: np.ndarray, threshold: float,
               weights: np.ndarray | None = None, basket_on: str = "ref") -> np.ndarray:
    """[sum |arm - ref|, sum sampling-only |diff|, sum unbiased d^2, basket size].

    ``weights`` (one per prompt) are bootstrap multiplicities. A prompt drawn
    twice counts twice in the shares but adds no new information, so the
    noise terms use the Kish effective number of answers,
    (sum w)^2 / sum w^2 over answers, rounded.

    ``basket_on``: "ref" selects cells on the reference share (the original
    construction); "pooled" selects on the mean of both arms' shares, which is
    uncorrelated with their difference when the two sampling noises have
    equal variance, so selection does not inflate the difference.

    Unbiased d^2 per cell: (s_arm - s_ref)^2 - s_arm(1 - s_arm)/(n_arm - 1)
    - s_ref(1 - s_ref)/(n_ref - 1), whose expectation is the squared
    difference of the true shares.
    """
    zero = np.zeros(4)
    if ref.shape[-1] == 0:
        return zero
    w = np.ones(ref.shape[0]) if weights is None else np.asarray(weights, dtype=float)

    def shares_and_n(a: np.ndarray) -> tuple[np.ndarray, int]:
        present = ~np.isnan(a[..., 0])  # (prompts, answers)
        aw = (present * w[:, None]).ravel()
        if aw.sum() == 0:
            return np.zeros(a.shape[-1]), 0
        flat = np.nan_to_num(a.reshape(-1, a.shape[-1]))
        share = (flat * aw[:, None]).sum(axis=0) / aw.sum()
        n_eff = int(round(aw.sum() ** 2 / (aw**2).sum()))
        return share, n_eff

    s_ref, n_ref = shares_and_n(ref)
    s_arm, n_arm = shares_and_n(arm)
    if n_ref == 0 or n_arm == 0:
        return zero
    select = s_ref if basket_on == "ref" else (s_ref + s_arm) / 2
    basket = select >= threshold - _EPS
    if not basket.any():
        return zero
    diff = s_arm[basket] - s_ref[basket]
    null = sum(null_abs_diff(p, n_ref, n_arm) for p in s_ref[basket])
    var_r = s_ref[basket] * (1 - s_ref[basket]) / max(n_ref - 1, 1)
    var_a = s_arm[basket] * (1 - s_arm[basket]) / max(n_arm - 1, 1)
    d2 = diff**2 - var_r - var_a
    return np.array([np.abs(diff).sum(), null, d2.sum(), basket.sum()], dtype=float)


def _category_table(cells: list[CategoryCells], threshold: float, basket_on: str):
    """Per category, one row per prompt multiset: the sums plus its probability."""
    tables = []
    for c in cells:
        rows = []
        n_prompts = c.ref.shape[0]
        for combo, prob in _prompt_multisets(n_prompts):
            weights = np.bincount(combo, minlength=n_prompts)
            rows.append([*_cell_sums(c.ref, c.arm, threshold, weights, basket_on), prob])
        tables.append(np.array(rows))
    return tables


def _signed_sqrt(x):
    return np.sign(x) * np.sqrt(np.abs(x))


def _stats(sums: np.ndarray) -> dict:
    """Statistics from summed columns (last axis: abs, null, d2, size)."""
    size = sums[..., _SIZE]
    with np.errstate(invalid="ignore", divide="ignore"):
        mad = sums[..., _ABS] / size
        null = sums[..., _NULL] / size
        return {"mad": mad, "null_mad": null, "excess": mad - null,
                "rmsd": _signed_sqrt(sums[..., _D2] / size)}


#: The test statistics. ``excess`` = MAD minus the sampling-only MAD (the
#: first proposal); ``rmsd`` = noise-corrected root-mean-square difference.
STATISTICS = ("excess", "rmsd")


@dataclass
class ShareTestResult:
    statistic: str
    basket_on: str
    threshold: float
    basket_size: int
    n_categories: int
    mad: float
    null_mad: float
    excess: float
    rmsd: float
    upper: float
    lower: float
    sesoi: float
    passes: bool
    n_boot: int

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def share_excess(cells: list[CategoryCells], threshold: float = THRESHOLD,
                 basket_on: str = "ref") -> dict:
    """Point estimates: basket size, MAD, sampling-only MAD, excess, RMSD."""
    total = sum((_cell_sums(c.ref, c.arm, threshold, None, basket_on) for c in cells),
                np.zeros(4))
    out = {k: float(v) for k, v in _stats(total).items()}
    out["basket_size"] = int(total[_SIZE])
    return out


def share_test(
    cells: list[CategoryCells],
    *,
    statistic: str = "rmsd",
    basket_on: str = "pooled",
    threshold: float = THRESHOLD,
    sesoi: float = SESOI,
    alpha: float = ALPHA,
    n_boot: int = 2000,
    seed: int = 20260926,
) -> ShareTestResult:
    """Equivalence test on a share statistic (one-sided upper bound vs ``sesoi``)."""
    if statistic not in STATISTICS:
        raise ValueError(f"statistic must be one of {STATISTICS}")
    point = share_excess(cells, threshold, basket_on)
    nan = float("nan")
    if not cells or point["basket_size"] == 0:
        return ShareTestResult(statistic, basket_on, threshold, 0, len(cells), nan, nan, nan,
                               nan, nan, nan, sesoi, False, 0)
    tables = _category_table(cells, threshold, basket_on)
    rng = np.random.default_rng(seed)
    n_cat = len(tables)
    totals = np.zeros((n_boot, 4))
    cat_draws = rng.integers(0, n_cat, size=(n_boot, n_cat))
    for j in range(n_cat):
        chosen = cat_draws[:, j]
        for ci in np.unique(chosen):
            t = tables[ci]
            rows = np.flatnonzero(chosen == ci)
            pick = rng.choice(len(t), size=len(rows), p=t[:, _PROB] / t[:, _PROB].sum())
            totals[rows] += t[pick, :4]
    ok = totals[:, _SIZE] > 0
    boots = _stats(totals[ok])[statistic]
    lower, upper = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return ShareTestResult(
        statistic=statistic,
        basket_on=basket_on,
        threshold=threshold,
        basket_size=point["basket_size"],
        n_categories=n_cat,
        mad=point["mad"],
        null_mad=point["null_mad"],
        excess=point["excess"],
        rmsd=point["rmsd"],
        upper=float(upper),
        lower=float(lower),
        sesoi=sesoi,
        passes=bool(upper < sesoi),
        n_boot=int(ok.sum()),
    )


# ------------------------------------------------------------ simulation


def simulate_cells(
    category_shares: list[np.ndarray],
    excess: float,
    *,
    n_prompts: int = 2,
    n_waves: int = 3,
    kappa: float | None = None,
    rng: np.random.Generator,
) -> list[CategoryCells]:
    """Synthetic reference and arm answers at given true reference shares.

    ``category_shares``: one array of true reference shares per category
    (items). The arm's true share is p +/- ``excess`` (random sign, flipped
    when it would leave [0, 1]), so the arm's true MAD from the reference is
    ``excess`` on every cell. With ``kappa``, each prompt draws its own
    shares from Beta(kappa p, kappa (1 - p)) and both arms share that prompt
    effect (answers to one prompt resemble each other in every arm).
    """
    cells = []
    for ci, p in enumerate(category_shares):
        p = np.clip(np.asarray(p, dtype=float), 0.0, 1.0)
        sign = rng.choice([-1.0, 1.0], size=p.shape)
        q = p + sign * excess
        flip = (q < 0) | (q > 1)
        q[flip] = p[flip] - sign[flip] * excess
        q = np.clip(q, 0.0, 1.0)
        ref = np.zeros((n_prompts, n_waves, len(p)))
        arm = np.zeros_like(ref)
        for j in range(n_prompts):
            if kappa:
                pj = rng.beta(np.maximum(kappa * p, 1e-3), np.maximum(kappa * (1 - p), 1e-3))
                qj = np.clip(pj + (q - p), 0.0, 1.0)
            else:
                pj, qj = p, q
            ref[j] = rng.random((n_waves, len(p))) < pj
            arm[j] = rng.random((n_waves, len(p))) < qj
        cells.append(CategoryCells(f"c{ci}", list(range(len(p))), ref, arm))
    return cells


def power(
    pool: list[np.ndarray],
    excess: float,
    *,
    n_categories: int = 20,
    reps: int = 300,
    n_boot: int = 1000,
    threshold: float = THRESHOLD,
    statistic: str = "rmsd",
    basket_on: str = "pooled",
    kappa: float | None = None,
    seed: int = 20260926,
) -> dict:
    """Share of simulated studies that pass (upper bound < sesoi) and that
    detect a real difference (lower bound > 0), plus the basket size.

    Each study draws ``n_categories`` categories' true shares from ``pool``
    (with replacement).
    """
    rng = np.random.default_rng(seed)
    passes, real, baskets, estimates = 0, 0, [], []
    for rep in range(reps):
        shares = [pool[i] for i in rng.integers(0, len(pool), n_categories)]
        cells = simulate_cells(shares, excess, kappa=kappa, rng=rng)
        res = share_test(cells, statistic=statistic, basket_on=basket_on,
                         threshold=threshold, n_boot=n_boot, seed=seed + rep)
        passes += res.passes
        real += bool(res.lower > 0)
        baskets.append(res.basket_size)
        estimates.append(getattr(res, statistic))
    return {
        "true_excess": excess,
        "p_pass": passes / reps,
        "p_real": real / reps,
        "basket_mean": float(np.mean(baskets)),
        "basket_min": int(np.min(baskets)),
        "estimate_mean": float(np.nanmean(estimates)),
    }
