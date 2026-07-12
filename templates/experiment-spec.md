# <Question, phrased as a falsifiable claim> — study spec

**Status:** draft | frozen | analyzing | published
**Frozen commit:** <git hash — record BEFORE running any extraction SQL>
**Experiment slug:** `NNN-short-slug`

> Freeze rule: everything in §4 (hypotheses) and §5 (model + decision rule) is
> fixed before anyone looks at the joined data. Count-only data-quality checks
> (class balance, null counts per column) are allowed pre-freeze; joint
> distributions are not. Predictors added after freeze are labelled
> **exploratory** in the write-up.

---

## 0. One-paragraph summary

<What we're testing, on what data, and what result we expect and why.>

## 1. The claim we can and cannot make

**What this design measures:** <the precise conditional question>

**What this design does NOT measure:** <the adjacent question readers will
assume we answered — say it before they do>

**Defensible claim:** "<the sentence we could publish>"

**Indefensible claim:** "<the overreach we must not publish>"

### Mechanistic prior

<Why do we expect the result we expect, from first principles? A predicted
result is a far stronger epistemic position than a mined correlation.>

## 2. Data-quality audits — run BEFORE the model

- **Audit A — negative-class contamination.** Are the "did not happen" rows
  real decisions, or artifacts (failed fetches, gated pages, missing
  enrichment)? How do we detect them programmatically, and what fraction are
  they?
- **Audit B — what does the outcome label actually mean?** Quote the
  classification code, don't paraphrase it.
- **Audit C — independence.** Repeated entities (same video/domain across many
  rows)? Count distinct; plan clustering or dedup.
- **Audit D — <study-specific measurement caveats>.**

Do not fit anything until A–D are answered in this file.

## 3. Data schema

One row per <unit>.

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| | | | yes / derived-only / never | |

The **Publishable?** column is filled in at spec time so the release gate's
allow-list is pre-registered too.

### Derived variables

<log transforms, standardization, ratio features — with rationale.>

## 4. Pre-registered hypotheses

- **H1 (primary):** …
- **H2, H3 …:** …
- **H_pos (positive control):** <a relationship that MUST show up — if it
  doesn't, the data cannot answer anything and the study stops.>
- **H_pla (placebo control):** <a variable that CANNOT plausibly matter — if
  it shows an effect, the standard errors are too small.>

## 5. Model and decision rule

**Model:** <e.g. pooled logit, cluster-robust SEs by <cols>; one focal
size-variable per model when predictors share a latent factor (collinearity
destroys equivalence power — check `collinearity_report`).>

**SESOI:** <the smallest effect that would change anyone's behavior, with the
rationale for the number.>

**Decision rule (TOST at 90% CI):**

| Result | Conclusion |
|---|---|
| CI entirely inside the SESOI band | Practically equivalent to zero — publishable null |
| CI excludes 1.0, extends beyond band | Real effect — report, revise thesis |
| CI excludes 1.0, inside band | Detectable but negligible — report honestly |
| CI wider than band, includes 1.0 | **Inconclusive — do NOT claim a null** |

**Power:** <simulate before real data: the pipeline must return NULL on
`true_effect=0` and REAL on an above-SESOI effect. `aeo_research.synthesize`.>

## 6. Known traps for this design

<Collider/selection bias and its control; effective sample = rarer class;
absence of evidence vs evidence of absence; anything study-specific.>

## 7. Robustness checks

1. Positive control first — if it fails, stop.
2. Placebo must be null.
3. Nonlinearity (deciles/splines).
4. Collinearity report (corr + VIF) in the write-up.
5. Dedup refit (one row per entity).
6. Per-<subgroup> refits — watch power.
7. Negative-class contamination sensitivity (exclude Audit-A rows).
8. Missingness: fit with and without null-heavy predictors; missingness is
   rarely random.

## 8. Deliverables and sequence

1. Audits A–D
2. Freeze spec (record commit hash above)
3. Extract (`sql/` — SQL committed before it runs)
4. Pipeline (`pipeline/01…05`)
5. Robustness suite
6. Article + anonymized dataset through the release gate
7. Companion blog post

## 9. Notes for the write-up

- Lead figure: <the single chart that carries the result>
- Framing: <constructive frame that matches what was measured>
- Sample size is reported as "N citations evaluated (in this study)".
- Publish the equivalence bound: "we could have detected X and found none."
