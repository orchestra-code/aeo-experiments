-- Experiment 007 domain-level metric table (READ-ONLY).
-- Output -> data/raw/domains.csv (gitignored).
--
-- One row per distinct domain in the study universe: every site:-scoped
-- domain plus every cited domain on executions that produced grounding rows.
-- Carries the public-authority metrics for the pre-freeze instrument
-- selection (harmonic centrality, PageRank rank, ETV percentile) and the
-- Publisher-coverage flags Audit D needs.
--
-- psql usage:
--   \copy (<this query>) TO 'experiments/007-site-consultations-observational/data/raw/domains.csv' CSV HEADER

SELECT
  d.domain                                AS domain,
  ccr.rank                                AS hc_rank,
  ccr.harmonic_centrality                 AS harmonic_centrality,
  ccr.page_rank                           AS page_rank,
  ccr.page_rank_rank                      AS page_rank_rank,
  pub."etvPercentile"                     AS etv_percentile,
  pub."organicEtv"                        AS organic_etv,
  pub."audienceSize"                      AS audience_size,
  (pub.id IS NOT NULL)                    AS has_publisher,
  (pub."organicMetricsFetchedAt" IS NOT NULL) AS organic_fetched
FROM (
  SELECT DISTINCT gs."siteScopeDomain" AS domain
  FROM grounding_searches gs
  WHERE gs."siteScopeDomain" IS NOT NULL
  UNION
  SELECT DISTINCT LOWER(REGEXP_REPLACE(cp.domain, '^www\.', ''))
  FROM "DiscoveryCitation" dc
  JOIN "CitedPage" cp ON cp.id = dc."citedPageId"
  WHERE EXISTS (
    SELECT 1 FROM grounding_search_executions gse
    WHERE gse."discoveryExecutionId" = dc."executionId"
  )
) d
LEFT JOIN common_crawl_domain_ranks ccr ON ccr.domain = d.domain
LEFT JOIN "Publisher" pub               ON pub.domain = d.domain;
