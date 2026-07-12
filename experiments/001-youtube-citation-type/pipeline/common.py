"""Shared paths and derivations for the experiment-001 pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw" / "extract.csv"
INTERIM = EXP / "data" / "interim"
PUBLIC = EXP / "data" / "public"
FIGURES = EXP / "figures"
RESULTS = EXP / "results"

CITATIONS_CSV = INTERIM / "citations.csv"  # row-level, all platforms + SEARCH_RESULT
VIDEOS_CSV = INTERIM / "videos.csv"        # (execution, video) unit, primary frame

#: Platforms where the inline-vs-evaluated contrast exists (spec §2 Audit B).
PRIMARY_PLATFORMS = ["openai", "gemini", "claude"]

SESOI_OR = 1.10
ALPHA = 0.10

#: Category levels below this share fold into "Other" (spec §3).
CATEGORY_MIN_SHARE = 0.02

Z_SCORE_COLS = [
    "log_subs",
    "log_views",
    "engagement_rate",
    "similarity",
    "log_duration",
    "log_age",
    "n_sources_evaluated",
    "placebo_dow",
]


def load_videos() -> pd.DataFrame:
    df = pd.read_csv(VIDEOS_CSV)
    return derive(df)


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Model variables per spec §3, z-scored on the PRIMARY frame."""
    df = df.copy()
    df["log_subs"] = np.log10(df["audience_size"].astype(float) + 1)
    df["log_views"] = np.log10(df["video_view_count"].astype(float) + 1)
    df["log_duration"] = np.log10(df["duration_seconds"].astype(float).fillna(0) + 1)

    reactions = df["reactions_count"].astype(float).fillna(0)
    comments = df["comments_count"].astype(float).fillna(0)
    views = df["video_view_count"].astype(float)
    df["engagement_rate"] = np.log1p(100 * (reactions + comments) / (views + 1))

    published = pd.to_datetime(df["published_at"], errors="coerce", utc=True, format="mixed")
    responded = pd.to_datetime(df["response_at"], errors="coerce", utc=True, format="mixed")
    age_days = (responded - published).dt.days.clip(lower=0)
    df["log_age"] = np.log10(age_days.astype(float) + 1)
    df["placebo_dow"] = published.dt.dayofweek.astype(float)

    # Category: rare levels -> Other, null -> Unknown (pre-registered).
    cat = df["video_category"].fillna("Unknown").astype(str)
    shares = cat.value_counts(normalize=True)
    rare = shares[shares < CATEGORY_MIN_SHARE].index
    df["category"] = cat.where(~cat.isin(rare), "Other")

    # psql \copy CSVs carry booleans as t/f; pandas round-trips give bools.
    df["has_captions"] = df["video_has_captions"].map(
        {True: 1.0, False: 0.0, "true": 1.0, "false": 0.0, "t": 1.0, "f": 0.0}
    )
    df["has_chapters_f"] = df["has_chapters"].astype(float)

    primary = df["platform"].isin(PRIMARY_PLATFORMS) & df["similarity"].notna()
    df["in_primary"] = primary
    for c in Z_SCORE_COLS:
        mu = df.loc[primary, c].mean()
        sd = df.loc[primary, c].std()
        df[c] = (df[c] - mu) / sd if sd and sd > 0 else 0.0
    return df


def primary_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["in_primary"]].copy()
