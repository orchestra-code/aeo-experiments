# Experiment 011: model results

Seed 20261103, 2000 bootstrap draws, 90% percentile CIs unless a row says otherwise, SESOI 0.1 (Jaccard gaps). 600 answers counted of 600 on disk, 40 prompts, 20 categories, waves [1, 2, 3]. Aggregates only: no answer text and no search query text.

Gap = mean(within:ui_default) - mean(cross:arm|ui_default). Positive means the arm is further from claude.ai than claude.ai is from itself across days.

Answers per arm x wave: all complete.

No-search rates: {'cc_none_search': 0.0, 'cc_stock_full': 0.0, 'opus55_plain': 0.0, 'sched_kit': 0.0, 'ui_default': 0.0}. Local arms: ['cc_stock_full', 'cc_none_search'].

## H_pos (positive control; the study stops if it fails)

Same-prompt minus cross-category cross-arm brand Jaccard (all arms vs ui_default, pooled, same wave) = +0.592 [+0.562, +0.622]; need at least 0.10 with the 90% CI excluding 0: **PASS**

Pairs 18720, NaN 0, prompts 40.

## H_pla (placebo): H1 gap on odd minus even prompts, TOST +/-0.10

Reported for each primary arm. It does not gate the analysis, because the split doubles the interval width. A REAL placebo gap is a caveat on that arm's H1.

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| H_pla cc_stock_full | brand-set Jaccard | +0.025 [-0.036, +0.081] | 90% | NULL | Practically equivalent: passes | 240 | 0 |  |
| H_pla sched_kit | brand-set Jaccard | +0.019 [-0.043, +0.078] | 90% | NULL | Practically equivalent: passes | 240 | 0 |  |

## H1 primary family (brand-set Jaccard gap = within:ui_default - cross:arm|ui_default; TOST +/-0.10; Holm over 2)

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| H1 sched_kit | brand-set Jaccard | +0.028 [-0.008, +0.063] | 95% | NULL | Practically equivalent: passes | 240 | 0 | Holm rank 1, bootstrap TOST p 0.0005, Holm p 0.0010 |
| H1 cc_stock_full | brand-set Jaccard | +0.065 [+0.037, +0.095] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 | Holm rank 2, bootstrap TOST p 0.0250, Holm p 0.0250 |

## H1 secondary (no multiplicity correction)

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| H1 cc_none_search | brand-set Jaccard | +0.056 [+0.026, +0.089] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 | secondary |
| H1 opus55_plain | brand-set Jaccard | +0.126 [+0.098, +0.154] | 90% | REAL | Real gap: report its size | 240 | 0 | replicates 009 (+0.067) |

## H2 (secondary): gap(arm) - gap(opus55_plain), TOST +/-0.10

Positive means the arm is further from claude.ai than the API is.

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| H2 cc_stock_full | brand-set Jaccard | -0.061 [-0.087, -0.033] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| H2 sched_kit | brand-set Jaccard | -0.098 [-0.122, -0.073] | 90% | REAL | Real gap: report its size | 240 | 0 |  |
| H2 cc_none_search | brand-set Jaccard | -0.070 [-0.098, -0.043] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |

## H3 (secondary): sched_kit vs cc_stock_full, mean of the two within-arm floors minus their same-wave cross-arm overlap, TOST +/-0.10

This tests the kit as built against a local run. It does not separate the cloud surface from the subagent and its added instruction.

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| H3 sched_kit vs cc_stock_full | brand-set Jaccard | +0.046 [+0.029, +0.064] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 360 | 0 |  |

## RBO gap on brand order, every arm (secondary; also R2)

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| RBO cc_stock_full | brand-order RBO | +0.065 [+0.030, +0.102] | 90% | REAL | Real gap: report its size | 240 | 0 |  |
| RBO sched_kit | brand-order RBO | +0.035 [+0.003, +0.070] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| RBO cc_none_search | brand-order RBO | +0.085 [+0.047, +0.123] | 90% | REAL | Real gap: report its size | 240 | 0 |  |
| RBO opus55_plain | brand-order RBO | +0.087 [+0.046, +0.128] | 90% | REAL | Real gap: report its size | 240 | 0 |  |

## Levels (same-prompt brand Jaccard; no test)

| Test | Metric | Estimate [CI] | CI | Pairs | NaN | Note |
|---|---|---|---|---|---|---|
| level within:ui_default | brand-set Jaccard | +0.670 [+0.632, +0.708] | 90% | 120 | 0 |  |
| level within:sched_kit | brand-set Jaccard | +0.703 [+0.672, +0.735] | 90% | 120 | 0 |  |
| level within:cc_stock_full | brand-set Jaccard | +0.673 [+0.641, +0.705] | 90% | 120 | 0 |  |
| level cross:cc_stock_full|ui_default | brand-set Jaccard | +0.605 [+0.572, +0.636] | 90% | 120 | 0 |  |
| level cross:sched_kit|ui_default | brand-set Jaccard | +0.642 [+0.606, +0.678] | 90% | 120 | 0 |  |
| level cross:cc_none_search|ui_default | brand-set Jaccard | +0.613 [+0.580, +0.649] | 90% | 120 | 0 |  |
| level cross:opus55_plain|ui_default | brand-set Jaccard | +0.544 [+0.511, +0.575] | 90% | 120 | 0 |  |
| level cross:cc_stock_full|sched_kit | brand-set Jaccard | +0.642 [+0.616, +0.667] | 90% | 120 | 0 |  |

## Domain gaps (descriptive; no verdicts)

Links in the answer for Claude Code, citation objects elsewhere, so a difference may be partly the measure. Evaluated domains are not observed on `sched_kit`. An arm over the Audit A limit (30% no-search answers) has its domain claims INCONCLUSIVE whatever the interval.

| Test | Metric | Estimate [CI] | CI | Pairs | NaN | Note |
|---|---|---|---|---|---|---|
| gap cc_stock_full | cited-domain Jaccard | +0.113 [+0.085, +0.144] | 90% | 240 | 0 |  |
| gap sched_kit | cited-domain Jaccard | +0.100 [+0.068, +0.137] | 90% | 240 | 0 |  |
| gap cc_none_search | cited-domain Jaccard | +0.125 [+0.096, +0.159] | 90% | 240 | 0 |  |
| gap opus55_plain | cited-domain Jaccard | +0.177 [+0.149, +0.210] | 90% | 240 | 0 |  |
| gap cc_stock_full | evaluated-domain Jaccard | +0.162 [+0.133, +0.194] | 90% | 240 | 0 |  |
| gap cc_none_search | evaluated-domain Jaccard | +0.175 [+0.147, +0.205] | 90% | 240 | 0 |  |
| gap opus55_plain | evaluated-domain Jaccard | +0.303 [+0.266, +0.342] | 90% | 240 | 0 |  |

## Behavior per answer (descriptive; no test)

`n/a` means the surface does not report it. `sched_kit` has no search count (a subagent's searches are not in the pulled transcript); its no-search rate uses the record's `searched` flag. `usd_estimate` is Claude Code's client-side estimate or the API ledger's batch price, for comparison only. `seconds` is the run's duration or, on `sched_kit`, the subagent's.

| arm | answers | searches | no_search_rate | fetches | backend_searches | subagent_tool_uses | evaluated_urls | links | cited_domains | brands | chars | usd_estimate | seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ui_default | 120 | 3.433 | 0.000 | n/a | n/a | n/a | 60.517 | 9.867 | 7.908 | 7.617 | 4638.800 | n/a | n/a |
| cc_stock_full | 120 | 5.092 | 0.000 | 2.283 | 5.342 | n/a | 88.342 | 13.100 | 10.358 | 7.300 | 5390.867 | 0.248 | 51.487 |
| sched_kit | 120 | n/a | 0.000 | n/a | n/a | 7.050 | n/a | 16.050 | 12.325 | 8.267 | 6464.192 | n/a | 53.012 |
| cc_none_search | 120 | 5.867 | 0.000 | 0.000 | 6.108 | n/a | 95.725 | 14.900 | 11.975 | 7.617 | 5911.875 | 0.244 | 44.888 |
| opus55_plain | 120 | 1.483 | 0.000 | 0.000 | n/a | n/a | 14.117 | 7.617 | 6.942 | 9.642 | 3965.275 | 0.070 | n/a |

Per wave:

| arm | wave | answers | searches | no_search_rate | links | brands | chars | usd_estimate | seconds |
|---|---|---|---|---|---|---|---|---|---|
| ui_default | 1 | 40 | 3.325 | 0.000 | 9.650 | 7.600 | 4780.700 | n/a | n/a |
| ui_default | 2 | 40 | 3.400 | 0.000 | 9.850 | 7.675 | 4714.375 | n/a | n/a |
| ui_default | 3 | 40 | 3.575 | 0.000 | 10.100 | 7.575 | 4421.325 | n/a | n/a |
| cc_stock_full | 1 | 40 | 4.200 | 0.000 | 12.425 | 7.425 | 5416.750 | 0.213 | 47.649 |
| cc_stock_full | 2 | 40 | 4.625 | 0.000 | 12.650 | 7.100 | 5548.200 | 0.227 | 47.699 |
| cc_stock_full | 3 | 40 | 6.450 | 0.000 | 14.225 | 7.375 | 5207.650 | 0.302 | 59.114 |
| sched_kit | 1 | 40 | n/a | 0.000 | 15.650 | 8.050 | 6557.325 | n/a | 51.195 |
| sched_kit | 2 | 40 | n/a | 0.000 | 16.575 | 8.550 | 6496.775 | n/a | 53.189 |
| sched_kit | 3 | 40 | n/a | 0.000 | 15.925 | 8.200 | 6338.475 | n/a | 54.652 |
| cc_none_search | 1 | 40 | 5.775 | 0.000 | 14.275 | 7.825 | 6131.525 | 0.244 | 45.165 |
| cc_none_search | 2 | 40 | 5.750 | 0.000 | 15.675 | 7.700 | 6078.050 | 0.236 | 43.614 |
| cc_none_search | 3 | 40 | 6.075 | 0.000 | 14.750 | 7.325 | 5526.050 | 0.252 | 45.884 |
| opus55_plain | 1 | 40 | 1.450 | 0.000 | 7.425 | 9.775 | 3946.850 | 0.070 | n/a |
| opus55_plain | 2 | 40 | 1.450 | 0.000 | 7.475 | 9.825 | 3987.750 | 0.070 | n/a |
| opus55_plain | 3 | 40 | 1.550 | 0.000 | 7.950 | 9.325 | 3961.225 | 0.072 | n/a |

## Usage on the plan (descriptive; ledger readings, local arms)

Change in window utilization as a fraction of the window. The value rounds to 1% and other work on the account moves it, so read these as rough. `prompts_per_day_implied` is answers / (7 x seven-day change), pooled over the study. `sched_kit` and claude.ai write no readings; Pro is measured separately (`harness/pro_usage_check.md`), in a ledger this pipeline does not read.

| plan | arm | wave | answers | five_hour_change | seven_day_change | five_hour_per_answer | seven_day_per_answer | prompts_per_day_implied |
|---|---|---|---|---|---|---|---|---|
| Max | cc_none_search | 1 | 40 | -0.4400 | 0.0100 | -0.0110 | 0.0003 | n/a |
| Max | cc_none_search | 2 | 40 | 0.1300 | 0.0100 | 0.0033 | 0.0003 | n/a |
| Max | cc_none_search | 3 | 40 | 0.1800 | 0.0100 | 0.0045 | 0.0002 | n/a |
| Max | cc_stock_full | 1 | 40 | 0.1700 | 0.0100 | 0.0042 | 0.0003 | n/a |
| Max | cc_stock_full | 2 | 40 | 0.2100 | 0.0200 | 0.0052 | 0.0005 | n/a |
| Max | cc_stock_full | 3 | 40 | 0.2100 | 0.0200 | 0.0052 | 0.0005 | n/a |
| Max | all local | all | 240 | 0.4600 | 0.0800 | 0.0019 | 0.0003 | 428.5714 |

## Robustness (spec §7; H1 gap, every arm, unadjusted 90% CIs)

### R1: top-10 brands instead of all brands

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| R1 cc_stock_full | top-10 brand Jaccard | +0.067 [+0.038, +0.097] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R1 sched_kit | top-10 brand Jaccard | +0.022 [-0.008, +0.052] | 90% | NULL | Practically equivalent: passes | 240 | 0 |  |
| R1 cc_none_search | top-10 brand Jaccard | +0.053 [+0.021, +0.086] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R1 opus55_plain | top-10 brand Jaccard | +0.118 [+0.088, +0.147] | 90% | REAL | Real gap: report its size | 240 | 0 |  |

### R2: RBO on brand order

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| R2 cc_stock_full | brand-order RBO | +0.065 [+0.030, +0.102] | 90% | REAL | Real gap: report its size | 240 | 0 |  |
| R2 sched_kit | brand-order RBO | +0.035 [+0.003, +0.070] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R2 cc_none_search | brand-order RBO | +0.085 [+0.047, +0.123] | 90% | REAL | Real gap: report its size | 240 | 0 |  |
| R2 opus55_plain | brand-order RBO | +0.087 [+0.046, +0.128] | 90% | REAL | Real gap: report its size | 240 | 0 |  |

### R3: drop one wave at a time

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| R3 -w1 cc_stock_full | brand-set Jaccard | +0.078 [+0.040, +0.116] | 90% | REAL | Real gap: report its size | 120 | 0 |  |
| R3 -w1 sched_kit | brand-set Jaccard | +0.044 [+0.005, +0.084] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 120 | 0 |  |
| R3 -w1 cc_none_search | brand-set Jaccard | +0.069 [+0.027, +0.114] | 90% | REAL | Real gap: report its size | 120 | 0 |  |
| R3 -w1 opus55_plain | brand-set Jaccard | +0.140 [+0.098, +0.182] | 90% | REAL | Real gap: report its size | 120 | 0 |  |
| R3 -w2 cc_stock_full | brand-set Jaccard | +0.036 [-0.000, +0.070] | 90% | NULL | Practically equivalent: passes | 120 | 0 |  |
| R3 -w2 sched_kit | brand-set Jaccard | -0.004 [-0.038, +0.033] | 90% | NULL | Practically equivalent: passes | 120 | 0 |  |
| R3 -w2 cc_none_search | brand-set Jaccard | +0.020 [-0.013, +0.053] | 90% | NULL | Practically equivalent: passes | 120 | 0 |  |
| R3 -w2 opus55_plain | brand-set Jaccard | +0.094 [+0.061, +0.128] | 90% | REAL | Real gap: report its size | 120 | 0 |  |
| R3 -w3 cc_stock_full | brand-set Jaccard | +0.082 [+0.037, +0.126] | 90% | REAL | Real gap: report its size | 120 | 0 |  |
| R3 -w3 sched_kit | brand-set Jaccard | +0.043 [-0.001, +0.086] | 90% | NULL | Practically equivalent: passes | 120 | 0 |  |
| R3 -w3 cc_none_search | brand-set Jaccard | +0.080 [+0.034, +0.128] | 90% | REAL | Real gap: report its size | 120 | 0 |  |
| R3 -w3 opus55_plain | brand-set Jaccard | +0.145 [+0.104, +0.188] | 90% | REAL | Real gap: report its size | 120 | 0 |  |

### R4: nothing censored (unplaced Haiku names added on both sides)

Candidate coverage by wave: {1: 1.0, 2: 1.0, 3: 1.0}.

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| R4 cc_stock_full | brand-set Jaccard | +0.065 [+0.037, +0.095] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R4 sched_kit | brand-set Jaccard | +0.031 [+0.000, +0.061] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R4 cc_none_search | brand-set Jaccard | +0.058 [+0.027, +0.090] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R4 opus55_plain | brand-set Jaccard | +0.127 [+0.098, +0.154] | 90% | REAL | Real gap: report its size | 240 | 0 |  |

### R5: category-level cluster bootstrap

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| R5 cc_stock_full | brand-set Jaccard | +0.065 [+0.047, +0.085] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R5 sched_kit | brand-set Jaccard | +0.028 [-0.001, +0.058] | 90% | NULL | Practically equivalent: passes | 240 | 0 |  |
| R5 cc_none_search | brand-set Jaccard | +0.056 [+0.029, +0.085] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R5 opus55_plain | brand-set Jaccard | +0.126 [+0.100, +0.154] | 90% | REAL | Real gap: report its size | 240 | 0 |  |

### R6: claude.ai chats flagged in collector notes excluded

0 claude.ai answers excluded.

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| R6 cc_stock_full | brand-set Jaccard | +0.065 [+0.037, +0.095] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R6 sched_kit | brand-set Jaccard | +0.028 [-0.003, +0.058] | 90% | NULL | Practically equivalent: passes | 240 | 0 |  |
| R6 cc_none_search | brand-set Jaccard | +0.056 [+0.026, +0.089] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R6 opus55_plain | brand-set Jaccard | +0.126 [+0.098, +0.154] | 90% | REAL | Real gap: report its size | 240 | 0 |  |

### R7: answers with no search excluded (ui_default included)

Answers excluded per arm: {}.

| Test | Metric | Estimate [CI] | CI | Verdict | Conclusion | Pairs | NaN | Note |
|---|---|---|---|---|---|---|---|---|
| R7 cc_stock_full | brand-set Jaccard | +0.065 [+0.037, +0.095] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R7 sched_kit | brand-set Jaccard | +0.028 [-0.003, +0.058] | 90% | NULL | Practically equivalent: passes | 240 | 0 |  |
| R7 cc_none_search | brand-set Jaccard | +0.056 [+0.026, +0.089] | 90% | NEGLIGIBLE | Detectable but negligible: passes | 240 | 0 |  |
| R7 opus55_plain | brand-set Jaccard | +0.126 [+0.098, +0.154] | 90% | REAL | Real gap: report its size | 240 | 0 |  |
