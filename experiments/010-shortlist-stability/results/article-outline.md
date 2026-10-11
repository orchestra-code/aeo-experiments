# Experiment 010, Stage 1: article outline (approved framing, 2026-10-11)

Target: `site/src/content/articles/ai-shortlist-stability.mdx` (EN, `draft: true`
until Jim flips it), the Stage 1 public dataset through the release gate, and
a companion blog post (EN and DE) in the spyglasses repo, outlined in
`results/blog-post-outline.md`.

Sources for every number: `results/stage1_model.md` (+ `.json`),
`results/stage1_robustness.md`, `results/stage1_audits.md`,
`results/audit_d_score.json`. Spec frozen at `6342963` (2026-10-03); deviations
1 to 8 in `spec.md`; instruments frozen at STOP 2 (2026-10-11, see the spec's
"Instrument freeze" section).

## Framing (Jim, 2026-10-11)

- **The story is the shortlist.** When ChatGPT or Claude recommends a B2B
  software vendor for a buyer's question, it recommends that vendor again in
  about four of five repeat runs. Gemini's shortlist is noticeably less
  consistent. "Chasing rank is futile; chasing shortlist inclusion is not."
- **Top pick and exact position are a short note late in the article**, not a
  headline. Earlier Spyglasses research already showed rank does not hold.
  One paragraph: top picks rotate inside a stable shortlist (the top pick is
  still shortlisted in the other run 95 to 99% of the time on ChatGPT and
  Claude). This also covers the judge's own top-pick noise, so it needs no
  separate section, only a sentence in the methods/claims.
- **Also notable:** "best for" use cases are less stable than the shortlist
  (possible follow-up study on why); the platforms disagree with each other
  on the shortlist; a small caveat that ChatGPT changed models mid-collection
  (which also leaves fewer days per model).
- **Figures:** lead with the shortlist only. Hero + lead figure
  `stage1_shortlist.png`; then `stage1_shortlist_runs.png` (stable core) and
  `stage1_platform_agreement.png`. The all-status figures
  (`stage1_retention.png`, `stage1_gaps.png`) go in an appendix at most.
- **Close by pre-announcing Stage 2** (as the 003 article pre-announced 005).

## Title and description (proposals)

- Title: "When AI shortlists your software, it usually shortlists you again"
  (alt: "AI's B2B shortlist holds up from run to run. Rank does not.")
- Description: pre-registered; 40 B2B software buying questions asked on 7
  days on ChatGPT, Gemini and Claude; shortlist repeat rates 81% / 78% / 64%;
  claude.ai replication 75%; ranks and top picks move far more.

## Numbers (final)

Answers evaluated in this study, Stage 1: 840 new answers (40 prompts x 7
waves x ChatGPT, Gemini, Claude API, 2026-10-03 to 2026-10-09) plus 234
claude.ai answers from experiment 009's holdout (26 prompts x 3 runs x 3
arms; the primary arm `ui_default` = 78 answers), plus 1,615 ChatGPT consumer
(headphone) and 81 agency answers (secondary). Total 2,770.

**Shortlist (recommended = top choice or one of many) retention within
prompt** (share of shortlisted vendors shortlisted again in another run of
the same question; pooled Dice; 90% CI, prompt-cluster bootstrap):

| Platform | Shortlist again | Exact position again | H1 (shortlist minus position) |
|---|---|---|---|
| ChatGPT (gpt-5-6 / gpt-6) | 0.81 [0.78, 0.84] | 0.35 | 0.46 [0.42, 0.50] Holm-supported |
| Claude API (Opus 5.5) | 0.78 [0.76, 0.81] | 0.22 | 0.56 [0.52, 0.59] supported |
| claude.ai (Opus 5.5, 009 holdout) | 0.75 [0.71, 0.80] | 0.28 | 0.47 [0.41, 0.53] supported |
| Gemini (3.5 Flash-Lite, app) | 0.64 [0.60, 0.68] | 0.27 | 0.37 [0.33, 0.41] supported |

H_pos passed everywhere (cross-category overlap 0.01 to 0.02).

**Stable core** (share of all shortlist places across a question's 7 runs
held by vendors shortlisted in every run / 5-6 / 2-4 / 1 run): ChatGPT 60 /
19 / 17 / 4; Claude API 56 / 19 / 21 / 4; Gemini 32 / 31 / 28 / 9. Vendor
view (brand-prompt pairs shortlisted at least once): shortlisted in >= 80% of
runs ChatGPT 50%, Claude API 43%, Gemini 25%; in only one run 18% / 18% /
32%. claude.ai (3 runs): 47% in every run, 34% in one.

**Context, market concentration:** two DIFFERENT questions in the same
category share 0.59 (ChatGPT), 0.47 (Claude API), 0.45 (Gemini), 0.50
(claude.ai) of their shortlist; the same question repeats 0.81 / 0.78 / 0.64
/ 0.75. Within minus between: 0.22, 0.32, 0.20, 0.25. Part of the stability
is a market's well-known vendors; the question adds the rest.

**Platforms disagree** (same prompt, same wave, shortlist overlap): ChatGPT
vs Gemini 0.63 [0.59, 0.67], ChatGPT vs Claude API 0.63 [0.59, 0.67], Gemini
vs Claude API 0.55 [0.52, 0.58]. Each platform agrees with itself on another
day more than with another platform on the same day (except Gemini, whose
self-agreement 0.64 equals its agreement with ChatGPT).

**Best for a use case (H7, secondary):** brand + use-case segment retention
0.51 (ChatGPT), 0.52 (Claude API), 0.46 (claude.ai), 0.39 (Gemini); shortlist
minus use case 0.25 to 0.30, all supported. The exact wording grouped as
phrases repeats 4 to 9% of the time. Segment classifier test-retest 96%.
Follow-up study idea: why the "best for" framing moves while the shortlist
holds.

**Recommended vs merely mentioned (H6):** the shortlist is exactly as stable
as the set of all vendors mentioned (difference 0.00, equivalent within
+/-0.05). The labels add meaning (which vendors are endorsed), not stability.
Shortlist differs from the mentioned set in 45% (ChatGPT), 68% (Claude API),
33% (Gemini) of answers. Answers that caution against a vendor: Claude API
28%, ChatGPT 11%, Gemini 7%; most common reason: company size fit.

**Late note, top pick and position (H2, H3, H4):** top pick repeats 0.55 /
0.43 / 0.32 / 0.39 (ChatGPT / Claude API / claude.ai / Gemini); the
first-named vendor 0.65 / 0.54 / 0.63 / 0.53; exact position 0.35 / 0.22 /
0.28 / 0.27. The top pick is less stable than the first-named vendor
everywhere (H3 supported). A top pick is still shortlisted in the other run
95% (ChatGPT), 99% (Claude API), 95% (claude.ai, interval reaches 0.88), 82%
(Gemini). Judge ceiling: re-judging identical text keeps the top pick 94%
(ChatGPT), 76 to 82% (Claude API, Gemini), 55% (claude.ai, 6 cases), while
the shortlist reproduces 97 to 100%. So top-pick churn is partly the
classifier; the shortlist is not.

**ChatGPT model change:** waves 1 to 5 report `gpt-5-6`, waves 6 and 7
`gpt-6` (from 2026-10-08). Within `gpt-5-6` alone (5 runs) shortlist
retention 0.83; conclusions unchanged (R2).

**Consumer and agency (secondary, ChatGPT, 2026-07/08 data):** headphones
shortlist 0.82 (17 runs per prompt over three weeks); brand-design agencies
0.36 (fragmented market, 27 prompts, 3 runs, underpowered). Shortlist
stability depends on how concentrated the market is.

## Mandatory content

- What we can and cannot claim: one question is not a category; US
  location, logged-out API/scraper paths (DataForSEO for ChatGPT and Gemini,
  Anthropic API for Claude), claude.ai by hand from one account; B2B software
  only for the primary claims; 7 consecutive days (Stage 2 tests time); 40
  synthetic prompts; the lexicon bounds the vendors counted (R1 with every
  vendor the classifier names gives the same conclusions); the classifier is
  an LLM (Spyglasses production recommendation classifier, gpt-5.6-luna,
  pinned); nothing about what buyers do with the answer.
- Equivalence bands and decision rules (0.10 margin for H1; 0.05 for H6).
- Pre-registration and deviations 1 to 8, plainly, including: STOP 2 ran
  late but before any metric (dev 5); citation links counted as mentions,
  found by the audit and fixed before any metric (dev 6); placebo split
  redesigned (dev 4) and the Gemini placebo came out "real change" (-0.06
  [-0.12, -0.00]; both random halves are still far above the 0.10 margin);
  refusal rule (dev 7); lead figure (dev 8).
- Audits: D precision 1.00 recall 1.00 (30 answers, read by a person);
  E judge test-retest 96% (kappa 0.89); G 96%; A 40 of 40 every wave.
- Robustness R1 to R6, R8: H1 holds everywhere.
- No brand names (published vendor codes only), no answer text. The 40 B2B
  prompts are public (009 release); headphone and agency prompts are not.

## Stage 2 pre-announcement

Waves 8 to 11 on 2026-10-16, 10-23, 10-30, 11-06 (same 40 prompts, same three
platforms, same time of day). Primary H5 (Holm across ChatGPT, Gemini, Claude
API): shortlist retention for runs at least 27 days apart minus runs 1 to 2
days apart, equivalent to 0 within +/-0.05 (TOST). Secondary: the same for
top pick and use case; ChatGPT consumer drift (>= 15 vs 0 to 2 days).
Article 2 about 2026-11-11. Everything Stage 2 uses is already frozen.
