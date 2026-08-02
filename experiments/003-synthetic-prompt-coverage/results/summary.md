# Experiment 003 — results summary

**Synthetic prompt panels don't see the market human prompts see**
Analysis run 2026-08-02 on the complete dataset, per the frozen spec
(commit 8ab4519, 2026-07-29). 1,325 runs evaluated in this study
(143 hum + 37 spy_a + 37 spy_b + 40 neu prompts × 5 daily waves,
plus 40 coffee contrast prompts × 1 wave). Collection cost $3.18.
Single model era throughout: `gpt-5-5` (R6 not triggered).

## Gate and placebo

- **H_pos (gate): PASS.** between:hum minus cross-intent cited-domain
  Jaccard = 0.295 [0.262, 0.327], permutation p = 0.0002. Consistent with
  the wave-1 early gate (0.296) and 002's 0.289. The instrument
  distinguishes same-intent from different-intent; collection and
  extraction are working.
- **H_pla (placebo): NULL.** Parity split 0.001 [−0.005, 0.009].

## Verdicts at a glance

| Layer | spy_a (Bose anchor) | spy_b (Soundcore anchor) | neu (scenario-only) |
|---|---|---|---|
| H1 exchangeability — brands | **REAL divergence** (−0.200) | **REAL** (−0.228) | NULL = equivalent (−0.041) |
| H1 — cited domains | **REAL** (−0.123) | **REAL** (−0.170) | NULL = equivalent (−0.030) |
| H1 — grounding tokens | **REAL** (−0.197) | **REAL** (−0.234) | **REAL** (−0.084) |
| H2 share agreement (MAD, band 0.05) | **REAL** 0.248, τ = 0.867 | **REAL** 0.261, τ = 0.200 | **REAL** 0.112, τ = 0.733 |
| H3 anchor bias | see DiD below | see DiD below | — |

SESOI 0.10 absolute Jaccard (H1) / 0.05 share MAD (H2); 90% cluster-bootstrap
CIs, prompt-level clusters, seed 20260729.

## H1 — exchangeability (article Q3)

Both **brand-anchored** panels fail exchangeability on **all three artifact
families**: a synthetic prompt's response overlaps a human prompt's response
0.12–0.23 Jaccard *less* than two different human prompts overlap each other
— every CI excludes zero and extends beyond the ±0.10 band.

- spy_a: brands −0.200 [−0.266, −0.134]; domains −0.123 [−0.165, −0.081];
  grounding −0.197 [−0.231, −0.164]
- spy_b: brands −0.228 [−0.282, −0.176]; domains −0.170 [−0.209, −0.133];
  grounding −0.234 [−0.266, −0.202]

The **neutral** panel is practically equivalent on response content: brands
−0.041 [−0.085, 0.002] and domains −0.030 [−0.062, 0.001] both sit inside
the band (NULL). Its grounding-token contrast is −0.084 [−0.118, −0.050]
— the estimate is inside the band but the CI reaches past it, so by the
pre-registered rule it is REAL and we report it as a modest but detectable
retrieval-behavior gap.

This **refines the mechanistic prior**: retrieval normalization is not
unconditional. A fluent same-intent prompt lands in-distribution only when
its content distribution does (neu); prompts sampled from a brand's catalog
frame sit far enough from the buyer population that even single-response
overlap degrades.

## H2 — panel share agreement (article Q7)

All three panels fail, including the one that passed H1. Basket: 6 brands
with human-panel share ≥ 5% (Sony, Bose, Sennheiser, Anker, Apple, JBL).

- spy_a: MAD 0.248 [0.174, 0.325] — 5× the band. Rank τ = 0.867.
- spy_b: MAD 0.261 [0.225, 0.317] — 5× the band. Rank τ = **0.200**: the
  Soundcore-anchored panel doesn't just shift levels, it **scrambles the
  brand ranking** (it sees Sony at 33.5% of responses vs the human panel's
  87.7%, Sennheiser at 16.2% vs 77.6%).
- neu: MAD 0.112 [0.082, 0.157] — **the predicted H1-holds/H2-fails
  dissociation appeared.** Every neutral prompt is individually
  in-distribution, but the panel's *mix* still misses the human share
  vector by more than twice the band (τ = 0.733).

The equivalence bound is the claim: we could have detected agreement within
5 share points and found none — the best panel missed by 11 on average.

## H3 — anchor bias (article Q6)

- **DiD = +0.411 [+0.189, +0.638] → anchor bias DETECTED.** Swapping the
  generator's anchor from Soundcore to Bose moves the measured Bose-vs-Anker
  share gap by **41 points**. Panel configuration determines the result.
- Decomposition (own-anchor share vs human panel):
  spy_a(Bose) −0.272 [−0.401, −0.148]; spy_b(Anker) +0.044 [−0.062, +0.149]
  — neither panel inflates its own anchor *above the human baseline*.
- **The mechanism is rival suppression, not self-inflation.** Pooled shares:
  Bose — hum 0.824, spy_a 0.551, spy_b 0.568 (the panels roughly tie);
  Anker — hum 0.729, spy_b 0.773 (≈ human), spy_a **0.346**. Each anchored
  panel surfaces its own anchor at whatever level its content frame allows,
  but *fails to surface the rival* the human panel sees. A Bose marketer
  reading the Bose-anchored panel would see Anker at half its real
  visibility.

## H4 — phrasing coverage (article Q17, descriptive)

- Human prompts: median 30 words (3–274). Synthetic: 11–16 words, σ ≈ 3.4.
- Behaviors **never emitted** by any synthetic panel: age of the recipient,
  requested output count ("give me 5"), output format, movie/in-flight
  usage. spy_a additionally never states a budget, names a recipient, or
  asks for review-star evidence.
- Over-emitted: form-factor terms (spy_b +67 points — the Soundcore catalog
  tilt made visible) and wireless/connectivity (+24 to +27).
- Profile coverage: the panels reproduce **5–8%** of the 79 distinct human
  flag-profiles (spy_a 8%, spy_b 6%, neu 5%).

## Auxiliary finding — the empty quarter of the anchored panel

25.4% of spy_a responses contain **zero recommended brands** (hum: 5.7%,
spy_b: 2.7%, neu: 3.0%). Ten of spy_a's 37 prompts — concentrated in the
`category_entry_points` (5 of 8) and `buyers_journey` (4 of 8) frameworks —
consistently draw long informational answers (median 409 words) with no
brand recommendations at all. A quarter of the Bose-anchored panel measures
nothing brand-shaped, which mechanically depresses every spy_a share and is
part of why own-anchor share sits below the human baseline.

## Replication of 002's geometry

Same instrument, one month later, fresh collection: between:hum brand
Jaccard 0.528 [0.482, 0.573] (002: 0.537); within:hum 0.724 [0.699, 0.747]
(002: 0.736). Human-panel brand shares also track 002's finals (Sony .877
vs .897, Bose .824 vs .820, Sennheiser .776 vs .802, Anker .729 vs .683,
Apple .485 vs .448, JBL .241 vs .167). The phrasing-effect baseline
replicates.

## Robustness

- R1 (rank-sensitive RBO): anchored-panel divergence survives (spy_a −0.093,
  spy_b −0.271). neu flips slightly REAL (−0.070 [−0.110, −0.032]): neutral
  prompts are set-exchangeable but show a small *rank-order* divergence —
  reported honestly alongside the H1 NULL.
- R2 (drop wave 1) and R3 (drop duplicate prompts): all verdicts unchanged.
- R4 (non-empty fan-outs only): grounding divergences unchanged.
- R5 (repeatability): synthetic prompts are also **noisier run-to-run** —
  within-prompt brand overlap is 0.09–0.11 lower than human prompts' across
  all three panels (REAL). Synthetic prompts occupy a less stable region of
  the response space even before comparing across panels.
- R6: single model (`gpt-5-5`) all waves — no subset refit needed.

## Audits

- **A:** 1,325/1,325 collected, zero failures. Empty fan-out rates per arm
  0.039–0.092, far under the 0.30 INCONCLUSIVE threshold.
- **B:** label definitions quoted from code in `results/audit.txt`.
- **C:** pair counts by condition in `results/audit.txt`; inference is
  prompt-level cluster bootstrap throughout.
- **D:** extractor recovered 100% of DataForSEO's own brand-entity
  annotations (180/1,285 responses carried them). 002-seeded lexicon entered
  unchanged (wave-1 mining found no new brands). **Manual 30-response
  spot-check still owed** — sample regenerated 2026-08-02 at
  `data/interim/spotcheck_sample.md`; requires precision ≥ 0.95 / recall
  ≥ 0.90 sign-off before release.

## The defensible claim (spec §1, filled in)

For one commercial-recommendation intent on ChatGPT via DataForSEO's
scraper, over one week: a brand-anchored synthetic prompt panel measured a
brand-share vector that differed from the human panel's by **25–26 points
on average** (neutral panel: 11 points; equivalence band 5), did **not**
inflate its own anchor's share above the human baseline but **suppressed
the rival anchor's** — swapping the anchor moved the measured
Bose-vs-Anker gap by **41 points** — and its responses overlapped
human-prompt responses **0.12–0.23 Jaccard less** than differently-worded
human prompts overlap each other (neutral panel: statistically
indistinguishable on brands and domains, band 0.10).

Not claimed: anything about other intents, platforms, locales, other
vendors' generators, prompt-weighting schemes, logged-in behavior, or
whether any synthetic panel *could* match humans. One draw per generator
configuration — conclusions are about "a panel this generator produced."

## Post-hoc interpretation layer (added 2026-08-02, exploratory)

`results/exploratory_content_mix.md` (`pipeline/91_content_mix.py`; figures
`content-mix-reweight` F5, `panel-rank-swing` F6):

- **Funnel stage:** restricting the spy panels to decision-stage prompts
  (the subset the product scores for share of voice) shrinks spy_a's H2 MAD
  0.248 → 0.162, leaves spy_b's unchanged (0.261 → 0.280), and *grows* the
  anchor DiD to +0.571 — the pre-registered verdicts are not a funnel-stage
  artifact.
- **Content mix:** raking the human panel to each spy panel's phrasing-flag
  mix explains **72%** of spy_a's share gap (eff. n 15) and 37% of spy_b's
  (eff. n 7): an anchored panel largely measures the anchor's own claimed
  territory. 002's budget flip (Bose −0.25 / JBL +0.32) replicates.
- **Home turf:** Bose ranks 2nd on every panel including its own (the
  instrument does not flatter its anchor); Anker swings 1st ↔ 5th purely by
  anchor choice. Supports the conditional-share-of-voice reading: winning
  on your own panel needs context, losing on it is the signal.

## Remaining steps to close the project

1. **Jim: label the Audit-D spot-check** (30 responses,
   `data/interim/spotcheck_sample.md`) → write
   `results/audit-d-signoff.md`. If thresholds fail, refine lexicon, log a
   deviation, re-run 01→04.
2. **Jim: sign `results/release-checklist.md`**, then commit
   `data/public/` (CSV + datasheet).
3. Research article + companion blog post (EN/DE) — full outline with
   narrative arc, figure map, and compliance checklist in
   `results/article-outline.md`.
