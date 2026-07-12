-- Pre-freeze data-quality counts (spec §9 step 1).
-- COUNT-ONLY by design: class balance and null rates, no joint distributions.
-- Run read-only. Each statement is independent.

-- YouTube-video citation rows by citationType and platform
SELECT dqe.platform, dc."citationType", COUNT(*) AS n
FROM "DiscoveryCitation" dc
JOIN "DiscoveryQueryExecution" dqe ON dqe.id = dc."executionId"
JOIN "CitedPage" cp ON cp.id = dc."citedPageId"
WHERE cp."normalizedUrl" ~ '^https://(m\.|music\.)?youtube\.com/(watch|shorts/|embed/|live/|v/)'
   OR cp."normalizedUrl" LIKE 'https://youtu.be/%'
GROUP BY 1, 2
ORDER BY 1, 2;

-- Null rates on the predictors (YouTube video pages only)
SELECT
  COUNT(*)                                                    AS pages,
  COUNT(*) FILTER (WHERE cp."fetchStatus" = 'fetched')        AS fetched,
  COUNT(*) FILTER (WHERE cp."embeddingUpdatedAt" IS NULL)     AS no_embedding,
  COUNT(*) FILTER (WHERE cp."videoViewCount" IS NULL)         AS null_views,
  COUNT(*) FILTER (WHERE cp."durationSeconds" IS NULL)        AS null_duration,
  COUNT(*) FILTER (WHERE cp."videoCategory" IS NULL)          AS null_category,
  COUNT(*) FILTER (WHERE cp."videoHasCaptions" IS NULL)       AS null_captions,
  COUNT(*) FILTER (WHERE cp."publishedAt" IS NULL)            AS null_published
FROM "CitedPage" cp
WHERE cp."normalizedUrl" ~ '^https://(m\.|music\.)?youtube\.com/(watch|shorts/|embed/|live/|v/)'
   OR cp."normalizedUrl" LIKE 'https://youtu.be/%';

-- Channel-publisher attribution + subscriber-count coverage on citations
SELECT
  COUNT(*)                                                         AS citation_rows,
  COUNT(*) FILTER (WHERE pub.id IS NOT NULL)                       AS has_publisher,
  COUNT(*) FILTER (WHERE pub.domain LIKE 'youtube.com/@%')         AS channel_publisher,
  COUNT(*) FILTER (WHERE pub."audienceSize" IS NOT NULL)           AS has_audience_size,
  COUNT(*) FILTER (WHERE dc."reactionsCount" IS NOT NULL)          AS has_reactions
FROM "DiscoveryCitation" dc
JOIN "CitedPage" cp ON cp.id = dc."citedPageId"
LEFT JOIN "Publisher" pub ON pub.id = dc."publisherId"
WHERE cp."normalizedUrl" ~ '^https://(m\.|music\.)?youtube\.com/(watch|shorts/|embed/|live/|v/)'
   OR cp."normalizedUrl" LIKE 'https://youtu.be/%';

-- Timestamp-bearing URLs by platform and type (stretch-goal feasibility)
SELECT dqe.platform, dc."citationType",
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE dc.url ~ '[?&#]t=\d') AS with_timestamp
FROM "DiscoveryCitation" dc
JOIN "DiscoveryQueryExecution" dqe ON dqe.id = dc."executionId"
JOIN "CitedPage" cp ON cp.id = dc."citedPageId"
WHERE cp."normalizedUrl" ~ '^https://(m\.|music\.)?youtube\.com/(watch|shorts/|embed/|live/|v/)'
   OR cp."normalizedUrl" LIKE 'https://youtu.be/%'
GROUP BY 1, 2
ORDER BY 1, 2;

-- Multi-YouTube executions (Audit D exposure), count-only
SELECT dqe.platform,
       COUNT(DISTINCT dc."executionId") AS executions_with_youtube,
       COUNT(DISTINCT dc."executionId") FILTER (WHERE per_exec.n > 1) AS executions_with_multiple
FROM "DiscoveryCitation" dc
JOIN "DiscoveryQueryExecution" dqe ON dqe.id = dc."executionId"
JOIN "CitedPage" cp ON cp.id = dc."citedPageId"
JOIN LATERAL (
  SELECT COUNT(*) AS n
  FROM "DiscoveryCitation" dc2
  JOIN "CitedPage" cp2 ON cp2.id = dc2."citedPageId"
  WHERE dc2."executionId" = dc."executionId"
    AND (cp2."normalizedUrl" ~ '^https://(m\.|music\.)?youtube\.com/(watch|shorts/|embed/|live/|v/)'
         OR cp2."normalizedUrl" LIKE 'https://youtu.be/%')
) per_exec ON TRUE
WHERE cp."normalizedUrl" ~ '^https://(m\.|music\.)?youtube\.com/(watch|shorts/|embed/|live/|v/)'
   OR cp."normalizedUrl" LIKE 'https://youtu.be/%'
GROUP BY 1
ORDER BY 1;
