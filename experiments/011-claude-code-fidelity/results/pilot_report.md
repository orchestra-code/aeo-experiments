# Experiment 011: feasibility report

Scored against `sketch.md`. Pilot data, never part of a confirmatory analysis. Aggregates only. The claude.ai reference is 009's stored `ui_default` waves 1 to 3.

## G1, clean instrument
40 of 40 runs finished and passed the `init` audit; need at least 38. **PASS**

## Behavior per answer
| Arm | n | Searches | Fetches | Backend searches | Evaluated URLs | Links in answer | Chars | Brands | No search |
|---|---|---|---|---|---|---|---|---|---|
| `ui_default` | 30 | 1.5 | 0.0 | nan | 13.7 | 4.9 | 3830 | 8.1 | 17% |
| `opus55_plain` | 10 | 1.5 | 0.0 | nan | 14.4 | 8.3 | 4234 | 8.8 | 0% |
| `cc_stock_full` | 10 | 4.4 | 2.4 | 4.7 | 78.2 | 12.2 | 5862 | 7.3 | 0% |
| `cc_stock_search` | 10 | 6.2 | 0.0 | 6.7 | 112.0 | 15.5 | 6235 | 8.2 | 0% |
| `cc_none_full` | 10 | 5.8 | 2.8 | 6.1 | 94.3 | 14.5 | 6036 | 8.4 | 0% |
| `cc_none_search` | 10 | 7.0 | 0.0 | 7.2 | 112.5 | 20.0 | 6869 | 8.1 | 0% |

## G2 and G3, per arm
| Arm | Answers, not questions or coding offers | Searched | Coverage, exact alias | Coverage, resolved | Links when searched | G2 | G3 |
|---|---|---|---|---|---|---|---|
| `cc_stock_full` | 100% | 100% | 84.9% | 98.9% | 100% | PASS | PASS |
| `cc_stock_search` | 100% | 100% | 83.2% | 96.3% | 100% | PASS | PASS |
| `cc_none_full` | 100% | 100% | 88.0% | 98.1% | 100% | PASS | PASS |
| `cc_none_search` | 100% | 100% | 87.6% | 93.3% | 100% | PASS | PASS |

Answers flagged by the pattern check: [('cc_none_full', 'b2b_09'), ('cc_none_search', 'b2b_09')]. Read by a person; cleared: [('cc_none_full', 'b2b_09'), ('cc_none_search', 'b2b_09')] (an offer to draft a demo script for a vendor call, not coding behavior).

G3 uses resolved coverage (sketch, deviation 1). As first scored, on exact aliases, every arm failed. The sensitivity gap below does not depend on either rule.

Coverage on the same lexicon, for comparison: `ui_default` exact 98.2%, resolved 100.0%; `opus55_plain` exact 90.7%, resolved 96.1%.

## G4 and G5, brand gap against claude.ai
Gap = claude.ai against itself across waves, minus the arm against claude.ai. Positive means further from claude.ai than claude.ai is from itself. 10 prompts, 90% interval, prompt-level bootstrap. A screen, not a test.

| Arm | Brand gap | Mean overlap with claude.ai | Same-day overlap with the API anchor |
|---|---|---|---|
| `opus55_plain` | +0.055 [-0.014, +0.134] | 0.633 | n/a |
| `cc_stock_full` | +0.056 [+0.000, +0.113] | 0.632 | 0.584 |
| `cc_stock_search` | +0.076 [+0.034, +0.115] | 0.612 | 0.624 |
| `cc_none_full` | +0.086 [+0.013, +0.152] | 0.602 | 0.567 |
| `cc_none_search` | +0.054 [+0.011, +0.098] | 0.634 | 0.647 |

claude.ai against itself on these 10 prompts: 0.688.

**G4 PASS:** anchor gap +0.055, limit 0.15. For scale, 009's confirmatory gap was +0.067.
**G5 PASS:** arms that passed G1 to G3 with a gap of at most 0.2: ['cc_stock_full', 'cc_stock_search', 'cc_none_full', 'cc_none_search'].

## Sensitivity: nothing censored
The same gap, with every Haiku name the lexicon cannot place added to the answer's brand set, on both sides, claude.ai included. These names are not curated: some are not brands, and spelling variants count as different names, so the level is lower. It shows how much the lexicon's blind spots move the gap.

| Arm | Gap, lexicon | Gap, nothing censored | Unplaced names per answer |
|---|---|---|---|
| `opus55_plain` | +0.055 | +0.075 [+0.000, +0.156] | 0.5 |
| `cc_stock_full` | +0.056 | +0.061 [+0.003, +0.119] | 0.1 |
| `cc_stock_search` | +0.076 | +0.093 [+0.050, +0.136] | 0.4 |
| `cc_none_full` | +0.086 | +0.106 [+0.044, +0.165] | 0.2 |
| `cc_none_search` | +0.054 | +0.092 [+0.045, +0.134] | 0.7 |
| `ui_default` | | | 0.0 |

## Other measures (descriptive; links are not 009's citation objects)
| Arm | Cited-domain gap | Evaluated-domain gap | Brand-order gap |
|---|---|---|---|
| `opus55_plain` | +0.101 [+0.032, +0.169] | +0.149 [+0.065, +0.230] | +0.162 [+0.093, +0.232] |
| `cc_stock_full` | +0.097 [+0.038, +0.154] | +0.168 [+0.103, +0.241] | +0.109 [+0.050, +0.173] |
| `cc_stock_search` | +0.124 [+0.051, +0.198] | +0.184 [+0.117, +0.252] | +0.071 [+0.019, +0.122] |
| `cc_none_full` | +0.126 [+0.067, +0.183] | +0.176 [+0.111, +0.247] | +0.124 [+0.064, +0.188] |
| `cc_none_search` | +0.120 [+0.061, +0.178] | +0.168 [+0.103, +0.240] | +0.094 [+0.045, +0.146] |

## Usage on this account (reported, not gated)
Change in window utilization across each arm's 10 answers. The value rounds to 1% and other work on the account moves it. Cost is Claude Code's client-side estimate, used only to compare arms.

| Arm | Runs | Five-hour change | Seven-day change | Estimated cost per answer | Time per answer |
|---|---|---|---|---|---|
| `cc_stock_full` | 10 | +0.03 | +0.00 | $0.23 | 51 s |
| `cc_stock_search` | 10 | +0.03 | +0.00 | $0.27 | 48 s |
| `cc_none_full` | 10 | +0.03 | +0.01 | $0.28 | 61 s |
| `cc_none_search` | 10 | +0.04 | +0.00 | $0.28 | 52 s |

Across all 40 answers: five-hour 4% to 18%, seven-day 16% to 17%. Other work on the account ran at the same time and the values round to 1%, so read these as rough. One plan, and its tier is not recorded in the stream.
