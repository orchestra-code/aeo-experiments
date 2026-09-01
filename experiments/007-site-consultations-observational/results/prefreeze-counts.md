# Pre-freeze count checks — 2026-09-01, prod read replica

INTERNAL. Absolute counts in this file are never published (data-policy: no
DB totals, no property counts). Publication uses shares/rates with "N
searches evaluated in this study" phrasing.

Run: `uv run python scripts/replica_psql.py -f experiments/007-site-consultations-observational/sql/counts.sql`
(replica confirmed: `pg_is_in_recovery() = t`, pooler-routed via harvested
replica tenant id — see `scripts/replica_psql.py`).

## C1 — executions/searches by platform

| platform | executions | distinct searches | scoped |
|---|---|---|---|
| openai | 49,459 | 39,971 | 6,737 |
| gemini | 39,378 | 38,131 | 8 |
| claude | 6,266 | 5,763 | 8 |
| unknown | 2,164 | 2,148 | 139 |

**`site:` scoping is essentially a ChatGPT behavior** (13.6% of openai
executions; single digits on gemini/claude). Gemini/Claude participate in the
NAMED-brand form instead — the descriptive layer must present the two forms
separately per platform.

## C2 — runType split (Audit E)

nightly 46,722 · report-path (NULL runType) 37,659 · weekly_grounding 12,886.

## C3 — prompt-link integrity

97,267 execution rows: 0 without a DiscoveryQueryExecution, 0 without a
resolvable PropertyDiscoveryQuery via either path. The COALESCE join is
sound.

## C4 — metric coverage for scoped domains (Audit D input)

2,270 distinct scoped domains → 1,496 with a Common Crawl rank (65.9%),
1,719 with a Publisher row (75.7%). Per-class (consulted vs retrieved-only)
coverage still to be computed in 02_audit.

## C5 — percentile denominator

`total_graph_nodes = 121,091,933`.

## Capture-artifact cliff (MUST be handled in the timeline figures)

The nightly DataForSEO ChatGPT feed stopped carrying fan-outs on
**2026-08-25** (daily openai grounding-execution ingest fell from 800–1,900
to 35–65; report-path direct-API ingest unaffected; gemini/claude controls
show no discontinuity). Verified same-day by exp 008's pilot (scraper returns
empty `fan_out_queries`/`search_results`/`model`) and by Jim in the DataForSEO
playground. Any weekly-trend figure must either end at 2026-08-24 or
normalize per capture path — otherwise the artifact masquerades as a behavior
change. There is also an ingest step-UP around 2026-08-08 (nightly ~540 →
~1,300–1,900/day) to understand before publishing the emergence timeline.
