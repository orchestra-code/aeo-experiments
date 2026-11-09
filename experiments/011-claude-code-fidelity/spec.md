# An unattended Claude Code run names the same brands as a person in claude.ai: study spec

**Status:** FROZEN
**Frozen commit:** `14fa495`
**Frozen date / seed:** 2026-11-03 / 20261103
**Experiment slug:** `011-claude-code-fidelity`

> Freeze rule: §4 (hypotheses) and §5 (model and decision rules) are fixed before
> wave 1 is collected. Frozen with the spec: the prompt panel (009's 40 prompts,
> public), the arm registry (`harness/collect_cc.py`), the scheduled-task prompt, the
> pinned Claude Code binary (sha256 in `data/raw/bin/`) and the analysis code. The
> brand lexicon is instrument data, not a hypothesis: it is extended from wave 1
> answers and frozen before any confirmatory metric is computed (§5). Any later
> change is logged under Deviations.

---

## A. Pre-freeze findings (2026-11-03)

Aggregates only. Tables: `results/pilot_report.md`. Criteria and deviations:
`sketch.md`. All of this is pilot data, on 10 prompts, and none of it enters the
confirmatory analysis.

**Feasibility (10 prompts x 4 local arms, 40 answers).** All 40 runs were clean and
on the subscription. The reference was 009's stored claude.ai answers. Gaps are
screens, not tests.

| Arm | Brand gap (90% interval) | Gap with unplaced names counted |
|---|---|---|
| `opus55_plain` (API anchor, same day) | +0.055 [-0.014, +0.134] | +0.075 |
| `cc_stock_full` | +0.056 [0.000, +0.113] | +0.061 |
| `cc_stock_search` | +0.076 [+0.034, +0.115] | +0.093 |
| `cc_none_full` | +0.086 [+0.013, +0.152] | +0.106 |
| `cc_none_search` | +0.054 [+0.011, +0.098] | +0.092 |

The lexicon coverage gate passed only after its scoring changed (sketch, deviation
1).

**Behavior.** Claude Code searches far more than claude.ai and reads far more: 4.4 to
7.0 searches per answer against 1.5, and 78 to 113 evaluated URLs against 14, on these
prompts. Haiku 5.5 reads the sources and Opus 5.5 writes the answer. Answers run about
60% longer. Brand counts per answer are about the same (7.3 to 8.4 against 8.1).

**Request shape, read from the request itself.** A local sink that forwards nothing
recorded the request body. Every local arm sends `model: claude-opus-5-5`,
`output_config.effort: medium` and adaptive thinking. The stock system prompt is 4,184
characters with these tools. `--system-prompt ""` leaves a 136-character block, so the
"no system prompt" arm is close to empty, not empty.

**Scheduled tasks.** These findings shape the design:
- A study prompt pasted in unchanged did **no web search** and answered from memory,
  and the session also called the push notification tool on its own (n = 1). The tool
  reported the push as requested; the account holder did not receive one. A task's prompt
  therefore has to ask for search, and the arm cannot use the prompt alone.
- The server attaches every connector on the account to a new task, even when the
  request lists none. Only an explicit clear removes them. An answer run with
  connectors attached is not a clean measurement, and such a task holds tools that can
  act on other systems.
- One task with a fresh subagent per prompt, told to use web search, finished 10 of 10
  prompts in 12.5 minutes with no connectors and no notification. Its gap to claude.ai
  was +0.068 [+0.013, +0.124], and +0.132 [+0.065, +0.193] with unplaced names counted.
  It overlapped local `cc_stock_full` at 0.614, while the local arms overlap each other
  at 0.688 to 0.793. So this is a real question and §4 tests it.
- The task's model can be set to Opus 5.5, and the transcript confirms each subagent ran
  on it. An `effort` field in the request was dropped without an error, and the run's log
  does not report effort, so the effort level is unverified. The study leaves it unset on
  all three waves. 009 found claude.ai's Medium and High settings do not change brands.
- The run log truncates answers. `claude --teleport <session>` pulls the full
  transcript. The main session's printed answers were exact copies of the subagents'
  reports (whole answers, 10 of 10). The pulled transcript records the version of the
  client that pulled it, not the cloud's, so the cloud version cannot be read.

**Usage.** 40 local answers moved a Max plan's five-hour window from 4% to 18% and its
seven-day window from 16% to 17%, with other work on the account at the same time.
On Pro (`harness/pro_usage_check.md`), 10 local answers with nothing else on the account
moved the five-hour window from 0% to 6% and left the seven-day window at 0%. Both round
to 1%, so these are rough. For comparison, 10 claude.ai chats used 11% of the same Pro
plan's five-hour window in 009's pilot, on a different date.

**Power.** §5.

## 0. One-paragraph summary

A team with a Claude subscription could run its own tracking prompts through Claude
Code, locally or as a scheduled task, instead of paying for the API. But Claude Code is
not claude.ai: its system prompt, search tool and path from search result to answer all
differ. We test whether, for B2B software research on Opus 5.5, an unattended Claude
Code run names the same brands as a person in claude.ai. 40 synthetic buyer prompts run
on 3 non-consecutive days through claude.ai by hand (the reference), local Claude Code
out of the box, a scheduled task built the way a subscriber would build it, local Claude
Code with no system prompt and search only, and the API as in 009. The primary test asks
whether each primary arm overlaps claude.ai about as much as claude.ai overlaps itself
across days, within +/-0.10. The pilot suggests small gaps, near the band's inner half,
so a pass is plausible and not assured.

## 1. The claim we can and cannot make

**What this design measures:** for 40 synthetic B2B software-buying prompts with no
location in them, on three days, from one claude.ai Pro account and one Claude Max
account: how closely each Claude Code configuration reproduces the brands named by
claude.ai on Opus 5.5, relative to how closely claude.ai reproduces itself from day to
day, and what that uses of a subscription's limits.

**What this design does NOT measure:**
- **Location-dependent visibility. This process is not suitable for tracking visibility
  when location matters.** Claude Code's `WebSearch` has no location setting, so neither
  this study nor anyone running this setup can choose where a search appears to come from. A scheduled
  task runs in Anthropic's cloud, from a place we do not know and cannot set. The
  prompts contain no location by construction, so the study says nothing about prompts
  where the answer depends on place, such as local services or regional vendors. We
  also did not test whether writing a place name into the prompt is an adequate
  substitute. The API can set a search location, and that remains the route for
  location-based tracking.
- Personalization. The claude.ai account has memory, chat search, preferences, styles,
  projects and connectors off. Real subscribers have history.
- Other languages, categories outside B2B software, other collectors, other accounts.
- Human buyer phrasing. The prompts are synthetic (009).
- Whether any use of a subscription is allowed under a given set of terms. That is not
  an empirical question and this study does not address it.

**Defensible claim:** "Across N answers evaluated in this study, a [local / scheduled]
Claude Code run on Opus 5.5 named the same brands as claude.ai [within / X points
outside] claude.ai's own day-to-day variation, for B2B software prompts with no location
in them."

**Indefensible claims:** "Claude Code equals what users see", any claim about prompts
where location matters, any claim about personalized sessions or other platforms, any
claim that the system prompt or search depth caused a result (this design does not
isolate them).

### Mechanistic prior

Retrieval normalizes: 009 found the same prompt and a similar search tool surface
overlapping brands whatever the request shape. Against that, Claude Code searches about
4 times as often and passes sources through a smaller model before the answer is written,
which could widen the set toward the long tail or narrow it toward what summaries
keep. The pilot's brand counts look unchanged. We expect a small positive gap, and we
expect cited domains to diverge further than brands.

## Arms, allocation and wave procedure

| Arm | Surface | Model / reasoning | System prompt | Tools | Role |
|---|---|---|---|---|---|
| `ui_default` | claude.ai, by hand, Pro | Opus 5.5, Medium (confirmed default) | claude.ai's own | claude.ai's own | **reference** |
| `cc_stock_full` | local `claude -p`, Max | `claude-opus-5-5`, effort medium | Claude Code's own | `WebSearch`, `WebFetch` | **primary** |
| `sched_kit` | scheduled task, Max | `claude-opus-5-5`, effort not set (unverified) | Claude Code's own, plus a subagent's | `Agent`, `WebSearch`, `WebFetch` | **primary** |
| `cc_none_search` | local `claude -p`, Max | `claude-opus-5-5`, effort medium | replaced, 136 characters remain | `WebSearch` | secondary |
| `opus55_plain` | API, Batches | `claude-opus-5-5`, effort medium | none | `web_search_20250305`, `user_location` Pittsburgh | secondary (replicates 009) |

The local arms follow the instrument rules in `sketch.md`: a pinned unmodified binary,
an empty environment, a check on every run that `apiKeySource` is `none`, no MCP servers,
the arm's exact tools, and one process per answer.

`sched_kit` is built as a subscriber would build it, and it tests that build, not the
cloud surface alone. Its frozen prompt (`harness/sched_kit.py`) tells the main session to
start one new general-purpose subagent per prompt on the same model, with this
instruction and nothing else, and to print the result unchanged:

> Use web search to research this question, then answer it the way you would answer the
> person asking it: <question text>

Each task's connectors are cleared and verified empty before it can fire, and
`PushNotification` is denied.

**Allocation.** 40 prompts x 3 waves. Claude Code: 3 arms, 360 answers. claude.ai: 120
chats. API: 120 calls on Batches, about $9 at the pilot's $0.073 per call, hard cap $25
on the ledger. Keys come only from this repo's `.env.local`.

**Wave procedure** (non-consecutive days; one account of each kind for the whole study):
1. Start of the session: submit the `opus55_plain` batch; start the local arms (order
   drawn from the seed); fire the scheduled tasks. `sched_kit` runs as 4 one-time tasks
   of 10 prompts each, the size the pilot exercised, with prompts assigned by seed.
2. The collector runs 40 claude.ai chats in randomized order under 009's protocol
   (`harness/ui_collection_protocol.md`, adapted to one arm), then one data export.
3. Ingest: `ui_default` must reach 40 of 40; `sched_kit` is pulled with
   `claude --teleport` and must reach 40 of 40. A task that dies is rerun for its missing
   prompts the same day, and logged. Local runs must pass the audit. The harness stops
   before the five-hour window reaches 60% or the seven-day window 50%, and never runs
   into overage.

## 2. Data-quality audits (run before the model)

- **Audit A: degenerate responses.** Per arm x wave: failed runs, audit failures, empty
  answers, zero searches, zero links, zero extracted brands, replies that only ask a
  question back, coding behavior. If more than 30% of an arm's answers have no search,
  its domain claims are INCONCLUSIVE. For `sched_kit`, the transcript records whether each
  subagent searched and its total tool count, not the number of searches, so its search
  depth is reported as a tool count. claude.ai chats that ask clarifying questions are scored on the first reply
  (009, deviation 1).
- **Audit B: what the labels mean.** "Brand named" = lexicon alias match in the answer
  text for the prompt's category, labelled sources blocks stripped
  (`pipeline/brands.py`). "Link in answer" = URL in the answer text
  (`aeo_research.claude_answers.from_claude_code_stream`). Claude Code has no citation
  objects, so this differs from `citations[]` on claude.ai and the API; domain results are
  descriptive. "Evaluated" = a link in a `WebSearch` result, local arms only (a subagent's
  searches are not in the pulled transcript).
- **Audit C: independence.** 40 prompts, 2 per category. Inference is prompt-level
  cluster bootstrap; R5 resamples categories.
- **Audit D: extraction validity** (signed by Jim Wrubel). A 30-answer random spot
  check, arm-blind, stratified across arms, read by hand: brand precision at least 0.95
  and recall at least 0.90, else refine the lexicon, log it and re-check.

## 3. Data schema

One row per answer (prompt x arm x wave).

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| item_id, category, intent | str | 009 prompts | yes | |
| prompt text | str | 009 | yes (already public) | synthetic |
| arm, wave, run_date, model | str/int | ledger / export | yes | |
| answer text | str | stream / export / transcript | **never** | data/raw only |
| search query text | str[] | stream | **never** | counts and overlap only |
| brands (ordered) | str[] | lexicon | yes (public facts) | |
| links, evaluated URLs | str[] | answer text / stream | derived-only | domains publish |
| n_searches, n_fetches, n_backend_searches, chars, n_brands | int | derived | yes | null for `sched_kit` where the transcript has no count |
| searched, subagent_tool_uses, resolved_model, report_match, instruction_exact | bool/int/str | transcript, `sched_kit` only | yes | |
| cost estimate, usage | float | stream | yes (aggregates per arm) | client-side estimate, comparison only |
| window utilization | float | `rate_limit_event` | yes (aggregates per plan) | rounds to 1% |
| scheduled-task prompt | text | `harness/sched_kit.py` | yes | |

### Derived variables

Jaccard with empty-vs-empty = NaN; truncated normalized RBO (p = 0.9) on brand order;
registered-domain heuristic as in 009.

## 4. Pre-registered hypotheses

Pair conditions: **within:ui** = same prompt, `ui_default`, different waves (3 pairs per
prompt). **cross:arm|ui** = same prompt, same wave, arm vs `ui_default` (3 pairs per
prompt). Gap = mean(within:ui) - mean(cross:arm|ui). Positive means the arm is further
from claude.ai than claude.ai is from itself.

**Primary family (Holm across 2 tests): H1, brand-set Jaccard gap** for `cc_stock_full`
and `sched_kit`: equivalent to 0 within +/-0.10. These are the two surfaces a subscriber
would use.

**Secondary (no multiplicity correction, labeled as such):**
- **H1 for `cc_none_search` and `opus55_plain`.** The second is a same-design replication
  of 009 (+0.067) and tells readers whether the reference moved.
- **H2, Claude Code against the API:** gap(arm) - gap(`opus55_plain`) for each Claude
  Code arm, TOST +/-0.10.
- **H3, scheduled against local:** for `sched_kit` and `cc_stock_full`, the mean of their
  two within-arm floors minus their same-wave cross-arm overlap, TOST +/-0.10. This tests
  whether the kit as built changes the answer compared to a local run. It does not separate
  the cloud surface from the subagent and its added instruction.
- **Brand order:** RBO gap for every arm.

**Descriptive (no verdict):** cited-domain gaps, on links for Claude Code and on citation
objects elsewhere, so a difference may be partly the measure; evaluated-domain gaps for
local arms; searches, fetches, evaluated URLs, links, brands, length; run time; usage per
answer on each plan, and the prompts per day that implies.

**H_pos (positive control; the study stops if it fails):** same-prompt cross-arm brand
Jaccard (all arms vs `ui_default`, pooled) exceeds cross-category cross-arm brand Jaccard
by at least 0.10, with a 90% CI excluding 0. It catches a broken join or extraction.

**H_pla (placebo):** the H1 gap on odd vs even prompt numbers, TOST +/-0.10, reported for
each primary arm. It does not gate the analysis, because the split doubles the interval
width (009, deviation 8). A REAL placebo gap is reported as a caveat on H1.

## 5. Model and decision rule

**Model:** nonparametric, as in 009. Pair-mean contrasts via
`aeo_research.overlap.cluster_boot` (prompt-level cluster bootstrap, 2,000 draws, 90%
percentile CI, seed = freeze date as YYYYMMDD). Holm over the 2 primary tests: each test's
bootstrap TOST p-value is the larger of the two one-sided tail probabilities at the band
edges, tests are ordered by p, and each verdict uses the CI at its Holm-adjusted level
(95% for the first, 90% for the second).

**SESOI:** 0.10 absolute Jaccard, the house band, the same as 009 so the results compare
directly: about one brand swapped in roughly half of a 5 to 10 brand answer.

**Decision rule (TOST, absolute scale):**

| Result | Conclusion |
|---|---|
| CI entirely inside +/-SESOI, includes 0 | Practically equivalent: passes |
| CI inside +/-SESOI, excludes 0 | Detectable but negligible: passes |
| CI excludes 0, extends beyond band | Real gap: report its size |
| CI wider than band, includes 0 | **Inconclusive: do not claim a null** |

**Power** (`pipeline/power_sim.py`: 009's real `ui_default` and `opus55_plain` per-prompt
values, 40 prompts, shifted to a planted true gap, 1,000 studies x 1,000 draws; it
reproduces 009's +0.067 unshifted):

| True gap | Pass, 90% CI | Pass, 95% CI | Real gap, 90% CI |
|---|---|---|---|
| 0.000 | 1.00 | 1.00 | 0.00 |
| 0.030 | 0.98 | 0.95 | 0.02 |
| 0.055 | 0.73 | 0.62 | 0.27 |
| 0.075 | 0.37 | 0.26 | 0.63 |
| 0.100 (false pass) | 0.06 | 0.03 | 0.94 |
| 0.125 | 0.00 | 0.00 | 1.00 |

The interval's half-width is about 0.032. So if the true gap is near the pilot's +0.055,
a pass is likely and not assured, and a true gap of +0.075 will more often read "Real gap",
however small. Either way the write-up reports the estimate, and a near miss is not a
failure of the idea. More prompts would narrow the interval, at the cost of comparability
with 009 and more hand collection. We keep 40 x 3.

**Lexicon protocol.** Start from experiment 010's frozen v3 (sha256
`6084f47c…5cf5d`, a superset of 009's v2.1), so that the 009 rules still apply. Haiku 4.5
proposes brand names from all wave 1 answers. A plan or edition of a vendor already in the
lexicon resolves to that vendor. Curation follows `009/harness/lexicon_rules.md`, then a
person reviews flagged rows and rows matching five or more answers. The sha256 is recorded
here before any confirmatory metric. Candidates from waves 2 and 3 are checked before the
freeze; if they show the lexicon missing more than 2% of names, it is extended under the
same rules, because missing names bias the comparison toward equivalence (009, deviation
7). Audit D validates it.

## 6. Known traps for this design

- **Location.** See §1. No Claude Code arm sets a location; `opus55_plain` keeps 009's
  Pittsburgh setting so the replication holds; local runs and cloud runs search from
  different places we cannot set. Any `sched_kit` vs local difference may include this.
- **Different accounts.** claude.ai runs on Pro and Claude Code on Max. Neither has
  memory or connectors in the measured path, but account-level rollouts are invisible to us.
- **A moving instrument.** The local binary is pinned. A scheduled task runs whatever
  version the cloud provides. We cannot read that version from the run's records, so a
  change between waves would not be visible. R3 drops each wave in turn.
- **The kit's wording.** `sched_kit` adds an instruction to use web search that no other
  arm has. claude.ai skipped search on 17% of these pilot prompts; `sched_kit` will
  likely never skip it. That is the kit as a subscriber would run it.
- **Retyped answers.** The main session retypes each subagent's answer. The transcript
  also holds each subagent's report, so Audit A compares every answer with its report, and
  checks that each subagent received the exact instruction. Any mismatch is reported.
- **One account's history.** The claude.ai account also holds 009's chats on the same
  prompts, some with what would be the same names. This study's chats are named
  `e011-w<wave>-ui_default-<item>`. The ingest matches only that exact name, only for chats
  created on or after the freeze date, never on prompt text, and writes neither chat when
  two share a name.
- **Search depth.** Claude Code searches about 4 times as much, so a pass on brands would
  not mean the sources match. Cited domains are descriptive and probably diverge.
- **Lexicon built partly in-sample.** The UI answers from 009 are fully covered and the new
  arms are not, so wave 1 candidates cover every arm before the freeze, and R4 checks it.
- **Timing.** The batch can land hours after the UI session; it is submitted at the start
  (009, deviation 5). R3 drops each wave in turn.
- **Limits.** A run stopped by the guard resumes the same day. If it cannot, that wave's
  missing answers are excluded and logged.

## 7. Robustness checks

1. H_pos first; if it fails, stop.
2. H_pla reported for each primary arm.
3. R1: top-10 brands instead of all brands.
4. R2: RBO on brand order.
5. R3: drop one wave at a time.
6. R4: nothing censored. Unplaced Haiku names added to each answer's brand set, both sides.
7. R5: category-level cluster bootstrap.
8. R6: exclude claude.ai chats flagged in collector notes.
9. R7: exclude answers with no search (`ui_default` included).

## 8. Deliverables and sequence

1. Pro usage check (Jim, `harness/pro_usage_check.md`). Done; the number is in §A.
2. **STOP 1: Jim reviews this spec.** Approved 2026-11-03, including `sched_kit` as a primary
   arm.
3. Analysis pipeline, built and dry-run on synthetic data before the freeze: planted
   equivalent and divergent arms are recovered and `03_model.py` exits non-zero when H_pos
   fails. Done. The same code run on 009's stored frame gives +0.067 [+0.034, +0.099], 009's
   published gap for `opus55_plain`. (009 built its pipeline after collection and logged that
   as a deviation.)
4. Freeze (two commits), record the hash and seed. Push.
5. Wave 1. Lexicon candidates, curation, **STOP 2: Jim reviews the lexicon**, freeze.
6. Waves 2 and 3.
7. Audit D (signed), model, robustness suite.
8. **STOP 3: results review.**
9. Only if approved: article, release, companion blog post (EN and DE), and any setup
   guide.

## 9. Notes for the write-up

- **Required, in the article, the blog post and any setup guide, in plain words:** this
  process is not suitable for tracking visibility when location matters, because the
  harness cannot control search location. The release checklist adds this as a sign-off
  item. Say what to use instead: the API, which can set a location.
- Lead figure: gap to claude.ai per arm against the +/-0.10 band, with claude.ai's own
  day-to-day overlap as the reference, next to searches per answer. The story the pilot
  suggests is that very different search behavior can still produce similar brand sets.
  Report what the data show instead if they disagree.
- Any setup guide must cover what the pilot found: ask for web search, one fresh subagent
  per prompt, clear the connectors, turn off notifications.
- Sample size phrased as "N answers evaluated (in this study)". Answers and search queries
  are never published.
- Publish the equivalence bound and the power table.

## Deviations from the frozen spec

1. **Export parser extended for a renamed tool (2026-11-03, before any brand measure or
   lexicon work on wave 1).** The wave 1 claude.ai export names the search call `WebSearch`,
   with an added `input.mode`. Its result block is still `web_search`. The frozen parser
   knew only `web_search` and `web_search_fast`, so it reported 0 searches for all 40 chats,
   although evaluated URLs parsed correctly. `WebSearch` was added to the parser's search
   tools. Answer text and citations do not depend on this list, so the brand measure is
   unaffected. Normalized output for all 251 chats in 009's exports was hashed before and
   after the change, and the hash is identical.
2. **Lexicon v1.2 after Audit D (2026-11-09, before any gap or confirmatory metric).** Audit D
   on v1.1 passed (precision 1.000, recall 0.992; 243 true positives, 0 false positives, 2
   missed). Jim Wrubel's review found both misses to be lexicon errors, and the two were fixed:
   the short form of a product already on a keep row was added as an alias, and a payroll
   vendor dropped in 009 because it appeared there only as a source is now kept, since 011's
   answers present it as an option. Two further notes questioned rules (a renamed product kept
   on its own row, and hotel systems dropped while their own messaging product counts); both
   rules were kept. v1.2, sha256 `d9fe9ce3ea232cb2af1357882a0849eea4fe9d775145bf8640958542c115b8b8`, changes the brand set of 3 of 600 answers, 2 of them
   in the audit sample. Those two sheet rows were updated to v1.2's extraction and re-scored;
   the review as made on v1.1 is kept in `data/raw/audit_d_sheet_reviewed_v1_1.csv`.

## Lexicon freeze record

Frozen 2026-11-03, after wave 1 answers were in and before any gap or brand comparison was
computed. `data/raw/lexicon_v1.csv`, sha256 `728794746267de5bdb6ff1662f3873cb9571a158881b0a04815412614c35f87a`, 1,453 rows: 010's v3 plus 83 rows for
011. Curation did not read arm labels. Names the lexicon cannot place, wave 1: 0.0% to 0.2%
per arm, against the 2% limit.

Review by Jim Wrubel: flagged and new rows one by one; the remaining rows matching five or
more answers were skimmed. Two rules applied at this review, for the record:

- **Source-only mentions.** A brand named only as the source of a claim is dropped, even if
  it sells in the category. This follows the 2026-09-28 reviewer calls in 009's lexicon and
  was not written in `lexicon_rules.md`. A name presented as an option counts even when it
  is written as a link. The question is whether a reader would take it as something to
  consider.
- **Retired products.** A product named only as something to move off is dropped. A vendor
  still on the market counts even when the answer warns against it.

The review sheet's context cells remove link targets and keep the brackets, so a linked
option can look like a citation. Rows were read with that in mind.

**Extension after waves 2 and 3 (2026-11-09), as §5 requires.** Checked against v1, the
lexicon could not place 2.1% to 5.9% of names in wave 2 and 0.8% to 4.1% in wave 3, against
the 2% limit, in 8 of 10 arm-waves. Of 150 flagged (category, name) pairs, 100 were truly
unplaced; the other 50 were already found inside a longer name. v1 was extended under the
same rules, again without reading arm labels: 94 rows, 36 keep and 58 drop.
`data/raw/lexicon_v1_1.csv`, sha256 `8e063e09873f8fb3d0d748c371c2c90904c6c039b80314d3debfacec6bd948ed`, 1,547 rows. Names the lexicon cannot place after
the extension: 0.0% to 0.7% per arm in every wave. v1 is kept unchanged for the record.

Review by Jim Wrubel: the 5 flagged rows and the 7 rows matching five or more answers one
by one, and the rest of the sheet read; all calls accepted as drafted. The sheet now marks
linked names, so a linked option no longer reads as a citation. No gap, brand comparison or
confirmatory metric had been computed.

## Audit notes

**Audit A coding flags read by a person (2026-11-09).** The pattern check flagged 7 of 600
answers across four arms. Each ends with the same offer to narrow the list and draft a demo
script for vendor calls, which is advice to a buyer, not coding behavior (the same call as
the feasibility run, sketch deviation 2). All 7 cleared; none is excluded.

**Audit D reading file.** Each answer now also lists the names the lexicon matched and drops
by rule, with the reason, so a deliberate exclusion is not marked missed. This changes only
what the reviewer reads, not extraction or any metric.

## Observations during collection

These are not deviations. They are recorded because they change how the results read.

1. **The claude.ai reference no longer behaves as it did in 009.** Wave 1 against 009's
   three `ui_default` waves (September 27 to October 1): searches per answer 3.33 against
   1.15 to 1.32; chats with no search 0 of 40 against 6 to 8 of 40; median URLs evaluated
   per answer 53 against 9 to 10; median answer length about 4,600 characters against about
   3,500; chats that open with a short text block before searching 34 of 40 against 0 to 1
   of 40. The account is the same one, confirmed from the export. The fresh reference is
   what this design relies on, so the test still answers its question about claude.ai as it
   stands now. It also means §6's search-depth note, and 009's result, describe an earlier
   claude.ai. Observation 3 points to a likely cause.
2. **The opening text block is scored.** The frozen parser joins every text block, so the
   short opening block in `ui_default` answers counts as answer text. The Claude Code arms
   score only the final text. Whether this moves any brand set is checked once the lexicon
   is frozen and reported as an exploratory sensitivity.
3. **The claude.ai chats show Claude Code's harness.** Every wave 1 chat's first message
   holds four injected blocks that none of 009's chats have, identical across all 40: a
   date note, a listing of agent types for an `Agent` tool, a list of deferred tools loaded
   through `ToolSearch`, and MCP server instructions. The last three use a
   `<system-reminder>` format, and the search tools are named as in Claude Code. The pasted
   prompt is still byte for byte the sheet's text. The system prompt is not in the export.
   The comparison is therefore no longer between two unrelated surfaces, and a pass or a
   failure has to be read that way. Later waves check that these blocks are unchanged.

   **What Anthropic documents.** On September 16, 2026 Anthropic announced that chat and
   Cowork had become one experience, rolling out gradually to Pro, Max and Ultra plans over
   several weeks, with Team and Free to follow and Enterprise from October 23
   ([announcement](https://claude.com/blog/cowork-is-now-claude)). Once an account has it,
   it cannot switch back, there is no web search toggle, and incognito chats open in the
   previous experience
   ([help article](https://support.claude.com/en/articles/16761823-claude-cowork-and-chat-are-one-claude)).
   Cowork "uses the same agentic architecture that powers Claude Code"
   ([help article](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork)).
   Claude Code stays a separate product behind its own tab.

   **What is inferred.** No Anthropic source found says that a chat answer runs on Claude
   Code's harness, and this account's rollout date is unknown. 009's last wave (October 1)
   shows none of these blocks and wave 1 (November 3) shows them, which fits the rollout
   reaching the account in between. That link is an inference from timing and from the
   export, not a documented fact.

   **Consequences.** What a person gets from claude.ai can now depend on plan and setting,
   so `ui_default` describes the unified experience on one Pro account. Incognito chats may
   still show the previous experience, but the export leaves them out, so this design cannot
   measure it. The protocol's step to check that web search is on no longer applies, because
   the toggle is gone.
