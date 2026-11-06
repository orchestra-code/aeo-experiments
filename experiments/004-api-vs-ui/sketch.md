# 004: Can the API stand in for the ChatGPT and Gemini UI? (design sketch)

**Status:** sketch, NOT a spec, nothing frozen as a confirmatory study. Rewritten
2026-11-05, before any study prompt was run through an API arm. It fixes the
hypothesis and the go/no-go criteria for a short feasibility run. `spec.md`
follows only if the run says a full study is worth doing.

This replaces the July 2026 sketch (headphone prompts from 003, still in git
history). The question is the same. The frame now matches experiments 009 and
011, so the three studies can be read side by side.

## The question

Experiment 009 found that, for B2B software research, Opus 5.5 through the API
with no system prompt names the same brands as a person in claude.ai (gap +0.067,
90% CI +0.034 to +0.099, inside the +/-0.10 band). Experiment 011 asks the same
of Claude Code. Neither says anything about ChatGPT or Gemini.

Tracking tools measure ChatGPT and Gemini in one of two ways: by scraping the
consumer UI, or by calling the vendor's API with a search tool turned on. This
study measures how far apart those two instruments land, on the same model, and
how much of the gap a leaked UI system prompt closes.

**Hypothesis.** For B2B software research, on the same model, an API answer with
search turned on names the same brands as the logged-out or free consumer UI, as
DataForSEO's LLM scraper collects it: the brand-set Jaccard gap is 0 within
+/-0.10. Tested separately for ChatGPT and for Gemini.

**What we expect.** A positive gap, larger than 009's. The API search tools are
not the UI's search backends (ChatGPT's UI has its own `slow` and `fast` engines,
product and business lookups; the Gemini app's grounding is not the API's
`google_search` tool), and neither vendor publishes the UI's system prompt.

## Platform eligibility

Jim Wrubel's rule: a platform is in only if the API offers the model the UI uses,
and we can tell which model that is.

**Gemini: in, free tier only.**

- Since 2026-10-09, Gemini personal accounts without a subscription get Flash-Lite
  only. The picker defaults to "Auto", which sends most prompts to Flash-Lite and
  may route some to a larger model (Gemini Apps Help, "Changes to Gemini model
  access and limits").
- DataForSEO's Gemini scraper reports a model on every answer. On 009's 40 B2B
  prompts, experiment 010 recorded "3.5 Flash-Lite" on 399 of 400 answers and
  "3.6 Flash" on one, which fits Auto routing.
- The API offers `gemini-3.5-flash-lite` (checked against this repo's key,
  2026-11-05).
- Paid tiers (AI Plus, AI Pro, AI Ultra, Workspace) are out. The paid app shows a
  picker label but not which model wrote a given answer, so it fails the rule.

**ChatGPT: in, logged-out UI.**

- DataForSEO scrapes the logged-out page (`check_url` is `chatgpt.com/?prompt=`).
  Its `model` field reads `gpt-6`, which names the family but not the tier.
- OpenAI's Oct 7, 2026 release note says Free and Go use GPT-6 Luna, and paid
  plans use GPT-6 Sol. OpenAI's models help page lists GPT-5.6 Luna for Free and
  Go instead. Logged-out users have never had Sol.
- This study takes `gpt-6-luna` as the logged-out model (Jim Wrubel's call, and
  the reading that fits a `gpt-6` field). The API offers it. No GPT-5.6 Luna arm
  is run. That choice is recorded as a measurement assumption, not a finding.

## Arms

All arms get the 40 prompt texts of 009 byte for byte (this sketch's run uses 10
of them), with no follow-up turn and no personal context.

| Arm | Instrument | Model | System prompt |
|---|---|---|---|
| `cg_ui` | DataForSEO ChatGPT LLM scraper, `force_web_search: true`, US, English | logged-out ChatGPT (`gpt-6` field) | ChatGPT's own |
| `cg_api_plain` | OpenAI Responses API, `web_search` tool, `user_location` country US | `gpt-6-luna`, default reasoning | none |
| `cg_api_low` | as `cg_api_plain`, lowest reasoning setting the API accepts | `gpt-6-luna` | none |
| `cg_api_leak` | as `cg_api_plain` | `gpt-6-luna`, default reasoning | adapted `web_tool.txt` |
| `gm_ui` | DataForSEO Gemini LLM scraper, US, English (`force_web_search` is not accepted) | free tier, Auto (model reported per answer) | Gemini's own |
| `gm_api_plain` | Gemini API, `google_search` grounding tool | `gemini-3.5-flash-lite`, default thinking | none |
| `gm_api_leak` | as `gm_api_plain` | `gemini-3.5-flash-lite` | adapted Gemini web app prompt |

`cg_api_low` exists because the leaked ChatGPT prompt says most users sit in the
default "Instant" configuration, and the API's default reasoning may not match it.

The UI arms are the reference. The `cg_ui` and `gm_ui` settings are 010's, so this
study's UI answers are collected the way 010 collected them.

### The leaked prompts

Both come from public repositories. Their provenance cannot be checked, and
neither vendor confirms them.

- **ChatGPT:** `web_tool.txt` from `tomek-gpu/system-prompts`, added 2026-10-09
  (34 KB). It is the web tool section of the current ChatGPT prompt: when to
  search, how to cite sources, the product recommendation and shopping policy, and
  Reddit guidance. No GPT-6 Chat system prompt has leaked. The newest is
  `OpenAI/gpt-5.6-sol.md` in `asgeirtj/system_prompts_leaks` (2026-08-22, paid
  tier, other model), which is not used.
- **Gemini:** `Google/gemini-3.8-flash.md` in `asgeirtj/system_prompts_leaks`
  (2026-09-13). Every Gemini web app leak in that repository is labeled "Paid
  tier", and none is for Flash-Lite. So the closest match borrows a paid-tier
  prompt written for another model. That is a weaker approximation than the
  ChatGPT one, and the write-up says so.

**Adaptation rule (fixed now, applied by script, file sha256 recorded):**

1. Keep the guidance on when to search, how to use results, how to cite sources,
   how to format answers, and product recommendations.
2. Drop tool syntax the API cannot execute (ChatGPT's `slow|`, `fast|`,
   `product|`, `business|` and `genui_*` records; Gemini's tool JSON
   definitions), plus image generation, widgets, memory and saved-information
   placeholders.
3. Where kept text names a dropped tool, replace the name with "the web search
   tool". No other wording changes.
4. Prepend the vendor's identity line from the same leak with the current date.
   For Gemini, drop the "Capabilities" block rather than rewrite its tier or
   model.

The adapted files and the leak sources stay in gitignored `data/raw/`. They are
released only if Jim Wrubel signs that off, as with 009's trimmed prompt.

## Measures

The same as 009 and 011, so results line up.

- **Brands:** 009's extraction (`pipeline/brands.py`, labelled sources blocks
  stripped) with 010's frozen lexicon v3 (sha256 `6084f47c...`), which was built
  partly from DataForSEO ChatGPT and Gemini answers to these 40 prompts. Coverage
  uses the lexicon's own matcher (a Haiku name counts as covered if a lexicon alias
  is found inside it), the rule 011 settled on in its deviation 1, stated here
  before any data.
- **Brand gap:** mean(within:ui) minus mean(cross:arm|ui). Positive means the arm
  is further from the UI than the UI is from itself. Prompt-level cluster
  bootstrap, 90% interval.
- **Cited and evaluated domains, descriptive:** DataForSEO `sources`; OpenAI
  `url_citation` annotations and `web_search_call` sources; Gemini
  `groundingMetadata` chunks. Gemini API chunk URIs are redirect links, so the
  domain comes from the chunk title or a resolved redirect, as the run finds
  workable. The instruments expose different fields, so domain results stay
  descriptive.
- **Search behavior:** searches or fan-out queries per answer, and answers with no
  search.
- **Cost:** API cost per answer from token and tool-call counts at list price,
  labeled as estimates (009's rule).

## Feasibility run

10 prompts (the 10 categories of 009's pilot: `b2b_01`, `06`, `09`, `14`, `17`,
`22`, `25`, `30`, `33`, `38`), all on one day:

- `cg_ui` and `gm_ui`: 3 runs each, submitted in three rounds spaced about an hour
  apart, so the within-UI floor exists on the day. 60 tasks.
- API arms: 1 run each, interleaved with the UI rounds. 50 answers.

Same-day UI repeats agree more than 009's across-day repeats, which makes the gap
here conservative (larger). These answers are pilot data and never enter a
confirmatory analysis. Cost cap for the run: $10.

## Go/no-go criteria (fixed before any study prompt runs)

Judged per platform. ChatGPT and Gemini can pass or fail independently.

- **G1, clean instrument.** Per arm, at least 9 of 10 (API) or 28 of 30 (UI) tasks
  return an answer. Every API response reports the pinned model id. At least 28
  of 30 `cg_ui` answers report `gpt-6`, and at least 27 of 30 `gm_ui` answers
  report 3.5 Flash-Lite (the rest are reported by model).
- **G2, they are answers.** Per arm, at least 90% are buyer-facing answers, not
  only a question back. At least 70% of API answers run a search. No leak-arm
  answer shows dropped tool syntax (`slow|`, `genui`, raw tool JSON). If one does,
  the adaptation failed.
- **G3, measurable.** Per arm, at least 90% of the brand names a Haiku pass finds
  are covered by lexicon v3. Domains parse in at least 80% of answers that
  searched.
- **G4, fidelity signal.** At least one API arm that passed G1 to G3 has a brand
  gap of at most 0.20 (point estimate). This is a screen, not a test. Ten prompts
  cannot certify anything.

**Cost is reported, not gated,** with a projection for the full study.

### Reading the outcome

- G1 to G3 fail: fix the harness and rerun. A failure here is about the
  instrument.
- G4 fails for every arm of a platform: the API is not a plausible stand-in for
  that UI on this evidence. Whether a confirmatory study of the gap is still worth
  publishing is decided at the stop below.
- G4 passes: draft `spec.md` with at most 2 API arms per platform. Take the arm
  with the smallest gap. Prefer a `plain` arm if it is within 0.03 of the smallest,
  since it needs no leaked prompt. Confirmatory answers are all new, so picking
  arms here does not bias the test.

## STOP

After this run, STOP for Jim Wrubel's go/no-go. Nothing below starts without it.

## What a full study would look like (not frozen)

40 prompts x 3 non-consecutive days, the same as 009. Each day: the UI arm and up
to 2 API arms per platform, interleaved. Primary, per platform: brand-set Jaccard
gap, TOST +/-0.10, Holm across that platform's API arms. Secondary: brand order
(RBO), cited and evaluated domains, search depth, the leak's effect (leak minus
plain). Positive and placebo controls as in 009. Audit D on a platform-blind
sample. Model-change check (Audit F) on every wave: a change of the reported UI
model mid-study is a deviation and gets a per-model refit.

**Read alongside 009 and 011.** One figure, one row per platform, the same metric
and band. The references differ, and the figure says so: claude.ai is a logged-in
Pro account collected by hand, while the ChatGPT and Gemini references are
logged-out or free-tier scrapes. The rows sit side by side. They are not pooled
into one estimate.

## What this does not settle

- **Logged-in and paid use.** DataForSEO collects logged-out ChatGPT and free-tier
  Gemini. Paid ChatGPT (GPT-6 Sol) and paid Gemini (3.8 Flash, Gemini 4 Argon) are
  follow-on studies, on accounts Jim Wrubel already has.
- **Who actually uses Gemini.** We suspect, and cannot confirm, that most Gemini
  use for work questions like these prompts comes from paid plans, in particular
  Workspace business accounts that include Gemini, and not from free personal
  accounts. Google publishes no split. What it has said: the Gemini app has 1
  billion users (Q3 2026 call, Oct 29); "more than 100 million seats for knowledge
  work" across all its AI services (same call); more than 8 million paid Gemini
  Enterprise seats by early 2026; nearly 90% of the Fortune 100 use Gemini
  Enterprise. The Oct 9 Flash-Lite limit covers personal accounts only, and
  Gemini Enterprise's default stayed 3.8 Flash. If the suspicion holds, a
  free-tier result describes a minority of B2B use, and the write-up leads with
  that.
- **The ChatGPT model.** `gpt-6-luna` is an assumption the UI does not report.
- **The leaks' effect.** `cg_api_leak` and `gm_api_leak` measure what these texts
  do through the API. They do not measure the real UI prompt, whose current
  version, completeness and tier are unknown.
- **Search location.** DataForSEO runs from a US location. The OpenAI arms set
  country US. The Gemini API's grounding tool has no location setting. B2B
  software prompts are expected to be insensitive to location, as in 011, and this
  is not tested.
- **Personalization.** None of the instruments has an account history.

## Housekeeping

- Experiment 010 collects on these prompts through wave 11 (2026-11-06). Its Stage
  2 answers stay sealed until its own analysis. Nothing here reads them.
- DataForSEO's async task API only, with the ledger, never `tasks_ready` (it is
  shared with another poller).
- Keys come from this repo's `.env.local` only. `DATAFORSEO_API_KEY` must be added
  there before the run.

## Clarifications and deviations

Logged in order. The criteria above are unchanged, as committed in `640edc7`.

1. **ChatGPT identity line (2026-11-05, before any study prompt ran).** Rule 4 of
   the adaptation says to prepend the identity line from the same leak, and
   `web_tool.txt` has none. The adapted ChatGPT prompt opens with the generic
   sentence every ChatGPT leak starts with, without a model clause ("You are
   ChatGPT, a large language model trained by OpenAI."), then "Current date:" and
   the run date. Naming a model would borrow from a leak this study does not use.
2. **Gemini leak context (2026-11-05, before any study prompt ran).** The leak's
   context block carries the leaker's own location. It is per-user context, like
   the saved-information placeholder, so rule 2 drops it. Keeping it would point
   search outside the US, where the UI arm runs. The date is set to the run date and
   the time of day is kept as written.
3. **Line-level adaptation (2026-11-05, before any study prompt ran).** Rule 2 is
   applied line by line where a kept section mentions dropped tools: lines on
   choosing between ChatGPT's two search engines, its recency field, ops other than
   search, the reference-id format and a pointer to a missing UI spec are dropped,
   as are lines whose only content is combining two dropped tools. Rule 3 is then
   applied literally, including where it reads oddly; those lines concern visual
   and safety topics that B2B software prompts do not touch. Gemini's follow-up
   rules are kept; if they produce questions back, G2 shows it. The exact rules are
   in `harness/leaks.py`, and the adapted files' sha256s in the gitignored manifest.
4. **UI error answers (2026-11-05, before any study prompt ran).** A DataForSEO
   answer that is the app's own error message counts as no answer and is resubmitted
   in the same round, at most 3 submissions per prompt and round, as 010's driver
   did. G1 counts final answers; the report shows first-try failures.
5. **Gemini UI search depth (2026-11-05, before any study prompt ran).** DataForSEO's
   Gemini result has no fan-out queries, so search depth for `gm_ui` is not
   observable. "Searched" means sources were reported.
6. **G2 flags (2026-11-05, before any study prompt ran).** "Buyer-facing" is screened
   by rule: no lexicon brand, a short answer that asks a question, or an error
   message. A person reads every flag, as in 011, and cleared ones are recorded in
   the report code.
7. **Second Gemini error wording (2026-11-05, after the pilot ran; a deviation).**
   Two pilot `gm_ui` answers in round 1 were a different Gemini app error ("I
   encountered an error ..."), which the error rule in 4 did not match, so they were
   neither resubmitted nor treated as missing. Reading the two G2 flags found them.
   The rule now matches that wording too, G1 counts only usable answers (28 of 30,
   need 28), and the brand gap leaves error answers out instead of scoring them as
   empty brand sets. That changed the Gemini screen from +0.050 to +0.101 for
   `gm_api_plain`; the verdicts did not change. In the full study these answers are
   resubmitted as in 4.
8. **Gemini UI follow-up markup (2026-11-05, after the pilot ran).** 24 of 30 `gm_ui`
   answers end with the web app's follow-up chip markup (the components the leaked
   prompt describes), which the scrape returns as raw tags. Brands in those chips
   are counted as answer brands. In the pilot, removing the markup changed no
   answer's brand set. The spec decides whether to strip it before extraction.
