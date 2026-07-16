"""Set/rank overlap metrics and cluster-bootstrap TOST for pairwise designs.

Built for prompt-consistency studies: N prompts x W repeated runs, comparing
artifact overlap (brand sets, cited domains, grounding-query tokens) between
pair conditions (within-prompt, between-prompt, cross-intent).

Inference notes:

- Pairwise overlap observations are dependent — every response participates in
  many pairs. All confidence intervals therefore come from a cluster bootstrap
  that resamples PROMPTS (the independent units), never pairs. Pair weights in
  a resample respect multiplicity: a pair between clusters drawn ``c_i`` and
  ``c_j`` times carries weight ``c_i * c_j``; a within-cluster pair carries
  ``c_i``.
- Equivalence claims use TOST logic on the absolute scale: the (1 - alpha)
  bootstrap CI must sit entirely inside ``[-sesoi, +sesoi]``. Verdict mapping
  is identical to :func:`aeo_research.stats.tost`.
- NaN metric values (e.g. Jaccard of two empty sets) are excluded from every
  statistic; report the exclusion rate in the audit stage.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse

from aeo_research.stats import Verdict

# ---------------------------------------------------------------- metrics


def jaccard(a: set, b: set) -> float:
    """|A ∩ B| / |A ∪ B|; NaN when both sets are empty (no evidence either way)."""
    if not a and not b:
        return float("nan")
    return len(a & b) / len(a | b)


def rbo(ranked_a: list, ranked_b: list, p: float = 0.9) -> float:
    """Rank-biased overlap, truncated at the longer list and normalized.

    Normalization divides by the maximum attainable score at these depths, so
    identical lists score 1.0 despite truncation (no extrapolation term —
    deterministic and preregisterable). NaN when both lists are empty.
    """
    if not ranked_a and not ranked_b:
        return float("nan")
    depth = max(len(ranked_a), len(ranked_b))
    seen_a: set = set()
    seen_b: set = set()
    score = 0.0
    max_score = 0.0
    for d in range(1, depth + 1):
        if d <= len(ranked_a):
            seen_a.add(ranked_a[d - 1])
        if d <= len(ranked_b):
            seen_b.add(ranked_b[d - 1])
        weight = (1 - p) * p ** (d - 1)
        score += weight * len(seen_a & seen_b) / d
        max_score += weight * min(d, len(ranked_a), len(ranked_b)) / d
    return score / max_score if max_score > 0 else float("nan")


#: Minimal English stopword list for search-query token overlap. Small on
#: purpose: fan-out queries are short and keyword-like; aggressive stopword
#: removal would delete signal.
QUERY_STOPWORDS = frozenset(
    "a an and are as at be best by for from how in is it of on or the to "
    "top what which with you your".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def token_set(queries: Iterable[str], stopwords: frozenset[str] = QUERY_STOPWORDS) -> set[str]:
    """Union of normalized tokens across a response's queries."""
    out: set[str] = set()
    for q in queries:
        out.update(t for t in _TOKEN_RE.findall(q.lower()) if t not in stopwords)
    return out


def tfidf_cosine(texts: list[str], ngram_max: int = 2) -> np.ndarray:
    """Pairwise TF-IDF cosine similarity (uni+bigrams), no sklearn dependency.

    Returns an ``n x n`` dense similarity matrix. Rows with no tokens get zero
    similarity to everything (including themselves).
    """
    vocab: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    for i, text in enumerate(texts):
        tokens = _TOKEN_RE.findall(text.lower())
        grams: list[str] = list(tokens)
        for n in range(2, ngram_max + 1):
            grams += [" ".join(tokens[j : j + n]) for j in range(len(tokens) - n + 1)]
        counts: dict[str, int] = {}
        for g in grams:
            counts[g] = counts.get(g, 0) + 1
        for g, c in counts.items():
            j = vocab.setdefault(g, len(vocab))
            rows.append(i)
            cols.append(j)
            vals.append(float(c))
    n = len(texts)
    if not vocab:
        return np.zeros((n, n))
    m = sparse.csr_matrix((vals, (rows, cols)), shape=(n, len(vocab)))
    df = np.asarray((m > 0).sum(axis=0)).ravel()
    idf = np.log((1 + n) / (1 + df)) + 1.0
    m = m.multiply(idf)  # type: ignore[assignment]
    norms = np.sqrt(np.asarray(m.multiply(m).sum(axis=1)).ravel())
    norms[norms == 0] = 1.0
    m = sparse.csr_matrix(m.multiply(1.0 / norms[:, None]))
    return np.asarray((m @ m.T).todense())


# ------------------------------------------------- pair enumeration


def condition_pairs(
    df: pd.DataFrame,
    *,
    primary_intent: str,
    contrast_intent: str | None = None,
    prompt_col: str = "item_id",
    wave_col: str = "wave",
    intent_col: str = "intent",
) -> pd.DataFrame:
    """Enumerate response pairs for the three pre-registered conditions.

    - ``within_prompt``: same prompt (primary intent), different waves.
    - ``between_prompt``: different prompts, same intent (primary), same wave
      (same-wave keeps day effects out of the phrasing contrast).
    - ``cross_intent``: primary vs contrast intent, same wave.

    Returns a frame with columns ``i, j`` (positional indices into ``df``),
    ``condition``, ``cluster_i, cluster_j`` (prompt ids). ``df`` must have a
    unique RangeIndex (use ``.reset_index(drop=True)`` first).
    """
    idx = np.arange(len(df))
    prompts = df[prompt_col].to_numpy()
    waves = df[wave_col].to_numpy()
    intents = df[intent_col].to_numpy()

    out: list[tuple[int, int, str]] = []
    for i, j in itertools.combinations(idx, 2):
        same_prompt = prompts[i] == prompts[j] and intents[i] == intents[j]
        same_wave = waves[i] == waves[j]
        if intents[i] == primary_intent and intents[j] == primary_intent:
            if same_prompt and not same_wave:
                out.append((i, j, "within_prompt"))
            elif not same_prompt and same_wave:
                out.append((i, j, "between_prompt"))
        elif (
            contrast_intent is not None
            and same_wave
            and {intents[i], intents[j]} == {primary_intent, contrast_intent}
        ):
            out.append((i, j, "cross_intent"))

    pairs = pd.DataFrame(out, columns=["i", "j", "condition"])
    pairs["cluster_i"] = prompts[pairs["i"]]
    pairs["cluster_j"] = prompts[pairs["j"]]
    return pairs


def pair_values(
    pairs: pd.DataFrame, values: list, metric: Callable
) -> pd.Series:
    """Apply a pairwise metric over enumerated pairs (values indexed positionally)."""
    return pd.Series(
        [metric(values[i], values[j]) for i, j in zip(pairs["i"], pairs["j"])],
        index=pairs.index,
        dtype=float,
    )


# ------------------------------------------------- cluster bootstrap


@dataclass
class BootResult:
    estimate: float
    lo: float
    hi: float
    n_clusters: int
    n_boot: int
    alpha: float
    sesoi: float | None = None
    verdict: Verdict | None = None
    n_pairs: int = 0
    n_nan: int = 0

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["verdict"] = self.verdict.value if self.verdict else None
        return d


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    total = weights.sum()
    return float((values * weights).sum() / total) if total > 0 else float("nan")


def cluster_boot(
    pairs: pd.DataFrame,
    *,
    value_col: str = "value",
    contrast: tuple[str, str | None],
    condition_col: str = "condition",
    sesoi: float | None = None,
    alpha: float = 0.10,
    n_boot: int = 2000,
    seed: int = 20260716,
) -> BootResult:
    """Prompt-level cluster-bootstrap CI for a condition mean or difference.

    ``contrast=("within_prompt", "between_prompt")`` estimates
    mean(within) - mean(between); ``contrast=("between_prompt", None)``
    estimates the level of one condition. With ``sesoi`` set, the verdict is
    the four-way TOST mapping on the absolute scale.
    """
    cond_a, cond_b = contrast
    work = pairs[[value_col, condition_col, "cluster_i", "cluster_j"]].copy()
    keep = work[condition_col].isin([c for c in contrast if c is not None])
    work = work[keep]
    n_nan = int(work[value_col].isna().sum())
    work = work.dropna(subset=[value_col]).reset_index(drop=True)
    if work.empty:
        raise ValueError("no usable pairs for the requested contrast")

    all_clusters = pd.concat([work["cluster_i"], work["cluster_j"]])
    codes, clusters = pd.factorize(all_clusters)
    n_clusters = len(clusters)
    ci_codes = codes[: len(work)]
    cj_codes = codes[len(work) :]
    same_cluster = ci_codes == cj_codes

    values = work[value_col].to_numpy()
    is_a = (work[condition_col] == cond_a).to_numpy()

    def stat(counts: np.ndarray) -> float:
        # Dyadic bootstrap weights: c_i * c_j between clusters, c_i within.
        w = np.where(same_cluster, counts[ci_codes], counts[ci_codes] * counts[cj_codes])
        a = _weighted_mean(values[is_a], w[is_a])
        if cond_b is None:
            return a
        b = _weighted_mean(values[~is_a], w[~is_a])
        return a - b

    observed = stat(np.ones(n_clusters))

    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for k in range(n_boot):
        draw = rng.integers(0, n_clusters, size=n_clusters)
        boots[k] = stat(np.bincount(draw, minlength=n_clusters).astype(float))
    boots = boots[~np.isnan(boots)]

    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])

    verdict = None
    if sesoi is not None:
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

    return BootResult(
        estimate=float(observed),
        lo=float(lo),
        hi=float(hi),
        n_clusters=n_clusters,
        n_boot=len(boots),
        alpha=alpha,
        sesoi=sesoi,
        verdict=verdict,
        n_pairs=len(work),
        n_nan=n_nan,
    )


def permutation_pvalue(
    observed: float,
    resample_stat: Callable[[np.random.Generator], float],
    *,
    n_perm: int = 5000,
    seed: int = 20260716,
) -> float:
    """One-sided permutation p-value: P(perm stat >= observed), add-one smoothed."""
    rng = np.random.default_rng(seed)
    hits = sum(resample_stat(rng) >= observed for _ in range(n_perm))
    return (1 + hits) / (n_perm + 1)
