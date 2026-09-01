-- Experiment 007 primary extraction (READ-ONLY; descriptive layer may run
-- pre-freeze, the joined model table must not be modeled until the spec is
-- frozen — see spec.md §freeze).
-- Output -> data/raw/extract.csv (gitignored).
--
-- Design notes:
-- - One row per grounding_search_execution (an observation of one fan-out on
--   one prompt run). Bucket time on gse."createdAt" — gs."createdAt" is only
--   the FIRST sighting of that query text for the property.
-- - query_text lands in gitignored raw/ only: needed for the named-brand
--   matcher and the site:-parse text fallback (pre-backfill rows). It is on
--   the never-publish list, not the never-extract list (docs/data-policy.md).
-- - site_scope_domain: persisted parse when present; Python re-parses the
--   text as fallback (mirror of production site-consultations.ts behavior).
-- - run_type = 'weekly_grounding' rows exist only to harvest Gemini fan-outs
--   (Audit E): kept, flagged, excluded from platform-mix figures.
-- - Metric joins are LEFT and coverage-biased by design (Audit D):
--   common_crawl_domain_ranks holds only the top ~10M domains; "Publisher"
--   only enriched ones. Publisher.domain can carry path suffixes (YouTube
--   channels) — the bare-host equality join under-matches those, which is
--   fine: they are not site:-consultable domains.
-- - Table-name trap: grounding tables are snake_case; DiscoveryQueryExecution,
--   ReportDiscoveryExecution, PropertyDiscoveryQuery, Publisher are unmapped
--   quoted PascalCase; property is @@map'd lowercase.
--
-- psql usage:
--   \copy (<this query>) TO 'experiments/007-site-consultations-observational/data/raw/extract.csv' CSV HEADER

SELECT
  gse.id                                  AS execution_link_id,
  gse."discoveryExecutionId"              AS discovery_execution_id,
  gse."propertyId"                        AS property_id,
  COALESCE(NULLIF(TRIM(gse.platform), ''), 'unknown') AS platform,
  gse."createdAt"                         AS executed_at,
  gse."orderInResponse"                   AS order_in_response,
  gs.id                                   AS grounding_search_id,
  gs.query                                AS query_text,
  gs."siteScopeDomain"                    AS site_scope_domain,
  pr."runType"                            AS run_type,
  pdq.id                                  AS property_query_id,
  pdq."queryType"                         AS query_type,

  -- authority metrics for the scoped domain (NULL when unscoped or unranked)
  ccr.rank                                AS scoped_hc_rank,
  ccr.harmonic_centrality                 AS scoped_harmonic_centrality,
  ccr.page_rank                           AS scoped_page_rank,
  pub."organicEtv"                        AS scoped_organic_etv,
  pub."etvPercentile"                     AS scoped_etv_percentile,
  pub."audienceSize"                      AS scoped_audience_size

FROM grounding_search_executions gse
JOIN grounding_searches gs   ON gs.id  = gse."groundingSearchId"
LEFT JOIN "DiscoveryQueryExecution" dqe ON dqe.id = gse."discoveryExecutionId"
LEFT JOIN prompt_runs pr                ON pr.id  = dqe."promptRunId"
LEFT JOIN "ReportDiscoveryExecution" rde ON rde.id = dqe."reportExecutionId"
LEFT JOIN "PropertyDiscoveryQuery" pdq
       ON pdq.id = COALESCE(rde."propertyQueryId", pr."propertyQueryId")
LEFT JOIN common_crawl_domain_ranks ccr ON ccr.domain = gs."siteScopeDomain"
LEFT JOIN "Publisher" pub               ON pub.domain = gs."siteScopeDomain";
