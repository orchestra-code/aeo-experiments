# Exploratory: prompt-attribute slices (NOT pre-registered)

**Status:** post-hoc exploratory analysis, run 2026-07-23 after the frozen
§4/§5 results were computed. Feature flags are regex-coded from prompt text
(`pipeline/90_exploratory_features.py`); prompt text itself stays internal
(SparkToro's data). ~13 contrasts tested with no multiplicity correction;
features are correlated with each other and unadjusted (univariate deltas).
Slices are small (n=16–30 prompts on the rare features). Treat as
hypothesis-generating; anything promoted to a headline claim needs its own
pre-registered follow-up.

## Feature prevalence (143 headphone prompts)

travel context 81% · music usage 72% · movies 32% · noise-cancelling 21% ·
specific budget 17% · named recipient 15% · reviews/stars 15% · form factor
12% · battery 12% · comfort 12% · wireless 11% · age mentioned 10% ·
output count 9% · output format 5% · value language 3% (n=4 — too small,
excluded from claims)

## Brand-mention deltas with 90% prompt-cluster bootstrap CIs excluding 0

| Prompt attribute | Effect on answers |
|---|---|
| Specific dollar budget (n=24) | Bose −0.36 [−0.50,−0.23], JBL +0.31 [+0.19,+0.43], Sennheiser −0.17 [−0.32,−0.02], Sony −0.12 [−0.25,−0.00] |
| Named gift recipient (n=22) | Bose −0.19 [−0.34,−0.05], JBL +0.14 [+0.02,+0.28], cited sources −0.48 [−0.78,−0.23] |
| Form factor mentioned (n=17) | Anker −0.24 [−0.41,−0.06] |
| "Wireless/bluetooth" (n=16) | ~1 fewer brand per answer: n_brands −0.85 [−1.61,−0.15] |
| Music usage (n=103) | Sennheiser +0.23 [+0.12,+0.33], Sony +0.15 [+0.06,+0.25] |
| Travel context (n=117) | Anker +0.23 [+0.10,+0.36] |

Not significant at 90%: noise-cancelling on any brand; movies on any brand;
budget on Apple/Anker; form factor on Apple (+0.15 [−0.01,+0.30]).

## Does matching feature profiles explain the phrasing effect?

Between-prompt same-wave brand Jaccard by number of matching key features
(budget, value, noise-cancel, form factor):

- 0–1 of 4 matching: 0.48
- 2 of 4: 0.43
- 3 of 4: 0.56
- 4 of 4: 0.57

Prompts with matching attribute profiles overlap ~0.10–0.14 more than
mismatched ones — a large share of the pre-registered within-vs-between gap
(Δ = 0.20). Interpretation: much of the "phrasing effect" is not surface
wording but legible intent sub-segmentation (price frame, use case,
form factor). The residual (matched-profile pairs at 0.57 still sit below
the within-prompt level of 0.74) is unexplained phrasing/noise.

## Marketer-facing implication (for the article, labeled exploratory)

"Prompt phrasing matters" decomposes into attributes a strategist can act
on: a stated dollar budget flips the recommendation set from premium
(Bose/Sennheiser) toward value (JBL); travel framing pulls Anker in; music
framing pulls Sennheiser/Sony up. A tracking panel whose phrasing mix
over- or under-represents these attributes will systematically mis-state
brand presence — the case for stratifying both the drift panel and the
periodic sweep by price-frame, use-case, and form-factor axes.
