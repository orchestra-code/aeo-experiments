-- Experiment 001 extraction (run AFTER the spec is frozen; commit before running).
-- Output -> data/raw/extract.csv (gitignored). Read-only.
--
-- Design notes:
-- - Description text never leaves the database: chapter times, link counts,
--   and word counts are derived in-query (contentMarkdown for YouTube pages
--   is synthesized title + description + stats line).
-- - SEARCH_RESULT rows are INCLUDED, flagged by citation_type: they are the
--   SERP "key-moments" comparison class for the timestamp stretch goal.
--   The primary model filters to CITED_INLINE/EVALUATED_SOURCE in Python.
-- - similarity = cosine(prompt embedding, page embedding); NULL when the
--   page was never fetched (Audit A) or the prompt embedding is missing.
-- - Channel publisher (audienceSize) is attached to the CITATION by the
--   enrichment job (dc."publisherId"); cp."publisherId" is the fallback.
--
-- psql usage:
--   \copy (<this query>) TO 'experiments/001-youtube-citation-type/data/raw/extract.csv' CSV HEADER

SELECT
  dc.id                                   AS citation_id,
  dc."executionId"                        AS execution_id,
  dc.url                                  AS citation_url,
  cp."normalizedUrl"                      AS normalized_url,
  dc."citationType"                       AS citation_type,
  dqe.platform                            AS platform,
  dqe.model                               AS model,
  dqe."createdAt"                         AS response_at,
  dqe."totalCitations"                    AS n_sources_evaluated,
  COUNT(*) OVER (PARTITION BY dc."executionId")
                                          AS n_youtube_in_execution,

  -- engagement snapshot on the citation (YouTube Data API)
  dc."reactionsCount"                     AS reactions_count,
  dc."commentsCount"                      AS comments_count,

  -- video attributes
  cp."durationSeconds"                    AS duration_seconds,
  cp."videoViewCount"                     AS video_view_count,
  cp."videoCategory"                      AS video_category,
  cp."videoHasCaptions"                   AS video_has_captions,
  cp."publishedAt"                        AS published_at,
  cp."fetchStatus"                        AS fetch_status,
  (cp."videoMetadata" ->> 'definition')            AS video_definition,
  (cp."videoMetadata" ->> 'defaultAudioLanguage')  AS video_language,
  (cp."videoMetadata" ->> 'madeForKids')           AS made_for_kids,

  -- channel publisher (subscribers); prefer the citation-level reattribution
  COALESCE(pub_dc."audienceSize", pub_cp."audienceSize") AS audience_size,
  (COALESCE(pub_dc.domain, pub_cp.domain) LIKE 'youtube.com/@%') AS has_channel_publisher,

  -- description-derived scalars (text itself stays in the DB)
  cp."wordCount"                          AS desc_word_count,
  regexp_count(cp."contentMarkdown", 'https?://')   AS desc_link_count,
  (
    SELECT string_agg(m[1], '|')
    FROM regexp_matches(cp."contentMarkdown", '(?:^|\n)\s*[-*•\[]*\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\b', 'g') m
  )                                       AS chapter_times,

  -- semantic-similarity control (H4 canary; collider correction)
  1 - (pdq.embedding <=> cp.embedding)    AS similarity

FROM "DiscoveryCitation" dc
JOIN "DiscoveryQueryExecution" dqe ON dqe.id = dc."executionId"
LEFT JOIN "ReportDiscoveryExecution" rde ON rde.id = dqe."reportExecutionId"
LEFT JOIN prompt_runs pr ON pr.id = dqe."promptRunId"
LEFT JOIN "PropertyDiscoveryQuery" pdq
       ON pdq.id = COALESCE(rde."propertyQueryId", pr."propertyQueryId")
JOIN "CitedPage" cp ON cp.id = dc."citedPageId"
LEFT JOIN "Publisher" pub_dc ON pub_dc.id = dc."publisherId"
LEFT JOIN "Publisher" pub_cp ON pub_cp.id = cp."publisherId"
WHERE cp.domain IN ('youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be')
  AND (cp."normalizedUrl" ~ '^https://(m\.|music\.)?youtube\.com/(watch|shorts/|embed/|live/|v/)'
       OR cp."normalizedUrl" LIKE 'https://youtu.be/%')
  AND dc."citationType" IS NOT NULL;
