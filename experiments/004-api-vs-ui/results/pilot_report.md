# Experiment 004: feasibility report

Scored against `sketch.md` (G1 to G4, per platform). Pilot data, never part of a confirmatory analysis. Aggregates only: no brand, answer or prompt text. Prompts: 10; UI rounds: 3; API arms: one answer per prompt. Costs are estimates at list prices checked 2026-11-05 (`harness/exp004.py`).

## ChatGPT

### G1, clean instrument

| Arm | Answers | Need | Model ids reported | Model check | First-try failures or app error messages | G1 |
|---|---|---|---|---|---|---|
| `cg_ui` | 30 | 28 | `gpt-6` 30 | 30 report `gpt-6`, need 28 | 0 of 30 submissions | PASS |
| `cg_api_plain` | 10 | 9 | `gpt-6-luna` 10 | 10 of 10 report `gpt-6-luna` | 0 failed attempts | PASS |
| `cg_api_low` | 10 | 9 | `gpt-6-luna` 10 | 10 of 10 report `gpt-6-luna` | 0 failed attempts | PASS |
| `cg_api_leak` | 10 | 9 | `gpt-6-luna` 10 | 10 of 10 report `gpt-6-luna` | 0 failed attempts | PASS |

### Behavior per answer

| Arm | n | Searched | Search calls | Queries (fan-out) | Cited URLs | Evaluated URLs | Cited domains | Chars | Brands | No search |
|---|---|---|---|---|---|---|---|---|---|---|
| `cg_ui` | 30 | 100% | n/a | 3.7 | 22.4 | 27.9 | 9.2 | 13125 | 5.8 | 0% |
| `cg_api_plain` | 10 | 100% | 3.3 | 12.3 | 6.5 | 63.6 | 4.8 | 4286 | 5.1 | 0% |
| `cg_api_low` | 10 | 100% | 14.9 | 42.0 | 7.0 | 209.7 | 5.3 | 4687 | 5.4 | 0% |
| `cg_api_leak` | 10 | 100% | 3.3 | 11.5 | 6.6 | 70.3 | 5.5 | 4348 | 4.6 | 0% |

OpenAI: search calls are `web_search_call` items; queries are the queries inside search actions. ChatGPT UI: queries are DataForSEO `fan_out_queries`.

### G2 and G3, per arm

| Arm | Buyer-facing answers | Flagged | Searched (API) | Leak-syntax answers | Haiku names | Covered by lexicon v3 | Domains parse when searched | G2 | G3 |
|---|---|---|---|---|---|---|---|---|---|
| `cg_ui` | 100% | 0 | n/a | 0 | 236 | 99% | 100% | PASS | PASS |
| `cg_api_plain` | 100% | 0 | 100% | 0 | 59 | 98% | 100% | PASS | PASS |
| `cg_api_low` | 100% | 0 | 100% | 0 | 73 | 97% | 100% | PASS | PASS |
| `cg_api_leak` | 100% | 0 | 100% | 0 | 62 | 97% | 100% | PASS | PASS |

Flagged = no lexicon brand, a short answer with a question and no brand, or the app's error message; listed by id on stdout for a person to read. Cleared by reading: 0. Leak syntax: tool records, reference ids, web app components or tool JSON (`harness/leaks.py`, `TOOL_SYNTAX`); gated on leak arms only. Covered: a Haiku name counts when a lexicon alias of the prompt's category matches inside it.

### G4, brand gap against the UI

Gap = UI against itself across the 3 rounds, minus the arm against the UI. Positive means further from the UI than the UI is from itself. 90% interval, prompt-level bootstrap. A screen, not a test.

| Arm | Brand gap [90% CI] | Mean overlap with UI | Prompts | Passed G1 to G3 |
|---|---|---|---|---|
| `cg_api_plain` | +0.059 [+0.005, +0.111] | 0.664 | 10 | yes |
| `cg_api_low` | +0.007 [-0.068, +0.085] | 0.715 | 10 | yes |
| `cg_api_leak` | +0.092 [+0.031, +0.151] | 0.631 | 10 | yes |

UI against itself on these prompts: 0.722. For scale, 009's confirmatory gap (Opus 5.5 API vs claude.ai) was +0.067.

**G4 PASS:** arms that passed G1 to G3 with a gap of at most 0.2: ['cg_api_leak', 'cg_api_low', 'cg_api_plain'].
**Selection rule:** first arm `cg_api_low` (smallest gap +0.007 by `cg_api_low`; a plain arm is preferred within 0.03). Other arms that passed G4, by gap: ['cg_api_plain', 'cg_api_leak'] (at most one more joins the spec).

## Gemini

### G1, clean instrument

| Arm | Answers | Need | Model ids reported | Model check | First-try failures or app error messages | G1 |
|---|---|---|---|---|---|---|
| `gm_ui` | 28 | 28 | `3.5 Flash-Lite` 30 | 30 report `3.5 Flash-Lite`, need 27 | 1 of 31 submissions | PASS |
| `gm_api_plain` | 10 | 9 | `gemini-3.5-flash-lite` 10 | 10 of 10 report `gemini-3.5-flash-lite` | 0 failed attempts | PASS |
| `gm_api_leak` | 10 | 9 | `gemini-3.5-flash-lite` 10 | 10 of 10 report `gemini-3.5-flash-lite` | 0 failed attempts | PASS |

### Behavior per answer

| Arm | n | Searched | Search calls | Queries (fan-out) | Cited URLs | Evaluated URLs | Cited domains | Chars | Brands | No search |
|---|---|---|---|---|---|---|---|---|---|---|
| `gm_ui` | 30 | 100% | n/a | not reported | 10.6 | 10.3 | 7.5 | 5521 | 5.5 | 0% |
| `gm_api_plain` | 10 | 100% | n/a | 1.7 | 7.4 | 7.4 | 7.2 | 5459 | 5.7 | 0% |
| `gm_api_leak` | 10 | 60% | n/a | 1.2 | 3.8 | 3.8 | 3.8 | 2620 | 4.9 | 40% |

Gemini API grounding chunk URIs are redirect links. Domains come from the chunk field named here, per answer: {'web.title': 16, 'none': 4}; 0 of 113 chunks had no usable domain. No redirect was resolved. The Gemini UI scrape reports no fan-out queries, so its search depth is not observable; "searched" there means sources were reported.

### G2 and G3, per arm

| Arm | Buyer-facing answers | Flagged | Searched (API) | Leak-syntax answers | Haiku names | Covered by lexicon v3 | Domains parse when searched | G2 | G3 |
|---|---|---|---|---|---|---|---|---|---|
| `gm_ui` | 93% | 2 | n/a | 24 | 223 | 99% | 100% | PASS | PASS |
| `gm_api_plain` | 100% | 0 | 100% | 0 | 69 | 100% | 100% | PASS | PASS |
| `gm_api_leak` | 100% | 0 | 60% | 0 | 54 | 98% | 100% | FAIL | PASS |

Flagged = no lexicon brand, a short answer with a question and no brand, or the app's error message; listed by id on stdout for a person to read. Cleared by reading: 0. Leak syntax: tool records, reference ids, web app components or tool JSON (`harness/leaks.py`, `TOOL_SYNTAX`); gated on leak arms only. Covered: a Haiku name counts when a lexicon alias of the prompt's category matches inside it.

### G4, brand gap against the UI

Gap = UI against itself across the 3 rounds, minus the arm against the UI. Positive means further from the UI than the UI is from itself. 90% interval, prompt-level bootstrap. A screen, not a test.

| Arm | Brand gap [90% CI] | Mean overlap with UI | Prompts | Passed G1 to G3 |
|---|---|---|---|---|
| `gm_api_plain` | +0.101 [+0.016, +0.187] | 0.558 | 10 | yes |
| `gm_api_leak` | +0.115 [+0.011, +0.230] | 0.544 | 10 | no |

UI against itself on these prompts: 0.659. For scale, 009's confirmatory gap (Opus 5.5 API vs claude.ai) was +0.067.

**G4 PASS:** arms that passed G1 to G3 with a gap of at most 0.2: ['gm_api_plain'].
**Selection rule:** first arm `gm_api_plain` (smallest gap +0.101 by `gm_api_plain`; a plain arm is preferred within 0.03). Other arms that passed G4, by gap: none (at most one more joins the spec).

## Cost (reported, not gated)

| Arm | Answers | Estimated cost | Per answer | Full study, 120 answers |
|---|---|---|---|---|
| `cg_ui` | 30 | $0.0720 | $0.0024 | $0.29 |
| `cg_api_plain` | 10 | $0.3685 | $0.0368 | $4.42 |
| `cg_api_low` | 10 | $1.6015 | $0.1602 | $19.22 |
| `cg_api_leak` | 10 | $0.3696 | $0.0370 | $4.44 |
| `gm_ui` | 30 | $0.0744 | $0.0025 | $0.30 |
| `gm_api_plain` | 10 | $0.2715 | $0.0272 | $3.26 |
| `gm_api_leak` | 10 | $0.1919 | $0.0192 | $2.30 |

Projected full study (40 prompts x 3 waves, the UI arm and 2 API arms per platform), taking the 2 most expensive API arms per platform: about $29.80, plus the Haiku pass. UI per-answer cost includes resubmitted tasks. Haiku pass so far: $0.3024.

## Verdicts

| Platform | G1 | G2 and G3 (arms passing G1 to G3) | G4 | Pick |
|---|---|---|---|---|
| ChatGPT | PASS | `cg_api_plain`, `cg_api_low`, `cg_api_leak` | PASS | `cg_api_low` |
| Gemini | PASS | `gm_api_plain` | PASS | `gm_api_plain` |

STOP: Jim Wrubel's go/no-go before anything else starts (sketch, STOP).
