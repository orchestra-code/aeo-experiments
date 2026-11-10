# Experiment 010, Stage 2: article outline (approved framing, 2026-11-09)

Target: `site/src/content/articles/ai-shortlist-stability-over-time.mdx` (EN),
the Stage 2 dataset update, and a companion blog post (EN and DE) in the
spyglasses repo. Stage 1 article: `ai-shortlist-stability.mdx` (published
2026-10-11); it pre-announced this test.

Sources for every number: `results/stage2_model.md` (+ `.json`),
`results/stage2_robustness.md`, `results/stage2_audits.md`, `spec.md`
(deviations 9 and 10). Figures: `results/figures/stage2_shortlist_by_lag.png`
(hero + lead), `stage2_status_by_lag.png` (secondary).

## Framing (Jim, 2026-11-09)

**"The shortlist held for a month."** ChatGPT and Claude are stable over five
weeks; Gemini is less stable but not drifting (its test is inconclusive, not
a drift). One short note on Gemini's top pick, the only thing that clearly
moved over time; it fits Stage 1: chase the shortlist, not the top spot.
Shortlist first, as in article 1.

## Numbers (final)

1,320 new answers evaluated in this study (40 B2B prompts x 11 waves x
ChatGPT, Gemini, Claude API; Oct 3 to Nov 6), plus 1,615 older ChatGPT
headphone answers (secondary drift check, up to 20 days apart).

**H5 (primary, Holm x3, TOST +/-0.05): shortlist repeat rate for answers 27+
days apart minus answers 1 to 2 days apart.**

| Platform | 1-2 days | 27+ days | Far minus near | Holm CI | Verdict |
|---|---|---|---|---|---|
| ChatGPT | 0.82 | 0.81 | -0.01 | [-0.04, 0.01] | practically equivalent (no drift) |
| Claude API | 0.79 | 0.76 | -0.02 | [-0.04, -0.01] | detectable but negligible |
| Gemini | 0.64 | 0.62 | -0.02 | [-0.06, 0.02] | inconclusive (interval passes -0.05) |

Pairs: ChatGPT 438 near / 320 far; Gemini 440 / 320; Claude 440 / 320.
H_pos passes (cross-category 0.01). Curve (shortlist by days apart, 1-2, 3-6,
7-13, 14-20, 21-26, 27-34): ChatGPT 0.82 .80 .82 .82 .80 .81; Claude API
.79 .77 .78 .77 .75 .76; Gemini .64 .65 .63 .64 .63 .62.

**Secondary (no correction):**
- Gemini top pick: 0.40 near, 0.23 far, -0.17 [-0.31, -0.04], real change.
  ChatGPT top pick 0.59 vs 0.60 and Claude 0.43 vs 0.46: inconclusive (top
  picks are rare; wide intervals).
- Best-for use case: ChatGPT -0.03 negligible, Claude API -0.03 negligible,
  Gemini -0.04 real (small).
- ChatGPT headphones (older data, 15+ days vs 0-2 days): -0.02 negligible.
- Stage 1 contrasts recomputed on all 11 waves (descriptive, no new
  verdicts): shortlist minus exact position 0.46 / 0.38 / 0.56, same as
  Stage 1.

**Robustness:** regression of pair repeat rate on days apart, change per 30
days: shortlist -0.01 (ChatGPT), -0.02 (Gemini), -0.03 (Claude API).
Alternative bins (0-6 vs 27-34 days): same verdicts. ChatGPT gpt-6 answers
only (waves 6-11, R2): +0.01 [-0.03, 0.05], no drift, on few pairs (39 near
/ 80 far). Every other check: same.

**Caveats:** ChatGPT changed from gpt-5-6 (waves 1-5) to gpt-6 (waves 6-11),
so its month-apart pairs span the change: no drift even so. One Gemini answer
reported "3.6 Flash". Placebo (H5 on random halves, +/-0.05) inconclusive on
ChatGPT and Gemini: underpowered by design (deviation 10j), a warning not a
stop. Collection: every wave 40/40; a few late retries (deviations 2, 9).
Five weeks, one season, the same caveats as article 1 (one question is not a
category; synthetic B2B questions; US; DataForSEO for ChatGPT and Gemini,
Anthropic API for Claude; no claude.ai in Stage 2).

## Mandatory content

What we can and cannot claim; the band and why 0.05; inconclusive vs null for
Gemini; pre-registration (spec 6342963, Stage 2 fixed before Stage 1 results
were seen) and deviations 9 and 10; audits; robustness; data and code. No
vendor names, no answer text, "answers evaluated in this study".
