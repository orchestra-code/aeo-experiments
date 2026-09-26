# Experiment 009 pilot report

Generated 2026-09-26 by `harness/pilot_report.py`. Aggregates only: no prompt, answer, query or brand text. Pilot data: 10 prompts, wave 0 (all arms) and a same-day repeat, wave 90 (`opus55_leak`, `sonnet5_leak_think`). API calls used Boston as the search location (pilot deviation); the UI account signs in from Pittsburgh.

Brand candidates: claude-haiku-4-5 with a JSON-schema output, one call per answer, 125 answers (125 with at least one brand), 291 canonical names in the draft lexicon (uncurated). Brand metrics are provisional until the lexicon is curated and frozen. Brand columns in the profile and overlap tables below use the Haiku draft names; the extraction comparison section shows lexicon v0.

## Per-arm profile (wave 0)

Means per answer. `zero_search` and `zero_cited` count answers. `usd_call` is the ledger's batch-priced mean (first-call cache writes included).

| arm | n | searches | zero_search | cited | zero_cited | evaluated | brands | chars | fetches | usd_call |
|---|---|---|---|---|---|---|---|---|---|---|
| haiku45_leak | 10 | 3.20 | 0 | 8.50 | 0 | 27.80 | 7.80 | 3277.50 | 0.00 | 0.06 |
| opus55_leak | 10 | 3.80 | 0 | 11.30 | 0 | 34.70 | 10.50 | 3984.40 | 0.00 | 0.18 |
| opus55_leak_fetch | 10 | 4.10 | 0 | 13.00 | 0 | 37.30 | 10.00 | 4405.60 | 0.00 | 0.20 |
| opus55_leak_raw | 5 | 2.80 | 0 | 9.40 | 0 | 25.20 | 12.60 | 3858.80 | 0.00 | 0.65 |
| opus55_leak_ws2026 | 10 | 8.20 | 0 | 0.00 | 10 | 58.80 | 9.20 | 3978.60 | 0.00 | 0.18 |
| opus55_plain | 10 | 1.80 | 0 | 8.60 | 0 | 16.30 | 12.20 | 4160.30 | 0.00 | 0.08 |
| sonnet5_leak_low | 10 | 1.60 | 2 | 5.50 | 3 | 14.10 | 8.60 | 4011.60 | 0.00 | 0.05 |
| sonnet5_leak_nothink | 10 | 2.30 | 3 | 4.60 | 5 | 20.40 | 9.30 | 4622.40 | 0.00 | 0.09 |
| sonnet5_leak_think | 10 | 2.80 | 0 | 8.20 | 1 | 25.20 | 9.70 | 4788.80 | 0.00 | 0.08 |
| sonnet5_prod | 10 | 3.10 | 0 | 12.70 | 0 | 27.00 | 10.90 | 7210.30 | 0.00 | 0.09 |
| ui_default | 10 | 1.80 | 0 | 7.10 | 0 | 16.40 | 11.40 | 4217.40 | 0.00 |  |

## Overlap with ui_default (same prompt, wave 0, mean over prompts)

| arm | n | brand_j | top10_j | brand_rbo | cited_dom_j | eval_dom_j | query_j |
|---|---|---|---|---|---|---|---|
| haiku45_leak | 10 | 0.32 | 0.37 | 0.50 | 0.07 | 0.11 | 0.24 |
| opus55_leak | 10 | 0.49 | 0.51 | 0.62 | 0.17 | 0.20 | 0.43 |
| opus55_leak_fetch | 10 | 0.50 | 0.49 | 0.60 | 0.17 | 0.23 | 0.48 |
| opus55_leak_raw | 5 | 0.56 | 0.58 | 0.67 | 0.08 | 0.14 | 0.46 |
| opus55_leak_ws2026 | 10 | 0.58 | 0.59 | 0.66 | 0.00 | 0.16 | 0.42 |
| opus55_plain | 10 | 0.48 | 0.51 | 0.57 | 0.20 | 0.26 | 0.52 |
| sonnet5_leak_low | 10 | 0.39 | 0.42 | 0.58 | 0.07 | 0.12 | 0.29 |
| sonnet5_leak_nothink | 10 | 0.44 | 0.43 | 0.52 | 0.04 | 0.10 | 0.26 |
| sonnet5_leak_think | 10 | 0.44 | 0.43 | 0.52 | 0.06 | 0.13 | 0.34 |
| sonnet5_prod | 10 | 0.40 | 0.39 | 0.56 | 0.09 | 0.13 | 0.27 |

## Overlap with opus55_leak (same prompt, wave 0, mean over prompts)

| arm | n | brand_j | top10_j | brand_rbo | cited_dom_j | eval_dom_j | query_j |
|---|---|---|---|---|---|---|---|
| haiku45_leak | 10 | 0.26 | 0.27 | 0.42 | 0.09 | 0.16 | 0.26 |
| opus55_leak_fetch | 10 | 0.50 | 0.50 | 0.63 | 0.36 | 0.40 | 0.61 |
| opus55_leak_raw | 5 | 0.57 | 0.57 | 0.74 | 0.26 | 0.36 | 0.62 |
| opus55_leak_ws2026 | 10 | 0.50 | 0.46 | 0.62 | 0.00 | 0.26 | 0.43 |
| opus55_plain | 10 | 0.52 | 0.51 | 0.58 | 0.24 | 0.31 | 0.56 |
| sonnet5_leak_low | 10 | 0.33 | 0.35 | 0.55 | 0.10 | 0.16 | 0.33 |
| sonnet5_leak_nothink | 10 | 0.36 | 0.35 | 0.48 | 0.12 | 0.17 | 0.30 |
| sonnet5_leak_think | 10 | 0.40 | 0.38 | 0.53 | 0.10 | 0.21 | 0.42 |
| sonnet5_prod | 10 | 0.36 | 0.33 | 0.51 | 0.14 | 0.17 | 0.35 |
| ui_default | 10 | 0.49 | 0.51 | 0.62 | 0.17 | 0.20 | 0.43 |

## Noise floor (same arm, wave 0 vs wave 90, same prompt)

| arm | n | brand_j | top10_j | brand_rbo | cited_dom_j | eval_dom_j | query_j |
|---|---|---|---|---|---|---|---|
| opus55_leak | 10 | 0.61 | 0.58 | 0.73 | 0.33 | 0.49 | 0.65 |
| sonnet5_leak_think | 10 | 0.47 | 0.49 | 0.62 | 0.16 | 0.31 | 0.62 |

## Brand extraction: Haiku candidates vs lexicon v0

Brand-set Jaccard with `ui_default` (same prompt, wave 0, mean over prompts) and the within-arm floor (wave 0 vs 90), under three extractions: `haiku_draft` (Haiku candidates, draft canonical names), `haiku_via_v0` (the same candidates mapped through lexicon v0, so merges and drops apply) and `lexicon_v0` (deterministic lexicon matching over the answer text, 003 method). Lexicon v0 is a first curation pass built from the pilot's own candidates, so this checks whether deterministic matching reproduces the model pass, not out-of-sample recall.

| arm | haiku_draft | haiku_via_v0 | lexicon_v0 |
|---|---|---|---|
| floor:opus55_leak | 0.61 | 0.79 | 0.80 |
| floor:sonnet5_leak_think | 0.47 | 0.58 | 0.60 |
| haiku45_leak | 0.32 | 0.40 | 0.42 |
| opus55_leak | 0.49 | 0.63 | 0.63 |
| opus55_leak_fetch | 0.50 | 0.69 | 0.70 |
| opus55_leak_raw | 0.56 | 0.59 | 0.58 |
| opus55_leak_ws2026 | 0.58 | 0.74 | 0.74 |
| opus55_plain | 0.48 | 0.67 | 0.68 |
| sonnet5_leak_low | 0.39 | 0.49 | 0.55 |
| sonnet5_leak_nothink | 0.44 | 0.61 | 0.62 |
| sonnet5_leak_think | 0.44 | 0.56 | 0.56 |
| sonnet5_prod | 0.40 | 0.53 | 0.48 |

| extraction | brands_per_answer | answers_with_none |
|---|---|---|
| haiku_draft | 10.28 | 0 |
| haiku_via_v0 | 7.96 | 0 |
| lexicon_v0 | 8.78 | 0 |

Per-answer agreement, Haiku via v0 vs lexicon v0: mean Jaccard 0.92, median 1.00, identical sets in 78 of 125 answers.

## Power simulation (confirmatory design)

40 prompts, 3 waves, reference `ui_default`. Gap = J_within(ui) - J_cross(arm, ui); equivalence when the 90% prompt-level cluster-bootstrap CI sits inside +/-0.10. `p_equivalent` is the share of 300 simulated studies (500 bootstrap draws each) that conclude NULL or NEGLIGIBLE. At a true gap of 0.10 it is the false-equivalence rate. `realized_gap` is the mean estimated gap across simulations; clipping at 0 shrinks it when the metric sits near the floor (cited domains), which inflates false equivalence there.

Assumptions: the UI within-arm floor is not observed in the pilot (one UI wave), so the API floor (`opus55_leak`, `sonnet5_leak_think`) stands in for it. Per-prompt level SD and pair noise SD come from the pilot (below). The optimistic rows treat the 3 within-UI and 3 cross pairs per prompt as independent; the conservative rows keep one of each, bracketing the dependence between pairs that share a response.

| metric | mean_cross | sd_prompt | sd_pair | n_prompt_obs |
|---|---|---|---|---|
| brands | 0.465 | 0.123 | 0.135 | 20 |
| brands (lexicon v0) | 0.596 | 0.124 | 0.111 | 20 |
| cited domains | 0.116 | 0.117 | 0.130 | 20 |

| metric | pairing | true_gap | realized_gap | p_equivalent | verdicts |
|---|---|---|---|---|---|
| brands | 3+3 pairs (optimistic) | 0.000 | -0.000 | 1.000 | NEGLIGIBLE 35, NULL 265 |
| brands | 3+3 pairs (optimistic) | 0.050 | 0.050 | 0.900 | NEGLIGIBLE 242, NULL 28, REAL 30 |
| brands | 3+3 pairs (optimistic) | 0.100 | 0.099 | 0.077 | NEGLIGIBLE 23, REAL 277 |
| brands | 1+1 pair (conservative) | 0.000 | 0.002 | 0.920 | INCONCLUSIVE 6, NEGLIGIBLE 11, NULL 265, REAL 18 |
| brands | 1+1 pair (conservative) | 0.050 | 0.052 | 0.487 | INCONCLUSIVE 13, NEGLIGIBLE 20, NULL 126, REAL 141 |
| brands | 1+1 pair (conservative) | 0.100 | 0.102 | 0.040 | INCONCLUSIVE 3, NEGLIGIBLE 5, NULL 7, REAL 285 |
| brands (lexicon v0) | 3+3 pairs (optimistic) | 0.000 | 0.000 | 1.000 | NEGLIGIBLE 38, NULL 262 |
| brands (lexicon v0) | 3+3 pairs (optimistic) | 0.050 | 0.049 | 0.977 | NEGLIGIBLE 282, NULL 11, REAL 7 |
| brands (lexicon v0) | 3+3 pairs (optimistic) | 0.100 | 0.098 | 0.083 | NEGLIGIBLE 25, REAL 275 |
| brands (lexicon v0) | 1+1 pair (conservative) | 0.000 | 0.002 | 0.987 | NEGLIGIBLE 26, NULL 270, REAL 4 |
| brands (lexicon v0) | 1+1 pair (conservative) | 0.050 | 0.052 | 0.623 | NEGLIGIBLE 92, NULL 95, REAL 113 |
| brands (lexicon v0) | 1+1 pair (conservative) | 0.100 | 0.100 | 0.047 | NEGLIGIBLE 12, NULL 2, REAL 286 |
| cited domains | 3+3 pairs (optimistic) | 0.000 | -0.000 | 1.000 | NEGLIGIBLE 30, NULL 270 |
| cited domains | 3+3 pairs (optimistic) | 0.050 | 0.039 | 0.993 | NEGLIGIBLE 269, NULL 29, REAL 2 |
| cited domains | 3+3 pairs (optimistic) | 0.100 | 0.082 | 0.330 | NEGLIGIBLE 99, REAL 201 |
| cited domains | 1+1 pair (conservative) | 0.000 | 0.002 | 0.997 | NEGLIGIBLE 38, NULL 261, REAL 1 |
| cited domains | 1+1 pair (conservative) | 0.050 | 0.042 | 0.797 | NEGLIGIBLE 105, NULL 134, REAL 61 |
| cited domains | 1+1 pair (conservative) | 0.100 | 0.085 | 0.157 | INCONCLUSIVE 1, NEGLIGIBLE 37, NULL 10, REAL 252 |

## Panel-share test (H1s brands, H1d cited domains)

Per-category shares: the fraction of an arm's answers in a category that name a brand (lexicon v0) or cite a registered domain. Statistics (`pipeline/shares.py`): `excess` = MAD over the basket minus the MAD expected from sampling alone (exact binomial expectation at the UI shares); `rmsd` = noise-corrected root-mean-square difference. Equivalence passes when the 95th-percentile upper bound of a two-stage (category, then prompt) cluster bootstrap is below 0.05.

### Pilot point estimates (illustrative only)

One wave, 10 of 20 categories, one answer per arm per category, so every share is 0 or 1 and the sampling corrections are degenerate. Shown to exercise the code, not to estimate anything.

| metric | arm | basket_ref | mad | excess | basket_pooled | rmsd |
|---|---|---|---|---|---|---|
| brands | opus55_plain | 95 | 0.189 | 0.189 | 119 | 0.594 |
| brands | opus55_leak | 95 | 0.295 | 0.295 | 114 | 0.642 |
| brands | sonnet5_leak_think | 95 | 0.316 | 0.316 | 117 | 0.667 |
| brands | sonnet5_leak_low | 95 | 0.400 | 0.400 | 117 | 0.716 |
| brands | sonnet5_prod | 95 | 0.337 | 0.337 | 134 | 0.728 |
| brands | haiku45_leak | 95 | 0.495 | 0.495 | 116 | 0.766 |
| cited domains | opus55_plain | 66 | 0.652 | 0.652 | 126 | 0.904 |
| cited domains | opus55_leak | 66 | 0.636 | 0.636 | 148 | 0.915 |
| cited domains | sonnet5_leak_think | 66 | 0.864 | 0.864 | 132 | 0.965 |
| cited domains | sonnet5_leak_low | 66 | 0.848 | 0.848 | 107 | 0.952 |
| cited domains | sonnet5_prod | 66 | 0.773 | 0.773 | 157 | 0.951 |
| cited domains | haiku45_leak | 66 | 0.864 | 0.864 | 137 | 0.967 |

### Power at the confirmatory design

20 categories drawn from the pilot's 10 (with replacement), 2 prompts x 3 waves (6 answers per arm per category), 200 simulated studies with 1000 bootstrap draws each. True UI shares per category come from the pilot (wave 0, confirmatory arms pooled with the UI). The arm's true share is the UI share plus or minus `true_diff` on every cell, so the true MAD and the true RMSD both equal `true_diff`. `prompt_effect` beta k=4 gives each prompt its own shares (shared by both arms). `p_pass` = equivalence passes (at `true_diff` 0.05 it is the false-pass rate); `p_real` = the lower bound is above 0; `estimate` = mean point estimate; `basket_mean` = mean basket size over 20 categories.

| metric | categories | items_per_category | items_share_ge_1_3 |
|---|---|---|---|
| brands | 10 | 17.6 | 9.8 |
| cited domains | 10 | 34.0 | 6.1 |

| metric | statistic | basket | threshold | prompt_effect | true_diff | p_pass | p_real | estimate | basket_mean |
|---|---|---|---|---|---|---|---|---|---|
| brands | excess | ref | 0.333 | none | 0.000 | 0.920 | 0.430 | 0.010 | 238.285 |
| brands | excess | ref | 0.333 | none | 0.025 | 0.740 | 0.705 | 0.017 | 238.285 |
| brands | excess | ref | 0.333 | none | 0.050 | 0.360 | 0.925 | 0.026 | 238.285 |
| brands | excess | ref | 0.333 | none | 0.100 | 0.005 | 1.000 | 0.047 | 238.285 |
| brands | excess | ref | 0.333 | beta k=4 | 0.000 | 0.945 | 0.220 | -0.000 | 236.250 |
| brands | excess | ref | 0.333 | beta k=4 | 0.025 | 0.815 | 0.520 | 0.007 | 236.250 |
| brands | excess | ref | 0.333 | beta k=4 | 0.050 | 0.565 | 0.810 | 0.016 | 236.250 |
| brands | excess | ref | 0.333 | beta k=4 | 0.100 | 0.020 | 1.000 | 0.037 | 236.250 |
| brands | rmsd | pooled | 0.333 | none | 0.000 | 0.030 | 0.010 | -0.013 | 222.705 |
| brands | rmsd | pooled | 0.333 | none | 0.025 | 0.020 | 0.010 | -0.002 | 222.835 |
| brands | rmsd | pooled | 0.333 | none | 0.050 | 0.010 | 0.045 | 0.024 | 223.065 |
| brands | rmsd | pooled | 0.333 | none | 0.100 | 0.000 | 0.250 | 0.100 | 223.875 |
| brands | rmsd | pooled | 0.333 | beta k=4 | 0.000 | 0.095 | 0.000 | -0.078 | 224.415 |
| brands | rmsd | pooled | 0.333 | beta k=4 | 0.025 | 0.090 | 0.000 | -0.073 | 224.630 |
| brands | rmsd | pooled | 0.333 | beta k=4 | 0.050 | 0.045 | 0.000 | -0.054 | 224.980 |
| brands | rmsd | pooled | 0.333 | beta k=4 | 0.100 | 0.000 | 0.100 | 0.038 | 226.040 |
| brands | rmsd | pooled | 0.250 | none | 0.000 | 0.040 | 0.010 | -0.010 | 259.130 |
| brands | rmsd | pooled | 0.250 | none | 0.025 | 0.020 | 0.010 | 0.002 | 259.235 |
| brands | rmsd | pooled | 0.250 | none | 0.050 | 0.010 | 0.050 | 0.031 | 259.285 |
| brands | rmsd | pooled | 0.250 | none | 0.100 | 0.000 | 0.300 | 0.105 | 258.935 |
| brands | rmsd | pooled | 0.250 | beta k=4 | 0.000 | 0.120 | 0.000 | -0.079 | 252.680 |
| brands | rmsd | pooled | 0.250 | beta k=4 | 0.025 | 0.110 | 0.000 | -0.074 | 253.175 |
| brands | rmsd | pooled | 0.250 | beta k=4 | 0.050 | 0.050 | 0.000 | -0.054 | 253.585 |
| brands | rmsd | pooled | 0.250 | beta k=4 | 0.100 | 0.000 | 0.110 | 0.043 | 254.865 |
| cited domains | excess | ref | 0.333 | none | 0.000 | 0.990 | 0.035 | 0.007 | 269.250 |
| cited domains | excess | ref | 0.333 | none | 0.025 | 0.990 | 0.060 | 0.008 | 269.250 |
| cited domains | excess | ref | 0.333 | none | 0.050 | 0.990 | 0.090 | 0.011 | 269.250 |
| cited domains | excess | ref | 0.333 | none | 0.100 | 0.875 | 0.465 | 0.023 | 269.250 |
| cited domains | excess | ref | 0.333 | beta k=4 | 0.000 | 0.975 | 0.050 | -0.013 | 270.125 |
| cited domains | excess | ref | 0.333 | beta k=4 | 0.025 | 0.985 | 0.035 | -0.013 | 270.125 |
| cited domains | excess | ref | 0.333 | beta k=4 | 0.050 | 0.975 | 0.055 | -0.010 | 270.125 |
| cited domains | excess | ref | 0.333 | beta k=4 | 0.100 | 0.880 | 0.280 | -0.000 | 270.125 |
| cited domains | rmsd | pooled | 0.333 | none | 0.000 | 0.020 | 0.005 | -0.004 | 207.105 |
| cited domains | rmsd | pooled | 0.333 | none | 0.025 | 0.015 | 0.005 | 0.008 | 207.330 |
| cited domains | rmsd | pooled | 0.333 | none | 0.050 | 0.005 | 0.035 | 0.036 | 208.560 |
| cited domains | rmsd | pooled | 0.333 | none | 0.100 | 0.000 | 0.345 | 0.120 | 214.780 |
| cited domains | rmsd | pooled | 0.333 | beta k=4 | 0.000 | 0.145 | 0.000 | -0.120 | 226.985 |
| cited domains | rmsd | pooled | 0.333 | beta k=4 | 0.025 | 0.100 | 0.000 | -0.120 | 227.560 |
| cited domains | rmsd | pooled | 0.333 | beta k=4 | 0.050 | 0.045 | 0.000 | -0.104 | 228.580 |
| cited domains | rmsd | pooled | 0.333 | beta k=4 | 0.100 | 0.000 | 0.100 | -0.020 | 233.095 |
| cited domains | rmsd | pooled | 0.250 | none | 0.000 | 0.040 | 0.000 | -0.005 | 316.895 |
| cited domains | rmsd | pooled | 0.250 | none | 0.025 | 0.020 | 0.015 | 0.007 | 317.405 |
| cited domains | rmsd | pooled | 0.250 | none | 0.050 | 0.005 | 0.045 | 0.041 | 318.070 |
| cited domains | rmsd | pooled | 0.250 | none | 0.100 | 0.000 | 0.495 | 0.126 | 320.350 |
| cited domains | rmsd | pooled | 0.250 | beta k=4 | 0.000 | 0.180 | 0.000 | -0.112 | 311.225 |
| cited domains | rmsd | pooled | 0.250 | beta k=4 | 0.025 | 0.175 | 0.000 | -0.110 | 312.080 |
| cited domains | rmsd | pooled | 0.250 | beta k=4 | 0.050 | 0.065 | 0.000 | -0.091 | 313.925 |
| cited domains | rmsd | pooled | 0.250 | beta k=4 | 0.100 | 0.000 | 0.125 | 0.010 | 319.920 |
