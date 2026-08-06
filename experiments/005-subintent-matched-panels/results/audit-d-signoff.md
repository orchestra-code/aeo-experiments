# Audit D — manual spot-check sign-off

**Result: PASS** (precision 0.974 ≥ 0.95, recall 0.919 ≥ 0.90), with four
extraction defects found, quantified, and logged as deviations. None of
them changes a pre-registered verdict.

## Method — independent blind labelling

This is the **first independent blind labelling pass in the program.** 003's
Audit D was a *verification* pass (the extractor's output was read alongside
each answer and confirmed), which is anchored on the list provided and is
therefore weak on recall. Here the extraction was withheld entirely.

- **Sample:** 30 headphone-panel responses, `data/interim/spotcheck_blind.md`,
  drawn with seed 20260802 — 20 `hum`, 9 `mat`, 1 `neu2`, spread across all
  five waves.
- **Task:** list every brand name appearing anywhere in the answer,
  deduplicated, in first-appearance order — mirroring `extract_brands()`
  (Audit B's label definition), explicitly *not* a judgment about which
  brands were recommended. Labellers were instructed to include brands
  suspected to be outside the lexicon, since recall is otherwise trivially 1.
- **Reviewer:** Jim Wrubel, 2026-08-06. Answer key (`spotcheck_key.md`) was
  not consulted during labelling.
- **Adjudication:** the 14 raw disagreements were re-examined against the
  source text; Claude proposed a classification and Jim ruled on it.

## Scores

| | Raw | Adjudicated |
|---|---|---|
| Precision | 0.880 (**fail**) | **0.974** (pass) |
| Recall | 0.912 (pass) | **0.919** (pass) |
| tp / fp / fn | 103 / 14 / 10 | 114 / 3 / 10 |

**11 of 14 raw false positives were confirmed correct extractions** that the
labelling missed — brands appearing in comparison tables, parentheticals,
and secondary sections (e.g. three `### Soundcore Space One` product
headings in #3; `### Technics EAH-AZ100` in #5; "Soundcore Q20i" in #7;
"Apple ecosystem (iPhone, iPad, Mac)" in #18/#19/#22). Attributable in part
to task design: the instruction stated that role does not matter, but a
13,000-word pass naturally pulls toward salient recommendations.

## Defects found (all logged in spec.md → Deviations)

**D1 — brand-as-platform false positives (3 of 3 confirmed FPs).** A single
failure mode: the lexicon matches a brand used as a *platform or service*
reference rather than a product. "such as **Apple Music**, Tidal, or Qobuz"
(#8); "What phone does he use? – **Samsung Galaxy** – **Google Pixel**"
(#23). Impact measured below.

**D2 — JLab is untracked and above the basket floor.** JLab appears in
**6.7% of human responses**, over the 5% threshold, so the H2 basket should
have contained 7 brands rather than 6.

**D3 — niche brands untracked, human-panel-only.** HiFiMAN (6 responses),
iClever (13), Belkin (8), BuddyPhones (5), eKids (3) — every occurrence
across the full 1,190-response dataset is in the `hum` arm. This is not a
sampling artifact and it *strengthens* the study's finding that human
prompts surface brands synthetic panels never reach.

**D4 — two gaps are not cleanly fixable.** boAt and Noise (Indian market)
collide with common English words — a bare `noise` alias matches 96% of
responses (noise cancellation). `Nothing` is only catchable as `nothing ear`;
#19's "design-forward brands like Nothing" is a true miss with no safe fix.
These require multi-word aliases, not bare ones.

## Impact on pre-registered verdicts — none

Per the frozen-instrument rule the lexicon was **not** refitted; the frozen
result stands as primary and these are reported as remedy checks.

| Correction | mat H2 MAD | neu2 H2 MAD | Verdict |
|---|---|---|---|
| As frozen (primary) | 0.0893 | 0.1372 | REAL |
| D2: 7-brand basket incl. JLab | 0.0783 | 0.1186 | REAL, unchanged |
| D1: product-only Apple aliases | 0.0827 | 0.1313 | REAL, unchanged |
| **D1 + D2 combined** | **0.0727** | **0.1135** | REAL, unchanged |

D1 also narrows the Apple gap (mat − hum) from −0.212 to −0.173: roughly
**18% of the single largest per-brand deviation is an extraction artifact**,
and it is differentially distributed (human answers carry platform-only
Apple references at 5.0% vs mat's 1.1%) — i.e. it biases in the direction
that flatters the headline. 82% of the gap survives, and both corrections
push the same way without moving either verdict off REAL.

## Known limit of this audit

30 responses detects a brand appearing in ≥10% of answers with ~96%
probability, 5% with ~79%, and 2% with ~45%. Gaps in the deep tail are
likely to remain. Recall is measured against what a human labeller spotted,
so it is an upper bound on true recall.

## Automated cross-check

The extractor recovered **100%** of DataForSEO's own brand/product entity
annotations on the 287 of 1,190 responses that carried them
(`results/audit.txt`, Audit D).

## Sign-off

- Blind labelling: **Jim Wrubel, 2026-08-06**
- Adjudication accepted: **Jim Wrubel, 2026-08-06**
- Lexicon: remains **frozen** as inherited from 003; defects D1–D4 recorded
  as deviations rather than refitted. Any future change must be logged under
  "Deviations from the frozen spec".
