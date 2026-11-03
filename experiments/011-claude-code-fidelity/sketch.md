# 011: Can an unattended Claude Code run stand in for a person in claude.ai? (design sketch)

**Status:** sketch, NOT a spec, nothing frozen as a confirmatory study. Written
2026-11-03, before any study prompt was run through Claude Code. It fixes the
hypothesis and the go/no-go criteria for a short feasibility run. `spec.md`
follows only if the run says a full study is worth doing.

## The question

Experiment 009 found that Opus 5.5 through the API, with no system prompt, names
the same brands as a person using claude.ai on Opus 5.5, within the +/-0.10
Jaccard band (gap +0.067, 90% CI +0.034 to +0.099).

A team that already pays for a Claude subscription has another route. It could
run its own tracking prompts on that subscription through Claude Code, in
headless mode (`claude -p`) or as a scheduled task. Nothing about that route is
claude.ai, though. The system prompt, the search tool and the path from search
result to answer are all different, and 009 says nothing about them.

**Hypothesis.** For B2B software research, on the same model and reasoning
level, an answer from unmodified Claude Code names the same brands as a person
in claude.ai: the brand-set Jaccard gap is 0 within +/-0.10.

**What we expect.** A positive gap, for the reasons below. The confirmatory
question is whether it stays inside the band, and which configuration comes
closest.

### Why it might not hold

Measured on one prompt outside the study (trail running shoes, 3 runs, smoke
test 2026-11-03), against the 120 `ui_default` answers of 009:

| | Claude Code, smoke | claude.ai, 009 |
|---|---|---|
| Searches per answer | 5 to 7 | 1.2 |
| Pages fetched per answer | 6 to 10 | 0 |
| Who reads the sources | Haiku 5.5 reads them, Opus 5.5 writes the answer | not observable |
| Structured citations | none, links in the answer text | yes |

Claude Code's documentation says `WebSearch` returns titles and URLs and that
`WebFetch` usually runs its prompt in a separate model call. The smoke test's
token counts agree: 250,000 to 415,000 input tokens went to Haiku 5.5 per answer,
and about 2,000 to 3,500 tokens opened the Opus 5.5 conversation.

These smoke results were seen before the criteria below were written. They
informed the arms (a search-only arm exists because claude.ai fetched nothing)
and the choice to report usage. No study prompt had been run.

## Arms

All arms use `claude-opus-5-5` at `--effort medium`, the same setting as 009's
reference. Two factors, 2 x 2:

| Arm | System prompt | Tools | Stands for |
|---|---|---|---|
| `cc_stock_full` | Claude Code's own | `WebSearch`, `WebFetch` | out of the box |
| `cc_stock_search` | Claude Code's own | `WebSearch` | stock prompt, closer to claude.ai's behavior |
| `cc_none_full` | replaced with empty (`--system-prompt ""`) | `WebSearch`, `WebFetch` | no coding-agent prompt |
| `cc_none_search` | replaced with empty | `WebSearch` | closest analog of 009's `opus55_plain` |

The prompt factor matters beyond this study: as far as the documentation shows,
a scheduled task has no way to replace the system prompt, so only the stock arms
describe that surface directly.

**Reference.** `ui_default` waves 1 to 3 from 009 (120 answers, about five weeks
old) for this feasibility run only. No hand collection is needed yet. The
confirmatory study collects its own claude.ai answers.

**Anchor.** `opus55_plain` through the Batches API, run the same day on the same
prompts, with the request shape of 009. It measures whether 009's stored
claude.ai answers are still a fair reference. If today's API answers have moved
well away from them, the staleness shows up here and not as a false Claude Code
gap.

Experiment 010 is still collecting on these prompts, and its Stage 2 answers stay
sealed until its own analysis. Nothing here reads them.

## Instrument rules

- **Pinned, unmodified binary.** Claude Code 2.1.316, sha256 recorded in the
  ledger and checked before every run. The installed `claude` may update at any
  time, and a study needs one version.
- **Subscription, verified per run.** In `-p` mode an `ANTHROPIC_API_KEY` always
  wins over a subscription login, and one lives in this repo's `.env.local`. The
  process starts from an empty environment (`env -i`, then only `HOME`, `PATH`,
  `USER`, `LANG`, and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`). A run counts only if
  the stream's `init` event reports `apiKeySource: none`.
- **No personal context.** A new empty working directory per run, no session
  persistence, `--setting-sources ""`, `--strict-mcp-config` (a claude.ai login
  otherwise brings its connectors along), `--disable-slash-commands`. `init` must
  report no MCP servers and exactly the arm's tools.
- **`--bare` is not usable.** It never reads a subscription login.
- **The prompt text is the only input,** byte for byte the 009 text.
- **One clean context per answer.** Each answer is its own process.
- **No overage.** The harness stops before a run if the five-hour window is at
  60% or more, the seven-day window at 50% or more, a window is not `allowed`, or
  overage is in use.

## Measures

Brand sets use 009's extraction (`pipeline/brands.py`, labelled sources blocks
stripped) with the frozen lexicon v3 of experiment 010, a superset of 009's v2.1
that lost no v2.1 match. Cited URLs here are the links in the answer text, since
the stream has no citation objects. That is a measurement difference from 009's
`citations[]`, so domain results are descriptive at this stage. Evaluated URLs
are the `WebSearch` result links in the stream.

**Brand gap**, as in 009: mean(within:ui) minus mean(cross:arm|ui). within:ui is
the same prompt across `ui_default` waves (3 pairs per prompt). cross:arm|ui pairs
the arm's answer with each of the 3 `ui_default` waves. Positive means the arm is
further from claude.ai than claude.ai is from itself. Prompt-level cluster
bootstrap, 90% interval. The pairs in cross:arm|ui are across days and weeks,
unlike 009's same-wave pairs, which is another reason for the anchor.

**Usage**, per answer: the stream's `rate_limit_event` utilization for the
five-hour and seven-day windows, read at each arm's start and end. It rounds to
1% and other work on the account moves it, so it is paired with Claude Code's
`total_cost_usd`, a client-side estimate used only to compare arms.

## Feasibility run

10 prompts (the 10 categories of 009's pilot: `b2b_01`, `06`, `09`, `14`, `17`,
`22`, `25`, `30`, `33`, `38`) x 4 arms x 1 wave = 40 Claude Code answers, plus 10
anchor answers. These answers are pilot data and never enter a confirmatory
analysis. The arms run in sequence, in an order drawn from the seed, so usage can
be read per arm.

## Go/no-go criteria (fixed before any study prompt runs)

- **G1, clean instrument.** At least 38 of 40 runs finish and pass the `init`
  audit (subscription, no MCP servers, exact tools, Opus 5.5 as the main model).
- **G2, they are answers.** Per arm, at least 90% of answers are a buyer-facing
  answer: no reply that only asks a question back, and no offer to write files or
  code. At least 70% of answers run a search (009's rule: above 30% without
  search, an arm's domain claims are inconclusive).
- **G3, measurable.** Per arm, at least 90% of the brand names a Haiku pass finds
  are covered by the lexicon. Missing names censor the long tail and bias the
  comparison toward equivalence (009, deviation 7). Parsed links exist in at
  least 80% of answers that searched.
- **G4, anchor.** `opus55_plain` gap against the stored reference is at most
  0.15. If it is higher, the stored reference is stale: collect fresh claude.ai
  answers for these 10 prompts by hand before reading G5.
- **G5, fidelity signal.** At least one arm that passed G1 to G3 has a brand gap
  of at most 0.20 (point estimate). This is a screen, not a test. Ten prompts
  cannot certify anything, and the band is 0.10, so 0.20 asks only whether a pass
  in a full study is still plausible.

**Usage is reported, not gated.** It does not decide whether the question is worth
answering. It decides whether anyone should run this daily.

### Reading the outcome

- G1 to G3 fail: fix the harness and rerun. A failure here is about the
  instrument.
- G4 fails: fresh hand-collected reference for the 10 prompts, then G5.
- G5 fails for every arm: Claude Code is not a plausible stand-in on this
  evidence. Whether a smaller confirmatory study of the gap itself is worth
  publishing is decided at the stop below.
- G5 passes: draft `spec.md` with at most 2 arms. Take the arm with the smallest
  gap. Prefer a stock arm if it is within 0.03 of the smallest, since it describes
  a surface that needs no prompt replacement. Confirmatory answers are all new, so
  picking arms here does not bias the test.

## STOP

After this run, STOP for Jim Wrubel's go/no-go. Nothing below starts without it.

## What a full study would look like (not frozen)

40 prompts x 3 non-consecutive days, same design as 009. Fresh `ui_default` by
hand, 40 chats per wave, reference for all tests. At most 2 Claude Code arms and
`opus55_plain` the same day. Primary: brand-set Jaccard gap, TOST +/-0.10, Holm
across the Claude Code arms. Secondary: brand order (RBO), cited and evaluated
domains, the direct contrast with `opus55_plain`. Positive and placebo controls as
in 009. Audit D on the Claude Code answers. A scheduled-task arm, if plumbing
allows, because that is the surface with no machine to keep running.

## What this does not settle

- **Terms.** Claude Code's legal page says OAuth login is "designed to support
  ordinary use of Claude Code and other native Anthropic applications", and that
  developers building products or services should use API keys. It also says it
  does not prevent an end user from signing in to the unmodified binary with their
  own subscription. Whether scheduled tracking is ordinary use is not stated. This
  study runs the unmodified binary on the collector's own subscription, at low
  volume. It does not establish that any commercial pattern is allowed.
- **Other surfaces.** A scheduled task runs in a cloud environment and may behave
  differently from a local `claude -p`.
- **Personalization, other plans.** One account, one plan. The usage numbers
  describe that plan.
- **Search location.** `WebSearch` has no location setting, while 009's claude.ai
  account signed in from Pittsburgh and its API arms set `user_location` there.
  The anchor keeps the 009 setting. B2B software prompts are expected to be
  insensitive to location, and no study here has tested that.
