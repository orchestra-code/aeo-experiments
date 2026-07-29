# Synthetic prompt panels don't see the market human prompts see — study spec

**Status:** frozen (2026-07-29, before wave-1 submission)
**Frozen commit:** 8ab4519 (spec + pipeline + harness + toolkit, this repo)
**Experiment slug:** `003-synthetic-prompt-coverage`

> Freeze rule: everything in §4 (hypotheses) and §5 (model + decision rule) is
> fixed before anyone looks at the joined data. Count-only data-quality checks
> and prompt-side shape statistics (lengths, flag prevalence — no response
> data) are allowed pre-freeze; response data is not collected until after
> the freeze. The brand LEXICON (pipeline/brands.py, seeded verbatim from
> 002's post-curation state) is extraction code, not a hypothesis: it may be
> re-curated from wave-1 mining, validated in Audit D, then held fixed; any
> later change is logged under "Deviations from the frozen spec". The three
> synthetic prompt panels were generated ONCE (2026-07-29) and are frozen as
> data in data/raw/generator/ — they are the measured objects, not tunable
> inputs; regenerating them after seeing responses would be a protocol
> violation.

---

## A. Pre-freeze findings (harness runs + 002 carry-overs, 2026-07-29)

Allowed pre-freeze: prompt-side shape observations, no response data.

- Panels generated: `spy_a` 37 prompts (bose.com anchor; snapshot name=Bose,
  category="Consumer Electronics"), `spy_b` 37 (soundcore.com; name=Soundcore,
  category="Headphones & Speakers"), `neu` 40 (scenario-only brief). Zero
  brand-name leaks, zero year mentions, zero exact duplicates in all three.
- **Length gap is visible before any collection**: human prompts median 30
  words (range 3–274 after the h054 exclusion); spy_a median 13 (9–19);
  spy_b median 11 (7–18); neu median 16 (7–24). Synthetic panels are short
  and uniform; humans ramble, story-tell, and paste constraints.
- spy_b's panel visibly tilts toward earbuds/workout/outdoor use-cases
  (Soundcore's product mix) rather than the survey's travel-gift scenario —
  the anchor's catalog steers the sampling frame. One spy_b prompt even
  phrases the category as a "platform" (framework template bleed-through).
- h016 (kept) is a respondent's refusal text ("I would not use AI for
  this..."), pasted into both survey questions — valid human behavior that no
  generator emits; its coffee twin c016 sits in the contrast panel.
- Smoke test (2 throwaway non-study prompts, separate ledger, 2026-07-29):
  both collected clean; `result.model` = `gpt-5-5` — the SAME model era as
  002, so the 002 share anchors in Audit D are likely to be tight rather than
  loose. `fan_out_queries` came back with a single query per response again;
  `sources[]` sparse (1 and 4) vs `search_results[]` (11 and 9), as in 002.
- Carry-overs from 002 (same instrument): DataForSEO rejects keywords over
  ~2,000 chars (h054 pre-excluded here); `sources[]` are citations,
  `search_results[]` are SERP extras; `result.model`/`fan_out_queries` can
  come back null in a batch (002 wave 7: 74/143 rows); empty∩empty overlap
  pairs are NaN, never 0.

## 0. One-paragraph summary

Prompt-tracking vendors measure "AI visibility" on panels of synthetic
prompts — configured, generated, or keyword-derived — and present the result
as what the market sees. Experiment 002 established the baseline geometry of
one intent (headphones-as-travel-gift, 143 human phrasings, ChatGPT via
DataForSEO): within-prompt brand Jaccard 0.736, between-prompt 0.537, a REAL
phrasing effect. 003 asks the next question: **if you swap the human panel
for a synthetic one, do you still measure the same market?** We run four
panels side by side for 5 days on the same platform: the human survey prompts
(re-run fresh — never compared against 002's July responses, a different
model era), two panels from the production Spyglasses generator anchored on
different brands (Bose = incumbent, Soundcore = mid-tier), and one neutral
scenario-only generated panel. We test (H1) whether synthetic→human response
overlap matches the human↔human between-prompt baseline, (H2) whether panel
brand-share vectors agree within 5 points, and (H3) whether a brand-anchored
panel inflates its own anchor's measured share — the "does panel
configuration determine the result?" question, answered with a
difference-in-differences across the two anchors. Expectation from the 002
mechanistic prior: retrieval normalizes phrasing, so H1 should land near the
between-prompt baseline; but the anchored generator optimizes prompts to
surface its brand, so we predict REAL anchor bias in H3 and coverage gaps in
the H4 flag profile.

## 1. The claim we can and cannot make

**What this design measures:** for one commercial-recommendation intent, on
one platform (ChatGPT with web search forced, via DataForSEO's scraper,
en-US), over one week: how closely do three specific synthetic prompt panels
reproduce (a) the pairwise response overlap, (b) the brand mention-share
vector, and (c) the phrasing-feature coverage of 143 contemporaneous
human-written prompts for the same intent — and whether the generator's brand
anchor shifts its own brand's measured share.

**What this design does NOT measure:** other intents, platforms, locales, or
vendors' generators (we test Spyglasses' own plus one neutral baseline);
logged-in/personalized behavior; whether ANY synthetic panel could match
humans (only whether these did); prompt *weighting* schemes (all prompts
count equally here, as in the product); or which brands deserve their share.
"Via DataForSEO's scraper" remains part of every claim.

**Defensible claim:** "A brand-anchored synthetic prompt panel measured a
brand-share vector that differed from the human panel's by X points on
average, inflated its own anchor's share by Y points [or did not], and its
responses overlapped human-prompt responses no less [/ Z points less] than
differently-worded human prompts overlap each other."

**Indefensible claim:** "Synthetic prompt tracking is meaningless" (or
"validated") in general, claims about other vendors' generators, other
intents/platforms, or any claim that panel-level agreement implies the
underlying score predicts business outcomes.

### Mechanistic prior

Two forces pull in opposite directions. (1) 002 showed ChatGPT's retrieval
pipeline normalizes phrasing: grounding queries and cited sources converge
across wildly different human wordings, so any fluent same-intent prompt —
synthetic included — should fall near the between-prompt overlap baseline.
This predicts H1 ≈ exchangeable. (2) The Spyglasses generator is built to
produce queries "that would likely surface the target company" from the
brand's own snapshot — its sampling frame is the brand's catalog, not the
buyer population. 002's exploratory sub-intent result (valued attributes
fragment outcomes: budget mentions flip Bose −0.36 / JBL +0.31) says prompt
*content* systematically steers brand sets. A panel whose content
distribution tilts toward the anchor's strengths should therefore tilt the
measured shares toward the anchor. This predicts REAL effects in H3 and
share-vector gaps in H2, concentrated on attribute-linked brands. If instead
H2/H3 come back null while H1 holds, retrieval normalization dominates and
synthetic panels are better proxies than the article assumes — an equally
publishable result.

## 2. Data-quality audits — run BEFORE the model

- **Audit A — degenerate responses.** Failed/stale tasks, empty markdown,
  zero extracted brands, empty `fan_out_queries` (despite
  `force_web_search: true`), zero sources — rates per arm × wave from the
  ledger + responses frame. Pre-registered policy: empty-vs-empty set pairs
  are NaN and excluded (rate reported); if >30% of any headphone arm's
  responses have empty fan-outs, that arm's grounding claims are
  INCONCLUSIVE regardless of CI.
- **Audit B — what the outcome labels mean.** Quoted from code:
  "brand recommended" = alias match of the frozen lexicon in cleaned answer
  markdown — `pipeline/brands.py::extract_brands` (verbatim 002 extraction);
  "domain cited" = registered domain of a normalized `result.sources[]` URL;
  "grounding tokens" = stopword-filtered token union over
  `result.fan_out_queries`; "panel share" = fraction of an arm's responses
  whose brand set contains the brand — `03_model.py::brand_share`.
- **Audit C — independence.** 143 hum + 37 + 37 + 40 synthetic prompts × 5
  waves, 40 coffee × 1 wave. Duplicate-text groups: h011/h044/h101/h111 (two
  pairs) and h016/c016 (cross-panel refusal twin) — kept, R3 refits without
  them. Synthetic prompts within an arm share generation ancestry BY DESIGN
  (that is the measured object — a panel, not independent draws); inference
  is prompt-level cluster bootstrap within arm, no pair-level SEs anywhere.
- **Audit D — extraction validity and drift.** (i) 30-response random
  spot-check: precision ≥ 0.95, recall ≥ 0.90, else refine lexicon and log.
  (ii) Anchor: hum-arm brand shares vs 002's finals (Sony .897, Bose .820,
  Sennheiser .802, Anker .683, Apple .448, JBL .167) — the model era differs,
  so drift is reported, not failed. (iii) `result.model` per arm × wave;
  drift triggers R6. (iv) DataForSEO `brand_entities` cross-check where
  present (validates the lexicon, never replaces it).

## 3. Data schema

One row per collected run (prompt × wave).

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| item_id / item_code | str | prompts.csv | derived-only (pseudonymized) | h/a/b/n/c### → `item_####` |
| panel (arm) | str | item_id prefix | yes | hum / spy_a / spy_b / neu / coffee |
| wave | int | ledger | yes | 1–5 (coffee: 1 only) |
| run_date | date | ledger collected_at | yes | |
| model | str | result.model | yes (public fact) | |
| prompt text | str | survey / generators | **never** — human text is SparkToro's; synthetic text is product-derived (prompts are proprietary per data policy) | stays in data/raw |
| framework / query_type | str | generator JSON | described in aggregate only | e.g. "8 of 37 from jobs_to_be_done" |
| answer markdown | str | result.markdown | **never** | interim only, feeds extraction |
| fan-out query text | str[] | result.fan_out_queries | **never** (token counts + derived overlap only) | |
| brands (ordered) | str[] | extraction | yes (public facts) | canonical names |
| cited URLs | str[] | result.sources[].url normalized | derived-only | domains publish; full URLs internal |
| cited domains | str[] | registered_domain(url) | yes (public facts) | |
| n_fanout, n_sources, n_brands, reply_word_count, had_web_search | int | derived | yes | |
| BrandSnapshot JSONs | json | harness | **never** (crawl-derived competitive profile) | generation provenance, data/raw only |

### Derived variables

Identical to 002 (URL normalization, registered-domain heuristic, grounding
token sets, Jaccard with empty∩empty→NaN, normalized truncated RBO p=0.9; no
embeddings anywhere). New in 003: per-arm **panel share** vectors (fraction
of responses mentioning each brand) and the H4 phrasing flags (002's 15
regexes, computed on prompt text of all panels).

## 4. Pre-registered hypotheses

Pair conditions (`aeo_research.overlap.arm_condition_pairs`):
**within:{arm}** (same prompt, different waves), **between:{arm}** (different
prompts, same arm, same wave), **cross:{a}|{b}** (different arms, same wave).
The phrasing contrast lives in same-wave pairs; `between:hum` is the
reference distribution throughout.

- **H1 (exchangeability, one per synthetic arm × {brands, domains, grounding
  tokens}):** Δ = mean(cross:hum|arm) − mean(between:hum) is practically
  equivalent to zero (|Δ| < 0.10 absolute Jaccard). I.e., a synthetic prompt's
  response overlaps a human prompt's response as much as two different human
  prompts' responses overlap each other. Verdict per arm; no averaging across
  arms.
- **H2 (panel share agreement, one per synthetic arm):** MAD =
  mean_b |share_arm(b) − share_hum(b)| over the basket B = {brands with
  hum-panel share ≥ 0.05}, pooled over waves. Equivalence if the 90% CI's
  upper bound < 0.05 (one-sided band — MAD is nonnegative). Kendall tau on
  the share ranks reported descriptively alongside.
- **H3 (anchor bias — the article's Q6):** three directional statistics, 90%
  cluster-bootstrap CIs, "detected" = CI excludes 0 from below:
  (a) share_spy_a(bose) − share_hum(bose); (b) share_spy_b(anker) −
  share_hum(anker); (c) DiD = [share_spy_a(bose) − share_spy_b(bose)] −
  [share_spy_a(anker) − share_spy_b(anker)]. The DiD is the primary carrier
  (it differences out panel-wide level effects); (a)/(b) decompose it.
- **H4 (coverage, exploratory, no test):** 002's 15 phrasing flags per panel:
  prevalence deltas vs hum, behaviors never emitted, length distributions,
  profile-coverage share. Descriptive by design — prompt-side only.
- **H_pos (positive control — must pass or the study stops):** between:hum
  cited-domain Jaccard exceeds cross:coffee|hum by ≥ 0.10 with the 90%
  cluster-bootstrap CI excluding 0 AND an arm-label permutation p < 0.05
  (wave-1 responses, hum vs coffee). 002 measured this gap at 0.289; if it
  vanishes, collection or extraction is broken.
- **H_pla (placebo):** parity split (odd/even item number) of between:hum
  pairs must be NULL/NEGLIGIBLE.

Reading H1 and H2 together matters: H1 can hold while H2 fails (every
synthetic prompt individually "in distribution", but the panel's *mix*
over-samples some sub-intents → shifted shares). That dissociation — fluent
prompts, wrong sampling frame — is the article's Q3/Q7 distinction and the
headline scenario we predict for the anchored arms.

## 5. Model and decision rule

**Model:** nonparametric throughout. H1: condition-mean differences of
pairwise overlap; prompt-level cluster bootstrap (dyadic weights c_i·c_j
between clusters, c_i within; 2,000 draws; 90% percentile CIs) —
`aeo_research.overlap.cluster_boot`. H2/H3: panel statistics bootstrapped by
resampling prompts with replacement independently within each arm (all waves
of a drawn prompt travel together) — `03_model.py::boot_share_stats`.
Permutation test for H_pos permutes hum/coffee labels over prompts (5,000
draws). Seed 20260729.

**SESOI:** 0.10 absolute Jaccard for H1 (one brand swapped in roughly half of
~5-brand answers — 002's band, kept for comparability). 0.05 absolute mean
share difference for H2: five points of mention share is the smallest gap
that would change a share-of-voice ranking decision between adjacent
competitors in the 002 share table (Bose .820 vs Sennheiser .802 differ by
less than 2 points; a 5-point instrument error scrambles such orderings).

**Decision rule (TOST logic at 90% CI, absolute scale):**

| Result | Conclusion |
|---|---|
| CI entirely inside ±SESOI | Practically equivalent — synthetic panel passes this layer |
| CI excludes 0, extends beyond band | Real divergence — report, quantify |
| CI excludes 0, inside band | Detectable but negligible — report honestly |
| CI wider than band, includes 0 | **Inconclusive — do NOT claim a null** |

H2 uses the one-sided variant (upper bound vs band). H3 is directional
estimation, not equivalence: report the CI; "bias detected" only if the CI
excludes 0 from below.

**Power:** the H1 machinery is 002's, already power-simulated in
`tests/test_overlap.py` (NULL at Δ=0, REAL at Δ=0.30, INCONCLUSIVE when
underpowered), extended with the cross-arm analogues
(`test_arm_power_sim_*`). The pipeline dry-runs end to end on `--synthetic`
data with a planted anchor bias (spy panels over-weight their own anchor 3×)
and a planted coffee floor; the dry run must PASS the gate and detect the
planted H3 effect before wave 1. Cross-arm pair counts per wave (~37×143 ≈
5.3k per arm) exceed 002's within-prompt counts; the binding constraint is
cluster count (37–40 synthetic prompts), which the INCONCLUSIVE row guards.

## 6. Known traps for this design

- **Scraper ≠ consumer product; contemporaneity is load-bearing.** All four
  panels run in the same waves on the same instrument. 002's July responses
  are NEVER joined into any test — different model era (002 saw `gpt-5-5`;
  Audit D reports what 003 sees). The 002 numbers quoted here are anchors
  and priors, not comparison data.
- **Generation is one-shot.** Panel quality varies run to run and we measure
  ONE draw per generator configuration — that is the vendor-realistic
  condition (a customer gets one panel), but it means arm-level conclusions
  are about "a panel this generator produced", not the generator's
  distribution. Stated in the write-up; the two spy arms double as partial
  replicates of the generator under different anchors.
- **Anchor confounding.** Bose and Soundcore differ in more than incumbency
  (catalog breadth, price tier). The DiD in H3 nets out panel-wide effects
  but cannot attribute the mechanism to "anchoring" vs "catalog tilt" — both
  are the same product behavior seen from different angles; the write-up
  treats them as one phenomenon.
- **Unequal panel sizes** (143 vs 37/37/40): all H1/H2 statistics are means
  over pairs/prompts, not counts; bootstrap CIs carry the width. No
  resampling to equalize.
- **Lexicon coverage bias**: synthetic panels might surface brands the
  headphone lexicon lacks (e.g. earbud-first brands from spy_b's tilt).
  Wave-1 `mine_candidates` re-curation + Audit D spot-check covers this; any
  addition is logged and applies to ALL arms.
- **Refusal/clarification answers** are valid rows with empty brand sets
  (NaN pairs); h016's refusal prompt is human behavior the generators never
  produce — excluded from nothing.
- **Shared DataForSEO account with production:** never call `tasks_ready`;
  poll `task_get` by our own stored ids only.
- **Cost cap:** 297 (wave 1, incl. coffee) + 257×4 = 1,325 tasks ≈ $3.18 at
  the $0.0024 priority rate; CLI cap 1,500 stays on.

## 7. Robustness checks

1. H_pos first — if it fails, stop (03_model exits 1).
2. H_pla placebo must be NULL/NEGLIGIBLE.
3. R1: rank-sensitive RBO instead of set Jaccard for each H1 brand contrast.
4. R2: drop wave 1 (lexicon-mining wave), refit H1 brands.
5. R3: drop duplicate-text prompts, refit H1 brands.
6. R4: grounding contrasts restricted to responses with non-empty fan-outs.
7. R5: within:arm vs within:hum repeatability contrast — do synthetic
   prompts even have the same run-to-run noise floor?
8. R6: dominant-model subset refit if `result.model` drifts mid-study.

## 8. Deliverables and sequence

1. Harness runs (DONE 2026-07-29, pre-freeze) → data/raw/generator/*.json
2. 00_prompts (panels → prompts.csv; counts asserted) — pre-freeze
3. 90_coverage_flags dry look allowed pre-freeze (prompt-side only)
4. Pipeline dry run: 01 --synthetic → 02 → 03 (gate must PASS, planted H3
   must be detected) → 04
5. Review + freeze spec (DONE 2026-07-29, hash above), then wave 1:
   `submit --intent headphones --wave 1` + `submit --intent coffee --wave 1`
   (tags `aeo-exp003-w1`), collect same day
6. Re-curate lexicon from wave-1 mining; Audit D spot-check
7. Waves 2–5 daily via run_wave.py (launchd `io.spyglasses.aeo-exp003`)
8. 01_features → 02_audit → 03_model (gate) → 04_figures → robustness → 90
9. 05_release (derived features only) + human release checklist
10. Article + companion blog post (EN/DE)

## 9. Notes for the write-up

- Lead figure: the share dot-plot (F1) — human bars, synthetic markers; the
  H3 carrier is the anchor-bias grouped bars (F4).
- Framing: constructive and self-implicating — we tested OUR OWN generator
  against the hardest baseline available (real humans, same intent, same
  week). Whatever H1–H3 return, publishing the number is the answer to "the
  burden of proof is on vendors." State plainly which layers pass and which
  don't; the H1-holds/H2-fails dissociation, if it appears, is the story.
- The article's Q3/Q6/Q7/Q17 map onto H1/H3/H2/H4 respectively — cite the
  question numbers explicitly in the article so readers can score us.
- Credit SparkToro prominently (survey provenance); reproducers are directed
  to Rand Fishkin for raw prompts. Synthetic prompt text withheld (product-
  derived); panels described by generation method + aggregate stats.
- Sample size phrased as "N runs evaluated (in this study)".
- Publish the equivalence bounds explicitly: "we could have detected a 0.10
  Jaccard shift / a 5-point share shift and found none" (or report what we
  found).

## Deviations from the frozen spec

- **2026-07-29 (wave 1):** wave 1 submitted and collected same day — 297/297
  tasks (257 headphone-panel + 40 coffee), zero failures, $0.71.
- **2026-07-29 (wave 1):** the H_pos gate was run EARLY, on wave-1 data only
  (Δ = 0.296 [0.257, 0.335], perm p = 0.0002, PASS — vs 002's 0.289), to
  avoid spending four more collection days on a broken pipeline; 002
  precedent. Extra discipline required here because, unlike 002, H1 *is*
  computable from wave-1 alone (cross-arm pairs are same-wave): a gate-only
  script (`results/early_gate_wave1.txt`) imported the frozen `h_pos_gate`
  and computed/printed nothing else. No other hypothesis was evaluated. The
  gate re-runs in its pre-registered position after wave 5.
- **2026-07-29 (wave 1):** lexicon candidate mining per §8 step 6 ran over
  wave-1 markdown (aggregate mention counts only, no per-arm shares): no
  unmatched brand candidates at the ≥5-mention threshold in either intent —
  every hit is a formatting artifact (Pros/Cons, star glyphs, prices). The
  002-seeded lexicon enters analysis UNCHANGED; the Audit-D 30-response
  manual spot-check still runs at analysis time.
