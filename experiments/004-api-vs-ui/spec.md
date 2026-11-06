# The API names the same brands as the ChatGPT and Gemini UI: study spec

**Status:** APPROVED 2026-11-06, not yet frozen (power table and pipeline pending, §8).
**Frozen commit:** (at freeze)
**Frozen date / seed:** (at freeze) / 20261106
**Experiment slug:** `004-api-vs-ui`

> Freeze rule: §4 (hypotheses) and §5 (model and decision rules) are fixed before
> wave 1 is collected. Frozen with the spec: the prompt panel (009's 40 prompts,
> public), the arm registry and pins (`harness/exp004.py`), the request code
> (`harness/collect_openai.py`, `harness/collect_gemini.py`, `harness/ui.py`), the
> answer normalizer (`harness/answers.py`) and the analysis code. The brand lexicon
> is instrument data, not a hypothesis: it starts from 010's frozen v3 and is
> extended only under §5's protocol, before any confirmatory metric. Any later
> change is logged under Deviations.

---

## A. Pre-freeze findings (2026-11-05)

Aggregates only. Tables: `results/pilot_report.md`. Criteria, clarifications and
deviations: `sketch.md`. All of this is pilot data, on 10 prompts on one day, and
none of it enters the confirmatory analysis.

**Feasibility.** Both platforms passed G1 to G4. Every API response reported its
pinned model. All 30 `cg_ui` answers reported `gpt-6` and all 30 `gm_ui` answers
reported `3.5 Flash-Lite`. Cost: $3.34.

| Arm | Brand gap to its UI (90% interval) | Status after the pilot |
|---|---|---|
| `cg_api_low` (`gpt-6-luna`, reasoning `none`) | +0.007 [-0.068, +0.085] | primary |
| `cg_api_plain` (`gpt-6-luna`, default reasoning) | +0.059 [+0.005, +0.111] | primary |
| `cg_api_leak` (adapted `web_tool.txt`) | +0.092 [+0.031, +0.151] | dropped (rule: at most 2 arms) |
| `gm_api_plain` (`gemini-3.5-flash-lite`, grounding) | +0.101 [+0.016, +0.187] | primary |
| `gm_api_leak` (adapted Gemini web app prompt) | +0.115 [+0.011, +0.230] | dropped (failed G2: searched on 6 of 10) |

The UI overlapped itself at 0.722 (ChatGPT) and 0.659 (Gemini) across three rounds
an hour apart. The study measures that floor across days instead, which will be
lower.

**Behavior.**
- The ChatGPT UI writes answers about 3 times as long as the API (13,100 characters
  against 4,300 to 4,700) and cites about 3 times as many URLs (22 against 7). Brand
  counts per answer are close (5.8 against 5.1 to 5.4).
- `cg_api_low` searched far more than the default setting: 14.9 search calls and 42
  queries per answer, against 3.3 and 12. It costs about 4 times as much.
- At reasoning `none`, the API accepts web search; `minimal` is refused with web
  search on. So "low" here means `none`.
- The leaked ChatGPT prompt moved the API further from the UI, not closer.
- Gemini UI and API answers were about the same length (5,500 characters), with
  similar brand counts (5.5 against 5.7).
- 24 of 30 `gm_ui` answers end with raw follow-up chip markup from the Gemini web
  app, the same components the leaked prompt describes. Stripping it changed no
  answer's brand set (sketch, deviation 8).
- Gemini's app returned two error wordings. One was caught and resubmitted; the
  other was not, which the pilot found and fixed (sketch, deviation 7).

**Power.** §5.

## 0. One-paragraph summary

Tracking tools measure ChatGPT and Gemini in one of two ways: they scrape the
consumer UI, or they call the vendor's API with search turned on. We test whether,
for B2B software research, the API names the same brands as the UI on the same
model. 40 synthetic buyer prompts (009's) run on 3 non-consecutive days through
DataForSEO's scrapers of the logged-out ChatGPT UI and the free Gemini app (the
references), through OpenAI's Responses API on `gpt-6-luna` at two reasoning
settings, and through the Gemini API on `gemini-3.5-flash-lite` with grounding. The
primary test asks whether each API arm overlaps its UI about as much as the UI
overlaps itself across days, within +/-0.10, the band 009 and 011 use. The three
studies are read side by side: Claude (009, 011), ChatGPT and Gemini (004), with no
pooled estimate.

## 1. The claim we can and cannot make

**What this design measures:** for 40 synthetic B2B software-buying prompts with no
location in them, on three days: how closely each API configuration reproduces the
brands named by DataForSEO's scrape of the logged-out ChatGPT UI and of the free
Gemini app, relative to how closely that scrape reproduces itself from day to day.

**What this design does NOT measure:**
- **Logged-in and paid use.** The ChatGPT reference is the logged-out page; the
  Gemini reference is a free personal account. Paid ChatGPT plans run GPT-6 Sol,
  which this study does not test. We suspect, and cannot confirm, that most Gemini
  use comes through paid plans and Google Workspace accounts, which run other models
  (Gemini Enterprise defaults to 3.8 Flash). The public figures do not split it:
  Google reports 1 billion Gemini app users (Q3 2026 call) and more than 8 million
  paid Gemini Enterprise seats by early 2026, and outside estimates of paid consumer
  subscribers range from 25 to 50 million. Paid ChatGPT and Gemini accounts are
  follow-on studies.
- What a person sees in the UI. DataForSEO's scraper is a proxy for the UI. We did
  not compare it with hand-collected UI answers in this study.
- Personalization, memory and follow-up turns.
- Location-dependent prompts. The prompts contain no location. The ChatGPT arms are
  all set to the US; the Gemini API grounding tool has no location setting (§6).
- Other languages, categories outside B2B software, other collectors.
- Human buyer phrasing. The prompts are synthetic (009).
- Whether the leaked system prompts are real. They were dropped after the pilot and
  are not part of this study.

**Defensible claim:** "Across N answers evaluated in this study, the [OpenAI /
Gemini] API on [model, setting] named the same brands as [the logged-out ChatGPT
UI / the free Gemini app], as DataForSEO collects it, [within / X points outside]
the UI's own day-to-day variation, for B2B software prompts with no location in
them."

**Indefensible claims:** "the API equals what users see", any claim about logged-in,
paid or Workspace users, any claim that reasoning or search depth caused a result
beyond the one contrast H2 tests, any claim about prompts where location matters.

### Mechanistic prior

009 found that, for Claude, the same model with a similar search tool overlaps
claude.ai's brands whatever the request shape. The pilot fits that for ChatGPT, where
API brand counts match the UI despite answers a third as long. Against it, neither
API search tool is the UI's search backend, and the Gemini app's grounding is not the
API's `google_search` tool. We expect small positive gaps for ChatGPT, a larger one
for Gemini, and cited domains to diverge further than brands on both.

## Arms, allocation and wave procedure

All arms get the 40 prompt texts of 009 byte for byte, with no follow-up turn and no
personal context.

| Arm | Instrument | Model / reasoning | System prompt | Search | Role |
|---|---|---|---|---|---|
| `cg_ui` | DataForSEO ChatGPT LLM scraper, priority queue | logged-out ChatGPT (`gpt-6` field) | ChatGPT's own | `force_web_search: true`, US (2840), English | **reference** |
| `cg_api_low` | OpenAI Responses API | `gpt-6-luna`, reasoning `none` | none | `web_search`, `user_location` country US | **primary** |
| `cg_api_plain` | OpenAI Responses API | `gpt-6-luna`, default reasoning | none | as above | **primary** |
| `gm_ui` | DataForSEO Gemini LLM scraper, priority queue | free tier, Auto (model reported per answer) | Gemini's own | not settable; US (2840), English | **reference** |
| `gm_api_plain` | Gemini API | `gemini-3.5-flash-lite`, default thinking | none | `google_search` grounding (no location setting) | **primary** |

The UI settings are 010's, so this study's UI answers are collected the way 010
collected them.

**Allocation.** 40 prompts x 3 waves x 5 arms = 600 answers: 240 DataForSEO tasks
and 360 API calls. Projected cost at pilot rates is about $28 plus the Haiku pass;
the ledger stops the study at $45 (pilot spend not counted). Keys come only from this
repo's `.env.local`, and do not change during the study.

**Wave procedure** (one wave per day, non-consecutive days: planned Friday Nov 6,
Sunday Nov 8 and Tuesday Nov 10, 2026; each wave starts between 10:00 and 14:00 ET
so time of day is similar):
1. Submit all 80 UI tasks first, in an order drawn from the seed, tagged
   `aeo-exp004-w<wave>`. DataForSEO's `tasks_ready` is never called; tasks are
   collected by id.
2. Run the three API arms at the same time as the UI tasks. Two workers run in
   parallel, one per vendor. The prompt order is drawn from the seed per wave. For
   each prompt, the two ChatGPT arms run back to back, in an order drawn from the
   seed, so time of day hits both equally.
3. Collect the UI tasks. An answer that is the app's own error message counts as no
   answer and is resubmitted the same day, at most 3 submissions per prompt and wave
   (sketch, clarification 4). A failed API call is retried the same day, at most 3
   attempts.
4. Completeness: every arm must reach 40 of 40 on the day. An answer still missing
   after the retries is excluded from that wave and logged. If an arm misses more
   than 4 answers in a wave, the wave is rerun for its missing prompts the next day
   and logged as a deviation.
5. Every API answer is checked for its pinned model id; a mismatch stops the wave.
   UI answers record the model DataForSEO reports, and are kept whatever it is
   (that is the UI as a user gets it); R8 excludes the ones that differ.

A wave takes about 90 minutes, mostly `cg_api_low`. Monday Nov 9 is 011's wave 3 and
has no 004 wave. 010's last wave runs at 20:00 ET on Friday Nov 6 on the same 40
prompts; 004's wave 1 finishes well before it, and 004 never reads 010 Stage 2 data.

## 2. Data-quality audits (run before the model)

- **Audit A: degenerate responses.** Per arm x wave: failed runs, resubmissions,
  error answers, empty answers, answers with no search, no citations, no extracted
  brands, replies that only ask a question back, and API answers whose model id is
  not the pin. If more than 30% of an arm's answers have no search, its domain
  results are INCONCLUSIVE. `gm_ui` search depth is not observable; "searched" there
  means sources were reported (sketch, clarification 5). A person reads every
  flagged answer, as in 011.
- **Audit B: what the labels mean.** "Brand named" = a lexicon alias match in the
  answer text for the prompt's category, with labelled source blocks stripped, as in
  009 (`extract_new` from 010). For `gm_ui`, the follow-up chip markup is stripped
  before extraction (`harness/answers.py`), because the API arms have no such
  element; R6 keeps it. "Cited" = DataForSEO `sources` (UI); `url_citation`
  annotations (OpenAI); grounding chunks (Gemini API, domain from the chunk title,
  since its URIs are redirect links). "Evaluated" = DataForSEO `search_results`
  (ChatGPT UI) and `web_search_call` sources (OpenAI). The instruments expose
  different fields, so domain results are descriptive.
- **Audit C: independence.** 40 prompts, 2 per category. Inference is prompt-level
  cluster bootstrap; R5 resamples categories.
- **Audit D: extraction validity** (signed by Jim Wrubel). A 30-answer random spot
  check, arm-blind, stratified across the five arms, read by hand: brand precision
  at least 0.95 and recall at least 0.90, else refine the lexicon, log it and
  re-check.

## 3. Data schema

One row per answer (prompt x arm x wave).

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| item_id, category, intent | str | 009 prompts | yes | |
| prompt text | str | 009 | yes (already public) | synthetic |
| arm, platform, wave, run_date, model | str/int | ledger / response | yes | |
| answer text | str | response | **never** | data/raw only |
| search query text | str[] | response | **never** | counts only |
| brands (ordered) | str[] | lexicon | yes (public facts) | |
| cited URLs, evaluated URLs | str[] | response | derived-only | domains publish |
| n_search_calls, n_queries, n_cited, n_evaluated, chars, n_brands | int | derived | yes | null where an instrument does not report it |
| submissions, error_answers, attempts | int | ledger | yes | |
| reasoning_effort | str | request | yes | |
| cost estimate | float | tokens and tool calls at list price | yes (aggregates per arm) | estimate, not an invoice |

### Derived variables

Jaccard with empty-vs-empty = NaN; truncated normalized RBO (p = 0.9) on brand order;
registered-domain heuristic as in 009.

## 4. Pre-registered hypotheses

Pair conditions, per platform: **within:ui** = same prompt, the platform's UI arm,
different waves (3 pairs per prompt). **cross:arm|ui** = same prompt, same wave, the
arm against its UI (3 pairs per prompt). Gap = mean(within:ui) - mean(cross:arm|ui).
Positive means the arm is further from the UI than the UI is from itself.

**Primary (H1, brand-set Jaccard gap, equivalent to 0 within +/-0.10).** Each
platform is its own family, since each answers its own question:
- ChatGPT: `cg_api_low` and `cg_api_plain`, Holm across the 2 tests.
- Gemini: `gm_api_plain`, one test.

**Secondary (no multiplicity correction, labeled as such):**
- **H2, reasoning setting:** for `cg_api_low` and `cg_api_plain`, the mean of their
  two within-arm floors (across waves) minus their same-wave cross-arm overlap,
  TOST +/-0.10. This tests whether turning reasoning off changes the brands.
- **Brand order:** RBO gap for every API arm.
- **Read-alongside:** 009's published gap (+0.067) and 011's results, next to
  004's, on one figure. No pooled estimate and no test across studies: the
  instruments, references and dates differ.

**Descriptive (no verdict):** cited- and evaluated-domain gaps; search calls, queries,
cited and evaluated URLs, brands and length per answer; answers with no search;
models reported by the UI; cost per answer and per 1,000 answers.

**H_pos (positive control; the study stops if it fails), per platform:** same-prompt
cross-arm brand Jaccard (the platform's API arms against its UI, pooled) exceeds
cross-category cross-arm brand Jaccard by at least 0.10, with a 90% CI excluding 0.
It catches a broken join or extraction.

**H_pla (placebo):** the H1 gap on odd against even prompt numbers, TOST +/-0.10,
for each primary arm. It does not gate the analysis, because the split doubles the
interval width (009, deviation 8). A REAL placebo gap is reported as a caveat on H1.

## 5. Model and decision rule

**Model:** nonparametric, as in 009 and 011. Pair-mean contrasts via
`aeo_research.overlap.cluster_boot` (prompt-level cluster bootstrap, 2,000 draws,
percentile CI, seed = freeze date as YYYYMMDD). ChatGPT's Holm step: each test's
bootstrap TOST p-value is the larger of the two one-sided tail probabilities at the
band edges; the tests are ordered by p, and each verdict uses the CI at its
Holm-adjusted level (95% for the first, 90% for the second). Gemini's single test
uses the 90% CI.

**SESOI:** 0.10 absolute Jaccard, the house band, the same as 009 and 011 so the
results compare directly: about one brand swapped in roughly half of a 5 to 10 brand
answer.

**Decision rule (TOST, absolute scale):**

| Result | Conclusion |
|---|---|
| CI entirely inside +/-SESOI, includes 0 | Practically equivalent: passes |
| CI inside +/-SESOI, excludes 0 | Detectable but negligible: passes |
| CI excludes 0, extends beyond band | Real gap: report its size |
| CI wider than band, includes 0 | **Inconclusive: do not claim a null** |

**Power** (`pipeline/power_sim.py`). Within:ui across days comes from 010 Stage 1
(waves 1 to 7, daily, the same 40 prompts through the same DataForSEO settings, 3
waves drawn per simulated study); the per-prompt spread of the cross-arm overlap comes
from the pilot. Shifted to a planted true gap, 1,000 studies x 1,000 draws.

| True gap | ChatGPT pass, 95% CI | ChatGPT pass, 90% CI | Gemini pass, 90% CI |
|---|---|---|---|
| 0.000 | (pending) | (pending) | (pending) |
| 0.050 | | | |
| 0.075 | | | |
| 0.100 (false pass) | | | |

(Filled in before the freeze.)

**Lexicon protocol.** Start from 010's frozen v3 (sha256 `6084f47c…5cf5d`), which was
built partly from DataForSEO ChatGPT and Gemini answers to these 40 prompts. 009's
Haiku pass proposes brand names from all wave 1 answers; coverage uses the lexicon's
own matcher (sketch, Measures). If no arm has more than 2% of names unplaced, v3 is
used unchanged and its sha256 is recorded here. Otherwise it is extended under
`009/harness/lexicon_rules.md` and the two reviewer rules recorded in 011's lexicon
freeze (source-only mentions and retired products are dropped). A person reviews
flagged rows and rows matching five or more answers (STOP 2), and the sha256 is
recorded here before any confirmatory metric. Curation does not read arm labels.
Waves 2 and 3 candidates are checked against the same 2% limit before the model runs;
missing names bias the comparison toward equivalence (009, deviation 7).

## 6. Known traps for this design

- **The ChatGPT model is an inference, not a documented fact.** DataForSEO reports
  `gpt-6`, the family, not the tier. No OpenAI source found names the model for
  signed-out users. What OpenAI does say (checked 2026-11-06):
  - OpenAI's GPT-6 announcement and the developer forum post of 2026-10-07: paid
    plans use GPT-6 Sol, and "Free and Go use GPT-6 Luna", from 2026-10-08.
  - OpenAI's model release notes, 2026-10-29: an update to "GPT-6 in Chat" applies to
    Free and Go users and to people using ChatGPT without signing in, while Plus and
    Pro get it only on the model they fall back to after their GPT-6 limit. So OpenAI
    groups signed-out users with Free and Go, on a model other than the paid default.
  - OpenAI's models help page still lists GPT-5.6 Luna for Free and Go, which
    contradicts the release notes and looks out of date.

  The study therefore takes `gpt-6-luna`, the reading that fits all three and the
  `gpt-6` field. It is also the cheapest GPT-6 model, which makes it the likely one to
  serve users who pay nothing. If the UI runs another model, a gap is partly a model
  gap. The write-up states the inference and its sources.
- **Gemini Auto routing.** The free app may send a prompt to a larger model. 010 saw 1
  of 400 answers do so; the pilot saw none of 30. R8 excludes those answers.
- **DataForSEO is a proxy.** The UI references are a scraper's view of the logged-out
  or free UI, not a person's session.
- **Location.** `cg_ui`, `gm_ui` and the OpenAI arms are set to the US. The Gemini API
  has no location setting; its requests leave from this machine in the US. A
  scraper's exit node and the API's search location are not visible.
- **Across-day floor.** within:ui spans days while cross:arm|ui is same day, as in 009.
  Day-to-day drift lowers the floor and so shrinks the gap. That is the intended
  yardstick (how much the UI moves on its own), and the pilot's same-day floor is not
  comparable to it.
- **Different search depth.** `cg_api_low` searches about 4 times as much as
  `cg_api_plain`, and the UI's answers are about 3 times as long. A pass on brands
  would not mean the sources match. Domains are descriptive.
- **Gemini app markup.** The follow-up chips are stripped before extraction (Audit B);
  R6 keeps them.
- **Error answers.** The Gemini app has returned at least two error wordings. Both are
  matched; any new one found in Audit A is added to the rule, resubmitted if found the
  same day, else excluded and logged.
- **Pilot prompts.** 10 of the 40 prompts were in the pilot, which picked the arms.
  Their new answers are new runs, so the choice does not bias the test. R9 drops them.
- **A moving instrument.** Either UI can change between waves without notice, and the
  `gpt-6` field would not show a tier change. R3 drops each wave in turn.
- **Same prompts elsewhere.** 010's wave 11 runs the same 40 prompts through the same
  scraper on Nov 6. The studies do not share tasks or data.
- **Prices.** Costs are estimates at the list prices checked 2026-11-05.

## 7. Robustness checks

1. H_pos first; if it fails, stop.
2. H_pla reported for each primary arm.
3. R1: top-10 brands instead of all brands.
4. R2: RBO on brand order.
5. R3: drop one wave at a time.
6. R4: nothing censored. Unplaced Haiku names added to each answer's brand set, both
   sides.
7. R5: category-level cluster bootstrap.
8. R6: `gm_ui` with the follow-up chip markup kept.
9. R7: exclude answers with no search (UI answers included).
10. R8: exclude UI answers whose reported model is not `gpt-6` or `3.5 Flash-Lite`.
11. R9: exclude the 10 pilot prompts.
12. R10: exclude UI answers that needed a resubmission.

## 8. Deliverables and sequence

1. **STOP 1: Jim reviews this spec.** Approved 2026-11-06, with the §1 and §6 wording.
2. Wave driver (`harness/run_wave.py`) and analysis pipeline, built and dry-run on
   synthetic data before the freeze: planted equivalent and divergent arms are
   recovered, and the model exits non-zero when H_pos fails. Run on the pilot frame,
   the pipeline reproduces the pilot report's gaps. The power table above is filled in.
3. Freeze (two commits), record the hash and seed. Jim pushes.
4. Wave 1, Friday Nov 6. Lexicon candidates and the coverage check; if v3 needs
   extending, curation and **STOP 2: Jim reviews the lexicon**, which can run while
   waves 2 and 3 are collected. Freeze it before any metric.
5. Waves 2 (Sunday Nov 8) and 3 (Tuesday Nov 10).
6. Audit D (signed), model, robustness suite.
7. **STOP 3: results review.**
8. Only if approved: article, release, companion blog post (EN and DE), written to be
   read alongside 009 and 011.

## 9. Notes for the write-up

- Lead figure: gap to the UI per arm against the +/-0.10 band, for Claude (009, 011),
  ChatGPT and Gemini side by side, with each UI's own day-to-day overlap as its
  reference.
- State in plain words: the references are DataForSEO's view of the logged-out
  ChatGPT page and the free Gemini app. Logged-in, paid and Workspace users may get
  other models, and the Gemini caveat on paid and Workspace use goes in the body, not
  a footnote.
- State the `gpt-6-luna` inference and its sources (§6). Recheck the help page and
  release notes before publishing, in case OpenAI has since documented it.
- The leaked prompts are mentioned as a pilot finding only (one moved the API further
  from the UI; the other stopped Gemini from searching on 4 of 10 prompts). Their text
  is not released unless Jim Wrubel signs that off.
- Sample size phrased as "N answers evaluated (in this study)". Answers and search
  queries are never published.
- Publish the equivalence bound and the power table.

## Deviations from the frozen spec

(none yet)
