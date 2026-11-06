# Experiment 004: power for H1 (spec §5)

Simulated with `pipeline/power_sim.py`: 1,000 studies x 1,000 bootstrap draws per true gap, seed 20261106, SESOI +/-0.1. A study passes when its interval lies inside the band. Aggregates only. Method and its limits: the script's docstring.

## Inputs

within:ui across days, experiment 010 Stage 1 (waves 1 to 7 only, submitted Oct 3 to 10, 2026; 010 Stage 2 was not read), brand-set Jaccard with 010's `extract_new` and lexicon v3:

| Platform | Answers | App error answers | Pairs | Mean over pairs | Mean over prompts (SD) | Adjacent days | Any 3 waves, range |
|---|---|---|---|---|---|---|---|
| ChatGPT | 280 | 0 | 840 | 0.701 | 0.701 (0.130) | 0.728 | 0.668 to 0.753 |
| Gemini | 280 | 0 | 840 | 0.515 | 0.515 (0.175) | 0.510 | 0.477 to 0.556 |

Models the UI scrapes reported in those answers: ChatGPT `gpt-5-6` 200, `gpt-6` 80; Gemini `3.5 Flash-Lite` 280. The ChatGPT label then was not `gpt-6`, so today's floor may differ.

Per-prompt spread from the 004 pilot (10 prompts, one day, centered): SD of the deviations D_p = within - cross, and of the cross overlap C_p:

| Platform | Values | SD of D_p | SD of C_p |
|---|---|---|---|
| ChatGPT | 20 | 0.131 | 0.134 |
| Gemini | 10 | 0.216 | 0.176 |

## Pass rates, scheme A (the spec's)

| True gap | ChatGPT pass, 95% CI | ChatGPT pass, 90% CI | Gemini pass, 90% CI | Mean half-width: ChatGPT 95%, ChatGPT 90%, Gemini 90% | Mean estimate: ChatGPT, Gemini |
|---|---|---|---|---|---|
| 0.000 | 100% | 100% | 88% | 0.037, 0.031, 0.050 | +0.005, +0.002 |
| 0.025 | 94% | 96% | 78% | 0.038, 0.032, 0.050 | +0.028, +0.025 |
| 0.050 | 68% | 77% | 52% | 0.038, 0.032, 0.050 | +0.052, +0.048 |
| 0.075 | 26% | 36% | 26% | 0.038, 0.032, 0.050 | +0.076, +0.071 |
| 0.100 (false pass) | 3% | 5% | 8% | 0.038, 0.032, 0.050 | +0.101, +0.094 |
| 0.125 (false pass) | 0% | 0% | 3% | 0.038, 0.032, 0.050 | +0.125, +0.116 |

## Brackets: scheme B (no covariance) and scheme C (exchangeable days)

| True gap | Scheme | ChatGPT pass, 95% | ChatGPT pass, 90% | Gemini pass, 90% | Mean half-width: ChatGPT 95%, Gemini 90% | Mean estimate: ChatGPT, Gemini |
|---|---|---|---|---|---|---|
| 0.000 | B | 90% | 97% | 75% | 0.065, 0.068 | +0.000, +0.000 |
| 0.025 | B | 70% | 83% | 59% | 0.065, 0.068 | +0.025, +0.025 |
| 0.050 | B | 24% | 42% | 27% | 0.065, 0.068 | +0.050, +0.050 |
| 0.075 | B | 4% | 9% | 6% | 0.065, 0.068 | +0.075, +0.075 |
| 0.100 | B | 0% | 0% | 1% | 0.065, 0.068 | +0.100, +0.100 |
| 0.125 | B | 0% | 0% | 0% | 0.065, 0.068 | +0.125, +0.125 |
| 0.000 | C | 98% | 98% | 100% | 0.037, 0.035 | +0.001, +0.000 |
| 0.025 | C | 89% | 92% | 91% | 0.037, 0.035 | +0.026, +0.025 |
| 0.050 | C | 68% | 75% | 69% | 0.037, 0.035 | +0.051, +0.050 |
| 0.075 | C | 35% | 40% | 40% | 0.037, 0.035 | +0.076, +0.075 |
| 0.100 | C | 8% | 12% | 10% | 0.037, 0.035 | +0.101, +0.100 |
| 0.125 | C | 1% | 2% | 0% | 0.037, 0.035 | +0.126, +0.125 |

Reading: "pass" at a true gap of 0.100 or more is a false pass. ChatGPT's first Holm test is read at 95% and its second at 90%; Gemini's single test at 90%.

Draws were not reduced: 1,000 studies x 1,000 draws for every cell.
