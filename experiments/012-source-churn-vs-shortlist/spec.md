# When AI's sources change, its shortlist holds: study spec

**Status:** DRAFT, not frozen. Do not collect.
**Frozen commit:** none yet
**Frozen date / seed:** none yet / 20261103 (proposed)
**Experiment slug:** `012-source-churn-vs-shortlist`
**Start condition:** after experiment 010 Stage 2, experiment 011 and the second part of 009 are finished, and after Jim approves this spec.

> Freeze rule: §4 (hypotheses) and §5 (model and decision rules) are fixed before
> wave 1 is collected. Frozen with the spec: the prompt panels, the collection
> schedule, the arm registry, the judge pin and the analysis code. The domain map
> and the lexicon extension are instrument data, built from the pilot and frozen
> before any confirmatory metric is computed. Any later change is logged under
> Deviations.

---

## A. Pre-freeze findings (2026-11-03)

All exploratory, from experiment 010 Stage 1 answers. Tables:
`results/exploration.md`. Code: `exploration/explore.py`. 010's Stage 2 waves were
not read. The 40 B2B prompts behind these findings are therefore not used for the
confirmatory test (§ Data).

| Share repeated between two runs (pooled Dice) | Shortlist | All cited | Third party cited | Third party retrieved |
|---|---|---|---|---|
| ChatGPT | 0.81 | 0.60 | 0.19 | 0.36 |
| Claude API | 0.78 | 0.52 | 0.46 | 0.53 |
| claude.ai | 0.75 | 0.25 | 0.22 | 0.30 |
| Gemini | 0.64 | 0.25 | 0.24 | no data |

What this changes in the design:

1. **Vendor echo.** 83% of ChatGPT's cited domains are vendor sites (43%, 44% and
   30% on the Claude API, Gemini and claude.ai), and 91% of ChatGPT's belong to a
   vendor named in the same answer. All-domain overlap partly restates the
   shortlist. Tests therefore use third-party sites.
2. **List length.** Thinning the shortlist at random to each answer's third-party
   count takes it to 0.20 on ChatGPT and 0.43 on the Claude API, level with cited
   third-party overlap. Comparing against short citation lists is not size-safe.
   The primary test uses retrieved lists, which are about as long as the shortlist.
3. **Weak coupling.** Within a prompt, the 10th to 90th percentile change in
   third-party overlap moves shortlist Jaccard by -0.01 to +0.06. Pairs sharing no
   third-party site differ by -0.02 to -0.07.
4. **Observation cannot explain why.** A stable shortlist fits model priors and
   also interchangeable sources, which imply opposite advice. Only changing the
   sources can separate them. This is the reason for a new study.
5. **Instrument error found during exploration.** Out-of-lexicon brands are stored
   with an `x:` prefix, which broke exact name matching, and alias-mapped brands
   were missed. Automatic domain labels needed 41 corrections out of 1,076 domains.
   Labels need a person's sign-off here (Audit D).

## 0. One-paragraph summary

We test whether the AI shortlist depends on the sources behind it, in three parts.
Part A repeats the observation on new prompts and adds same-day repeats. Part B compares search on with search off. Part C gives Claude controlled
sets of pages, including sets with a vendor's name removed, and measures what changes.
We expect sources to churn more than the shortlist (A), a shortlist that mostly
survives without search (B), and a small but real drop when a vendor's name is
removed from the pages (C).

## 1. The claim we can and cannot make

**What this design measures:** how much the set of vendors AI recommends changes when
its sources change on their own (A), are removed (B), or are swapped or edited by us (C).

**What this design does NOT measure:** long-run influence. A model's prior knowledge
was itself formed from the web, so a shortlist that survives without search does not
mean past coverage is worthless. Parts B and C measure the effect of sources at answer
time only. They also say nothing about buyer behavior.

**Defensible claim, if the results hold:** "At answer time, changing the sources AI sees
moves its shortlist by X, while removing a vendor from those sources lowers that vendor's
chance of being shortlisted by Y."

**Indefensible claim:** "Sources do not matter", "earned media does not work" or "AI
ignores what it reads."

### Mechanistic prior

For well-known B2B categories, models hold strong priors from training data, and search
results list many of the same market leaders. So we expect the shortlist to depend less
on any one page than the citation list does. We expect the dependence to be larger for
lesser-known vendors, which have weaker priors, and that is the most useful practical
question here (H6).

## Data, arms and collection

**Panels.**

- `b2b_new`: 40 new prompts from 009's generator (`harness/make_prompts.py`), same 20
  categories x 2 intents, new seed, no overlap with the 40 prompts used in exploration.
  Primary.
- `consumer`: 40 human headphone prompts sampled by seed from 002's panel, for
  comparability with consumer-based reports. Generalization only. Prompt text stays
  unpublished.

**Part A, observation.** Schedule: 6 runs over 3 days, at about 09:00 and 21:00 Eastern,
which gives same-day and next-day pairs.

| Platform | Route | Cited list | Retrieved list |
|---|---|---|---|
| ChatGPT | DataForSEO task API, as in 010 | `sources[]` | `search_results[]` (may be unread) |
| Gemini | DataForSEO task API, as in 010 | `sources[]` | none |
| Claude | Batches API, `claude-opus-5-5`, web search tool, as in 010 | `cited_urls` | `evaluated_urls` |

Each route is an API or scraper path. Claude here is not its consumer app. Perplexity is out
of scope for this study (Jim, 2026-11-03).

**Part B, search on vs off.** `b2b_new`, 6 runs per arm on Part A's schedule. Claude's search-on arm is Part A's Claude arm.

- Claude: `claude-opus-5-5` with and without the web search tool. Effort fixed and
  stated. All other parameters identical.
- ChatGPT: OpenAI API with and without its web search tool, from 008's collector. No
  consumer route offers search off, so this arm describes the API.

Arms are run in the same batch and day. Answers with search off that claim to have
searched are flagged (Audit A).

**Part C, controlled sources.** Claude API only. 30 `b2b_new` prompts, 4 runs per arm,
batched. Citations on, via `document` blocks with `citations: {enabled: true}`, no search
tool. Effort stays fixed. Each prompt's two document sets come from Part A: pick its two
Claude runs with the lowest third-party overlap, then fetch up to 10 pages cited or
retrieved in each.

| Arm | Documents | Purpose |
|---|---|---|
| `none` | no documents | prior only |
| `set_a` | pages from run A | baseline |
| `set_b` | pages from run B | swapped sources |
| `set_a_redacted` | set A with one target vendor's name and domain replaced by a neutral label, and the sentences naming it removed | direct effect of being named |

Target vendors: one per prompt, drawn by seed, stratified across prompts into a
well-known group (in the `none` arm's shortlist in at least 3 of 4 runs) and a lesser-known
group (named in set A, in the `none` shortlist in at most 1 of 4). The `none` arm therefore
runs first, and targets are fixed before any other Part C arm.

Fetched text stays in gitignored `data/raw` and is never released. Fetching starts with
plain HTTP. Firecrawl is the fallback, capped at 10,000 credits (Jim, 2026-11-03). Production
draws on the same credits, so the run logs its spend. Part C needs at most 600 pages (30 prompts x
2 sets x 10 pages).

**Budget, estimates from 010 and 011 to be replaced after the pilot.**

| Item | Calls | Estimate |
|---|---|---|
| Part A, DataForSEO | 960 | $2.30 |
| Part A, Claude | 480 | $35 |
| Part B, Claude search off (on arm reuses Part A) | 240 | $12 |
| Part B, OpenAI, both arms | 480 | measure in pilot |
| Part C, Firecrawl fallback | up to 600 pages | hard cap 10,000 credits |
| Part C, Claude | 480 | $50 |
| Judge, including the 010 bridge | about 3,000 | $3 |
| Proposed hard cap | | $175 |

## 2. Data-quality audits (run before the model)

- **Audit A, refusals and empty results.** 010's rules. A search-on answer with no search,
  and a search-off answer claiming a search, are flagged and reported by arm.
- **Audit B, what citation fields mean.** Quote each route's parsing code. Confirm whether
  cited lists match in-text links (0.97 Jaccard on ChatGPT and Gemini in exploration).
  Remove non-source links, such as Gemini shopping cards that link to `google.com/search`.
- **Audit C, independence.** Prompts are clusters. Report repeated domains across prompts.
- **Audit D, domain map.** Build it from pilot answers, then a person signs off on labels.
  Vendor means a company named as a brand in answers in the same category. Precision and
  recall on 100 appearance-weighted domains, held back and blind, must reach 0.90 before
  any metric is computed.
- **Audit E, judge repeatability.** 10% of answers re-judged, as in 010.
- **Audit F, model changes.** Reported model per answer. A mid-study change means analyzing
  each model separately, as in 010.
- **Audit G, redaction.** Target vendor's names and aliases must be absent from all
  `set_a_redacted` documents, checked by rule. A sample of 30 is read by a person for
  leftover clues.
- **Audit H, fetch coverage.** Share of target pages fetched by arm. Part C needs at least
  70% for a prompt to stay in, and sets A and B must be within 2 documents of each other.

## 3. Data schema

One row per answer.

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| prompt code, category, intent | string | panel | yes | no prompt text for `consumer` |
| platform, arm, wave, run time, model | mixed | ledger | yes | |
| shortlist vendors | list | judge + lexicon | codes only | reuse 010's codes |
| cited and retrieved domain counts, by class | int | responses | yes | |
| cited and retrieved domains, URLs | list | responses | never | matches 010 |
| fetched page text, documents | text | Part C | never | |
| search counts | int | responses | yes | |

### Derived variables

The shortlist set `R` (010 §3), third-party sets, and pooled Dice retention. Jaccard is
reported alongside it for outside comparisons.

## 4. Pre-registered hypotheses

### Primary family (Holm)

- **H1, sources change more than the shortlist.** `R` retention minus retrieved third-party
  retention exceeds 0.10 within prompt, on `b2b_new`, for ChatGPT and the Claude API.
  Two tests.
- **H3, the shortlist without search.** Claude API: retention between two search-on answers
  minus retention between a search-on and a search-off answer. Tested against the ±0.10
  band, in both directions.
- **H5, swapped sources.** Part C: retention between `set_a` runs minus retention between
  `set_a` and `set_b` runs, tested against the ±0.10 band.
- **H6, being named matters.** Part C: the target vendor's shortlist rate in `set_a` minus
  `set_a_redacted`. One-sided, greater than 0, on all targets.

### Secondary (no multiplicity correction)

- **H2, weak coupling.** Within a prompt, no-shared minus shared third-party Jaccard,
  within ±0.10, on each platform.
- **H3b.** H3 on the OpenAI API.
- **H6b.** H6 is larger for lesser-known targets than well-known ones.
- **H7, time gap.** Same-day minus next-day source retention, within ±0.05, by platform.
- **H8, prior share.** The share of `set_a` shortlist appearances also in the same prompt's
  `none` shortlist. Descriptive, with interval.
- **H9, source support.** The share of `set_a` shortlist vendors not named in any supplied
  document. Descriptive. Because we know exactly what the model saw, this is a direct
  measure of knowledge from outside the documents.

### Controls

- **H_pos, positive control.** Within-prompt `R` retention minus cross-category retention is
  at least 0.10 with an interval above 0, on each platform. Also for third-party cited sites.
  If it fails, the study stops.
- **H_pos_C, manipulation check.** Citations in `set_a` point to supplied documents in at
  least 80% of cases, and `set_a` and `set_b` citation overlap is below 0.30. If it fails,
  Part C stops.
- **H_pla, placebo.** The H1 gap on two random prompt halves, drawn within intent, within
  ±0.10, as in 010.

## 5. Model and decision rule

**Model:** nonparametric, as in 010. Pooled Dice retention, prompt-level cluster bootstrap,
2,000 draws, seed fixed at freeze, 90% percentile intervals, contrasts draw by draw. H6 uses
the same bootstrap over target vendors, clustered by prompt.

**SESOI:** ±0.10 on retention, as in 010. It equals about 1 vendor in 10, the smallest change
that would alter a shortlist claim. H6's smallest effect of interest is 0.10 in shortlist rate.

**Decision rule:**

| Result | Conclusion |
|---|---|
| Interval inside the band | Practically equivalent: publishable null |
| Interval excludes 0, extends beyond the band | Real effect: report it, revise the thesis |
| Interval excludes 0, inside the band | Detectable but negligible |
| Interval wider than the band and includes 0 | Inconclusive: do not claim a null |

**What each outcome means.**

| H3 | H5 | H6 | Reading |
|---|---|---|---|
| Null | Null | Null | Priors dominate at answer time, for these categories |
| Real | Null | Real | Sources matter, and different pages say similar things |
| Real | Real | Real | Particular sources matter, and exploration was misleading |
| Null | Null | Real | Priors dominate overall, but being named still helps a given vendor |

**Power.** From exploration, on 40 prompts: the 90% half-width is 0.036 to 0.040 at 7 runs and
0.049 at 3 runs on the H1 contrast, and about 0.03 on a stand-in arm contrast at 3 runs per
arm. Parts A and B are adequately sized against ±0.10. Part C is the risk: 20 prompts gave a
half-width of 0.056 to 0.072 at 7 runs, so 30 prompts at 4 runs is expected to be near 0.07 and
leaves little room. **Before freeze,** run a synthetic power simulation for Part C and for H6
at target level, with the pipeline returning null on a zero effect and real on an effect above
the SESOI. Increase prompts or runs if the simulation calls for it.

## 6. Known traps for this design

- **Prior contamination.** The model's knowledge comes from the web, so search off is not
  "no sources ever".
- **Selection in search.** In observational data, the model chooses when to search. Part B
  assigns it.
- **Replay is not retrieval.** Part C supplies pages in a way no product does. Its results
  may not transfer. Part B and Part A anchor the comparison, and we report `set_a` against
  the matching search-on answers.
- **Redaction is a blunt edit.** Removing sentences changes more than a name, and pages can
  read oddly. Audit G limits this. Removing only the name, as a second redaction form, is a
  robustness check.
- **Echo in reverse.** A vendor site might be cited because it was named, or named because
  it was retrieved. H1 and H2 use third-party sets to reduce this, but do not resolve it.
- **Bounded by list length.** All comparisons against short lists need the size-matched check.
- **Concentrated markets.** Well-known categories favor our hypothesis. Report by category
  and by the between-prompt baseline.
- **Fresh prompts in old categories.** The new prompts share categories with exploration, so
  this tests new prompts in familiar markets, not new markets.

## 7. Robustness checks

1. Positive controls first. If they fail, stop.
2. Placebo must be null.
3. Size-matched shortlist on every H1 comparison.
4. Chance-corrected retention, using the between-prompt baseline.
5. Vendor labels: reviewed map against automatic.
6. All named brands instead of lexicon brands.
7. Only pairs where both answers cite something.
8. Per-category and per-intent refits. Watch power.
9. Per-model refits, if Audit F finds a change.
10. Mention set instead of `R`, in case of a judge change.

## 8. Deliverables and sequence

1. **Backlog clears.** 010 Stage 2, 011, 009 part 2.
2. **Pilot** of 5 prompts on all routes and arms: OpenAI search-off,
   real costs, fetch success. STOP for Jim's go/no-go, with the budget updated.
3. **Freeze** after the power simulation and pilot. Two commits, per `docs/workflow.md`.
4. **Part A** collection, then build and sign the domain map (Audit D). STOP.
5. **Part B** alongside Part A, then **Part C** after its document sets are built. STOP before
   Part C spending.
6. **Pipeline and audits**, then results. STOP for Jim's review.
7. **Article, dataset through the release gate, companion blog post.**

## 9. Notes for the write-up

- Lead figure: shortlist retention by arm, from search on through search off, swapped and
  redacted.
- Framing: what changes when sources change. The practical result is H6b: whether lesser-known
  vendors depend more on being named.
- Sample size is reported as "N citations evaluated (in this study)".
- Publish the equivalence bounds. Keep the point that search off still reflects past web content.
- The research note `ai-sources-vs-shortlist` is exploratory and cites this spec. Update it with
  a link when results publish.

## Decisions (Jim, 2026-11-03)

1. **OpenAI API arm:** included in Part B. Its result stays secondary (H3b), and it describes the
   API, not ChatGPT.
2. **Firecrawl:** allowed as Part C's fallback, capped at 10,000 credits.
3. **Perplexity:** not included.
4. **Judge:** pin the production judge current at freeze in a new `harness/judge_pin.json`, recording
   its commit, model, reasoning effort and file hashes. Do not reuse 010's pin (`gpt-5.6-luna`), since
   production has moved on. Re-judge a seeded 10% sample of 010 Stage 1 answers with the new pin and
   report agreement with the old labels. Every 012 answer uses the one pin, so 012's own comparisons
   do not depend on the bridge. If shortlist membership agrees on under 90% of the vendors in the
   sample, comparisons with 010 are reported as not directly comparable.

## Deviations from the frozen spec

None yet. The spec is not frozen.
