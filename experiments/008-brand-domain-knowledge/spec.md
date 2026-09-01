# AI models KNOW brand domains rather than guessing them per run — study spec

**Status:** frozen
**Frozen commit:** 891a5ab
**Frozen date:** 2026-09-01 (seed 20260901; waves start 2026-09-02)
**Experiment slug:** `008-brand-domain-knowledge`

> Freeze rule: §4 (hypotheses) and §5 (decision rules) are fixed before wave 1.
> Pilot wave 0 (~50 tasks, tag `aeo-exp008-smoke`) runs BEFORE the freeze and
> may change: R (replicates), the platform set, prompt-template wording, and
> the primary-outcome definition. It may NOT change hypotheses after wave 1.
> The brand panel (`pipeline/brands.py`) and its brand→domain map are part of
> the frozen instrument.

---

## 0. One-paragraph summary

When an AI assistant consults a brand's site directly — a `site:domain.com`
grounding search, or retrieval concentrated on one domain after a brand-named
search — it has committed to a belief about which domain belongs to the brand.
Anecdotes say this belief is sometimes wrong. We test whether wrongness
behaves like a **stable stored association** (the same wrong domain, run after
run — a lookup that is miswired) or like a **per-run generative guess**
(morphologically plausible `brandname.com`-style errors that flip between
runs and "self-correct" the next day). 48 real brands in four tiers
(guessable / non-obvious domain / recently-migrated / obscure) × 2 prompt
templates, run against the direct OpenAI Responses API (the Gemini arm died
in the pilot, §8b) across 10 daily waves, with 3-per-day spaced replicates
on wave 1 to separate within-day stochasticity from day-over-day drift
(allocation C, §7). All claims are rates with CIs — a
quiet week is an upper bound, never proof of impossibility.

## 1. The claim we can and cannot make

**What this design measures:** *when the model emits a domain-bearing signal
for a brand it was asked about*, (a) how often that domain is the brand's
canonical one, by tier; (b) whether errors repeat (same wrong domain across
replicates and days) beyond an independence baseline; (c) what the errors ARE
(the old real domain vs a morphological guess vs another real entity's
domain vs a non-existent one).

**What this design does NOT measure:**
- Marginal "does the model know brand X's domain" — we observe the belief
  only when the model elects to surface it (consultation-conditional
  selection). Claims read "when the model consults …", never "the model
  believes …" unconditionally.
- Anything about Perplexity or Google AI Overviews (no grounding captured),
  or about model families beyond those run (likely ChatGPT-only if the
  Gemini pilot fails — one model family, stated plainly).
- Existence proofs. Zero wrong observations in a cell ⇒ a rule-of-three
  (3/n) upper bound on the rate, not "cannot happen".

**Defensible claim:** "Across N runs evaluated in this study, when ChatGPT
consulted a brand's site directly it used the canonical domain X% of the time
(95% CI …); errors repeated the same wrong domain at Y× the independence
baseline, consistent with a stored (mis)association rather than per-run
guessing." (Or the stochastic mirror image.)

**Indefensible claim:** "ChatGPT doesn't know brand domains", "AI will send
your traffic to the wrong site Z% of the time" (our prompts are not the
traffic mix), or any per-brand shaming lead ("ChatGPT thinks X lives at Y")
presented as more than an observed example.

### Mechanistic prior

Both mechanisms are plausible and they predict DIFFERENT error content:
- A **stored association** is trained on a snapshot, so its failures should
  concentrate where the world moved after training: tier C (migrated
  domains), with the error being specifically the OLD real domain, stable
  across replicates and days.
- A **generative guess** samples from name morphology, so its failures should
  concentrate where morphology misleads: tier B (non-obvious domains), with
  the error being `brandname.com`/`brandname.io`-style tokens (several of
  which are real sites owned by unrelated entities — bear.com, motion.com —
  making the guess look confirmed), flipping between replicates.
The design's whole point is that these two predictions separate cleanly in
the data; reality may of course be a mixture, and the mixture weights are
themselves the result.

## 2. Data-quality audits — run BEFORE the model

- **Audit A — emission conditioning.** What fraction of runs emit any
  domain-bearing signal at all, by tier × template × platform? The analysis
  set conditions on emission; report the funnel from all runs → emitting runs
  → scoped runs.
- **Audit B — outcome label.** `domain_correct` compares the normalized
  consulted domain to the frozen `true_domain`; hits on a frozen
  `old_domains` entry are labelled `stale`, NOT wrong-other — quote the
  scoring code. `error_kind ∈ {stale_old_domain, morphological_guess,
  other_real, nonexistent}`; `morphological_guess` = the frozen
  `expected_guess` token set per brand; `nonexistent` requires a resolution
  check at analysis time (recorded with its check date).
- **Audit C — independence.** Replicates within a day and waves within a
  brand are correlated by design; every rate clusters on brand (and
  brand×template where n allows). The effective sample for error-structure
  claims is the number of BRANDS with ≥2 wrong observations — report it
  before interpreting H2.
- **Audit D — panel validity at freeze.** Every `true_domain` resolves
  (HTTP 200-family on the canonical host) and is confirmed from the brand's
  own site; every tier-C `old_domains` entry is documented with the migration
  date and a source. Entity-ambiguity annotations (brands whose name
  collides with a bigger entity) are recorded per brand at freeze.
- **Audit E — model drift.** `.model` recorded per task; if the platform
  swaps models mid-study, report per-model strata — a swap is a documented
  natural experiment, never silently averaged over.

## 3. Data schema

One row per collected task in `data/interim/responses.csv`; raw fan-out
strings additionally preserved in `data/raw/fanouts.csv` (gitignored — 005's
pipeline tokenized them away; this study's object IS the raw string).

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| item_id | str | ledger | yes | encodes brand, template, replicate (`b07_tB_p1_r2`) |
| brand / tier / template | str | brands.py | yes | study-generated panel |
| wave / replicate_slot | int | ledger | yes | |
| platform / model | str | ledger + result.model | yes | Audit E |
| issued_site_query | bool | fan_out_queries parse | yes | primary emission flag |
| site_domain | str | parse | yes | study brands only — non-customer |
| domain_correct | enum correct/stale/wrong | scored vs frozen map | yes | Audit B |
| error_kind | enum | scored | yes | |
| consulted_domains / cited_domains | str[] | search_results / sources | derived-only | secondary outcome |
| fan_out_raw | str | fan_out_queries | **never** | data/raw only (house rule: fan-out text is never published, even study-generated) |
| answer markdown | str | result.markdown | never | raw only |

## 4. Pre-registered hypotheses (finalize wording at freeze; structure fixed)

- **H1 (emission, descriptive):** per-tier/template/platform rate of runs
  emitting a domain-bearing signal, with Wilson CIs. No gate; the pilot's
  point estimates are recorded next to the final ones.
- **H2 (primary — repeat structure):** among brands with ≥2 wrong
  observations, the probability two wrong observations of the same brand name
  the SAME wrong domain exceeds the independence baseline (permutation of the
  pooled per-brand wrong-domain distribution; expected agreement Σp²).
  Systemic verdict: observed − baseline ≥ **0.25**. Stochastic verdict:
  observed − baseline ≤ **0.05** with CI inside the band (TOST). Between:
  mixture/inconclusive, reported as such.
- **H3 (error content):** stale_old_domain share of errors is higher in tier
  C than tier B, AND morphological_guess share is higher in tier B than tier
  C (both, directionally, cluster-bootstrap CI excluding zero).
- **H4 (self-correction):** P(correct at t+1 | wrong at t) vs
  P(correct at t+1 | correct at t), day-over-day within brand×template.
  Stored-association predicts a large gap (wrong stays wrong); per-run
  guessing predicts transitions near-independent of yesterday.
- **H5 (tier accuracy, descriptive):** accuracy ordered A ≥ B and A ≥ C,
  reported with CIs; no gate.
- **H_pos (positive control):** tier A accuracy ≥ 0.90 when a domain is
  emitted. Below that the instrument (prompts, parsing, or scoring) is
  broken — stop and fix before interpreting anything else.
- **H_pla (placebo control):** within tier, the brand name's alphabetical
  rank must not predict accuracy. An effect means the clustering/CIs are
  wrong.

## 5. Measurement and decision rules

**Primary outcome:** the domain of a `site:` fan-out naming the brand's
prompt-run. **Secondary (pre-registered):** the modal domain of
`search_results[]` entries attributable to a brand-named fan-out, used only
when the pilot shows `site:` emission is too rare (< ~10% of brand-identity
runs) to power H2 — the pilot decides WHICH is primary, before freeze, and
the spec records the decision.

**Rates:** Wilson 95% CIs; zero cells get rule-of-three (3/n) upper bounds.
**H2:** permutation baseline, 5,000 draws, seed = freeze date.
**H3/H4:** cluster bootstrap on brand, 2,000 draws.
**Null claims:** only via TOST inside the pre-registered band; inconclusive
is reported as inconclusive.
**Dry run:** `01_features.py --synthetic` plants (a) a pure-lookup world and
(b) a pure-guess world; `03_model.py` must return the matching verdicts on
both before any real collection is scored.

## 6. Known traps for this design

- **Consultation-conditional selection** (§1) — the headline framing trap.
- **Same-day response caching** would fake within-day concordance: pilot
  probes identical prompts batch-submitted vs spaced; if byte-identical
  markdown comes back, all replicates move to spaced sub-slots and the spec
  records it. (Cross-day caching is already refuted by 002/003/005, which
  resubmitted identical text daily and measured day-over-day variation.)
- **Entity ambiguity**: "Bear", "Motion", "Things" collide with bigger
  entities; templates carry a per-brand category anchor so the model answers
  about the intended entity, and an answer about the WRONG entity (scored
  from the markdown in Audit B spot-checks) is excluded from domain scoring,
  counted separately as `wrong_entity`.
- **Tier C is not "wrong = old"** by fiat: old domains often still resolve
  and redirect. `stale` is its own outcome class precisely because the
  stale-vs-wrong distinction IS the hypothesis.
- **The 1500-task CLI cap**: allocation below exceeds it; `--max-total-tasks
  3600` is set deliberately per study (never blanket `--force`).

## 7. Allocation and cost (FROZEN — option C, picked by the study owner
## 2026-09-01 after the §8c calibration)

48 brands × 2 templates = 96 items/pass. Instrument: direct OpenAI
Responses API (gpt-5.6-terra + web_search), `harness/collect_openai.py`.
- **Wave 1: R=3** — core (r0) at ~10:30, rep1 at ~14:30, rep2 at ~18:30
  local, spaced by the launchd triggers = 288 calls.
- **Waves 2–10: R=1** (core only) = 864 calls.
- **Total 1,152 calls ≈ 30M input + 2M output tokens** at the measured
  26.1k in / 1.7k out per call (§8c). 10 days wall-clock, start 2026-09-02.
- Power: 100% site: emission (§8c) means every call yields domain
  observations. 96 within-day replicate pairs ×2 on wave 1; 9-step
  day-over-day chains per item. Zero-error cells get rule-of-three (3/n)
  upper bounds: ≈240 wave-observations per tier → bound ≈1.3%.
- Replicate mechanics: replicate encoded in `item_id`
  (`{brand}_{p1|p2}_r{0,1,2}`) under intents core/rep1/rep2; the
  collector's (intent, item_id, wave) idempotence gives each slot one
  shot. Spacing via `run_wave.py` + launchd (3 triggers/day, one intent
  per trigger; self-destructs after wave 10 collects).

## 8. Pilot wave 0 checklist (~50 tasks, before freeze)

1. Gemini `fan_out_queries` present? (Production evidence predicts EMPTY —
   the DataForSEO Gemini scraper exposes no fan-out field. If confirmed:
   ChatGPT-only, recorded in §1 "cannot measure".)
2. Emission calibration: 10 brands × 2 templates × both platforms; decide
   primary outcome (§5) and R.
3. Same-day cache probe (§6): one prompt 3× in a single batch AND 3× spaced;
   byte-compare markdown.
4. SKILL.md smoke rules: `.markdown/.fan_out_queries/.sources/.model`
   present; record `.model`; location_code 2840; note the euronics.ee-style
   locale-leakage precedent in audit expectations.
5. Template wording sanity: spot-read 10 answers for wrong-entity responses;
   tighten category anchors if needed (allowed pre-freeze only).

## 8b. Pilot wave 0 findings (2026-09-01 — 31 tasks, $0.07; pre-freeze)

The pilot ran §8 items 1–4 and **killed the planned instrument**:

1. **DataForSEO ChatGPT scraper no longer exposes the search phase.** All 26
   ChatGPT tasks (10 brands × 2 templates, 3 cache replicates, 3 exp-005-style
   category probes) returned `fan_out_queries: []`, `search_results: []`,
   `se_results_count: 0`, `model: null` — while `sources` stayed populated
   (3–15 per answer), so web search clearly ran. Exp 005 (2026-08-05, same
   payload shape) had 100% fan-out coverage and `model: "gpt-5-5"`. The
   scraper's search-phase extraction changed/broke between 2026-08-05 and
   2026-09-01 — plausibly tracking the same ChatGPT UI change that introduced
   `site:` searches. The primary outcome as designed (§5) is currently
   unobservable through DataForSEO.
2. **Gemini arm is dead, twice over:** the endpoint rejects the
   `force_web_search` field's presence (40501), and its responses carry no
   fan-out surface (harness now omits the field for Gemini). ChatGPT-only,
   as §8.1 anticipated.
3. **No same-day batch caching:** three identical batch-submitted prompts
   returned three distinct answers (distinct markdown hashes/lengths). The
   spaced half of the probe is moot pending the instrument decision.
4. **Sources-accuracy preview** (exploratory, n=10 brands): ChatGPT's cited
   sources contained the brand's canonical domain for 10/10 brand-identity
   prompts (usually top-ranked; `notion.com` not `.so`, `usemotion.com`,
   `linear.app`, `hellobonsai.com`); the comparison template 8/10. Gemini
   (via its scraper): 2/5, with third-party review sites dominating. No
   old-domain or morphological-guess domains surfaced anywhere.
5. **Instrument decision (RESOLVED 2026-09-01): direct OpenAI Responses API
   with the `web_search` tool** — the exact path Spyglasses production
   harvests `web_search_call.action.query` from, on the model prod pins
   (gpt-5.6-terra). Probe (`harness/probe_openai_direct.py`, 3 prompts)
   confirmed the collector AND previewed the phenomenon:
   - `motion_p1` → 4 web_search_call items incl. `site:usemotion.com pricing …`
     and `site:usemotion.com/pricing …` — the model used the TRUE non-obvious
     tier-B domain, not the motion.com morphological guess;
   - `notion_p1` → `site:notion.com/help …` — the NEW tier-C domain, not
     notion.so;
   - even the category probe emitted one `site:` search
     (`site:sennheiser-hearing.com …`).
   site:-emission on brand-identity prompts looks strong (2/2 brands) —
   viable power for §4. Collector refinements for the real harness: some
   `web_search_call` items carry no `action.query` (record `action.type`;
   likely open_page/find-style actions), and `action.sources` came back
   empty — try the Responses API `include` parameter for
   `web_search_call.action.sources` before deciding sources are unavailable.
   This makes 008's instrument IDENTICAL to the pipeline that produces 007's
   observational corpus — a coherence gain, at the cost of measuring the API
   surface rather than the consumer UI (state this in §1). Allocation (§7)
   re-costs at Responses-API pricing at freeze.
6. **Production-side flag (outside this study):** if nightly ChatGPT prompt
   runs ingest grounding from DataForSEO `fan_out_queries`, that ingest may
   have thinned/flatlined since the scraper change — check openai-platform
   grounding-row volume by week on the replica.

Consequences for the design if the direct-API probe succeeds: allocation
(§7) is re-costed for Responses-API pricing at freeze; H1 emission rates are
calibrated on the new instrument before freeze; everything in §4's structure
stands.

### §8c — Direct-API calibration (2026-09-01, 23 calls, panel verified)

- **Emission is 100%** on the new instrument: 13/13 brand-identity (p1) and
  10/10 comparison (p2) calls emitted ≥1 `site:` query. The low-emission
  power worry is gone; replicate/wave counts can shrink.
- **First domain scoring: 26 TRUE, 0 STALE, 0 GUESS, 10 other** — and every
  "other" is the model consulting a COMPETITOR's site on a comparison
  prompt (ClickUp for Asana, Adobe for Figma, Obsidian for Notion, Apple
  and Nintendo for Sony), replicating 007's comparison-trigger finding on a
  second instrument. No wrong domain for an asked brand yet; the pilot
  brands skew famous, so tiers B/C/D carry the study.
- **Identical-prompt probe** (Figma p1 ×3, one batch): stable emission,
  stable TRUE domain, distinct responses — no caching, usable within-day
  variance.
- **Panel verified** (`harness/verify_panel.py`): two dead tier-B brands
  replaced (Tome→Granola/granola.ai, Height→Amie/amie.so); Paymo's
  canonical corrected to paymoapp.com (paymo.biz redirects there;
  paymo.com is dead — a natural morphological-guess trap);
  Gamma/GoTo/Meta 403/400 scripted fetches noted as WAF, domains verified.
- **Measured cost basis**: 26.1k input + 1.7k output tokens per call
  (median 26.9k in, p90 38.3k). Allocation options at freeze, in calls
  (price per M tokens supplied at decision time):
  - **A — frozen plan as drafted**: 2,112 calls ≈ 55M in / 3.6M out.
  - **B — trimmed replicates**: R1 × 14 waves × 96 items, plus R3 on waves
    1–2 for tiers B/C/D only = 1,632 calls ≈ 43M in.
  - **C — lean**: 10 waves × R1 × 96 + day-1 R3 = 1,152 calls ≈ 30M in.
  - **D — p1-weighted**: p1 all 14 waves, p2 on waves 1/7/14 = 816 calls
    ≈ 21M in.
  Given 100% emission, rule-of-three bounds stay under ~1% wrong-rate per
  tier even under C/D. Study owner picks before FROZEN is set.

## 9. Deliverables and sequence

1. Pilot wave 0 → decisions recorded in this file
2. Freeze spec + panel (`pipeline/brands.py`) + domain map; `data/raw/FROZEN`
   sentinel; seed = freeze date
3. `run_wave.py` (005 pattern: ledger state machine, FROZEN gate, launchd
   sub-slots, self-destruct after wave 14)
4. Waves 1–14; `02_audit.py` A–E; `03_model.py`; robustness
5. Figures (`04_figures.py` via `save_figure()`): lead = per-tier accuracy
   dot-plot with CI whiskers; error-content stacked contrast (H3); transition
   diagram (H4)
6. Article + derived dataset through the release gate (`05_release.py` —
   derived features only; fan-out text never published)
7. Companion blog post EN+DE in the spyglasses repo

## 10. Notes for the write-up

- Lead framing: "Does AI know your domain, or is it guessing?" — answered as
  a measured mixture, not a binary.
- Mandatory "What we can and cannot claim" section; publish equivalence
  bounds and every rule-of-three upper bound ("we could have detected a rate
  above X and did not").
- Honor the founding caveat: a week without an erroneous consultation does
  not mean it can't happen — every absence is an upper bound.
- Cross-reference experiment 007: 007 shows the behavior in the wild
  (observational, customer corpus, derived aggregates only); 008 is the
  controlled instrument over non-customer brands.
