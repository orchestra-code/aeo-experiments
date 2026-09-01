# AI assistants consult high-authority domains directly instead of searching the open web — study spec

**Status:** frozen
**Frozen commit:** 065e37d
**Frozen date:** 2026-09-01 (seed 20260901)
**Experiment slug:** `007-site-consultations-observational`

> Freeze rule: everything in §4 (hypotheses) and §5 (model + decision rule) is
> fixed before anyone looks at the joined data. Count-only data-quality checks
> (class balance, null counts per column) are allowed pre-freeze; joint
> distributions are not. Predictors added after freeze are labelled
> **exploratory** in the write-up.
>
> **007-specific split:** this study has two layers with different rigor
> classes, declared here so neither borrows the other's authority:
> - **Descriptive layer (exploratory, may ship first):** timelines, platform
>   mixes, classification shares (§8 figures F1–F4, F6). No hypothesis tests,
>   no causal language, labelled exploratory in the article.
> - **Correlational layer (pre-registered):** the §5 model. The spec freezes
>   before the model runs on the joined extract. Running the descriptive layer
>   first inevitably shows us marginal distributions — that is disclosed in the
>   write-up, and it is why the correlational hypotheses are stated in terms of
>   a conditional contrast the marginals do not reveal.
>
> **DISCLOSED PRE-FREEZE DEVIATION (2026-09-01, study owner's direction):**
> before the freeze, `pipeline/03_prefreeze_explore.py` examined the joint
> consulted-vs-cited × authority-metric distributions to SELECT the frozen
> model's predictors (harmonic centrality and AIPVS tier certain; PageRank /
> ETV percentiles only if materially different from those two). The
> correlational layer is therefore published as **exploratory with a
> disclosed selection step**, not as clean confirmatory pre-registration.
> The selection run is committed; its seed (20260901) and sample rules are
> recorded in `pipeline/02b_aipvs.py`.

---

## 0. One-paragraph summary

Since roughly August 2026, ChatGPT's grounding searches sometimes carry an
explicit `site:domain.com` operator — the model electing to consult one
specific site rather than search the open web. A related, older behavior names
a brand in the query without the operator. Using the Spyglasses production
grounding-search corpus (read-only extract from the production replica), we
(1) describe the emergence, platform mix, and own/competitor/third-party
composition of directly-consulted domains, and (2) test whether, among domains
an assistant retrieved for category-level (non-brand) prompts, the ones it
consults *directly* sit measurably higher on public authority metrics
(Common Crawl harmonic centrality; DataForSEO organic visibility) than the
ones it merely retrieved. Mechanistic prior: direct consultation is a trust
shortcut, so it should concentrate on domains the model already treats as
authorities.

## 1. The claim we can and cannot make

**What this design measures:** among domains that appear in the retrieval/
citation pool for category-level prompts, the association between a domain's
public authority metrics and the probability the assistant issues a direct
`site:` consultation of it.

**What this design does NOT measure:**
- Anything causal — no one assigned authority at random.
- Domain choice for prompts we never ran, or platforms whose grounding we do
  not store: **no Perplexity and no Google AI Overview grounding exists in this
  corpus** (Perplexity runs through a path that captures no search queries;
  AIO exposes none). Claude grounding exists only for the small add-on-enabled
  subset. Claims are ChatGPT-first, Gemini-second, and say so.
- Whether the model *knows* brand→domain mappings (that is experiment 008).

**Defensible claim:** "Among N grounding searches evaluated in this study,
domains that AI assistants consulted directly ranked in the Xth percentile of
harmonic centrality, versus the Yth for domains retrieved but never consulted
directly — a gap of Z percentile points (95% CI …)."

**Indefensible claim:** "High authority causes AI to consult your site
directly", or any absolute count of searches/properties in the Spyglasses
database, or any prompt or fan-out text.

### Mechanistic prior

A `site:` consultation skips open-web ranking entirely: the model has decided,
before retrieval, whose answer it wants. That decision has to come from the
model's prior (training-data prominence, link centrality) rather than from the
current SERP. So consultation should correlate with *training-visible*
authority (harmonic centrality — a link-graph measure over Common Crawl, close
to what pretraining saw) at least as strongly as with *current commercial*
visibility (organic ETV). If the correlation ran the other way — consultation
tracking fresh SERP strength but not centrality — the trust-shortcut story
would be wrong and "AI consultation" would just be SERP ranking in disguise.

## 2. Data-quality audits — run BEFORE the model

- **Audit A — negative-class contamination.** The "retrieved but not consulted"
  class comes from cited/retrieved domains on the same prompts. Rows where the
  domain never had a chance to be consulted (execution produced no fan-outs at
  all; platform stores no grounding) must be excluded from the denominator.
  Report the excluded fraction.
- **Audit B — outcome label.** "Consulted directly" = the execution emitted a
  grounding search whose persisted `siteScopeDomain` (or text-parse fallback,
  quoted in `pipeline/01_features.py`) equals the domain, normalized
  (lowercase, no www, registrable-host match). Quote the parse code, don't
  paraphrase.
- **Audit C — independence.** The same domain recurs across hundreds of
  prompts and many properties (reddit.com…), and the same prompt recurs
  nightly. Cluster on BOTH prompt (propertyQueryId) and domain; report
  distinct counts of each. The effective sample is the rarer class
  (consulted domains), not row count.
- **Audit D — metric coverage bias.** Harmonic centrality exists only for the
  top ~10M domains; organic metrics only for enriched publishers. Missingness
  is *informative* (unranked ≈ low authority). Primary model runs on the
  ranked subset; a sensitivity refit imputes floor values for unranked
  domains. Report coverage per class — if consulted domains are ranked at 95%
  and retrieved-only at 60%, say so prominently, because that gap is itself
  the effect.
- **Audit E — capture artifacts.** Two known, verified discontinuities that
  are properties of the CAPTURE pipeline, not of model behavior:
  1. `prompt_runs.runType = 'weekly_grounding'` rows exist only to harvest
     Gemini fan-outs and inflate Gemini's share; flagged in the extract,
     excluded from platform-mix figures (kept, flagged, for the pooled model).
  2. **The nightly DataForSEO ChatGPT feed stopped carrying fan-outs on
     2026-08-25** (verified on the replica 2026-09-01: daily openai ingest
     fell ~95% while the report-path direct API and the gemini/claude
     controls were unaffected; independently confirmed by exp 008's pilot
     and in the DataForSEO playground). Timeline figures end at 2026-08-24
     or normalize per capture path. An ingest step-UP around 2026-08-08 must
     also be understood before the emergence timeline is published.
     See `results/prefreeze-counts.md`.

Do not fit anything until A–E are answered in this file.

## 3. Data schema

One row per (grounding-search execution × platform) in `extract.csv`; the
model layer pivots to one row per (prompt-execution × candidate domain).

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| execution_link_id | id | gse.id | never (pseudonymize to exec_NNNN) | |
| property_id | id | gse.propertyId | never (pseudonymize) | clustering only |
| platform | str | gse.platform | yes | openai/gemini/claude/unknown |
| executed_at | ts | gse.createdAt | yes (week bucket) | bucket on THIS, not gs.createdAt |
| query_text | str | gs.query | **never** | raw/ only; needed for named-brand classify + parse fallback |
| site_scope_domain | str | gs.siteScopeDomain ?? parse | derived-only | publish class + percentiles, not per-property domains |
| run_type | str | prompt_runs.runType | yes | weekly_grounding flag (Audit E) |
| query_type | str | PropertyDiscoveryQuery.queryType | yes | brand_identity / brand_comparison vs discovery-class |
| scope_class | enum | derived (own/competitor/third_party) | yes | via property+competitor context extract |
| named_class | enum | derived via brand_match.py | yes | own/competitor/both/none, non-scoped rows |
| hc_rank / harmonic_centrality | num | common_crawl_domain_ranks | yes (percentiles) | Audit D coverage |
| organic_etv / etv_percentile | num | "Publisher" | yes (percentiles) | Audit D coverage |
| cited_domains | str[] | DiscoveryCitation via execution | derived-only | the comparison pool |

**Property/competitor context extract** (second CSV, raw/ only, never
published): per-property companyName, aliases, domain, competitor
name/aliases/url — input to `src/aeo_research/brand_match.py` (the Python
port of spyglasses `buildCompetitorNamedQueryMatcher`; parity pinned by
`tests/test_matcher_parity.py`, which mirrors the TS suite at spyglasses
commit `3f6c332c` / PR #198).

### Derived variables

- `hc_percentile` from `rank` against `CommonCrawlMetadata.total_graph_nodes`
  (same formula as production `computeHarmonicCentralityPercentile`).
- `consulted` (outcome): domain received ≥1 direct `site:` consultation within
  the prompt-execution.
- `pool`: union of consulted + cited domains for the same prompt-execution.

## 4. Pre-registered hypotheses (FROZEN form — predictors selected in the
## disclosed pre-freeze step; percentile forms replaced by rank forms because
## Common Crawl ranks only the top ~10M of a 121M-node graph, compressing
## every ranked domain into a 92–100 percentile ceiling)

Unit: (discovery-class execution × third-party domain) pool rows —
"consulted" vs "cited but never consulted", own/competitor domains excluded
on both sides via the property context.

- **H1a (graph visibility):** consulted domains are more likely to be ranked
  in the Common Crawl graph at all. OR(ranked) SESOI: 1.5.
- **H1b (graph rank, ranked subset):** consulted domains rank higher.
  OR per 10× rank improvement (−1 unit of log10 rank) SESOI: 1.30.
- **H2 (AIPVS, scored subset):** consulted domains are more likely
  Premium/Strong tier. OR(Premium+Strong vs Moderate+Limited) SESOI: 1.5.
- **H3 (descriptive, no gate):** brand-comparison prompts consult directly
  at a higher per-answer rate than brand-identity and discovery prompts.
- **H_pos (positive control):** the government/bar-association cohort's
  consultation rate exceeds the pool base rate by ≥3×. If the extract can't
  reproduce what the production dashboard already shows, the join is broken —
  stop.
- **H_pla (placebo control):** parity of the domain's string length
  (even/odd) shows OR CI covering 1.0. If it doesn't, the clustering is
  wrong — stop.

Dropped in the disclosed selection step (recorded, not tested as headline
claims): PageRank rank (duplicates the Common Crawl signal), organic-ETV
percentile (an AIPVS input at 40% weight).

## 5. Model and decision rule (FROZEN)

**Models** (one focal predictor each — the predictors are correlated by
construction, and equivalence power dies under collinearity):
- **M1:** logit `consulted ~ ranked_in_cc`, all pool rows.
- **M2:** logit `consulted ~ z(log10 hc_rank)`, ranked rows only; OR
  reported per 10× rank improvement.
- **M3:** logit `consulted ~ premium_or_strong`, AIPVS-scored rows. The
  cited-only side is a seeded 5,000-domain random sample (seed 20260901) —
  outcome-side control subsampling leaves ORs consistent and biases only the
  intercept (case-control result); stated in the write-up.

**Uncertainty:** cluster-robust SEs by domain (the dominant repeat unit),
plus a 500-draw domain-cluster bootstrap as a check; report whichever CI is
wider. Seed 20260901.

**Decision rule (TOST at 90% CI):** standard house table — CI inside the
SESOI band = publishable null; excludes 1.0 beyond band = real; excludes 1.0
inside band = negligible; wider than band including 1.0 = **inconclusive, no
null claim**.

**Sanity gate before interpretation:** a synthetic shuffle run (consulted
labels permuted within execution, seed 20260901) must return null on every
model — the pipeline's own placebo.

## 6. Known traps for this design

- **Collider/selection:** the pool conditions on retrieval — every domain we
  compare was already surfaced by the model for this prompt. Framed
  explicitly as a conditional contrast; no marginal-authority claims.
- **Consultation is rare on discovery prompts** (~single-digit % of scoped
  rows are third-party on category prompts) — effective n is the consulted
  class. Report it; if under ~200 distinct consulted (prompt, domain) pairs,
  the correlational layer downgrades to descriptive.
- **Platform is confounded with capture path** (Gemini fan-outs come from the
  dedicated harvest; Claude only on add-on properties). Platform is a
  covariate/stratum, never a headline comparison of "which AI does this more"
  beyond the descriptive layer with the caveat stated.
- **Customer-data rules:** prompts and fan-out text never leave `data/raw/`
  (gitignored); published artifacts carry derived features and aggregate
  shares only; no absolute DB totals or property counts; "N searches
  evaluated in this study" phrasing.

## 7. Robustness checks

1. H_pos first — if it fails, stop.
2. H_pla must be null.
3. Nonlinearity: HC deciles (the relationship should be convex — elite
   domains take most consultations).
4. Collinearity report (HC vs ETV percentile corr + VIF).
5. Dedup refit: one row per domain (majority outcome), losing the
   per-prompt structure.
6. Per-platform refit (openai only; gemini if n allows).
7. Audit-D sensitivity: floor-imputed unranked domains.
8. Time split: pre/post the `site:` emergence inflection (named-brand
   consultations exist throughout; scoped ones only recently).

## 8. Deliverables and sequence

1. Audits A–E (`pipeline/02_audit.py` → `results/audit.txt`)
2. Descriptive layer figures (exploratory, may ship early):
   - **F1** weekly % of grounding searches that are site:-scoped, by platform
   - **F2** same timeline for brand-NAMED non-scoped searches (brand_match.py)
   - **F3** own / competitor / third_party mix of scoped searches
   - **F4** direct-consultation rate by queryType class (brand vs discovery)
   - **F6** third-party consulted-domain kinds (community/gov/review/retail)
3. Freeze spec (record commit), then extract joined model table
4. Model + robustness (`03_model.py`) — **F5** HC-percentile distribution,
   consulted vs retrieved-only (decile plot; lead figure)
5. Article + derived dataset through the release gate (`05_release.py`)
6. Companion blog post EN+DE in the spyglasses repo

## 9. Notes for the write-up

Editorial decisions from Jim (2026-09-01) — binding for the article:
- **No emergence visual, passing mention only.** The arrival of site: is
  already covered by other voices; it is not our story. F1 stays an internal
  figure.
- **Never mention the capture-path split** (API vs UI-scrape, the Aug-25
  DataForSEO loss) — client-sensitive; must not get ahead of corporate
  messaging. The article's methods note says which platform's data is shown
  and nothing about pipeline internals.
- **No platform-coverage discussion** (why Perplexity/AIO/Claude data is or
  isn't present). Scope claims positively to the data shown.
- **The differentiator is WHO gets consulted** (F3/F6 + refined taxonomy) —
  nobody else has classified the recipients. Lead there.
- **F4's operator takeaway:** publish factual (non-superlative)
  product-vs-competitor comparison pages — comparison questions are what
  send AI to a site directly.
- **Panel-mix skew is named honestly**: the client mix (law-heavy) shapes the
  third-party list; show the sector-balanced view alongside the raw one.

- Lead figure: refined consultation-taxonomy chart (F6 v2), then the
  authority contrast (F5).
- Framing: "AI keeps a short list of sites it trusts enough to ask directly —
  here's what gets a site on it" — constructive, matches the conditional
  design.
- Mandatory "What we can and cannot claim" section; publish the equivalence
  bound; distinguish inconclusive from null.
- SESOI rationale: an operator deciding where to invest content effort acts
  on "consulted vs not" only if the authority gap is large enough to target;
  a sub-10-percentile difference changes no roadmap.
- Sample sizes phrased "N grounding searches evaluated in this study"; never
  DB totals or property counts.
- Platform scope handled positively (per the §9 editorial decisions): the
  article says which platforms' data it shows, and does not discuss what is
  absent or why. The spec (this file) remains the honest internal record of
  coverage.

---

## Deviations from the frozen spec

- **D1 (2026-09-01) — shuffle placebo failed under the frozen pooled logit;
  estimator repaired to execution-conditioned logit.** The §5 within-answer
  label shuffle returned non-null on M1 (OR 0.907, CI90 0.838–0.982) and M2
  (1.072, 1.031–1.115) under the pooled estimator: with 363k rows, pooled
  logit picks up answer-level composition (answers differ in category mix,
  pool size, and consulted count), which the within-answer shuffle
  preserves. This is exactly the failure mode the gate exists to catch, and
  it means part of the pooled ORs (M1 2.141, M2 1.147, M3 1.339) is
  between-answer confounding rather than within-answer domain choice — the
  estimand §1 describes. Repair (`pipeline/05b_conditional_model.py`):
  conditional logit grouped by answer eliminates every answer intercept;
  same predictors, SESOIs, seed; shuffle placebo re-run under the
  conditional estimator must be null; uncertainty via 200-draw
  domain-cluster bootstrap. The pooled run is retained in
  `results/model_results.csv` for the record; the conditional estimates are
  the reported ones, and the article states the placebo catch explicitly.
