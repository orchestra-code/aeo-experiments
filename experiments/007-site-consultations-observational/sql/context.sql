-- Experiment 007 classification context (READ-ONLY).
-- Output -> data/raw/context.csv (gitignored, NEVER published — this is
-- per-customer brand/competitor identity, used only as matcher.py input).
--
-- One row per (property, competitor); properties without competitors still
-- appear once with NULL competitor columns so their own-brand terms exist.
-- Python groups by property_id and feeds pipeline/matcher.py the same shape
-- production hands buildCompetitorNamedQueryMatcher.
--
-- psql usage:
--   \copy (<this query>) TO 'experiments/007-site-consultations-observational/data/raw/context.csv' CSV HEADER

SELECT
  p.id                    AS property_id,
  p."companyName"         AS company_name,
  p.aliases               AS property_aliases,
  p.domain                AS property_domain,
  p."seedUrl"             AS property_seed_url,
  p."additionalDomains"   AS additional_domains,
  c.id                    AS competitor_id,
  c.name                  AS competitor_name,
  c.aliases               AS competitor_aliases,
  c.url                   AS competitor_url
FROM property p
LEFT JOIN "Competitor" c
       ON c."propertyId" = p.id AND c.active
WHERE EXISTS (
  SELECT 1 FROM grounding_searches gs WHERE gs."propertyId" = p.id
);
