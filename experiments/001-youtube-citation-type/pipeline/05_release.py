#!/usr/bin/env python3
"""Step 5 — anonymized dataset through the release gate -> data/public/.

The allow-list below IS the pre-registered "Publishable?" column of spec §3.
The gate (aeo_research.release_dataset) hard-fails on anything else.
Complete templates/release-checklist.md before publishing the output.
"""

from __future__ import annotations

import pandas as pd
from aeo_research import ColumnSpec, Datasheet, pseudonymize, release_dataset
from common import PUBLIC, load_videos

COLUMNS = [
    ColumnSpec("video_id", "YouTube video id (public)", public_fact=True),
    ColumnSpec("exec_pseudonym", "Pseudonymized response grouping key (exec_0001, ...)"),
    ColumnSpec("platform", "AI platform (openai, gemini, claude, perplexity, google_ai_overview)"),
    ColumnSpec("cited", "1 = cited inline in the answer; 0 = evaluated but not cited"),
    ColumnSpec("moment_cited", "1 = the citation deep-links a moment (t= timestamp)"),
    ColumnSpec("similarity", "Cosine similarity, prompt embedding x video title+description embedding (rounded)"),
    ColumnSpec("audience_size", "Channel subscribers at enrichment time (YouTube Data API)"),
    ColumnSpec("video_view_count", "Video views at enrichment time"),
    ColumnSpec("reactions_count", "Video likes at enrichment time"),
    ColumnSpec("comments_count", "Video comments at enrichment time"),
    ColumnSpec("duration_seconds", "Video duration in seconds"),
    ColumnSpec("video_category", "YouTube category name", public_fact=True),
    ColumnSpec("video_has_captions", "Whether the video has captions"),
    ColumnSpec("chapter_count", "Timestamp-marker lines in the video description"),
    ColumnSpec("has_chapters", "Description has YouTube-style chapters (>=3 markers incl. 0:00)"),
    ColumnSpec("desc_link_count", "Links in the video description"),
    ColumnSpec("desc_word_count", "Word count of the video title+description"),
    ColumnSpec("published_month", "Video publication month (YYYY-MM)"),
    ColumnSpec("n_sources_evaluated", "Sources the assistant evaluated for this response"),
    ColumnSpec("fetch_ok", "1 = video page content was successfully fetched"),
    ColumnSpec("timestamp_seconds", "The t= timestamp in seconds, when present"),
]


def main() -> None:
    df = load_videos()
    df = df.sort_values(["execution_id", "video_id"]).reset_index(drop=True)
    df["exec_pseudonym"] = pseudonymize(df["execution_id"], "exec")
    df["published_month"] = pd.to_datetime(
        df["published_at"], errors="coerce", utc=True, format="mixed"
    ).dt.strftime("%Y-%m")
    df["similarity"] = df["similarity"].round(3)

    paths = release_dataset(
        df,
        COLUMNS,
        PUBLIC,
        Datasheet(
            title="YouTube moment citations across AI answer surfaces (derived features)",
            dataset_slug="youtube-citation-type",
            study="001-youtube-citation-type",
            notes=[
                "One row per (response, video) pair; responses are pseudonymized.",
                "All platforms included; the study's primary model uses the "
                "google_ai_overview rows with cited = 1.",
                "SEARCH_RESULT (SERP-appended) rows are excluded from units.",
                "Metrics are point-in-time snapshots from the YouTube Data API at enrichment.",
            ],
        ),
    )
    print(f"  {paths['csv']}")
    print(f"  {paths['datasheet']}")
    print("  Complete templates/release-checklist.md before publishing.")


if __name__ == "__main__":
    main()
