# 010: Is the AI shortlist stable when rank is not? (design sketch)

**Status:** superseded by `spec.md` (the evaluation said go, 2026-10-03).
Kept as the record of what was fixed before classification. Written
2026-10-03, before any answer was classified. This file fixes the exploration split, the metrics and
the go/no-go criteria for the initial evaluation; `spec.md` follows only if
the evaluation says the study is worth running.

## The question

Our earlier studies (002, its rank-stability follow-up, 005, 009) found that
mention position is not stable enough for a brand to claim "we rank first in
ChatGPT". But buyers doing B2B research do not act on position. They act on
the shortlist: the two to five vendors an answer recommends, which become the
demo calls. If the shortlist comes back the same across runs, position inside
it matters little.

Hypothesis: across repeated runs of the same prompt, a brand's recommendation
status (top choice, recommended with a "best for" use case, recommended,
cautioned against) repeats far more reliably than its exact position.

## Instrument

The Spyglasses recommendation judge, unchanged: `assessBrandMentions` logic in
`packages/core/src/services/mention-assessment-judge.ts` (spyglasses repo,
`MENTION_ASSESSMENT_VERSION` 2, model `gpt-5.6-luna`, reasoning effort none,
same system prompt, schema and post-processing). The runner records the
spyglasses commit and the judge file's sha256 and refuses to run if the file
changes mid-study. It stores the judge's raw output as well as the
post-processed result, so the "more than two top choices are demoted" rule can
be audited.

Brand identity comes from each source experiment's frozen, audited lexicon,
not from the judge's spellings. Lexicon brands found in an answer are passed
as the judge's `trackedPresent` brands (the setup of a property that tracks
every known brand in its category). A lexicon brand the judge leaves out is
"unclassified". Names the judge adds outside the lexicon are kept for
diagnostics only.

## Data (existing answers only; nothing new is collected)

| Dataset | Source | Platform | Category | Prompts | Runs per prompt | Dates |
|---|---|---|---|---|---|---|
| `chatgpt_consumer` | 002 + 003 + 005, `hum` arm | ChatGPT (`gpt-5-5`, DataForSEO) | headphones (consumer) | 143 | 17 (7 + 5 + 5) | Jul 16 to Aug 6 |
| `chatgpt_agency` | 002, 003 and 005 wave 1 only, `coffee` arm | ChatGPT (`gpt-5-5`, DataForSEO) | brand design agencies (B2B services) | 40 | 3 (1 + 1 + 1) | Jul 16, Jul 29, Aug 2 |
| `claude_b2b` | 009 | claude.ai (`ui_default`, `ui_think`) and API (`opus55_plain`) | 20 B2B software categories | 40 | 3 per arm | Sep 27 to Oct 1 |

The prompt texts are identical across 002, 003 and 005 (checked 2026-10-03:
143/143 and 40/40), so a prompt's runs span three weeks. Excluded: 003/005
synthetic arms (different prompt sources; can be added later), 008 (brand
knowledge prompts, not shortlist questions), the other 009 API arms (not what
buyers see, and not what Spyglasses tracks after the switch to Opus).

There is no ChatGPT or Gemini B2B software dataset. That gap is the main
argument for a new collection if this evaluation says go.

## Exploration split (keeps a confirmatory holdout)

Classifying the answers creates the outcome variable for the first time. To
keep a confirmatory test possible on existing data, only one third of the
prompts are classified now; the rest stay unclassified until a spec is frozen.

- Seed `20261003`. Each unit is ranked by `sha256("20261003:" + unit)`; the
  lowest-ranked units go to exploration.
- `chatgpt_consumer`: unit = prompt; 48 of 143 prompts.
- `chatgpt_agency`: unit = prompt; 13 of 40 prompts.
- `claude_b2b`: unit = category (both prompts of a category move together, so
  the between-prompt baseline stays inside one market); 7 of 20 categories,
  14 prompts.

The assignment is written to `split.csv` (ids only) and committed before the
judge runs.

## Metrics (all on lexicon brands)

Per answer: mentioned set **M** (lexicon matches, first-mention order, as in
the source studies); recommended set **R** (top choice or one of many); top
choice **T**; best-for picks **BF** (one of many with at least one best-for
phrase); cautioned **C**. Position statuses for comparison: first-mentioned
brand **P1**; exact (brand, position) pairs **Pk**, the "we rank #k" claim;
and **Rpos**, the first |R| brands by position, a size-matched position-only
shortlist.

**Retention** of a status S over pairs of runs of the same prompt in the same
arm: the share of brand appearances in S in one run that keep S in the other,
pooled over pairs (equivalently, pooled Dice: 2·Σ|Sa∩Sb| / Σ(|Sa|+|Sb|)).
Read it as: "if a brand had this status in one run, how often does it have it
in another run of the same prompt?" Pair Jaccard is reported alongside for
continuity with earlier studies.

Baseline: the same metric between different prompts of the same category on
the same day (the program's usual positive control).

Inference: prompt-level cluster bootstrap, 2,000 resamples, 90% percentile
intervals. Everything in the initial evaluation is exploratory.

Also reported: answers with at least one top choice; category mix; raw top
choices demoted by the two-top-choice cap; unclassified rate; evidence
verification rate; retention by days between runs (`chatgpt_consumer`, 0 to
21 days); shortlist agreement between claude.ai and the Opus API arm
(`claude_b2b`).

## Go/no-go criteria for the initial evaluation (fixed before classifying)

- **G1, instrument works.** The judge returns a result for at least 98% of
  answers; at least 90% of evidence quotes verify; at most 5% of lexicon
  brand mentions are unclassified.
- **G2, the shortlist is not just the mention list.** In at least one
  dataset, at least 10% of lexicon brand mentions are generic mentions or
  cautions, or R differs from M in at least 25% of answers. If R equals M,
  shortlist stability is the brand-overlap result we already published.
- **G3, top choices exist.** In at least one dataset, at least 25% of answers
  carry a top choice. Below that, top-choice stability cannot be studied with
  the production judge as it stands.
- **G4, the story.** Retention of R minus retention of Pk is at least 0.10
  with an interval above 0 in at least one dataset, and R's within-prompt
  retention beats the between-prompt baseline by at least 0.10.

Pursue the study if G1 to G3 pass. G4 decides the headline: if it fails, the
finding is "the shortlist is no more stable than position", which is still
reportable but a different article.

## Owed after the evaluation

STOP for Jim: go/no-go, then (if go) the confirmatory spec on the held-out
two thirds, and whether to add a new B2B collection on ChatGPT and Gemini over
several weeks.
