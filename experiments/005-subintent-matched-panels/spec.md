# Can a sub-intent-matched synthetic panel mirror human prompts? — study spec

**Status:** frozen (2026-08-02, approved by Jim before any collection)
**Frozen commit:** recorded in the follow-up commit per house convention
**Experiment slug:** `005-subintent-matched-panels`

> Freeze rule: everything in §4 (hypotheses) and §5 (model + decision rule)
> is fixed before anyone looks at joined response data. Count-only
> data-quality checks and prompt-side shape statistics are allowed
> pre-freeze; response data is not collected until after the freeze. The
> brand LEXICON (pipeline/brands.py, verbatim from 003's Audit-D-validated
> state) and the 15 phrasing-flag regexes (pipeline/flags.py, verbatim from
> 002/003) are frozen instruments. The two synthetic panels were generated
> ONCE (2026-08-02) by regenerate-until-valid (never hand-edited) and are
> frozen as data in data/raw/generator/ — regenerating them after seeing
> responses is a protocol violation.

---

## A. Pre-freeze findings (harness runs, 2026-08-02)

Allowed pre-freeze: prompt-side shape observations, no response data.

- `mat`: 55 prompts, stratified to the 003 human panel's joint profile
  over the six STRATIFY_FLAGS (travel, music, budget, recipient, form
  factor, wireless). 12 cells with ≥2 human prompts cover 89.5% of the
  human panel; 55 slots allocated by largest remainder; per-slot length
  bands drawn from the human band marginal (seed 20260802, realized draw
  31 medium / 17 long / 7 short). Regex re-validation: **achieved cells
  match targets exactly** (Audit E). Median 23 words (range 8–80) vs the
  human panel's 30 (3–274) — the first synthetic panel in this program
  whose length distribution approaches the human one.
- `neu2`: 40 prompts, exact replication draw of 003's neu generator (same
  model, system prompt, and brief, verbatim). Median 15 words (6–21).
- Zero brand-name leaks (validated against the full alias lexicon), zero
  years, zero duplicates in either panel.
- Prompt-side flag prevalence teaser (H4 dry look): mat tracks hum where
  stratified (budget 0.11 vs 0.16, recipient 0.13 vs 0.15); neu2 drifts
  (recipient 0.42 vs 0.15) — the stratification is doing visible work
  before any collection.
- Pipeline dry run on `--synthetic` data (planted effects: mat draws from
  the hum brand distribution, neu2 from a reversed one): gate PASS (0.348,
  perm p = 0.0002), placebo NULL, H1_mat NULL on all families, planted
  H2_neu2 detected REAL (0.128), H3′ machinery runs on the two qualifying
  flags. H2_mat's dry-run CI is wide (INCONCLUSIVE at estimate 0.043)
  because the synthetic frame's brand distribution is far flatter than
  real answers (27 basket brands vs 003's 6); the real-data basket
  concentrates shares and narrows this CI substantially (003 measured
  H2 CIs of ±0.04–0.08 width on the same design).

## 0. One-paragraph summary

003 established the dissociation: a neutral scenario generator's prompts
are individually response-equivalent to human phrasings (H1 NULL on brands
and domains) but the panel's mix still misses the human share vector by 11
points (H2 REAL). A post-hoc pilot on 003 data showed that neutral prompts
sharing a sub-intent flag with a human prompt produce answers statistically
equivalent to human-human same-flag pairs — suggesting the entire remaining
gap is sub-intent mix. 005 is the pre-registered causal test: generate a
scenario panel whose joint sub-intent profile is STRATIFIED to the human
panel's (the Mad-Libs clause design used as an instrument), run it beside
the re-run human panel and a fresh unstratified draw, and test whether the
stratified panel mirrors the human panel at BOTH the response level (H1)
and the share level (H2). **Registered prediction: mat passes H1 and H2;
neu2 passes H1 on brands/domains and fails H2 (replicating 003); H3′
matched-stratum contrasts come back NULL for mat's qualifying flags.** If
mat passes both layers, synthetic panels have a validated recipe for
representing human intent; if it fails H2 anyway, sub-intent mix was not
sufficient and the residual becomes the next measured object. Either
result publishes.

## 1. The claim we can and cannot make

**What this design measures:** for one commercial-recommendation intent on
one platform (ChatGPT with web search forced, via DataForSEO's scraper,
en-US), over five days: whether a scenario-generated panel stratified to
the human panel's sub-intent profile reproduces (a) pairwise response
overlap and (b) the brand mention-share vector of 143 contemporaneous
human prompts — and whether an unstratified draw of the same generator
replicates 003's pass-H1/fail-H2 dissociation.

**What it does NOT measure:** other intents/platforms/locales;
brand-anchored generation (003 covered it; no anchored arm here);
multi-turn behavior; curated customer panels; whether the recipe works for
intents lacking a human-profile source (that dependency is the recipe's
stated cost: stratification targets came FROM a human panel).

**Defensible claim if mat passes:** "A synthetic panel stratified to a
human panel's sub-intent mix measured the same brand-share vector within X
points and the same response overlap within Y, where an unstratified panel
from the same generator did not." Indefensible: "synthetic panels are
validated in general" (the recipe requires a human-derived target mix).

### Mechanistic prior

002: prompt content steers brand mix (budget flips, use-case lifts);
retrieval normalizes phrasing within a sub-intent. 003: response-level
exchangeability holds for scenario prompts but panel mix drives share
divergence; raking hum to a panel's content mix reproduces most of the
share gap for in-human-space mixes. Pilot (003 review): flag-matched
neutral×human pairs are fully equivalent (travel −0.039 NULL n=30;
recipient −0.002 NULL n=29). All three point the same way: **sub-intent
mix is the sampling frame; match it at generation time and both layers
should close.** The live risks: (i) residual authorship signal (length,
specificity) beyond the six stratified flags; (ii) joint-profile
interactions the marginal-ish stratification misses; (iii) the ~10%
uncovered human mass (singleton cells).

## 2. Data-quality audits — run BEFORE the model

A–D as in 003 (completeness/degenerate rates with the 0.30 empty-fan-out
INCONCLUSIVE rule; label definitions quoted from code; clustering and pair
counts; extraction validity with 30-response manual spot-check at
precision ≥ 0.95 / recall ≥ 0.90, model-version drift table, and the 003
hum-share anchor for drift reporting). New:

- **Audit E — stratification manipulation check.** The mat panel's
  achieved cell distribution (regex re-validation over the frozen flags)
  must match its frozen targets exactly; achieved length bands reported
  against the drawn allocation. Any mismatch means H2_mat's verdict is
  about a mis-stratified panel — reported against the ACHIEVED
  distribution and logged in Deviations.

## 3. Data schema

Identical to 003 (one row per prompt × wave; same derived variables, URL
normalization, Jaccard with empty∩empty→NaN, truncated RBO). Additions:
mat rows carry `framework="stratified"` and `query_type=<stratum cell>`.
Publishability: human/coffee prompt text NEVER (SparkToro's); mat/neu2
prompt text releasable at 05_release under the data policy's
synthetic-study-prompts exemption (study-generated, no brand anchors,
styles publicly reproducible); answer markdown and fan-out text never.

## 4. Pre-registered hypotheses

Pair conditions as in 003: within:{arm}, between:{arm}, cross:{a}|{b};
`between:hum` is the reference throughout.

- **H1 (exchangeability, per synthetic arm × {brands, domains, grounding
  tokens}):** Δ = mean(cross:hum|arm) − mean(between:hum), TOST at |Δ| <
  0.10 absolute Jaccard. Registered prediction: mat NULL on all three;
  neu2 NULL on brands/domains (003 replication).
- **H2 (share agreement, per synthetic arm):** MAD over the basket (brands
  with hum share ≥ 0.05, pooled over waves); equivalence if the 90% CI's
  upper bound < 0.05; Kendall tau descriptive. Registered prediction: mat
  equivalent; neu2 REAL divergence (003 measured 0.112).
- **H3′ (matched-stratum exchangeability — the pilot, pre-registered):**
  for each STRATIFY_FLAG carried by ≥ 10 prompts of an arm (frozen floor;
  by construction mat qualifies on travel_context and usage_music), the
  brand-Jaccard contrast of cross:hum|arm pairs where BOTH prompts carry
  the flag vs between:hum pairs where both carry it, TOST at 0.10.
  Registered prediction: NULL for mat's qualifying flags. Rarer strata
  (budget, recipient, form, wireless) are underpowered at proportional
  allocation and are analyzed under the 9x exploratory convention only.
- **H4 (coverage, exploratory, no test):** the 15 flags per panel,
  prevalence deltas, never-emitted behaviors, lengths, profile coverage.
- **H_pos (positive control — must pass or the study stops):** as 003:
  between:hum cited-domain Jaccard exceeds cross:coffee|hum by ≥ 0.10 with
  the 90% CI excluding 0 AND permutation p < 0.05 (wave-1, hum vs coffee).
- **H_pla (placebo):** parity split of between:hum pairs NULL/NEGLIGIBLE.

Reading H1+H2 together carries the study: mat passing both = the recipe
works; mat passing H1 but failing H2 = sub-intent mix (as stratified) is
not sufficient — the residual (length? interactions? uncovered mass?) is
quantified via H4 and the reweighting machinery from 003 (exploratory).

## 5. Model and decision rule

Nonparametric, identical machinery to 003: prompt-level cluster bootstrap
(2,000 draws, 90% percentile CIs) via `aeo_research.overlap.cluster_boot`;
share statistics by within-arm prompt resampling
(`03_model.py::boot_share_stats`); permutation test for H_pos (5,000
draws). Seed 20260802. SESOI 0.10 absolute Jaccard (H1/H3′), 0.05 share
MAD (H2) — unchanged from 003 for comparability. Decision table as 003
(TOST at 90%: NULL inside band / REAL beyond with 0 excluded / NEGLIGIBLE
inside band with 0 excluded / INCONCLUSIVE otherwise — never claim a null
from an INCONCLUSIVE row).

**Power:** machinery power-simulated in 002/003 (`tests/test_overlap.py`).
Cross-arm pair counts: mat 55×143 ≈ 7.9k per wave — more than 003's spy
arms. Binding constraint is cluster count (55/40), guarded by the
INCONCLUSIVE row. The dry run (§A) passed the gate and detected the
planted effects before any spend.

## 6. Known traps for this design

- **Contemporaneity is load-bearing.** hum re-runs fresh; 002/003
  responses are never joined into any test. 003's numbers are anchors.
- **Generation is one-shot** (vendor-realistic): conclusions are about
  these panels, not the generator's distribution.
- **Stratification ≠ perfect matching:** 10.5% of human mass (singleton
  cells) is unrepresented; length is drawn at band level, not matched
  per-profile; the six flags don't span everything humans do (age,
  output-format asks are unstratified). These are the named suspects if
  mat fails H2.
- **H3′ power is concentrated** in travel/music by proportional
  allocation — a deliberate trade: quota-boosting rare strata would break
  the mix match that H2 requires.
- **Refusal/clarification answers** are valid rows with empty brand sets.
- **Shared DataForSEO account with production:** never call `tasks_ready`;
  poll `task_get` by stored ids only.
- **Cost cap:** (143+55+40)×5 + 40 = 1,230 tasks ≈ $2.95 at the priority
  rate; CLI cap 1,500 stays on.

## 7. Robustness checks

1. H_pos first — if it fails, stop (03_model exits 1).
2. H_pla placebo must be NULL/NEGLIGIBLE.
3. R1: rank-sensitive RBO for each H1 brand contrast.
4. R2: drop wave 1, refit H1 brands.
5. R3: drop duplicate-text prompts, refit H1 brands.
6. R4: grounding contrasts restricted to non-empty fan-outs.
7. R5: within:arm vs within:hum repeatability contrast.
8. R6: dominant-model subset refit if `result.model` drifts.

## 8. Deliverables and sequence

1. Harness runs (DONE 2026-08-02, pre-freeze) → data/raw/generator/*.json
2. 00_prompts (DONE) — 143 hum + 55 mat + 40 neu2 + 40 coffee
3. Pipeline dry run (DONE — gate PASS, planted effects detected)
4. Review + FREEZE (write data/raw/FROZEN, commit, record hash here)
5. Nightly launchd `io.spyglasses.aeo-exp005` (10:30 ET): wave 1 submits
   headphones + coffee together; waves 2–5 headphones only; self-destructs
   after wave 5 collects (~day 5)
6. Re-curate lexicon from wave-1 mining if needed; Audit D spot-check
7. 01→05 + 90 after wave 5; release gate + checklist
8. Article (EN) + companion blog post — the 003 article pre-announces this
   study; report against its registered predictions explicitly

## 9. Notes for the write-up

- Lead figure: share dot-plot (hum bars, mat/neu2 markers). H3′ carrier:
  matched-strata grouped bars.
- Cite 003's article and the pilot table; score the registered predictions
  one by one (they are falsifiable and public before collection).
- Q3/Q7 of the 31-questions article are the scorecard again; SparkToro
  credit as always; "via DataForSEO's scraper" on every platform claim.
- Sample size phrased as "N runs evaluated (in this study)".
- Publish the equivalence bounds: "we could have detected a 0.10 Jaccard
  shift / a 5-point share shift."

## Deviations from the frozen spec

(none yet — spec not frozen)
