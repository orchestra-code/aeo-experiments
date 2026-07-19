# Prompt phrasing barely changes what ChatGPT recommends — and barely changes how it searches — study spec

**Status:** frozen (2026-07-16, before wave-1 submission)
**Frozen commit:** 2ee335a (spec + pipeline + toolkit, this repo)
**Experiment slug:** `002-prompt-consistency`

> Freeze rule: everything in §4 (hypotheses) and §5 (model + decision rule) is
> fixed before anyone looks at the joined data. Count-only data-quality checks
> (row counts, duplicate counts, blank counts on the survey file) are allowed
> pre-freeze; response data is not collected until after the freeze. The brand
> LEXICON (pipeline/brands.py) is extraction code, not a hypothesis: it is
> curated from wave-1 candidate mining, validated in Audit D, then held fixed;
> any later change is logged under "Deviations from the frozen spec".

---

## A. Pre-freeze findings (smoke test, 2 throwaway prompts, 2026-07-16)

Allowed pre-freeze: shape-only observations from non-survey prompts.
`result.model` = `gpt-5-5`; `fan_out_queries` can be a SINGLE query per
response (token-set overlap still defined, but grounding sets will be small);
`sources[]` held 2 citations per response vs 10 `search_results[]` (small
cited-domain sets → H2d pair values will be coarse-grained; the NaN policy
and cluster bootstrap handle this, and the INCONCLUSIVE row protects against
overclaiming); DataForSEO also returns `chat_gpt_brand_entity` product
annotations with inconsistent coverage (used as Audit D cross-check only).

## 0. One-paragraph summary

SparkToro's 2025 consistency study collected 142+ human-written prompts for
one intent ("headphones as a gift for a traveling family member") and found
the same top brands in 55–77% of AI answers despite near-zero prompt
similarity — but each prompt ran once, across 7 different LLMs, so phrasing
and platform were confounded. We rerun their de-identified survey prompts
(144 usable rows per intent in our export) on ONE platform (ChatGPT via
DataForSEO's LLM scraper, en-US), each prompt once per day for 7 days, and
extend the measurement below the answer into the retrieval layer: the
grounding (fan-out) searches the model runs and the sources it cites. We
expect phrasing to move brand recommendations by no more than the model's own
run-to-run noise (equivalence, not just "no significant difference"), and the
same for cited domains and grounding-query tokens — first-party evidence for
"prompts vary, outputs vary, but the AI search pipeline in between is stable."
The survey's second intent (coffee-shop brand-design agency, 144 prompts, one
wave) supplies the positive and placebo controls.

## 1. The claim we can and cannot make

**What this design measures:** for one commercial-recommendation intent, on
one platform (ChatGPT with web search forced, queried via DataForSEO's
scraper, location US, language en), over one week: how much does answer-level
brand overlap, cited-source overlap, and grounding-search overlap differ
between (a) repeated runs of the same prompt and (b) runs of differently
worded same-intent prompts?

**What this design does NOT measure:** other intents, other platforms, other
locales, logged-in/personalized ChatGPT behavior, the consumer product ("via
DataForSEO's scraper" is part of every claim), or anything about which
brands/sources *should* appear. It also cannot separate ChatGPT's internal
nondeterminism from DataForSEO's infrastructure variation — that composite IS
the run-to-run baseline we compare against.

**Defensible claim:** "Rewording a same-intent prompt changed ChatGPT's brand
recommendations by no more than X percentage points of Jaccard overlap
relative to the model's own run-to-run variability, and its cited domains and
grounding searches by no more than Y — measured across 144 human-written
phrasings × 7 daily runs."

**Indefensible claim:** "AI recommendations are deterministic", "prompt
wording never matters", "this holds for Gemini/Claude/AI Overviews", or any
claim about *which* brands deserve their share.

### Mechanistic prior

ChatGPT's answer pipeline for commercial queries is retrieval-mediated: the
model rewrites the user's prompt into a small set of search queries, retrieves
a SERP-shaped candidate pool, and composes an answer over it. Query rewriting
is trained to normalize intent, and the retrieval index is shared across
users; so diverse phrasings should funnel into similar grounding queries,
similar retrieved sources, and therefore similar brand sets — while the
surface text of the answer varies freely. If instead phrasing directly steered
retrieval, between-prompt overlap would drop far below within-prompt overlap.
We predicted convergence before collecting data; SparkToro's answer-level
result makes the answer layer likely, but the retrieval-layer prediction is
untested.

## 2. Data-quality audits — run BEFORE the model

- **Audit A — degenerate responses.** Failed/stale tasks, empty markdown,
  zero extracted brands (clarifying-question answers), empty
  `fan_out_queries` (despite `force_web_search: true`), zero sources — rates
  per intent × wave from the ledger + responses frame. Pre-registered policy:
  empty-vs-empty set pairs are NaN and excluded (rate reported); if >30% of
  headphone responses have empty fan-outs, grounding claims (H2g) are
  reported as INCONCLUSIVE regardless of CI.
- **Audit B — what the outcome labels mean.** Quoted from code:
  "brand recommended" = alias match of the frozen lexicon in cleaned answer
  markdown (URLs stripped, word-boundary, longest-alias-first) —
  `pipeline/brands.py::extract_brands`; "domain cited" = registered domain of
  a normalized `result.sources[]` URL (`search_results[]` excluded — SERP
  extras, not citations) — `pipeline/01_features.py`; "grounding tokens" =
  stopword-filtered token union over `result.fan_out_queries` —
  `aeo_research.overlap.token_set`.
- **Audit C — independence.** 144 prompts × 7 waves (headphones) + 144 × 1
  (coffee); 4 headphone prompts sit in duplicate-text groups (kept — they are
  independent respondents — with a dedup robustness refit). Every response
  participates in many pairs → ALL inference is prompt-level cluster
  bootstrap; no pair-level SEs anywhere.
- **Audit D — extraction validity and drift.** (i) 30-response random
  spot-check: manual brand list vs extractor; require precision ≥ 0.95 and
  recall ≥ 0.90, else refine lexicon and log the deviation. (ii) Sanity
  anchor: SparkToro found their top brands in 55–77% of responses; our
  top-brand shares should land in that neighborhood (anchor, not a
  hypothesis). (iii) `result.model` tabulated per wave — model drift during
  the week triggers robustness R6. (iv) Cross-check against DataForSEO's own
  `chat_gpt_brand_entity` annotations where present (smoke test showed
  coverage is inconsistent — null on some responses — so entities validate
  the lexicon, never replace it).

## 3. Data schema

One row per collected run (prompt × wave).

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| item_id / item_code | str | survey row | derived-only (pseudonymized) | h###/c### → `item_0001` |
| intent | str | survey column | yes | headphones / coffee |
| wave | int | ledger | yes | 1–7 |
| run_date | date | ledger collected_at | yes | |
| model | str | result.model | yes (public fact) | |
| prompt text | str | survey | **never** — SparkToro's data, not ours to share | stays in data/raw |
| answer markdown | str | result.markdown | **never** | interim only, feeds extraction + H3 |
| fan-out query text | str[] | result.fan_out_queries | **never** (token counts + derived overlap only) | |
| brands (ordered) | str[] | extraction | yes (public facts) | canonical names |
| cited URLs | str[] | result.sources[].url normalized | derived-only | domains publish; full URLs kept internal |
| cited domains | str[] | registered_domain(url) | yes (public facts) | |
| n_fanout, n_sources, n_brands, reply_word_count, had_web_search | int | derived | yes | |

### Derived variables

- URL normalization: lowercase host, strip `www.`, fragments, tracking params
  (`utm_*`, `gclid`, …), trailing slash. Registered domain via a small
  ccTLD-aware heuristic (`bbc.co.uk` → 3 labels).
- Grounding tokens: lowercase alphanumeric tokens minus a minimal stopword
  list (deliberately small — fan-out queries are keyword-like).
- Pair metrics: Jaccard on sets (empty∩empty → NaN, excluded); normalized
  truncated RBO (p=0.9) on ordered brand lists; TF-IDF cosine (uni+bigram) on
  answer text. No embeddings anywhere — deterministic and preregisterable.

## 4. Pre-registered hypotheses

Pair conditions: **within-prompt** (same headphone prompt, different waves),
**between-prompt** (different headphone prompts, same wave — same-wave keeps
day effects out of the phrasing contrast), **cross-intent** (headphones ×
coffee, wave 1, time-matched).

- **H1 (primary):** Δ_brand = mean(within-prompt brand Jaccard) −
  mean(between-prompt brand Jaccard) is practically equivalent to zero
  (|Δ| < SESOI). I.e., rephrasing costs no more brand overlap than the
  model's own run-to-run noise.
- **H2d (retrieval stability, domains):** same equivalence for cited-domain
  Jaccard.
- **H2g (retrieval stability, grounding):** same equivalence for
  grounding-token Jaccard.
- **H2u (descriptive):** cited-URL Jaccard reported with CI, no equivalence
  claim pre-registered (URL-level overlap is expected to be lower and noisier).
- **H3 (exploratory, no test):** TF-IDF cosine of answer text by condition —
  reported descriptively to show output wording varies while the layers above
  hold. No verdict by design.
- **H_pos (positive control — must pass or the study stops):** between-prompt
  within-intent cited-domain Jaccard exceeds cross-intent Jaccard by ≥ 0.10
  with the 90% cluster-bootstrap CI excluding 0 AND a prompt-label
  permutation p < 0.05. If same-intent prompts don't cite more-similar
  domains than different-intent prompts, collection or extraction is broken.
- **H_pla (placebo):** splitting between-prompt pairs by survey-row parity
  (odd/even item number — a label that cannot matter) must yield a
  NULL/NEGLIGIBLE difference. If parity "matters", the bootstrap is
  anti-conservative.

The headline "the pipeline in between is stable" additionally requires the
absolute between-prompt LEVELS (reported with bootstrap CIs) to be
substantially above the cross-intent level — equivalence of within/between
plus a high floor, not equivalence alone.

## 5. Model and decision rule

**Model:** nonparametric. Condition means of pairwise overlap; inference via
prompt-level cluster bootstrap (resample the 144 prompts with replacement;
dyadic pair weights c_i·c_j between clusters, c_i within; 2,000 draws; 90%
percentile CIs) — `aeo_research.overlap.cluster_boot`. Permutation test for
H_pos permutes intent labels over prompts (5,000 draws). Seed 20260716.

**SESOI: 0.10 absolute Jaccard.** At the expected ~5-brand answers, 0.10 ≈
one brand swapped in roughly half of pairs — the smallest gap that would
change a marketer's tracking decisions. Same band for domains and grounding
tokens.

**Decision rule (TOST logic at 90% CI, absolute scale):**

| Result | Conclusion |
|---|---|
| CI entirely inside ±0.10 | Practically equivalent — publishable null |
| CI excludes 0, extends beyond band | Real phrasing effect — report, revise thesis |
| CI excludes 0, inside band | Detectable but negligible — report honestly |
| CI wider than band, includes 0 | **Inconclusive — do NOT claim a null** |

**Power:** simulated in `tests/test_overlap.py` — the bootstrap-TOST returns
NULL on a true Δ=0 (60 clusters), REAL on Δ=0.30, INCONCLUSIVE when
underpowered. With 144 clusters × 21 within-pairs and ~70k between-pairs, the
design is comfortably powered for a 0.10 band unless between-cluster variance
is extreme (the INCONCLUSIVE row protects us there).

## 6. Known traps for this design

- **Scraper ≠ consumer product.** All claims are scoped "ChatGPT via
  DataForSEO's LLM scraper". `force_web_search: true` is required to observe
  the retrieval layer at all and is part of the measured condition.
- **Fixed US location vs prompts mentioning euros/European shops.** Not
  fixed; a claim boundary stated in the article.
- **Model drift across the week.** `result.model` recorded per response;
  drift triggers R6 subgroup refit and is itself a reportable finding.
- **Empty fan-outs.** See Audit A policy (>30% empty → H2g INCONCLUSIVE).
- **No-recommendation answers** (clarifying questions) are valid rows with
  empty brand sets; empty∩empty pairs are NaN, exclusion rate audited.
- **Duplicate survey prompts** (4 items): kept, dedup refit in R3.
- **Shared DataForSEO account with production:** we never call `tasks_ready`;
  we poll `task_get` by our own stored ids (production matches its own ids
  and ignores ours — verified in the production poller code).
- **Pair dependence:** handled exclusively by the cluster bootstrap; H_pla
  checks the bootstrap isn't anti-conservative.
- **Cost cap:** CLI refuses past 1,500 tasks (~$3.60) without --force.

## 7. Robustness checks

1. H_pos first — if it fails, stop (03_model exits 1).
2. H_pla placebo must be NULL/NEGLIGIBLE.
3. R1: rank-sensitive RBO instead of set Jaccard for brands.
4. R2: drop wave 1 (lexicon-mining wave) and refit H1/H2d.
5. R3: drop duplicate-text prompts, refit H1.
6. R4: H2g restricted to responses with non-empty fan-outs.
7. R5: across-wave between-prompt domain level vs same-wave level (day-drift
   check on the phrasing contrast).
8. R6: dominant-model subset refit if `result.model` drifts mid-study.

## 8. Deliverables and sequence

1. 00_prompts (survey → prompts.csv; counts asserted) — pre-freeze, count-only
2. Freeze spec (record commit hash above), then wave 1 (headphones + coffee)
   via `scripts/llm_scraper.py` (tag `aeo-exp002-w1`), collect same day
3. Curate brand lexicon from wave-1 mining; Audit D spot-check
4. Waves 2–7 daily; `status` check each day
5. 01_features → 02_audit (A–D in results/audit.txt) → 03_model (gate) →
   04_figures → robustness
6. 05_release (derived features only) + human release checklist
7. Article + companion blog post (EN/DE)

## 9. Notes for the write-up

- Lead figure: brand-share bars (SparkToro-comparable); the H1 carrier is the
  ECDF of pairwise brand Jaccard by condition.
- Framing: "your clients' 'is my prompt representative?' worry, measured" —
  prompts vary, outputs vary, the pipeline in between is stable. More answer-
  text variability (H3) STRENGTHENS the story: wording churns, the
  recommendation set doesn't.
- Credit SparkToro prominently (survey provenance, link to their study, with
  gratitude); reproducers who want the raw prompts are directed to Rand
  Fishkin (LinkedIn / SparkToro contact form). We publish derived features
  only.
- Sample size phrased as "N runs evaluated (in this study)".
- Publish the equivalence bound explicitly: "we could have detected a 0.10
  Jaccard shift and found none" (or report what we did find).

## Deviations from the frozen spec

- **2026-07-16 (wave 1):** survey row 54 (items h054/c054, the same
  respondent in both intents — a 2,341/2,259-char "mega-prompt") was rejected
  by DataForSEO's task_post with `40501 Invalid Field: 'keyword'` (keyword
  length limit; the longest accepted prompt was 1,982 chars). Excluded from
  the study rather than truncated — truncation would alter the respondent's
  phrasing. Effective n = 143 prompts per intent. Both arms lose the same
  row, so the cross-intent contrast stays symmetric.
- **2026-07-16 (wave 1):** the H_pos gate was run EARLY, on wave-1 data only
  (Δ = 0.313 [0.266, 0.364], perm p = 0.0002, PASS), to avoid spending six
  more collection days on a broken pipeline. Exactly the frozen test, frozen
  code, no other hypothesis was computed early (H1/H2 need within-prompt
  pairs, which require ≥2 waves). The gate will re-run in its pre-registered
  position after wave 7.
- **2026-07-16 (wave 1):** coffee-arm lexicon curated from wave-1 candidate
  mining per the §2/Audit D plan (69 agencies; dribbble/behance dropped —
  portfolio platforms, not agencies). Headphone seed lexicon unchanged by
  mining. Zero-brand rates after curation: headphones 4.9%, coffee 23.1%
  (clarifying-question answers — valid rows, empty sets per the NaN policy).
- **2026-07-18 (wave 3):** the automated wave driver skipped its 20:00 ET
  slot due to a UTC-vs-local calendar-day comparison bug (a wave submitted at
  20:00 ET carries the next day's UTC date, so the driver judged it "already
  submitted today"). Caught the same evening; wave 3 was submitted at 20:57
  ET after the fix (`run_wave.py`, commit noted in git history). Wave spacing
  is therefore 24h55m between waves 2→3 instead of 24h00m; run_date and
  `.model` are recorded per response and the R5 day-drift robustness check is
  unaffected. No data was lost and no wave ran twice.
