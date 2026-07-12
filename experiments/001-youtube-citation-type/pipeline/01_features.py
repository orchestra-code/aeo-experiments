#!/usr/bin/env python3
"""Step 1 — parse, derive, and collapse to the (execution, video) unit.

Reads data/raw/extract.csv (see sql/extract.sql) and writes:
  data/interim/citations.csv  row-level, all platforms incl. SEARCH_RESULT (stretch)
  data/interim/videos.csv     (execution_id, video_id) unit rows (primary study)

--synthetic generates the same shapes from aeo_research.synthesize for an
end-to-end dry run without touching production data.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from aeo_research import parse_timestamp, parse_video_id, synthesize
from common import CITATIONS_CSV, INTERIM, RAW


def parse_chapter_times(s: str | float | None) -> list[int]:
    """'0:00|2:18|1:02:33' (from extract.sql string_agg) -> seconds."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return []
    out = []
    for token in str(s).split("|"):
        parts = token.strip().split(":")
        if not all(p.isdigit() for p in parts):
            continue
        if len(parts) == 2:
            out.append(int(parts[0]) * 60 + int(parts[1]))
        elif len(parts) == 3:
            out.append(int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]))
    return out


def from_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW)
    df["video_id"] = df["citation_url"].map(parse_video_id)
    fallback = df["video_id"].isna()
    df.loc[fallback, "video_id"] = df.loc[fallback, "normalized_url"].map(parse_video_id)
    df["timestamp_seconds"] = df["citation_url"].map(parse_timestamp)

    chapters = df["chapter_times"].map(parse_chapter_times)
    df["chapter_count"] = chapters.map(len)
    df["has_chapters"] = chapters.map(lambda c: len(c) >= 3 and 0 in c)
    df["fetch_ok"] = (df["fetch_status"] == "fetched").astype(int)

    dropped = int(df["video_id"].isna().sum())
    if dropped:
        print(f"  ! {dropped} rows with unparseable video ids dropped")
    return df[df["video_id"].notna()].copy()


def from_synthetic() -> pd.DataFrame:
    df = synthesize().rename(columns={"response_date": "response_at"})
    df["citation_url"] = "https://www.youtube.com/watch?v=" + df["video_id"]
    df["normalized_url"] = "https://youtube.com/watch?v=" + df["video_id"]
    df["fetch_ok"] = (df["fetch_status"] == "fetched").astype(int)
    df["chapter_times"] = ""
    df["model"] = "synthetic"
    df["video_definition"] = "hd"
    df["video_language"] = "en"
    df["made_for_kids"] = "false"
    df["has_channel_publisher"] = True
    df["citation_id"] = df.index.map(lambda i: f"synthetic{i:012d}")
    return df


def collapse(df: pd.DataFrame) -> pd.DataFrame:
    """(execution_id, video_id) units; t=-variant CitedPages collapse here.

    Pre-registered rule (spec §3): cited = any variant CITED_INLINE; metadata
    from the variant with similarity (i.e. an embedding), else with views.
    SEARCH_RESULT rows are excluded from units entirely.
    """
    d = df[df["citation_type"].isin(["CITED_INLINE", "EVALUATED_SOURCE"])].copy()
    d["cited"] = (d["citation_type"] == "CITED_INLINE").astype(int)

    d = d.sort_values(
        ["execution_id", "video_id", "similarity", "video_view_count"],
        na_position="last",
    )
    first = d.groupby(["execution_id", "video_id"], as_index=False).first()
    outcome = d.groupby(["execution_id", "video_id"], as_index=False)["cited"].max()
    units = first.drop(columns=["cited"]).merge(outcome, on=["execution_id", "video_id"])
    units["has_timestamp"] = units["timestamp_seconds"].notna().astype(int)
    return units


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="dry-run on generated data")
    args = ap.parse_args()

    df = from_synthetic() if args.synthetic else from_raw()
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_csv(CITATIONS_CSV, index=False)

    units = collapse(df)
    units.to_csv(INTERIM / "videos.csv", index=False)

    print(f"  citations.csv : {len(df):,} rows (all types)")
    print(f"  videos.csv    : {len(units):,} (execution, video) units")


if __name__ == "__main__":
    main()
