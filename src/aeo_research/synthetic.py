"""Synthetic data with the real dataset's causal structure.

Lets the full pipeline (features → audit → model → figures → release) be
proven end-to-end before any production data is extracted, and verifies the
statistical machinery has teeth: with ``true_effect=0`` the TOST on the
popularity predictors must return NULL; with a large ``true_effect`` it must
return REAL.

Shape matches experiment 001 (post-pivot): the modelling frame is Google AI
Overviews video citations, outcome = *moment citation* (a ``t=`` timestamp on
the cited URL), driven by video structure (chapters, captions, duration).
Popularity (subscribers/views) affects retrieval — inducing the usual
collider with similarity in the observed sample — but has no direct effect
on moment citation unless ``true_effect`` says so. Small non-AIO platform
samples (no timestamps, mixed inline/evaluated) exercise the descriptive
paths.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CATEGORIES = ["Education", "Science & Technology", "Howto & Style", "People & Blogs", "Other"]

#: Structure effects on the moment-citation log-odds (the mechanism the
#: pipeline must detect — H1/H2/H3 in the spec).
CHAPTER_BETA = 0.9
CAPTION_BETA = 0.5
DURATION_BETA = 0.7


def synthesize(
    n: int = 5400,
    moment_rate: float = 0.44,
    true_effect: float = 0.0,
    n_other_platforms: int = 600,
    seed: int = 42,
) -> pd.DataFrame:
    """One row per citation, matching the experiment-001 extract columns."""
    rng = np.random.default_rng(seed)
    pool = n * 6  # oversample, then condition on retrieval → collider

    sim = rng.normal(0, 1, pool)
    size = rng.normal(0, 1, pool)  # latent channel size; independent of sim in population

    retrieved = rng.random(pool) < 1 / (1 + np.exp(-(-1.0 + 1.2 * sim + 1.0 * size)))
    idx = np.flatnonzero(retrieved)[:n]
    if len(idx) < n:
        raise RuntimeError("retrieval pool too small; raise the oversample factor")
    sim, size = sim[idx], size[idx]

    subs = np.clip(10 ** (rng.normal(4.2, 1.1, n) + 0.35 * size), 10, 3e8).round()
    views = np.clip(subs * rng.lognormal(-0.6, 1.3, n), 10, 5e9).round()
    duration = np.clip(rng.lognormal(6.2, 0.9, n), 20, 4 * 3600).round()
    log_dur_z = (np.log10(duration) - np.log10(duration).mean()) / np.log10(duration).std()
    # true_effect applies to the OBSERVABLE predictor (standardized log subs),
    # so the TOST verification tests measure exactly the injected magnitude.
    log_subs_z = (np.log10(subs) - np.log10(subs).mean()) / np.log10(subs).std()

    chapter_count = rng.choice([0, 0, 0, 3, 5, 8], n)
    has_chapters = chapter_count >= 3
    has_captions = rng.random(n) < 0.65

    intercept = np.log(moment_rate / (1 - moment_rate)) - (
        CHAPTER_BETA * has_chapters.mean() + CAPTION_BETA * has_captions.mean()
    )
    eta = (
        intercept
        + CHAPTER_BETA * has_chapters
        + CAPTION_BETA * has_captions
        + DURATION_BETA * log_dur_z
        + true_effect * log_subs_z
    )
    moment = rng.random(n) < 1 / (1 + np.exp(-eta))
    ts = np.where(moment, (rng.random(n) * 0.9 * duration).astype(int) + 1, -1)

    aio = pd.DataFrame(
        {
            "execution_id": [f"e{i:08d}" for i in range(n)],
            "video_id": rng.choice([f"vid{i:08d}xyz"[:11] for i in range(int(n * 0.93))], n),
            "platform": "google_ai_overview",
            "citation_type": "CITED_INLINE",
            "similarity": sim,
            "audience_size": subs,
            "video_view_count": views,
            "duration_seconds": duration,
            "video_category": rng.choice(CATEGORIES, n, p=[0.3, 0.25, 0.2, 0.15, 0.1]),
            "video_has_captions": has_captions,
            "reactions_count": (views * rng.beta(2, 60, n)).round(),
            "comments_count": (views * rng.beta(1.5, 400, n)).round(),
            "published_at": pd.Timestamp("2026-07-01")
            - pd.to_timedelta(rng.integers(5, 2600, n), "D"),
            "response_at": pd.Timestamp("2026-07-01"),
            "n_sources_evaluated": rng.integers(3, 25, n),
            "n_youtube_in_execution": 1,
            "fetch_status": "fetched",
            "desc_word_count": rng.integers(5, 400, n),
            "desc_link_count": rng.integers(0, 12, n),
            "chapter_count": chapter_count,
            "has_chapters": has_chapters,
            "timestamp_seconds": np.where(ts >= 0, ts, np.nan),
        }
    )

    # Small non-AIO samples: no timestamps, mixed inline/evaluated (matches
    # the real per-platform scarcity) — exercises the descriptive paths.
    m = n_other_platforms
    rng2 = np.random.default_rng(seed + 1)
    other = aio.sample(m, replace=True, random_state=seed).reset_index(drop=True).copy()
    other["execution_id"] = [f"o{i:08d}" for i in range(m)]
    other["platform"] = rng2.choice(
        ["gemini", "perplexity", "openai", "claude"], m, p=[0.5, 0.4, 0.07, 0.03]
    )
    other["citation_type"] = np.where(
        (other["platform"].isin(["gemini", "openai"])) & (rng2.random(m) < 0.1),
        "EVALUATED_SOURCE",
        "CITED_INLINE",
    )
    other["timestamp_seconds"] = np.nan

    return pd.concat([aio, other], ignore_index=True)
