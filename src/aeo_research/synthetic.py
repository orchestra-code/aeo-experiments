"""Synthetic data with the real dataset's causal structure.

Lets the full pipeline (features → audit → model → figures → release) be
proven end-to-end before any production data is extracted, and verifies the
statistical machinery has teeth: with ``true_effect=0`` the TOST must return
NULL; with a large ``true_effect`` it must return REAL.

The generator reproduces the collider structure of the real data: retrieval
is caused by BOTH semantic similarity and channel size, and only retrieved
videos are observed — so similarity and size are spuriously negatively
correlated in-sample, and a model without the similarity control produces a
spurious negative size coefficient. That trap is the reason the similarity
control is mandatory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Platforms that can produce both CITED_INLINE and EVALUATED_SOURCE.
PRIMARY_PLATFORMS = ["openai", "gemini", "claude"]

CATEGORIES = ["Education", "Science & Technology", "Howto & Style", "People & Blogs", "Other"]


def synthesize(
    n: int = 5500,
    cited_rate: float = 0.7,
    true_effect: float = 0.0,
    seed: int = 42,
) -> pd.DataFrame:
    """One row per (execution, video), matching experiment-001 extract columns."""
    rng = np.random.default_rng(seed)
    pool = n * 6  # oversample, then condition on retrieval → collider

    sim = rng.normal(0, 1, pool)
    size = rng.normal(0, 1, pool)  # latent channel size; independent of sim in population

    retrieved = rng.random(pool) < 1 / (1 + np.exp(-(-1.0 + 1.2 * sim + 1.0 * size)))
    idx = np.flatnonzero(retrieved)[:n]
    if len(idx) < n:
        raise RuntimeError("retrieval pool too small; raise the oversample factor")
    sim, size = sim[idx], size[idx]

    intercept = np.log(cited_rate / (1 - cited_rate))
    eta = intercept + 1.4 * sim + true_effect * size
    cited = (rng.random(n) < 1 / (1 + np.exp(-eta))).astype(int)

    subs = np.clip(10 ** (rng.normal(4.2, 1.1, n) + 0.35 * size), 10, 3e8).round()
    views = np.clip(subs * rng.lognormal(-0.6, 1.3, n), 10, 5e9).round()
    duration = rng.lognormal(6.2, 0.9, n).round()

    video_ids = np.array([f"vid{i:08d}xyz"[:11] for i in range(int(n * 0.93))])
    chapter_count = rng.choice([0, 0, 0, 3, 5, 8], n)

    df = pd.DataFrame(
        {
            "citation_id": [f"c{'0' * 15}{i:09d}" for i in range(n)],
            "execution_id": [f"e{i:08d}" for i in range(n)],  # singletons, as in real data
            "video_id": rng.choice(video_ids, n),
            "platform": rng.choice(PRIMARY_PLATFORMS, n, p=[0.45, 0.35, 0.2]),
            "citation_type": np.where(cited == 1, "CITED_INLINE", "EVALUATED_SOURCE"),
            "cited": cited,
            "similarity": sim,
            "audience_size": subs,
            "video_view_count": views,
            "duration_seconds": duration,
            "video_category": rng.choice(CATEGORIES, n, p=[0.3, 0.25, 0.2, 0.15, 0.1]),
            "video_has_captions": rng.random(n) < 0.65,
            "reactions_count": (views * rng.beta(2, 60, n)).round(),
            "comments_count": (views * rng.beta(1.5, 400, n)).round(),
            "published_at": pd.Timestamp("2026-07-01")
            - pd.to_timedelta(rng.integers(5, 2600, n), "D"),
            "response_date": pd.Timestamp("2026-07-01"),
            "n_sources_evaluated": rng.integers(3, 25, n),
            "n_youtube_in_execution": 1,
            "fetch_status": "fetched",
            "desc_word_count": rng.integers(5, 400, n),
            "desc_link_count": rng.integers(0, 12, n),
            "chapter_count": chapter_count,
            "has_chapters": chapter_count >= 3,
            "timestamp_seconds": np.where(rng.random(n) < 0.06, rng.integers(1, 900, n), np.nan),
        }
    )
    return df
