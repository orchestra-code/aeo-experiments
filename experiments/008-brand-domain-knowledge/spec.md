# AI models KNOW brand domains rather than guessing them per run — study spec

**Status:** draft (freeze AFTER pilot wave 0 — pilot calibrates emission rates
and the Gemini arm; panel + domain map freeze WITH the spec)
**Frozen commit:** <record before wave 1 submits; `data/raw/FROZEN` sentinel
gates `run_wave.py`>
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
templates × ChatGPT (+ Gemini if the pilot shows fan-outs) × 14 daily waves,
with 3-per-day spaced replicates on waves 1–4 to separate within-day
stochasticity from day-over-day drift. All claims are rates with CIs — a
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

## 7. Allocation and cost (draft — final numbers at freeze, after pilot)

48 brands × 2 templates = 96 items/pass.
- ChatGPT: waves 1–4 at R=3 spaced sub-slots (≈08:00/14:00/20:00 local) =
  1,152 tasks; waves 5–14 at R=1 = 960. Subtotal 2,112 ≈ $5.07.
- Gemini (only if pilot shows fan_out_queries): R=1 × 14 waves = 1,344 ≈
  $3.23.
- Total ≤ 3,456 tasks ≈ $8.30 on the priority queue, 14 days wall-clock.
- Power sketch: waves 1–4 give ≥288 within-day replicate pairs per tier;
  the 13-step daily chains give ≥312 day-over-day transitions per tier.
  Effective n for H2 is brands-with-≥2-wrong — if the pilot's error rate
  implies < 8 such brands per contrast tier, bump R or extend tier B/C at
  freeze (recorded).

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
5. **Instrument decision (PENDING a valid OpenAI API key):** the replacement
   collector is the direct OpenAI Responses API with the `web_search` tool —
   the exact path Spyglasses production harvests `web_search_call.action.query`
   from (site: operators included), and the model prod pins (gpt-5.6-terra).
   This makes 008's instrument IDENTICAL to the pipeline that produces 007's
   observational corpus — a coherence gain, at the cost of measuring the API
   surface rather than the consumer UI (state this in §1).
   `harness/probe_openai_direct.py` is ready; the local spyglasses
   OPENAI_API_KEY is invalid (`invalid_api_key`) so the probe has not run.
6. **Production-side flag (outside this study):** if nightly ChatGPT prompt
   runs ingest grounding from DataForSEO `fan_out_queries`, that ingest may
   have thinned/flatlined since the scraper change — check openai-platform
   grounding-row volume by week on the replica.

Consequences for the design if the direct-API probe succeeds: allocation
(§7) is re-costed for Responses-API pricing at freeze; H1 emission rates are
calibrated on the new instrument before freeze; everything in §4's structure
stands.

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
