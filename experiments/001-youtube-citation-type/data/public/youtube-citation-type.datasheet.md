# YouTube moment citations across AI answer surfaces (derived features)

- **Study:** 001-youtube-citation-type
- **Rows:** 5,978 (citations evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-07-13

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `video_id` | YouTube video id (public) |
| `exec_pseudonym` | Pseudonymized response grouping key (exec_0001, ...) |
| `platform` | AI platform (openai, gemini, claude, perplexity, google_ai_overview) |
| `cited` | 1 = cited inline in the answer; 0 = evaluated but not cited |
| `moment_cited` | 1 = the citation deep-links a moment (t= timestamp) |
| `similarity` | Cosine similarity, prompt embedding x video title+description embedding (rounded) |
| `audience_size` | Channel subscribers at enrichment time (YouTube Data API) |
| `video_view_count` | Video views at enrichment time |
| `reactions_count` | Video likes at enrichment time |
| `comments_count` | Video comments at enrichment time |
| `duration_seconds` | Video duration in seconds |
| `video_category` | YouTube category name |
| `video_has_captions` | Whether the video has captions |
| `chapter_count` | Timestamp-marker lines in the video description |
| `has_chapters` | Description has YouTube-style chapters (>=3 markers incl. 0:00) |
| `desc_link_count` | Links in the video description |
| `desc_word_count` | Word count of the video title+description |
| `published_month` | Video publication month (YYYY-MM) |
| `n_sources_evaluated` | Sources the assistant evaluated for this response |
| `fetch_ok` | 1 = video page content was successfully fetched |
| `timestamp_seconds` | The t= timestamp in seconds, when present |

## Notes

- One row per (response, video) pair; responses are pseudonymized.
- All platforms included; the study's primary model uses the google_ai_overview rows with cited = 1.
- SEARCH_RESULT (SERP-appended) rows are excluded from units.
- Metrics are point-in-time snapshots from the YouTube Data API at enrichment.
