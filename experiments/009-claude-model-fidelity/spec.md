# Cheaper Claude API calls reproduce what a claude.ai subscriber sees in B2B software research: study spec

**Status:** FROZEN
**Frozen commit:** `1730d38`
**Frozen date / seed:** 2026-09-26 / 20260926
**Experiment slug:** `009-claude-model-fidelity`

> Freeze rule: §4 (hypotheses) and §5 (model and decision rules) are fixed
> before wave 1 is submitted. The prompt panel (`data/raw/prompts.csv`, 40
> synthetic prompts), the arm registry (`harness/arms.py`, core arms), the
> trimmed leaked prompt (sha256 in `data/raw/system_prompts/manifest.json`)
> and the extraction code are frozen with the spec. The brand LEXICON is
> extraction data, not a hypothesis: it is extended from wave 1 answers and
> frozen before any confirmatory metric is computed (§5, lexicon protocol).
> Any later change is logged under Deviations.

---

## A. Pre-freeze findings (smoke 2026-09-25, pilot 2026-09-26)

Aggregates only. Full tables: `results/pilot_report.md`; design notes:
`sketch.md`.

**Smoke test** (1 prompt x 6 arms, realtime, $1.13):
- Request shapes accepted on every arm; the explicit 1-hour cache marker on
  the system prompt plus top-level automatic caching works (repeat calls read
  the 20.8k-token cached prefix).
- No arm wrote tool calls as text; the kept claude.ai citation instructions
  did not suppress the API's structured `citations[]`.
- Sonnet 5 with thinking disabled and the leaked prompt answered without
  searching on 3 of 3 prompts.

**Leaked prompt:** pinned commit `17200e14`; 158,640 tokens raw on Opus 5.5
and Sonnet 5 (120,691 on Haiku 4.5), mostly claude.ai tool definitions. The
trimmed prompt is 18,120 tokens (12,473 on Haiku). Trim rules:
`harness/leak_trim_rules.md`.

**Pilot** (10 prompts in 10 categories; all API arms at wave 0, a same-day
repeat of `opus55_leak` and `sonnet5_leak_think` at wave 90; 10 claude.ai
chats; $15.55 API):
- **claude.ai export format confirmed:** the export holds search queries,
  search results with URLs and text citations; 10 of 10 chats matched and
  parsed.
- **UI default reasoning label is Medium** for Opus 5.5, matching API
  `effort: "medium"`. The higher setting is "High" (wording to be confirmed
  from the collector's notes).
- **Plain Opus matches the UI's behavior profile.** Per answer: UI 1.8
  searches, 7.1 cited URLs, 16.4 evaluated URLs; `opus55_plain` 1.8, 8.6,
  16.3.
- **The leaked prompt roughly doubles searching** on Opus (3.8 searches, 34.7
  evaluated URLs per answer).
- **Search skips on Sonnet:** with thinking disabled, 3 of 10 answers ran no
  search; at effort low, 2 of 10. Adaptive thinking at default effort skipped
  none.
- **`web_search_20260209` ruled out:** 8.2 searches per answer but zero inline
  citations on 10 of 10 answers.
- **web_fetch unused:** 0 fetches across 10 prompts when attached.
- **Noise floors** (same arm, same day, same prompt): brand Jaccard 0.61
  (`opus55_leak`) and 0.47 (`sonnet5_leak_think`) with the Haiku draft
  names, 0.80 and 0.60 with lexicon v0; cited registered-domain Jaccard 0.33
  and 0.16.
- **Cross-arm brand Jaccard with the UI** (lexicon v0, confirmatory arms):
  Opus 0.63 to 0.68; Sonnet (think, low, prod) 0.48 to 0.56; Haiku 0.42.
- **Deterministic extraction reproduces the model pass:** per-answer brand
  sets from lexicon v0 matching agree with the Haiku candidates mapped
  through v0 at mean Jaccard 0.92 (identical in 78 of 125 answers). v0 was
  built in-sample, so this is not an out-of-sample recall estimate.
- **Location deviation:** the pilot's API calls used Boston, Massachusetts;
  the UI account signs in from Pittsburgh. Every confirmatory wave uses
  Pittsburgh, Pennsylvania, US for the API `user_location`.
- **Cost:** batch-priced mean per call (first-call cache writes included):
  `opus55_leak` $0.18, `opus55_plain` $0.08, `sonnet5_leak_think` $0.08,
  `sonnet5_leak_low` $0.05, `sonnet5_prod` $0.09, `haiku45_leak` $0.06.
- **Subscription usage:** the 10 pilot chats (Opus 5.5, Medium) used 11% of
  the Pro plan's 5-hour limit and 1% of its weekly limit. claude.ai reports
  usage only as a share of those limits, so there is no per-chat dollar
  figure for the UI side. An 80-chat wave would use most of one 5-hour
  window, so each wave runs as two sessions (see the wave procedure).

**Review decisions (Jim Wrubel, 2026-09-26):** `sonnet5_prod` stays
secondary (it is the production default for cost reasons; this study decides
whether that changes); `ui_think` is kept; the panel-share tests are
secondary estimation, not equivalence tests.

## 0. One-paragraph summary

Tracking Claude at scale means calling the API, and the cheapest believable
call (Sonnet 5 or Haiku 4.5) costs a fraction of the model a claude.ai
subscriber gets by default (Opus 5.5 since 2026-09-22). We test whether, for
B2B software research, a cheaper API call returns the same brands and cites
the same sources as a subscriber on the default model. 40 synthetic buyer
prompts (20 software categories x 2 intents) run on 3 non-consecutive days
through two claude.ai arms collected by hand (Opus 5.5 at the default Medium
reasoning, and at High) and seven API arms (Opus 5.5 plain and with the
leaked claude.ai system prompt; Sonnet 5 plain, with the leak at default and
low effort, and as Spyglasses ships it today; Haiku 4.5 with the leak). The
primary tests ask whether each cheap arm's answers overlap the UI's as much
as the UI overlaps itself across days (per-answer brand sets); panel-level
brand and cited-domain shares are estimated per category with confidence
intervals (secondary, because 6 answers per category cannot certify a
5-point agreement; §5). The pilot predicts real gaps for the cheap arms (0.17 to 0.38 below the API
noise floor on brands), so the likely headline is a measured, priced gap,
not an equivalence.

## 1. The claim we can and cannot make

**What this design measures:** for 40 synthetic B2B software-buying prompts,
on three days, from one fresh claude.ai Pro account and the Anthropic API at
one location: how closely each API configuration reproduces the brands named
and the domains cited by claude.ai on Opus 5.5, relative to how closely
claude.ai reproduces itself from day to day; plus the measured dollar cost
per call of each configuration.

**What this design does NOT measure:**
- Logged-in personalization. The UI account is fresh, with memory, chat
  search, preferences, styles, projects and connectors off. Real subscribers
  have history; that is out of scope and said so prominently.
- Other locations, languages, categories outside B2B software, or other
  collectors. One account, one collector, one city (Pittsburgh).
- "The effect of THE claude.ai system prompt." The leak's provenance cannot
  be verified and the API's `web_search` is not claude.ai's retrieval stack
  (claude.ai also offers `web_search_fast` and `web_fetch`). Arms with the
  leak measure **instrument divergence** (the 004 sketch framing rule), a
  best-effort bound.
- Human buyer phrasing. Prompts are synthetic, generated by Haiku 4.5 under
  rules (no brands, no location, 15 to 45 words) and reviewed by a person.

**Defensible claim:** "Across N answers evaluated in this study, Sonnet 5
through the API named the same brands as claude.ai on Opus 5.5 [within /
X points outside] claude.ai's own day-to-day variation, and its panel-level
brand shares differed by Y points on average, at Z% of the Opus cost."

**Indefensible claim:** "Claude API tracking equals what users see",
"vendors using the API are wrong", any claim about personalized sessions,
other platforms, or other query types, or any causal claim about the leaked
system prompt.

### Mechanistic prior

Two forces. (1) Retrieval normalizes: the same prompt and the same search
tool should surface overlapping sources and therefore overlapping brands,
whatever the model. (2) The model decides how much to search and how to
compose: the pilot shows search counts ranging from 1.6 to 3.8 per answer
across arms, and smaller models name fewer brands. Brand overlap should
track model tier and search depth; the UI's low search count (1.8) makes
plain Opus the natural match. We expect the cheap arms to fail equivalence
on per-answer brand sets and to come closer on panel shares, where
dominant vendors per category are shared.

## Arms, allocation and wave procedure

| Arm | Surface | Model / reasoning | System prompt | Role |
|---|---|---|---|---|
| `ui_default` | claude.ai, by hand | Opus 5.5, Medium (UI default) | claude.ai's own | **reference** |
| `ui_think` | claude.ai, by hand | Opus 5.5, High | claude.ai's own | H2 |
| `opus55_plain` | API | `claude-opus-5-5`, effort medium | none | H1-ref, H3 |
| `opus55_leak` | API | `claude-opus-5-5`, effort medium | trimmed leak | H1-ref, H3 |
| `sonnet5_plain` | API | `claude-sonnet-5`, adaptive thinking | none | **primary** |
| `sonnet5_leak_think` | API | `claude-sonnet-5`, adaptive thinking | trimmed leak | **primary**, H2 |
| `sonnet5_leak_low` | API | `claude-sonnet-5`, adaptive, effort low | trimmed leak | secondary, H2 |
| `sonnet5_prod` | API | production request, byte for byte | Spyglasses discovery prompt | secondary |
| `haiku45_leak` | API | `claude-haiku-4-5`, no thinking | trimmed leak | **primary** |

Research API arms (all but `sonnet5_prod`): `web_search_20250305`,
`max_uses` 10, `user_location` Pittsburgh, Pennsylvania, US; `max_tokens`
16000; no temperature; no refusal fallbacks. The leak arms cache the system
prompt for 1 hour. `sonnet5_prod` reproduces
`callClaudeDirectWithWebSearch` (max 5 searches, no location, no caching),
verified by test against the spyglasses source.

**Allocation:** 40 prompts x 3 waves. API: 7 arms, 840 calls on the Batches
API (estimate about $90 from pilot per-call costs; hard cap $250 via the
ledger's `--max-cost`). UI: 80 chats per wave (40 prompts x 2 arms), 240
total.

**Wave procedure** (waves on non-consecutive days):
1. `make_ui_sheet.py --wave N` (already generated for waves 1 to 3): the 80
   chats in an order randomized per wave.
2. The collector runs the sheet per `harness/ui_collection_protocol.md`
   (settings check, fresh chat per row, rename `wN-arm-item_id`, no
   regenerate or follow-up) in two sessions on the same day: rows 1 to 40,
   then rows 41 to 80 in a later 5-hour usage window. If the usage limit
   interrupts a session, the collector stops, notes the row, and resumes in
   the next window; no chat is started while limited.
3. During the session: `collect_anthropic.py submit --wave N --arms all`
   (Pittsburgh default), then `status` / `collect` when the batch ends.
4. After the session: one claude.ai data export into
   `data/raw/ui_exports/wN/`, then `ingest_claude_export.py --wave N` must
   report 80 of 80 matched before the next wave.

## 2. Data-quality audits (run before the model)

- **Audit A: degenerate responses.** Per arm x wave: failed or errored
  batch requests, `pause_turn` continuations, empty answers, zero searches,
  zero cited URLs, zero extracted brands, refusals. Empty-vs-empty set pairs
  are NaN and excluded (rate reported). If more than 30% of an arm's answers
  have no search, that arm's domain claims are INCONCLUSIVE whatever the CI.
  UI: unmatched, duplicate or voided chats from the ingest report; any UI
  chat run with the wrong model or reasoning setting (collector notes) is
  excluded and listed.
- **Audit B: what the labels mean.** Quoted from code:
  "brand named" = lexicon alias match in the answer text for the prompt's
  category, `harness/pilot_report.py::lexicon_extract` (moves to
  `pipeline/brands.py` at freeze); "domain cited" = registered domain of a
  normalized URL in a text block's `citations[]` (API) or
  `citations[].details.url` (export), `aeo_research.claude_answers`;
  "domain evaluated" = registered domain of a `web_search_tool_result` item
  (API) or `tool_result` knowledge item (export); "grounding tokens" =
  stopword-filtered tokens of the search queries (`overlap.token_set`).
- **Audit C: independence.** 40 prompts, 2 per category; each prompt runs in
  every arm and wave. Inference is prompt-level cluster bootstrap; no
  pair-level standard errors. Category is a coarser cluster: robustness R6
  resamples categories.
- **Audit D: extraction validity** (signed by Jim). A 30-response random
  spot check stratified across arms: brand precision at least 0.95 and
  recall at least 0.90 against a manual read, else refine the lexicon, log
  it, and re-check. Also report agreement between lexicon extraction and the
  Haiku candidates (R4).

## 3. Data schema

One row per answer (prompt x arm x wave).

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| item_id | str | prompts.csv | yes | `b2b_01` to `b2b_40` |
| category, intent | str | prompts.csv | yes | 20 categories, shortlist / evaluate |
| prompt text | str | make_prompts.py | **yes** (synthetic exemption, docs/data-policy.md; release checklist sign-off) | study-generated, no brands |
| arm, wave, run_date, model | str/int | ledger / export | yes | |
| answer text | str | API / export | **never** | data/raw only |
| search query text | str[] | server_tool_use / tool_use | **never** (token counts and overlap only) | |
| brands (ordered) | str[] | lexicon extraction | yes (public facts) | canonical vendor names |
| cited URLs | str[] | citations | derived-only | domains publish; full URLs internal |
| cited / evaluated domains | str[] | registered_domain | yes (public facts) | |
| n_searches, n_cited, n_evaluated, n_brands, chars | int | derived | yes | |
| usage, cost_usd | dict/float | ledger | yes (aggregates per arm) | batch pricing, `aeo_research.pricing` |
| leaked prompt, trimmed prompt | text | pinned commit | **never** | sha256 and trim rules only |
| collector notes, chat names | text | UI sheet / export | derived-only | protocol deviations counted |

### Derived variables

URL normalization and registered-domain heuristic as in 002/003; Jaccard
with empty-vs-empty = NaN; truncated normalized RBO (p = 0.9) on brand order;
per-category **panel share** = fraction of an arm's answers in that category
that name a brand (or cite a domain); source class per cited domain (vendor,
review marketplace, community, publisher, analyst, other) from a frozen
domain map built with the lexicon.

## 4. Pre-registered hypotheses

Pair conditions: **within:ui** = same prompt, `ui_default`, different waves
(3 pairs per prompt); **cross:arm|ui** = same prompt, same wave, arm vs
`ui_default` (3 pairs per prompt). Gap = mean(within:ui) - mean(cross:arm|ui).
Positive gap = the arm is further from the UI than the UI is from itself.

**Primary family** (Holm across its 3 tests): **H1b (per-answer brands)**
for the cheap arms `sonnet5_plain`, `sonnet5_leak_think` and `haiku45_leak`:
the brand-set Jaccard gap is equivalent to 0 within +/-0.10.

**Secondary: panel shares, estimated with CIs, no equivalence verdict**
(construction and power in §5, `pipeline/shares.py`), for every API arm:
- **H1s (panel brand share):** per-category brand shares (the fraction of an
  arm's 6 answers in a category naming the brand, lexicon extraction),
  basket = (category, brand) cells whose share pooled over the arm and the
  UI is at least 1/3; statistic = noise-corrected root-mean-square
  difference (RMSD) between arm and UI over the basket, with a 90% two-stage
  cluster-bootstrap CI. Read as "differs by at least X" when the lower bound
  is above 0; never read as equivalence. Kendall tau on within-category share
  ranks reported alongside.
- **H1d (panel cited-domain share):** the same construction on registered
  domains the answer cites.

**Other secondary tests** (no multiplicity correction, labeled as such):
- H1b for `sonnet5_leak_low` and `sonnet5_prod`.
- Per-answer cited-domain gap and evaluated-domain gap (+/-0.10) for all API
  arms (the domain equivalence tests; the pilot simulation puts their false
  equivalence at 0.16 to 0.33, so a pass is reported with that caveat); RBO
  gap on brand order.
- **H1-ref (ceiling):** H1b and the domain gaps for `opus55_plain` and
  `opus55_leak`.
  If both fail, no API configuration reproduces the UI at any price, and the
  cheap arms are also reported against `opus55_plain` as a secondary
  reference.

**H2 (reasoning):** `sonnet5_leak_think` vs `sonnet5_leak_low` (cross-arm
brand and cited-domain Jaccard, against the mean of their two within-arm
floors), and `ui_default` vs `ui_think` (same construction). TOST +/-0.10.

**H3 (API vs subscription, same model):** the H1b and cited-domain gaps of
`opus55_plain` and `opus55_leak`. **H3b:** does the leak close the plain
gap? Difference of gaps, gap(`opus55_plain`) - gap(`opus55_leak`), TOST
+/-0.10; a positive REAL result means the leak moves the API closer to the
UI. Framed as instrument divergence only.

**Fair model comparison (descriptive):** `sonnet5_plain` vs `opus55_plain`
gaps (same request shape, different model), with a bootstrap CI on the
difference.

**H_pos (positive control; the study stops if it fails):** same-prompt
cross-arm brand Jaccard (all API arms vs UI, pooled) exceeds cross-category
cross-arm brand Jaccard by at least 0.10, 90% CI excluding 0. H_pos is a
pipeline sanity check: different categories share few vendors, so it is
expected to pass easily. Its job is to catch broken extraction or a broken
join (for example answers attached to the wrong prompt), not to test a claim.

**Descriptive gradient:** cross-arm brand Jaccard for same prompt, same
category with the other intent, and different category, expected to fall in
that order (same prompt > same category > cross category). Reported with
cluster-bootstrap CIs, no test.

**H_pla (placebo):** the H1b gap computed on odd vs even prompt numbers
differs by a NULL or NEGLIGIBLE amount (TOST +/-0.10) for every primary arm.

## 5. Model and decision rule

**Model:** nonparametric. Pair-mean contrasts via
`aeo_research.overlap.cluster_boot` (prompt-level cluster bootstrap, dyadic
weights, 2,000 draws, 90% percentile CI, seed = freeze date as YYYYMMDD).
Panel shares: `pipeline/shares.py`, two-stage cluster bootstrap (categories
with replacement, then prompts within each drawn category, all waves and
both arms of a drawn prompt together; the basket and the noise terms are
recomputed in every draw). Holm over the 3 primary tests: each test's
bootstrap TOST p-value is the larger of the two one-sided tail
probabilities at the band edges; tests are ordered by p, and each verdict
uses the CI at its Holm-adjusted level.
`cluster_boot` returns the draws' CI only, so the pipeline computes these
tail probabilities from the same draws.

**SESOI:** 0.10 absolute Jaccard for per-answer gaps (the house band, one
brand swapped in roughly half of a 5 to 10 brand answer). For panel shares,
0.05 (five points of share, the smallest error that reorders adjacent
vendors in a share-of-voice table) remains the reference line in the write-up,
but no equivalence verdict is drawn against it (see below).

**Decision rule (TOST at 90% CI, absolute scale):**

| Result | Conclusion |
|---|---|
| CI entirely inside +/-SESOI | Practically equivalent: the arm passes this layer |
| CI excludes 0, extends beyond band | Real gap: report and price it |
| CI excludes 0, inside band | Detectable but negligible |
| CI wider than band, includes 0 | **Inconclusive: do not claim a null** |


**Power** (pilot simulation, `harness/pilot_report.py`; 40 prompts, 3 waves;
share of 300 simulated studies concluding equivalence; the API floor stands
in for the unobserved UI floor):

| Metric | Pairing | True gap 0 | 0.05 | 0.10 (false equivalence) |
|---|---|---|---|---|
| Brands (Haiku draft) | optimistic | 1.00 | 0.90 | 0.08 |
| Brands (Haiku draft) | conservative | 0.92 | 0.49 | 0.04 |
| Brands (lexicon v0) | optimistic | 1.00 | 0.98 | 0.08 |
| Brands (lexicon v0) | conservative | 0.99 | 0.62 | 0.05 |
| Cited domains | optimistic | 1.00 | 0.99 | 0.33 |
| Cited domains | conservative | 1.00 | 0.80 | 0.16 |

"Optimistic" treats the 3 + 3 pairs per prompt as independent;
"conservative" keeps one of each. The pilot's cheap-model gaps (0.17 to
0.29 on Haiku draft names, 0.24 to 0.38 on lexicon v0, measured against the
API floor) are large relative to the band, so a REAL verdict is well powered
for the cheap arms; equivalence is powered only for arms whose true gap is
near 0. The high false-equivalence rate on per-answer cited domains is why
the domain gaps are secondary.

**Panel-share construction and why it is secondary** (resolves the draft's
open decision 1). A vendor sold in one category appears in at most 2 of 40
prompts, so shares pooled over the panel all sit near or below 0.05 and a
pooled test would pass by construction; shares are therefore per category.
Two statistics were simulated at the confirmatory design (20 categories
drawn from the pilot's 10, 2 prompts x 3 waves = 6 answers per arm per
category, pilot-scale true shares, 200 studies x 1,000 bootstrap draws;
`results/pilot_report.md` has the full table):

- **Excess MAD** (MAD over cells with UI share at least 1/3, minus the MAD
  expected from sampling alone). Passes easily when the arms agree, but a
  single cell's share difference at 6 answers has a sampling SD near 0.27,
  and the absolute difference of two noisy shares responds weakly to a small
  true difference. Brands: pass rate 0.92 to 0.95 at a true difference of 0,
  but still 0.36 to 0.57 at 0.05 (the false-pass rate) and 0.005 to 0.02 at
  0.10. Cited domains: 0.88 pass even at 0.10. Not a valid equivalence test.
- **Noise-corrected RMSD** (basket on the pooled share, so selection does
  not inflate the difference). Unbiased when prompts do not share effects
  (estimate 0.024 at a true 0.05, 0.100 at 0.10), but its upper bound
  cannot reach 0.05 at this sample size: pass rate 0.02 to 0.15 at a true 0
  (brands and domains alike). A shared prompt effect (Beta, k = 4) biases
  the estimate downward. Detection of a real difference (lower bound above
  0) at a true 0.10: 0.10 to 0.35. A threshold of 1/4 instead of 1/3 enlarges
  the basket (about 255 vs 225 brand cells, 315 vs 220 domain cells) without
  changing either conclusion.

| Statistic (basket) | Metric | True diff 0 | 0.025 | 0.05 (false pass) | 0.10 |
|---|---|---|---|---|---|
| Excess MAD (UI >= 1/3) | brands | 0.92 to 0.95 | 0.74 to 0.82 | 0.36 to 0.57 | 0.005 to 0.02 |
| Excess MAD (UI >= 1/3) | cited domains | 0.98 to 0.99 | 0.99 | 0.98 to 0.99 | 0.88 |
| RMSD (pooled >= 1/3) | brands | 0.03 to 0.10 | 0.02 to 0.09 | 0.01 to 0.045 | 0.00 |
| RMSD (pooled >= 1/3) | cited domains | 0.02 to 0.15 | 0.02 to 0.10 | 0.005 to 0.045 | 0.00 |

(Pass rates; ranges span the two prompt-effect settings. Expected basket at
the confirmatory design: about 225 brand cells and 210 to 230 cited-domain
cells at pooled share 1/3; about 240 and 270 at UI share 1/3.)

**Decision (smallest change that fixes it):** panel shares cannot support an
equivalence claim at 6 answers per category, so H1s and H1d are demoted to
secondary estimation: noise-corrected RMSD with its 90% CI, pooled-share
basket at 1/3, reported against the 0.05 reference line but never as a
pass. The primary family keeps the per-answer brand test (H1b), which the
pilot simulation powers. A share equivalence test would need several times
more answers per category (more prompts per category or more waves).

**UI noise floor (still open).** H1b uses the UI's own within-prompt floor,
which the pilot did not observe (one UI wave). Waves 1 to 3 supply it; the
power table above assumes it equals the API floor.

**Descriptive outcomes (no test):** searches per answer, no-search rate,
cited and evaluated counts, source-class mix of cited domains, answer
length, brands per answer, and measured $/call per arm (batch pricing,
`aeo_research.pricing`, cache effects included). The $/call table feeds the
Claude add-on cost model.

**Lexicon protocol.** Haiku 4.5 proposes candidates for every wave 1 answer
(all arms); they are merged into lexicon v0 under the rules in
`harness/lexicon_rules.md`; a person reviews every row; the file's sha256 is
recorded here; extraction is then deterministic (longest alias first, word
boundaries, first-mention order, per-category rows). This happens after
wave 1 answers are in and before any confirmatory metric is computed. Audit
D validates it.

**Lexicon v1, frozen 2026-09-28:** `data/raw/lexicon_v1.csv`, sha256
`9425a4d3f2d393b59eb925c96a2b69dc8be9aa639d1f8446465815866bc263e3`.
950 rows (600 keep, 350 drop) across all 20 categories. Candidates came from
`harness/lexicon_candidates.py --wave 1` (360 answers, $0.62). The rows
were curated under deviation 3 and reviewed by Jim (deviation 4). No
confirmatory metric had been computed.

## 6. Known traps for this design

- **The UI is one account.** Results describe a fresh, depersonalized Pro
  account; account-level experiments or rollouts on claude.ai are invisible
  to us. The collector records the model and reasoning labels each session.
- **Search stack mismatch.** claude.ai has `web_search_fast` and `web_fetch`;
  the API arms have `web_search` only. Divergence on cited domains is partly
  a tool difference; the write-up says so.
- **Search skips.** Some Sonnet configurations answer without searching
  (pilot: up to 3 of 10). No-search answers have empty cited sets; they are
  kept (that is the product behavior) and excluded in R3.
- **Batch vs realtime.** API arms run on the Batches API during the UI
  session; batch completion can lag by up to hours. The run_date is shared;
  exact timing is recorded.
- **Cache effects on cost.** First calls per arm pay 1-hour cache writes;
  $/call is reported per wave with and without the first call.
- **Lexicon built partly in-sample.** v0 came from pilot answers; wave 1
  candidates extend it for all 20 categories. The same lexicon applies to
  every arm, so it cannot favor one arm by construction, but a brand only one
  arm names could be missed by the candidate pass (Audit D recall check).
- **Categories are clusters.** Two prompts per category share vendors, so
  prompt-level resampling can understate uncertainty; R6 checks it.
- **Cost cap:** `--max-cost 250` on the study ledger; estimate about $90.

## 7. Robustness checks

1. H_pos first; if it fails, stop.
2. H_pla is reported for every primary arm and does not gate the analysis (deviation 8).
3. R1: top-10 brands instead of all brands (H1b).
4. R2: RBO on brand order instead of set Jaccard.
5. R3: exclude answers with no search (domain tests).
6. R4: Haiku-candidate extraction mapped through the frozen lexicon instead
   of lexicon matching (H1b, H1s).
7. R5: drop one wave at a time (H1b, H1d).
8. R6: category-level cluster bootstrap (H1b, H1s).
9. R7: exclude UI chats flagged in collector notes.

## 8. Deliverables and sequence

1. Harness, smoke and pilot (DONE 2026-09-25/26; §A).
2. Resolve the §5 open decisions; power simulation for H1s / H1d; move the
   extraction code to `pipeline/`.
3. Pipeline dry run on synthetic data: planted equivalent and divergent arms
   are recovered; `03_model.py` exits non-zero when H_pos fails.
4. Freeze (two commits), record hash and seed.
5. Waves 1 to 3 (API batch during each UI session; export and ingest after).
6. Lexicon extension from wave 1 candidates, review, freeze (DONE 2026-09-28; sha256 under the lexicon protocol in §5).
7. `01_features` to `04_figures`, Audit D (signed), robustness suite.
8. STOP for results review (`results/model_summary.txt`, figures, cost per
   arm).
9. Only if approved: article, release (`05_release.py`, signed checklist,
   prompts under the synthetic exemption), companion blog post (EN and DE).

## 9. Notes for the write-up

- Lead figure: per-arm gap to the UI (brands and cited domains) against
  $/call, with the UI's own day-to-day floor as a reference band.
- Framing: the question every Claude tracking vendor faces, answered with
  measured cost. State the equivalence bound: "we could have detected a
  0.10 Jaccard gap / a 5-point share gap."
- Say plainly what the UI arm is (a fresh account, personalization off, one
  city) and what the leak arms are (instrument divergence, provenance
  unverified).
- Sample size phrased as "N answers evaluated (in this study)".
- Prompts may be published (synthetic exemption); answers and search
  queries never.

## Deviations from the frozen spec

1. **Clarifying questions in UI chats (2026-09-27, wave 1).** In 3 of 80
   wave 1 chats, claude.ai asked clarifying questions with its
   `ask_user_input_v0` widget: `ui_default/b2b_28`, `ui_think/b2b_28` and
   `ui_think/b2b_36`. The collector answered them, and the questions,
   options and selections are recorded in `data/raw/ui_sheets/w1_notes.md`.
   The spec did not cover this. The API arms cannot ask and never get the
   extra context, so only the first reply is scored, up to the second human
   message. The full chat is kept as `normalized.full_chat`, and each
   response carries `normalized.clarifying_questions`. These chats are
   flagged in the collector notes, so R7 is the sensitivity check that drops
   them. The same rule applies to waves 2 and 3. Decided by Jim before any
   confirmatory metric was computed.
2. **Wave 1 UI chat out of order (2026-09-27).** Sheet row 63,
   `ui_think/b2b_09`, was skipped during the session. It was run at 17:17
   ET, after row 80, on the same day and account, and the export was
   redone.
3. **Lexicon unit and sources blocks (2026-09-27, before the lexicon
   freeze and before any confirmatory metric).** Three changes, decided by
   Jim during wave 1 curation:
   - *Unit is the brand the answer names.* `harness/lexicon_rules.md`
     merged acquired products and product lines into the vendor that owns
     them. Curation showed that this rests on ownership facts that often came
     from the answers themselves and could not be verified, and it hides
     which brand the buyer was shown. The unit is now the brand as named: a
     product with its own distinctive name is its own row, and only renames
     and descriptively named product lines merge. A bare company name counts
     only when the company name is itself the brand; where the company has
     its own product row in the category, the bare name is a drop row, so
     one vendor is not counted twice.
   - *The buyer's other systems* are dropped in every category, including
     vendors v0 had kept when they were named only as integration targets.
   - *Sources blocks are stripped before extraction.* The production
     discovery prompt asks for the sources consulted, so 33 of 40 wave 1
     `sonnet5_prod` answers end with a labelled list of publishers and vendor
     sites. `pilot_report.strip_sources` removes the label and its list for
     every arm; in wave 1 it changes only those 33 answers.
   - *Open-source tools* count as brands when the answer presents them as
     an option in the category. They are dropped only when named as a
     component, engine or source system. The rules had dropped open-source
     projects everywhere; Jim changed this at review (2026-09-28).
4. **Lexicon review scope (2026-09-28).** The protocol says a person
   reviews every row. Jim reviewed 416 of 950 rows by hand. They are every
   row the curators flagged (131; Jim changed 9 decisions) and every other
   row that matched five or more wave 1 answers (285; no changes). Together
   they cover 81% of the kept brand matches in wave 1. The other 534 rows
   each match four or fewer answers and were curated by model only. Audit D's
   30-response spot check covers them. Three further open-source rows,
   matching four answers in all, were switched to keep to apply Jim's
   open-source call consistently.
5. **Wave 2 API batch finished the next day (2026-09-30).** The batch was
   submitted at 17:40 EDT on 2026-09-29, during the second UI session.
   The UI chats ran from 12:24 to 18:59 EDT. At 23:44 EDT none of its 280
   requests had finished, and it ended at 04:20 EDT on 2026-09-30. The
   answers were therefore generated about 5 to 10 hours after the UI chats,
   on the next calendar day, beyond the "hours" of lag the batch-vs-realtime
   caveat anticipates. The run_date and the date in the leak prompt stay
   2026-09-29. Wave 1's batch ended within the UI day. Wave 3's batch is
   submitted at the start of the first UI session to reduce the gap. R5
   (drop one wave at a time) shows whether wave 2 moves the results.
6. **Pipeline and domain map built after collection (2026-10-01).** §8
   steps 2 and 3 placed the move of extraction to `pipeline/`, the analysis
   scripts and the synthetic dry run before the freeze. They were not done
   then. The pipeline (`01_features` to `04_figures`) and the synthetic dry
   run were built after wave 3 was collected. The source-class domain map
   (§3) was drafted then too, for review by a person. Before any
   confirmatory metric was computed on real data, the synthetic dry run had
   to pass, Audit D had to pass, and the domain map had to be frozen.
   `03_model.py` was first run on real data only after all three.
7. **Lexicon extended with waves 2 and 3 (2026-10-01, before any
   confirmatory metric).** Lexicon v1 was built from wave 1 candidates only.
   Haiku candidates for waves 2 and 3 showed it missed 6.9% and 8.1% of
   their brand names (0.3% in wave 1), mostly long-tail vendors. Missing
   names drop out of every arm's brand set. That censors the long tail and
   biases the brand comparison toward equivalence. The wave 2 and 3
   candidates (434 uncovered category-brand rows) were curated into lexicon
   v2 under the same rules. v1 decisions were left unchanged except
   where Jim corrected them at review. That covered nine bare company
   names that the bare-company rule should already have dropped, one
   keep, and two renames or mergers folded into one brand. Otherwise only
   aliases and new rows were added. Jim reviewed every flagged new row and
   every new row matching five or more answers. v2 replaces v1 for all
   extraction, and Audit D runs on v2. Lexicon v2, frozen 2026-10-01:
   `data/raw/lexicon_v2.csv`, sha256
   `a2745081980cb819b7de7e0dc698d0fecb001fc7a677259e68d57bf5c744e1eb`,
   1,324 rows (788 keep, 536 drop). 0.3% of Haiku brand names have no
   alias, in every wave.
8. **The placebo does not block (2026-10-01).** §7 says H_pla must be NULL
   or NEGLIGIBLE. The synthetic dry run showed the odd/even split roughly
   doubles the CI width: with no planted effect, 2 of 3 primary arms came
   out INCONCLUSIVE. H_pla is reported for every primary arm and never stops
   or gates the analysis. A REAL placebo gap is reported as a caveat on
   H1b.
9. **Panel shares are descriptive (2026-10-01).** The noise-corrected RMSD
   for H1s/H1d failed the synthetic dry run, so the reported statistic
   changed. It subtracts a sampling-noise term that treats an arm's 6
   answers in a category as independent. They are 2 prompts asked 3 times,
   and answers to one prompt are highly consistent. The correction
   therefore over-subtracts, and arms planted to match the UI scored about
   -0.20. Its prompt-level bootstrap interval also failed to cover its own
   estimate. In its place, each API arm's within-category vendor ranking is
   compared with `ui_default`'s and averaged over categories, with a 90%
   category-level bootstrap interval and no verdict. Two questions are
   answered: (a) same vendors in the same order (RBO of share-ranked
   lists, Kendall tau over the pooled basket) and (b) same vendors
   regardless of order (Jaccard of vendors named in at least 2 of 6
   answers, and of all vendors named). Cited domains get the same
   treatment, and `ui_think` vs `ui_default` is shown as a reference. The
   per-answer tests are unchanged: H1b (primary) answers (b) per answer and
   the RBO gap answers (a).
