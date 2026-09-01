-- Experiment 007 citation pool (READ-ONLY) — the "retrieved but not
-- consulted" comparison class for the §5 model.
-- Output -> data/raw/citations.csv (gitignored).
--
-- One row per (discovery execution, cited domain), with the same authority
-- joins as extract.sql so both classes are measured identically. Restricted
-- to executions that produced at least one grounding-search row: an execution
-- with no fan-outs never had a chance to consult anything, so its citations
-- would contaminate the negative class (spec Audit A).
--
-- CitedPage.domain is used as the domain key; Python normalizes (lowercase,
-- strip www.) to match site_scope_domain before pooling.
--
-- psql usage:
--   \copy (<this query>) TO 'experiments/007-site-consultations-observational/data/raw/citations.csv' CSV HEADER

SELECT DISTINCT
  dc."executionId"                        AS discovery_execution_id,
  dqe."createdAt"                         AS response_at,
  cp.domain                               AS cited_domain,
  ccr.rank                                AS cited_hc_rank,
  ccr.harmonic_centrality                 AS cited_harmonic_centrality,
  pub."organicEtv"                        AS cited_organic_etv,
  pub."etvPercentile"                     AS cited_etv_percentile
FROM "DiscoveryCitation" dc
JOIN "DiscoveryQueryExecution" dqe ON dqe.id = dc."executionId"
JOIN "CitedPage" cp                ON cp.id  = dc."citedPageId"
LEFT JOIN common_crawl_domain_ranks ccr
       ON ccr.domain = LOWER(REGEXP_REPLACE(cp.domain, '^www\.', ''))
LEFT JOIN "Publisher" pub
       ON pub.domain = LOWER(REGEXP_REPLACE(cp.domain, '^www\.', ''))
WHERE EXISTS (
  SELECT 1 FROM grounding_search_executions gse
  WHERE gse."discoveryExecutionId" = dc."executionId"
);
