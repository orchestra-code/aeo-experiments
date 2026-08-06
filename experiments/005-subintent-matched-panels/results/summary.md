# Experiment 005 — results summary

**Matching the sub-intent mix buys exchangeable responses, not an
exchangeable market**
Analysis run 2026-08-06 on the complete dataset, per the frozen spec
(commit `80e6c09`, 2026-08-02). 1,230 runs evaluated in this study
(143 hum + 55 mat + 40 neu2 prompts × 5 daily waves, plus 40 coffee
contrast prompts × 1 wave). Collection cost $2.95. Single model era
throughout: `gpt-5-5` (R6 not triggered).

## Registered-prediction scorecard

The spec fixed five predictions in public before collection. Three held,
and the central one did not.

| # | Registered prediction (spec §0/§4) | Outcome |
|---|---|---|
| P1 | mat passes H1 (exchangeability) | **CONFIRMED** — brands −0.001, domains −0.001, grounding −0.054, all inside the 0.10 band |
| P2 | **mat passes H2 (share agreement)** | **FALSIFIED** — MAD 0.089 [0.071, 0.125], band 0.05 |
| P3 | neu2 passes H1 on brands + domains (003 replication) | **SPLIT** — domains NULL (+0.011); brands **REAL** (−0.055), the other side of the rule from 003's −0.041 |
| P4 | neu2 fails H2 | **CONFIRMED** — MAD 0.137 [0.100, 0.184] |
| P5 | H3′ NULL for mat's qualifying flags | **CONFIRMED** — travel −0.009, music −0.038, both NULL |

**The headline is P2.** Stratifying a synthetic panel to the human panel's
joint sub-intent profile made its responses individually indistinguishable
from human ones — marginally (H1) *and* inside matched strata (H3′) — and
still missed the human brand-share vector by 8.9 points against a 5-point
band. Sub-intent mix was **necessary but not sufficient**: it cut the gap
from neu2's 13.7 points to 8.9 (003's unstratified neu measured 11.2), and
it bought exchangeability that 003's anchored panels never had, but it did
not reach equivalence.

## Gate and placebo

- **H_pos (gate): PASS.** between:hum minus cross-intent cited-domain
  Jaccard = 0.306 [0.274, 0.338], permutation p = 0.0002. Consistent with
  003 (0.295) and 002 (0.289).
- **H_pla (placebo): NULL.** Parity split −0.003 [−0.008, 0.005].

## Verdicts at a glance

| Layer | mat (stratified) | neu2 (unstratified) |
|---|---|---|
| H1 — brands | **NULL = equivalent** (−0.001) | REAL divergence (−0.055) |
| H1 — cited domains | **NULL** (−0.001) | **NULL** (+0.011) |
| H1 — grounding tokens | NEGLIGIBLE (−0.054) | NEGLIGIBLE (−0.045) |
| H2 — share MAD (band 0.05) | **REAL** 0.089, τ = 0.867 | **REAL** 0.137, τ = 0.733 |
| H3′ — matched strata | **NULL** on both qualifying flags | REAL on both qualifying flags |

SESOI 0.10 absolute Jaccard (H1/H3′) / 0.05 share MAD (H2); 90%
cluster-bootstrap CIs, prompt-level clusters, seed 20260802.

## H1 — exchangeability (article Q3)

The stratified panel is **exactly on the human baseline** for both content
families: a mat prompt's response overlaps a human prompt's response
0.516 [0.477, 0.553] on brands against the human-human baseline of
0.517 [0.471, 0.559] — a difference of −0.001. Cited domains likewise
(0.306 vs 0.308). This is the cleanest exchangeability result in the
program; 003's best panel (neu) sat at −0.041 and its anchored panels at
−0.12 to −0.23.

- mat: brands −0.001 [−0.038, 0.037]; domains −0.001 [−0.030, 0.026];
  grounding −0.054 [−0.082, −0.028]
- neu2: brands −0.055 [−0.106, −0.006]; domains +0.011 [−0.022, 0.041];
  grounding −0.045 [−0.076, −0.016]

Two honest qualifications:

- **Grounding is NEGLIGIBLE, not NULL, for both arms.** The estimates sit
  inside the band but the CIs exclude zero — a small, detectable
  retrieval-behavior gap that survives R4 (non-empty fan-outs only).
  Directionally this *improves* on 003, where neu's grounding contrast
  (−0.084) reached past the band and was called REAL.
- **neu2's brand replication lands on the other side of the decision
  rule.** 003 measured neu at −0.041 [−0.085, 0.002] → NULL; 005's fresh
  draw measures −0.055 [−0.106, −0.006] → REAL, because the CI spills just
  past −0.10. The point estimates are close and the direction is the same;
  the verdict flip is a borderline-CI artifact, not a contradiction, and
  should be reported as such rather than as a failed replication.

## H2 — share agreement (article Q7) — the falsified prediction

Basket: the same 6 brands with human-panel share ≥ 5% (Sony, Bose,
Sennheiser, Anker, Apple, JBL).

- **mat: MAD 0.089 [0.071, 0.125] → REAL.** Rank τ = 0.867.
- **neu2: MAD 0.137 [0.100, 0.184] → REAL.** Rank τ = 0.733.

Per-brand (share of responses mentioning the brand):

| Brand | hum | mat | Δ | neu2 | Δ |
|---|---|---|---|---|---|
| Sony | 0.890 | 0.833 | −0.057 | 0.795 | −0.095 |
| Bose | 0.808 | 0.804 | **−0.005** | 0.720 | −0.088 |
| Sennheiser | 0.766 | 0.665 | −0.101 | 0.485 | −0.281 |
| Anker | 0.698 | 0.782 | +0.084 | 0.765 | +0.067 |
| Apple | 0.463 | 0.251 | **−0.212** | 0.280 | −0.183 |
| JBL | 0.234 | 0.156 | −0.077 | 0.125 | −0.109 |

Stratification bought real ground — Bose lands within half a point, and
Sennheiser's 28-point miss shrinks to 10 — but **Apple alone accounts for
40% of mat's total absolute deviation**, and the panel systematically
under-mentions five of six brands while over-mentioning Anker.

The equivalence bound is the claim: we could have detected agreement within
5 share points, and the sub-intent-matched panel missed by 8.9.

## H3′ — matched-stratum exchangeability (the pre-registered pilot)

The 003 pilot replicates for the stratified panel and fails for the
unstratified one:

- mat, travel_context (n=46): −0.009 [−0.051, +0.030] → **NULL**
- mat, usage_music (n=41): −0.038 [−0.088, +0.009] → **NULL**
- neu2, travel_context (n=32): −0.079 [−0.141, −0.024] → REAL
- neu2, recipient_named (n=17): +0.074 [+0.019, +0.122] → REAL

Read with H1: within a shared sub-intent, a stratified synthetic prompt is
interchangeable with a human one. The failure is **not** at the prompt
level at all — it is entirely in the panel's composition.

## H4 — phrasing coverage (exploratory, article Q17)

This is where the H2 residual lives. The manipulation worked precisely
where it was applied and nowhere else:

**Mean |prevalence delta| vs the human panel**

| Panel | the 6 stratified flags | the 9 unstratified flags |
|---|---|---|
| mat | **0.039** | 0.135 |
| neu2 | 0.197 | 0.094 |

Stratification cut error on its six target dimensions **5×** (0.197 →
0.039) and bought nothing on the other nine — mat is, if anything,
slightly further off there than the unstratified draw. That number is
dominated by one flag: mat emits comfort language in **45%** of prompts
against the human panel's 12% (+0.34), an artifact of the Mad-Libs clause
template. Excluding comfort, the two panels are effectively tied on the
unstratified flags (≈0.109 vs 0.102) — the honest statement is that
constraining six dimensions did not improve the other nine, not that it
actively degraded them.

- Behaviors mat **never emits**: recipient age, requested output count
  ("give me 5"), output format, movie/in-flight usage (human prevalence
  10%, 9%, 4%, 31%).
- Under-emitted: noise-cancellation (−0.13), star-rating/review evidence
  (−0.13), form factor (−0.06), battery (−0.06).
- Length: mat median 23 words (8–80) vs human 30 (3–274) — much closer
  than neu2's 15 (6–21), but the drawn band allocation under-sampled short
  prompts (0.127 realized vs the human marginal's 0.203).
- **Profile coverage: mat reproduces 13% of the 79 distinct human
  flag-profiles** (22 profiles), neu2 8%. Matching six marginals does not
  reconstruct the joint.

## Exploratory probe — is the Apple gap a brand-naming artifact? No.

(9× exploratory convention; not pre-registered. Probe script in the
session scratchpad — promote to `pipeline/91_*.py` only if this layer goes
into the article.)

Human prompts may name brands; synthetic panels are brand-name-free by
construction, so the obvious suspect for Apple's −0.212 is human prompts
saying "iPhone"/"AirPods". **It does not explain the gap.** Only 7 of 143
human prompts mention the Apple ecosystem; dropping them moves the human
Apple share 0.463 → 0.451 and mat's MAD 0.089 → 0.087. The human panel
surfaces Apple at ~45% even with every brand-naming prompt removed, against
mat's 25%. The residual is a property of what human phrasings *ask for*,
not of what they name — consistent with the unstratified-flag gaps above
(movies, noise cancellation, review evidence).

## Replication of 002/003 geometry

Same instrument, fresh collection: between:hum brand Jaccard 0.517
[0.471, 0.559] (003: 0.528; 002: 0.537); within:hum 0.704 [0.679, 0.726]
(003: 0.724; 002: 0.736). Human-panel shares track 003's anchor closely
(Sony .890 vs .877, Bose .808 vs .824, Sennheiser .766 vs .776, Anker .698
vs .729, Apple .463 vs .485, JBL .234 vs .241). Contemporaneity holds and
the phrasing-effect baseline replicates a third time.

## Robustness

- **R1 (rank-sensitive RBO): the verdicts invert.** mat −0.060
  [−0.101, −0.019] → REAL; neu2 −0.051 [−0.093, −0.011] → NEGLIGIBLE. The
  stratified panel reproduces **which** brands appear (set Jaccard −0.001)
  but not **the order** they appear in. Reported alongside the H1 NULL, as
  003 did for neu.
- R2 (drop wave 1) and R3 (drop duplicate prompts): all verdicts unchanged
  (mat −0.001 both; neu2 −0.064 / −0.056, still REAL).
- R4 (non-empty fan-outs only): grounding contrasts unchanged
  (mat −0.054, neu2 −0.045).
- R5 (repeatability): **NULL for both arms** (mat −0.038 [−0.086, 0.009],
  neu2 −0.018 [−0.060, 0.029]). 003's finding that synthetic prompts are
  noisier run-to-run does **not** reproduce here — these panels are as
  stable as the human one.
- R6: single model (`gpt-5-5`) all waves — no subset refit needed.

## Audits

- **A:** 1,230/1,230 collected, zero failures. Empty fan-out rate 0.000 for
  every arm (threshold 0.30) — grounding claims stay in scope. Zero empty
  replies. No-brand response rates: mat 0.018, hum 0.056, neu2 0.090,
  coffee 0.325 (the floor behaving as a floor).
- **B:** label definitions quoted from code in `results/audit.txt`.
- **C:** 89.9k mat×hum and 79.1k neu2×hum pairs; inference is prompt-level
  cluster bootstrap throughout (55/40 clusters is the binding constraint,
  guarded by the INCONCLUSIVE row — which no primary test hit).
- **D: PASS, signed 2026-08-06** (`results/audit-d-signoff.md`) — precision
  0.974, recall 0.919 on the program's first *independent blind* labelling
  pass (003's was a verification pass, which is anchored and weak on
  recall). The extractor also recovered **100%** of DataForSEO's own
  brand-entity annotations (287/1,190 responses carried them).
  Four extraction defects were found, quantified, and logged as deviations
  rather than refitted — the lexicon stays frozen:
  - **Apple's share is inflated by platform references** ("Apple Music",
    "Apple ecosystem"), differentially: 5.0% of human responses vs 1.1% of
    mat's. Restricting to product aliases narrows the Apple gap −0.212 →
    −0.173 and mat's H2 MAD to 0.0827. **~18% of the single largest
    per-brand deviation is an extraction artifact** — and it biases toward
    the headline, so it is stated in the article, not buried.
  - **JLab is untracked at 6.7% of human responses** — above the 5% floor,
    so the basket should have held 7 brands. Including it: mat 0.0783,
    neu2 0.1186. Verdicts unchanged.
  - HiFiMAN, iClever, Belkin, BuddyPhones and eKids are untracked and
    appear **only in the human arm** across all 1,190 responses —
    strengthening the finding that human prompts reach brands synthetic
    panels never do.
  - boAt, Noise and Nothing cannot be added safely (common English words);
    they need multi-word aliases.

  Both corrections push the same direction and neither moves a verdict off
  REAL; combined they leave mat near 0.073 against the 0.05 band. Audit
  power: 30 responses detects a 10%-prevalence brand ~96% of the time, 5%
  ~79%, 2% ~45% — deep-tail gaps likely remain, and recall is measured
  against what a human spotted, so it is an upper bound.
- **E (stratification manipulation check): PASS, exact cell match.** All 12
  strata hit their frozen targets exactly. Achieved length bands match the
  drawn allocation exactly; the draw itself under-represents short prompts
  vs the human marginal (logged above as a named residual suspect, not a
  deviation — the allocation was frozen pre-collection).

## The defensible claim (spec §1, filled in)

For one commercial-recommendation intent on ChatGPT via DataForSEO's
scraper, over five days: a synthetic panel stratified to a human panel's
joint sub-intent profile produced responses **statistically
indistinguishable** from human-prompt responses — 0.516 vs 0.517 brand
Jaccard, 0.306 vs 0.308 on cited domains, and equivalent inside matched
travel and music strata (band 0.10) — while still measuring a brand-share
vector **8.9 points off** the human panel's on average (band 5.0), where an
unstratified panel from the same generator missed by 13.7. The residual
concentrates in sub-intent dimensions outside the stratification target:
the stratified panel reproduces 13% of distinct human phrasing profiles,
never asks about movie use, recipient age, output count or format, and
over-emits comfort language 4×.

Not claimed: that a richer stratification would close the gap (untested);
anything about other intents, platforms, locales, or vendors' generators;
that the recipe transfers to intents lacking a human panel to stratify
*from* — that dependency is the recipe's stated cost. One draw per
generator configuration: conclusions are about "a panel this generator
produced," not the generator's distribution.

## What this means for the program

003 asked whether synthetic panels see the market humans see, and found
they do not. 005 asked whether matching the sub-intent mix fixes it, and
answers: it fixes the *prompt-level* problem completely and the
*panel-level* problem only partway. The measurable object that remains is
the joint profile — 13% coverage of human phrasing profiles is now the
number to beat, and the next design question is whether quota-boosting the
uncovered strata can close H2 without breaking the mix match H2 requires.

## Remaining steps to close the project

1. ~~**Audit-D spot-check**~~ — PASS, signed 2026-08-06
   (`results/audit-d-signoff.md`); four defects logged as deviations, no
   verdict moved.
2. **Release checklist** — `results/release-checklist.md` staged with the
   gate already green (`05_release.py` exit 0, brand-leak scan clean across
   204 aliases × 95 released prompts); needs Jim's review + signature, then
   `data/public/` can be committed (runs CSV + mat/neu2 prompt text under
   the data policy's synthetic-study-prompts exemption; human and coffee
   prompt text never ship).
3. **Decide the post-hoc layer** — whether to promote the residual probe,
   the within-sub-intent share cut, and the binary decomposition into
   `pipeline/91_*.py` for the article.
4. **Revise this summary's framing before drafting.** It currently leads
   with "H2 fails". The post-hoc work showed the panels agree on *pool
   membership* (82% vs 72% of travel prompts ever surfacing Apple; within a
   few points on the other five head brands) and largely on ranking
   (τ 0.73–0.87), and that the share metric has a noise floor the human
   panel does not clear against itself — Apple flips run-to-run within 68%
   of human prompts, and only 9.5% return it in all five runs. The honest
   lead is "the pool and ranking transfer; the consistency does not."
5. **Article (EN) + companion blog post (EN/DE)** — the 003 article
   pre-announced this study; score the five registered predictions
   explicitly, lead with the share dot-plot (F1) and carry H3′ on the
   matched-strata bars (F4). State the Apple extraction artifact explicitly
   (it flatters our own headline).

## Deviations from the frozen spec

None. §4/§5 ran as frozen; no code changes were made after `80e6c09`.
