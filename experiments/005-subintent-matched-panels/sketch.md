# 005 — Can synthetic prompts mirror humans if the sub-intents match? (design sketch)

**Status:** sketch — NOT a spec, nothing frozen. Motivated during 003's
article review (2026-08-02); spec after the 003 article ships.

## The question

003 found the dissociation: a neutral scenario generator's prompts are
individually response-equivalent to human phrasings (H1 NULL on brands and
domains) but the panel's *mix* still misses the human share vector by 11
points (H2 REAL). 002 found that human prompts sharing a sub-intent (budget,
travel frame, use case) converge on brands, domains, and grounding. Put
together: is the remaining synthetic-vs-human gap **just sub-intent mix**?
If a generator produced prompts whose sub-intent profile distribution
matches the human panel's — the original intent of the Mad-Libs clause
design ("best wireless headphones" / "... with over-ear form factor" /
"... budget-friendly" / "... for someone who travels") — would the panel
finally mirror the human one at BOTH the response level and the share
level? That would upgrade 003's constructive ending from "scenario-first
helps" to "here is the recipe for a human-mirroring panel," with the
obvious product payoff.

## Pilot evidence (post-hoc, from 003 data — recompute at spec time)

Flag-matched pairwise brand Jaccard, same-wave hum×synthetic pairs vs the
flag-matched hum×hum baseline (cluster bootstrap, 1,000 draws, seed
20260729, band 0.10; "n" = synthetic prompts carrying the flag):

| Flag match | Arm | n | hum-both | cross-both | Δ [90% CI] | read |
|---|---|---|---|---|---|---|
| travel | neu | 30 | 0.566 | 0.526 | −0.039 [−0.086, +0.003] | NULL — equivalent |
| recipient | neu | 29 | 0.419 | 0.417 | −0.002 [−0.077, +0.055] | NULL — equivalent |
| travel | spy_a | 6 | 0.566 | 0.574 | +0.008 [−0.072, +0.080] | NULL (tiny cell) |
| music | spy_a | 5 | 0.576 | 0.445 | −0.131 [−0.187, −0.078] | REAL residual |
| noise-cancel | spy_a | 9 | 0.558 | 0.355 | −0.203 [−0.352, −0.063] | REAL residual |
| travel | spy_b | 8 | 0.566 | 0.445 | −0.121 [−0.238, −0.018] | REAL residual |
| noise-cancel | spy_b | 5 | 0.558 | 0.309 | −0.249 [−0.416, −0.092] | REAL residual |
| comfort | spy_b | 7 | 0.479 | 0.367 | −0.112 [−0.234, −0.010] | REAL residual |
| form-factor | spy_a/b | 11/29 | 0.339 | 0.247/0.259 | inconclusive | wide CIs |
| wireless | spy_a/b | 13/14 | 0.336 | 0.266/0.281 | inconclusive | wide CIs |

Two readings, both load-bearing for the design:

1. **Neutral generation + matched sub-intent = full response-level
   equivalence.** The neu panel's matched cells (travel, recipient — its two
   dominant frames, 29–30 prompts each) sit dead on the human baseline,
   and mismatched pairs are the drag (travel mismatch 0.435 vs 0.526
   matched). Sub-intent mix looks like the whole story for scenario-style
   prompts.
2. **Single-clause matching does NOT rescue anchored prompts.** Matching one
   flag leaves REAL residual gaps in most spy cells — anchored prompts
   stack the anchor's whole content bundle, so agreeing on one clause still
   mismatches the rest of the profile (and possibly length/specificity).
   Matching must target the **joint profile distribution**, not marginals
   of one flag.

Caveats: post-hoc on post-hoc, no multiplicity control, cells of 5–9 for
most spy rows, single-flag conditioning only. This is a pilot, not a result.

## Arms (same platform/instrument as 002/003, same waves)

| Arm | Panel | Tests |
|---|---|---|
| `hum` | 143 SparkToro prompts, re-run contemporaneously | baseline (house rule: never join old responses) |
| `mat` | scenario generator, Mad-Libs clause substitution **stratified to the human panel's flag-profile distribution** (recipient, budget, use case, form factor, output format...) | the headline: H1 AND H2 equivalence |
| `neu2` | scenario generator, unstratified (003 replication) | does 003's dissociation replicate? |
| `mat_anchor` (optional) | anchored generator + profile stratification | can stratification rescue an anchored panel, or does the content bundle persist? |

## Design skeleton

- Stratification target: the 143-prompt human panel's joint flag profiles
  (79 distinct in 003). Practical rule at spec time: match the joint
  distribution of the top-k flags (k≈5–6 by prevalence), sample panel size
  50–60 so every stratum with human mass ≥3% is represented; publish the
  target and achieved marginals pre-freeze (prompt-side, allowed).
- Hypotheses: H1/H2 exactly as 003 (same bands, same machinery — the point
  is comparability); add the pre-registered matched-pair contrast from the
  pilot (cross-both vs hum-both per stratum) as a named secondary.
- Prediction to pre-register: `mat` passes H1 AND H2; `neu2` passes H1,
  fails H2 (replication); `mat_anchor` closes part of the share gap but
  keeps a REAL residual (the 003 raking result says content mix is ~72% of
  spy_a's gap; stratification is the causal version of that reweighting).
- Power: the pilot's inconclusive cells had 5–13 prompts; stratified cells
  need ≥10 prompts for the flags that matter. 002's power-sim machinery
  extends directly.
- Cost: ~250 prompts × 5 waves ≈ $3 at the priority rate — same envelope
  as 003.

## Framing constraints

- This is the constructive follow-up 003's article promises ("scenario-first
  generation, phrasing diversification"): if `mat` passes both layers, the
  product recipe is validated and publishable; if it fails H2 anyway,
  sub-intent mix was NOT sufficient and the residual is the next mystery —
  either result ships.
- Human prompts remain SparkToro's; same credit and withholding rules.
- One intent, one platform, via DataForSEO's scraper — same claim boundary
  as 002/003, stated everywhere.

## Open questions for spec time

1. Stratify on joint profiles (sparse, faithful) or top-k marginals via
   raking-style targets (dense, approximate)? Pilot says joint matters for
   anchored prompts; scenario prompts may get away with marginals.
2. Does prompt LENGTH need matching too? Human median 30 words vs synthetic
   11–16 — length may carry specificity the flags don't capture (the
   pilot's spy residuals hint at it).
3. Include `mat_anchor` (4 arms, more cost/complexity) or defer the anchored
   question to a later study?
4. Re-run coffee gate panel, or promote 003's wave-1 gate design unchanged?
