# Being shortlisted by AI is stable when rank is not: study spec

**Status:** FROZEN
**Frozen commit:** `6342963`
**Frozen date / seed:** 2026-10-03 / 20261003
**Experiment slug:** `010-shortlist-stability`

> Freeze rule: §4 (hypotheses) and §5 (model and decision rules) are fixed
> before wave 1 of the new collection is submitted and before any holdout
> answer is classified. Frozen with the spec: the exploration split
> (`split.csv`), the prompt panel (`data/raw/prompts_b2b.csv`, the 40 prompts
> of experiment 009), the collection schedule (`collection_schedule.json`),
> the judge pin (`harness/judge_pin.json`) and the harness code. The brand
> LEXICON v3 and the "best for" TAXONOMIES are instrument data, not
> hypotheses: they are built from early answers and frozen before any
> confirmatory metric is computed (§5 protocols). Any later change is logged
> under Deviations.
>
> Two analysis stages are pre-registered together here (see "Two stages").
> Stage 1 (run to run) is analyzed and may be published before the Stage 2
> data exist. Nothing that Stage 2 depends on (its hypotheses, lag bins,
> lexicon, taxonomies or the collection schedule) may change after Stage 1
> results are seen.

---

## A. Pre-freeze findings (2026-10-03)

All from the exploration third of the existing data (`sketch.md`, committed
before classification in `dbe61a7`; results in `results/exploration.md`,
`results/exploration_bestfor.md`, `results/power.md`). None of it is
confirmatory, and none of it touched the holdout.

1. **Instrument.** The production judge ran on 981 answers ($1.08, about
   $0.001 per answer at list price); 979 parsed first time, the other 2 on
   retry, as production retries. Evidence quotes verified 96%. A second pass
   on 200 answers agreed on 96% of brand categories (Cohen's kappa 0.91); a
   top choice survived the re-judge 95 to 96% of the time. So run-to-run
   change in top choices is the AI, not the judge.
2. **Go/no-go G1 to G4 all passed.** Shortlist (recommended) retention 0.83
   (ChatGPT headphones) and 0.78 (claude.ai B2B), against exact-position
   retention 0.50 and 0.36. Flat over three weeks on ChatGPT (0.83 at 0 to 2
   days apart, 0.82 at 15 to 21).
3. **Top choice is no steadier than rank 1.** ChatGPT 0.68 vs 0.68; Claude
   0.50 vs 0.81. But a top choice stayed at least recommended in 96 to 98% of
   other runs: top picks rotate inside the shortlist.
4. **Classification adds no stability on its own.** The recommended set is
   as stable as the mentioned set (difference -0.01 to +0.02) and as stable
   as a position-only list of the same size. Its value is telling
   endorsements from mentions: in Claude B2B answers the two sets differ in
   51% of answers and 29% of answers caution against a vendor; ChatGPT
   headphone answers almost never caution.
5. **Fragmented markets churn.** Brand-design agencies on ChatGPT: shortlist
   retention 0.41 (0.22 counting agencies outside the lexicon). Headphones
   look stable partly because the market is concentrated: two different
   headphone questions share 0.72 of their shortlist anyway.
6. **"Best for" ("Where AI picks you").** Grouped as the platform groups it
   today (`normalizePhrase`), a brand's best-for phrase repeats in 0.05 to
   0.11 of reruns. Grouped into use-case segments, 0.47 to 0.57. Segment
   classifier test-retest 95%; 1% of phrases fit no segment. The taxonomy
   builder always filled its cap (8 segments plus "general"), so the cap is
   fixed here rather than chosen per category.
7. **Smoke wave (4 B2B prompts on each platform via DataForSEO).** ChatGPT
   reports model `gpt-5-6` (the 2026-07/08 data was `gpt-5-5`), with
   sources and fan-out present. Gemini reports `3.5 Flash-Lite`, as scraped
   from the Gemini app; production collects Gemini through the same
   DataForSEO path, so this is the Gemini Spyglasses customers see in their
   numbers. Judged, the 8 answers show cautions (2 of 8), generic mentions of
   the buyer's other systems, and fewer top picks than ChatGPT headphones.
8. **Precision planning** (`results/power.md`). Projected 90% half-widths:
   H1 0.03 to 0.05 against exploration gaps of 0.33 to 0.42; drift (H5) 0.007
   on ChatGPT consumer data; top-choice contrasts in B2B 0.10 to 0.14
   (top picks are rarer), which is why they are secondary.

## 0. One-paragraph summary

AI-visibility tools sell rank ("you're #1 in ChatGPT"), and our earlier
studies showed rank does not hold from one run to the next. B2B buyers do not
act on rank; they act on the shortlist the answer gives them, the vendors that
get the demo calls. This study tests whether being shortlisted by AI is
stable, in two pre-registered stages. Stage 1 (run to run): across repeated
runs of the same buyer question a few days apart, does a vendor the answer
recommends get recommended again, far more reliably than it holds its exact
position? Stage 2 (over time): does that hold over five weeks? The instrument
is the Spyglasses recommendation judge, unchanged. The data: a new collection
of 40 B2B software prompts on ChatGPT, Gemini and Claude (7 daily waves for
Stage 1, then 4 weekly waves for Stage 2), and the untouched two thirds of existing
answers from experiments 002, 003, 005 (ChatGPT, consumer headphones and
design agencies) and 009 (claude.ai, B2B software). Expected, from the
exploration: shortlist retention near 0.8, 30 to 40 points above exact
position; top picks that rotate within a stable shortlist; no drift.

## 1. The claim we can and cannot make

**What this design measures:** for a fixed buyer question asked repeatedly to
one AI platform, how often a vendor keeps the status the answer gave it
(recommended, top choice, best for a use case, cautioned against) in another
run a few days later (Stage 1), and whether that changes over five weeks
(Stage 2).

**What this design does NOT measure:**
- What buyers do with the answer. "The shortlist is who gets the demo" is the
  motivation, not a finding.
- Personalized or logged-in sessions, follow-up turns, or platforms other
  than ChatGPT, Gemini and Claude.
- Whether a vendor is shortlisted for its category in general: the unit is a
  specific question. Different questions in one category produce different
  shortlists (that is the between-prompt baseline, reported for context).
- Why a vendor is shortlisted.

**Defensible claims (if the hypotheses hold):**
- Stage 1: "When ChatGPT, Gemini or Claude recommends a B2B software vendor
  for a buyer's question, it recommends that vendor again in about X% of
  repeat runs. The vendor's exact position repeated only Y% of the time, and
  the top pick changed between runs about as often as the first-named vendor
  did."
- Stage 2: "That rate did not change over five weeks: answers a month apart
  agreed on the shortlist as often as answers a day apart."

**Indefensible claims:** "AI's shortlist for your category is stable" (one
question is not a category); "being shortlisted means buyers will contact
you"; "the top pick is stable"; anything about fragmented markets beyond the
agency result; anything about AI Overviews, AI Mode or Perplexity.

### Mechanistic prior

A shortlist answer starts from a candidate set the model assembles from its
prior knowledge and the pages its search retrieves. Vendors with a strong
prior and steady retrieval presence enter that set in almost every run, so
membership is stable in concentrated markets and churns in fragmented ones.
The order of the list and the single "pick" depend on sampled reasoning about
fit to the asker's details, so they vary more. The exploration matches this:
top picks change, but they stay on the list.

## Data, arms and collection

| Dataset | Source | Platform (model) | Prompts | Runs per prompt | Role |
|---|---|---|---|---|---|
| `chatgpt_b2b` | new, DataForSEO | ChatGPT (`gpt-5-6` at smoke) | 40 | 7 (Stage 1), 11 (Stage 2) | primary |
| `gemini_b2b` | new, DataForSEO | Gemini app (`3.5 Flash-Lite` at smoke) | 40 | 7 (Stage 1), 11 (Stage 2) | primary |
| `claude_api_b2b` | new, Anthropic API | Claude, `opus55_plain` (Opus 5.5) | 40 | 7 (Stage 1), 11 (Stage 2) | primary |
| `claude_b2b` | 009 holdout, `ui_default` | claude.ai, Opus 5.5 default | 26 (13 categories) | 3 | primary |
| `chatgpt_consumer` | 002+003+005 holdout | ChatGPT (`gpt-5-5`) | 95 | 17 | secondary |
| `chatgpt_agency` | 002+003+005 holdout | ChatGPT (`gpt-5-5`) | 27 | 3 | secondary (low power) |

`claude_b2b` holdout also carries `ui_think` and `opus55_plain` answers
(robustness and the cross-arm comparison).

`claude_api_b2b` uses experiment 009's collector and arm `opus55_plain`
unchanged (Opus 5.5, effort medium, no system prompt, web search tool
`20250305`, user location Pittsburgh): the request shape Spyglasses tracks
Claude discovery with, which 009 found close to claude.ai. Smoke call
2026-10-03: one search, three citations, $0.11 in real time.

**New collection.** The 40 prompts of experiment 009 (20 B2B software
categories, one "shortlist" and one "evaluate" prompt each), unchanged, on
all three platforms. ChatGPT and Gemini go through `scripts/llm_scraper.py`
(priority queue, US location, `force_web_search` on ChatGPT; the Gemini
endpoint rejects it); Claude through 009's `collect_anthropic.py` (Batches
API). Waves on days 0 to 6 (daily) and 13, 20, 27, 34 from the start date in
`collection_schedule.json` (2026-10-03, so waves run Oct 3 to 9, Oct 16,
Oct 23, Oct 30, Nov 6). `run_wave.py`, run daily at 20:00 local time by
launchd, submits each wave the same evening on all three platforms (Claude's
batch first), collects the DataForSEO tasks after the queue wait, and
collects the Claude batch on its next run; one ledger per platform. A
Claude answer's run date is its batch submission date. A wave submitted after
its date is logged LATE and recorded as a deviation; it stays in the analysis
with its true lag. Cost: 880 DataForSEO tasks at about $0.0024, 440 Claude
calls at about $0.07 (009's batch estimate, not yet reconciled with
Anthropic billing), plus judging: about $38. Fourteen
of the 40 prompts were in the Claude exploration set; their new ChatGPT,
Gemini and Claude API answers are new runs, and no result has been computed
on them.

**Holdout judging.** Immediately after freeze: `build_tasks.py --split holdout
--allow-holdout`, then `judge_runner.mts --split holdout` (about 1,930
answers, about $2).

## Two stages

| | Stage 1: run to run | Stage 2: over time |
|---|---|---|
| Question | Is being shortlisted stable from run to run, compared with position and the top pick? | Does it hold over five weeks? |
| New data | waves 1 to 7 (daily, Oct 3 to 9) | waves 1 to 11 (adds Oct 16, Oct 23, Oct 30, Nov 6) |
| Holdout data | all holdout datasets | `chatgpt_consumer` lags (0 to 21 days) |
| Primary family | H1 (4 datasets) | H5 (3 datasets) |
| Analysis | after wave 7 and the STOP 2 freezes | after wave 11 |
| Report | article 1, about Oct 12 | article 2, about Nov 9 |

Firewall rules:
1. Stage 1 uses only waves 1 to 7 of the new collection. Waves 8 to 11 are
   collected by the frozen schedule whatever Stage 1 shows.
2. Article 1 pre-announces Stage 2: its date, H5, its band and its bins (as
   the 003 article pre-announced 005).
3. Stage 2 does not re-test Stage 1 hypotheses. H1 to H4 on all 11 waves are
   reported descriptively only, so no claim gets two chances.
4. Lexicon v3 and the taxonomies are frozen once (STOP 2) and used for both
   stages; brands that first appear in waves 8 to 11 are covered by R1, never
   by re-curation.
5. The `chatgpt_consumer` holdout is judged at Stage 1 (for its run-to-run
   results), but its drift contrast is computed only at Stage 2.

## 2. Data-quality audits (run before the model)

- **Audit A, collection completeness.** Per platform (ChatGPT, Gemini,
  Claude) and wave, at least 38 of 40 tasks collected with a non-empty answer. Missing tasks are resubmitted
  the same day by the driver. A wave below 36 of 40 on a platform is excluded
  from H5's lag bins for that platform (kept elsewhere) and logged. Refusals
  and empty answers are flagged and excluded.
- **Audit B, what the labels mean.** The categories are the production
  judge's (`MENTION_ASSESSMENT_SYSTEM_PROMPT`, quoted in the article
  appendix): top choice = singled out as the pick, rarely more than one, a
  segment winner ("best for enterprises") is NOT a top choice; one of many =
  recommended alongside others; generic mention = named without endorsement;
  cautioned against = steered away from for this asker. More than two top
  choices in one answer are demoted to one of many (the raw output is kept;
  the demotion rate is reported). Judge pinned: `harness/judge_pin.json`
  (sha256 of the judge and its imports, spyglasses commit, `gpt-5.6-luna`,
  reasoning effort none, `MENTION_ASSESSMENT_VERSION` 2).
- **Audit C, independence.** Pairs share prompts; the prompt is the
  bootstrap cluster. The two prompts of a B2B category share a market, so
  robustness R5 clusters by category.
- **Audit D, lexicon v3 precision and recall.** 30 answers from new waves 1
  and 2 (15 per platform, platform-blind), brands marked by a person against
  the extraction. Pass: precision at least 0.95, recall at least 0.90 (the
  009 thresholds).
- **Audit E, judge test-retest.** A seeded 10% sample of each stage's
  confirmatory answers (Stage 2: waves 8 to 11 only; the Stage 1 sample is
  reused) is judged twice. Category agreement at least 90% (exploration:
  96%). Below that, the retention figures carry an instrument-noise caveat
  and R4 is promoted to the main text.
- **Audit F, model drift.** The reported model of every answer is recorded
  (DataForSEO's `model` field; the Claude API's model id). A model change mid-collection is reported as a finding; R2
  restricts to the modal model.
- **Audit G, best-for classifier.** Segment test-retest on all distinct
  phrases at least 90% (exploration: 95%).

## 3. Data schema

One row per (answer, lexicon brand), plus one row per answer.

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| dataset, platform, model | str | collection | yes | |
| item_id | str | prompts | yes | B2B prompts are public (009 release); headphone and agency prompt text never |
| category | str | prompts | yes (B2B); coded (consumer, agency) | |
| wave, run_date | int, date | ledger / answer | yes | |
| brand | str | lexicon | coded (`v0001`) | as in 009's release |
| position | int | lexicon extraction | yes | first-mention order |
| status | enum | judge | yes | top_choice, one_of_many, generic_mention, cautioned_against, unclassified |
| best-for segment ids | list | taxonomy + classifier | yes (segment labels for B2B) | phrases never |
| caveat reason types | list | judge | yes | reason text never |
| answer text, phrases, evidence | str | | never | |

### Derived variables

Per answer, over lexicon brands: **M** mentioned; **R** recommended (top
choice or one of many), the shortlist; **T** top choice; **C** cautioned
against; **P1** first-mentioned brand; **Pk** exact (brand, position) pairs;
**WP** "Where AI picks you" pairs (brand in R, best-for phrase key from
`normalizePhrase`); **WS** use-case pairs (brand in R, best-for segment).

**Retention** of a status S over a set of answer pairs = 2·Σ|Sa ∩ Sb| /
Σ(|Sa| + |Sb|) (pooled Dice): the share of brand appearances with status S
in one answer that keep it in the other. **Directional retention** T→R =
Σ(|Ta ∩ Rb| + |Tb ∩ Ra|) / Σ(|Ta| + |Tb|).

Pair conditions: **within** = same prompt, same platform or arm, different
waves; **between** = different prompts, same category, same platform, same
wave (descriptive market-concentration baseline); **cross** = different
categories, same platform, same wave (positive control). **Lag** = days
between the two answers' run dates.

## 4. Pre-registered hypotheses

### Stage 1: run to run (new waves 1 to 7, holdouts)

**Stage 1 primary family** (Holm across its 4 tests):

- **H1 (the shortlist beats position)**, for `chatgpt_b2b`, `gemini_b2b`,
  `claude_api_b2b` and `claude_b2b`: within-prompt retention of R exceeds within-prompt
  retention of Pk by more than 0.10. Test: one-sided, H0: R - Pk <= 0.10.

**Stage 1 secondary** (no multiplicity correction, labeled as such), for the
four B2B datasets unless noted:

- **H2 (the shortlist beats the top pick):** R - T > 0.10 (one-sided,
  H0: R - T <= 0.10).
- **H3 (the top pick is no steadier than rank 1):** T - P1 < +0.10
  (non-superiority: upper 90% bound below +0.10).
- **H4 (top picks stay shortlisted):** directional T→R at least 0.90 (lower
  90% bound at least 0.90).
- **H6 (classification neither adds nor removes stability):** R - M
  equivalent to 0 within +/-0.05 (TOST).
- **H7 ("Where AI picks you" is less stable than the shortlist):** R - WS >
  0.10 (one-sided). Reported with WP (the platform's current phrase
  grouping) as an estimate; expected below 0.20.
- **Generalization:** H1 to H4, H6 and H7 on `chatgpt_consumer` and
  `chatgpt_agency`; agency is reported as underpowered.

**Stage 1 descriptive (no test):** the level of R retention with its CI (the
headline number); the share of shortlisted brand-prompt pairs shortlisted in
at least 80% of a prompt's runs; between-prompt baselines; answers with a top
choice, with a caution, raw top choices demoted; cautioned-status retention
where there are at least 30 appearances; caveat reason mix; cross-platform
shortlist agreement (ChatGPT vs Gemini vs Claude API, same prompt, same
wave); `claude_b2b` arm comparison (ui_default vs ui_think vs opus55_plain).

**Stage 1 H_pos (positive control; the study stops if it fails):** for each
dataset, within-prompt R retention exceeds cross-category R retention by at
least 0.10 with the 90% CI excluding 0. It catches broken joins and broken
extraction (answers filed under the wrong prompt), not a claim. For
`chatgpt_consumer` and `chatgpt_agency`, "cross" is headphone vs agency
answers from the same study wave.

**Stage 1 H_pla (placebo):** the H1 gap computed on odd vs even prompt
numbers differs by a NULL or NEGLIGIBLE amount (TOST +/-0.10) for each
primary dataset.

### Stage 2: over time (new waves 1 to 11)

**Stage 2 primary family** (Holm across its 3 tests):

- **H5 (the shortlist does not drift)**, for `chatgpt_b2b`, `gemini_b2b` and
  `claude_api_b2b`:
  retention of R over within-prompt pairs at least 27 days apart minus
  retention over pairs 1 to 2 days apart is equivalent to 0 within +/-0.05
  (TOST). Pairs per prompt: 8 far, 11 near.

**Stage 2 secondary** (no multiplicity correction):
- H5 on `chatgpt_consumer` using its holdout lags: pairs at least 15 days
  apart vs 0 to 2 days apart, TOST +/-0.05.
- H5 applied to T (top-choice drift) and WS (use-case drift) on the new B2B
  datasets, TOST +/-0.05, reported as secondary.

**Stage 2 descriptive (no test):** retention by days apart for R, T, P1, Pk,
WS (the curve); H1 to H4 recomputed on all 11 waves (descriptive only,
firewall rule 3); the platform model reported on every wave; `claude_api_b2b`
answers compared with 009's `opus55_plain` answers to the 26 holdout prompts
(same arm, Sep 27 to Oct 1, so 2 to 6 weeks of extra lag; the 14 exploration
prompts are left out of this comparison).

**Stage 2 H_pos:** as Stage 1, on all 11 waves.

**Stage 2 H_pla:** H5 computed on odd vs even prompt numbers differs by a
NULL or NEGLIGIBLE amount (TOST +/-0.05) for each primary dataset.

## 5. Model and decision rule

**Model:** nonparametric. Pooled retention ratios with a prompt-level
cluster bootstrap (prompts drawn with replacement; within pairs weighted by
the drawn count of their prompt, between and cross pairs by the product of
their two prompts' counts), 2,000 draws, 90% percentile intervals, seed =
freeze date. Contrasts are computed draw by draw. Pair-mean Jaccard
(`aeo_research.overlap.cluster_boot`) is reported alongside for continuity
with earlier studies.

**p-values for Holm:** for a one-sided margin test, the share of draws at
or below the margin; for TOST, the larger of the two tail shares at the band
edges. Holm at family alpha 0.05 within each stage's primary family (the two
stages answer different questions and are reported separately); each verdict
uses the CI at its Holm-adjusted level.

**SESOI:** 0.10 for H1, H2, H7 (the house band: one vendor in a typical
five-to-eight-vendor shortlist). 0.05 for H5 and H6: five points of
retention lost in five weeks would mean tracking has to be recalibrated
monthly, which matters to anyone reading a trend line. 0.90 for H4 (nine in
ten).

**Decision rules (90% CI):**

| Test | Result | Conclusion |
|---|---|---|
| Margin (H1, H2, H7) | lower bound above 0.10 | Supported: more stable by more than 0.10 |
| | lower bound in (0, 0.10] | More stable, possibly by less than 0.10 |
| | CI includes 0 | Not shown |
| Equivalence (H5, H6, H_pla) | CI inside the band | Practically equivalent (null) |
| | CI excludes 0, inside band | Detectable but negligible |
| | CI excludes 0, extends beyond band | Real change: report it |
| | CI includes 0, extends beyond band | **Inconclusive: do not claim a null** |
| Non-superiority (H3) | upper bound below +0.10 | Supported |
| Level (H4) | lower bound at least 0.90 | Supported |

**Precision** (`results/power.md`, exploration resampled to confirmatory
size): H1 half-width 0.03 to 0.05 against exploration gaps of 0.33 to 0.42;
H5 0.007 on ChatGPT consumer data (B2B expected wider, up to about 0.03, still
inside the 0.05 band if the true drift is near 0); H2 and H3 in B2B 0.10 to
0.14 with the 3-run Claude proxy (Stage 1 has 21 pairs per prompt from 7
waves rather than 3, so narrower); H4 0.01 to 0.03.

**Lexicon protocol (v3, new collection).** After waves 1 and 2, the judge's
names that are not in lexicon v2.1 (the untracked names, all categories)
are candidates. They are merged into v2.1's rows under 009's rules (the unit
is the brand the answer names; renames and descriptive product lines merge;
the buyer's own other systems are dropped; open-source tools offered as
options count), by an Opus curator pass with every new row flagged for a
person, then reviewed by Jim. The file's sha256 is recorded here, Audit D
runs, and only then is any metric computed on new answers. Holdout datasets
keep their frozen lexicons (009 v2.1; 005's headphone and agency lexicon).
Brands outside a lexicon are covered by R1.

**Taxonomy protocol ("best for").** One taxonomy per category, shared across
platforms: headphones and agencies reuse the exploration taxonomies (built
from exploration answers only). The 20 B2B categories are rebuilt from the
pooled best-for phrases of the Claude answers (exploration and holdout) and
new waves 1 and 2, with `bestfor_segments.mts taxonomy` (utility model,
effort medium, 8 segments plus "general"). Phrases are classified with
`classify` (effort none), twice (Audit G). Taxonomy files are frozen (sha256
recorded here) before any best-for retention is computed. Phrase keys for WP
use the platform's own `normalizePhrase`.

## 6. Known traps for this design

- **Set size drives retention.** Larger statuses retain more by chance in a
  concentrated market. The between-prompt baseline and the position-only
  list of the same size (exploration: identical to R) are reported so
  readers can see what is AI behavior and what is market concentration.
- **Exact position is a strict comparator.** Almost any membership measure
  beats it. H1 is the claim the industry's rank metrics invite; H2 and H3
  (shortlist vs top pick, top pick vs rank 1) are the sharper tests and are
  reported with equal prominence even though they are secondary.
- **Top choices are rarer in B2B**, so their contrasts are noisier;
  inconclusive is a possible and reportable outcome.
- **Model updates during collection** are part of what a vendor experiences.
  Stage 2's H5 includes them; R2 shows the result without them.
- **Seeing Stage 1 before Stage 2.** The firewall rules under "Two stages"
  keep Stage 2 fixed; any change after Stage 1 is a logged deviation and the
  affected Stage 2 result is labeled exploratory.
- **The lexicon bounds the brand universe.** Brands outside it are invisible
  to the primary metrics; R1 uses every name the judge lists.
- **Claude holdout has 3 runs over 4 days**, so it has no drift test. Its
  role is to replicate H1 to H4 on the platform the study started from.

## 7. Robustness checks

1. H_pos first; if it fails, stop.
2. H_pla must be null or negligible.
3. **R1** every brand the judge names (lexicon brands plus normalized
   untracked names, order = the judge's order of first appearance).
4. **R2** modal model only, per platform.
5. **R3** exclude answers with no lexicon brand, refusals and empty answers.
6. **R4** judge second pass on the Audit E sample: retention recomputed with
   the second pass, and the identical-text ceiling reported.
7. **R5** category-level clusters for the B2B datasets.
8. **R6** `claude_b2b` with `ui_default` and `ui_think` pooled (6 runs per
   prompt; 009 found the reasoning setting does not change brands).
9. **R7** (Stage 2) H5 with alternative bins (days 0 to 6 vs 27 to 34; and
   a regression of pair retention on lag).
10. **R8** per-intent split (009's "shortlist" vs "evaluate" prompts).

All checks run at both stages except R7 (Stage 2 only).

## 8. Deliverables and sequence

1. Jim reviews the draft and the decisions. **STOP 1** (done 2026-10-03).
2. Freeze: two commits (spec, then the hash), pushed. Install the launchd job.
3. Holdout judging and the Audit E sample (same day as freeze).
4. Waves 1 and 2, then lexicon v3 candidates and curation; Jim reviews the
   flagged rows and does the Audit D sheet. **STOP 2.** Freeze lexicon v3 and
   the 20 B2B taxonomies.
5. Wave 7 (Oct 9; Claude batch collected Oct 10): judge waves 1 to 7, Stage 1 pipeline
   (`pipeline/20_` to `24_`, `--stage 1`) on the new data and the holdouts,
   robustness. **STOP 3** for Jim's Stage 1 results review.
6. Article 1 (pre-announcing Stage 2), anonymized Stage 1 dataset through the
   release gate, companion blog post (EN and DE).
7. Wave 11 (Nov 6; Claude batch collected Nov 7): judge waves 8 to 11, Stage 2 pipeline
   (`--stage 2`). **STOP 4** for Jim's Stage 2 results review.
8. Article 2, dataset update, companion blog post (EN and DE).

## 9. Notes for the write-up

- Article 1 lead figure: retention by status, a dot plot with intervals
  (shortlist, best-for use case, top choice, rank 1, exact position), one row
  per platform. It closes with the pre-announced Stage 2.
- Article 2 lead figure: shortlist retention by days apart (flat line
  expected), with top choice and use case alongside.
- Framing: "being shortlisted is the claim that holds up"; never "rank
  tracking is useless". The top-pick result is part of the story: picks
  rotate inside a stable list.
- Sample size reported as "N answers evaluated (in this study)".
- Publish the bands: "we could have detected a five-point drift and found
  none" (if so).
- Product tie-in (blog post only): share of recommendation is the reliable
  number; top-choice share needs many runs; "Where AI picks you" phrases need
  grouping by use case.

## Decisions (Jim, 2026-10-03)

1. Claude added to the collection (`claude_api_b2b`, both stages).
2. Start 2026-10-03 (Saturday) rather than Tuesday; wave 1 fires from the
   20:00 launchd run that evening, so every wave runs at the same hour. The
   launchd job is installed at freeze.
3. Jim does the Audit D sheet after wave 2.
4. The frozen spec is pushed to the public repo at freeze.

## Deviations from the frozen spec

(none yet)
