# Experiment 003 — exploratory content-mix and funnel-stage analysis

**Status: post-hoc (2026-08-02), after the pre-registered results.**
Motivated by the product-interpretation question: is the anchored
panels' divergence an artifact of funnel stage, and how much of it is
the panel measuring the anchor's own claimed territory? The frozen
H1-H3 verdicts in results/model_summary.txt stand unchanged.

Caveats: raking uses 4 flag marginals only (no interactions);
effective sample sizes are small because few human prompts phrase
things the way the panels do — treat the explained-fraction numbers
as descriptive, not tested. The generator snapshots
(data/raw/generator/*.json) document the encoded positioning: Bose =
noise cancelling / wireless / battery / frequent-flyer segments;
Soundcore = earbud product lines (open-ear, sleep, workout) from a
homepage-only crawl.

## A. Decision-stage subset (awareness query types dropped)
Dropped 25 prompts (buyers_journey_awareness, category_entry_point); spy_a keeps 24/37, spy_b 25/37; hum/neu carry no query-type labels and are unchanged.
Zero-brand response rate: hum 0.057, spy_a 0.150, spy_b 0.040, neu 0.030
- H2_spy_a: +0.162 [+0.102, +0.240]
- H2_spy_b: +0.280 [+0.235, +0.352]
- H3_own_vs_hum:spy_a: -0.157 [-0.299, -0.014]
- H3_own_vs_hum:spy_b: +0.047 [-0.087, +0.170]
- H3_did: +0.571 [+0.306, +0.822]
Reading: intent mix explains roughly a third of spy_a's H2 gap (0.248 -> 0.162) and none of spy_b's (0.261 -> 0.280); the anchor DiD *grows* on the decision-stage subset (+0.411 -> +0.571). The pre-registered verdicts are not an artifact of funnel stage.

## B. Content mix — does asking the panel's questions produce the panel's market?

Within the HUMAN panel: share shift when a flag is present (percentage points; n = prompts with flag):
- f_form_factor (n=16): anker -0.30, apple +0.07, bose -0.13, jbl -0.07, sennheiser -0.21, sony -0.16
- f_wireless (n=16): anker -0.19, apple -0.22, bose -0.17, jbl +0.12, sennheiser -0.24, sony -0.17
- f_noise_cancel (n=29): anker +0.05, apple -0.02, bose +0.07, jbl +0.03, sennheiser -0.04, sony +0.03
- f_budget_specific (n=23): anker +0.06, apple +0.02, bose -0.25, jbl +0.32, sennheiser -0.16, sony -0.09
- f_travel_context (n=116): anker +0.21, apple -0.02, bose +0.13, jbl +0.01, sennheiser +0.07, sony +0.13
- f_usage_music (n=102): anker +0.06, apple -0.04, bose +0.13, jbl +0.01, sennheiser +0.22, sony +0.13
The budget flip (bose down, jbl up) replicates 002's exploratory sub-intent finding on fresh data: prompt content steers brand mix.

Raking hum to spy_a's flag mix ({'form_factor': 0.3, 'wireless': 0.35, 'travel_context': 0.16, 'usage_music': 0.14}):
- effective sample size 15 of 143 human prompts
              hum  hum_reweighted  spy_a
anker       0.729           0.487  0.346
apple       0.485           0.431  0.395
bose        0.824           0.534  0.551
jbl         0.241           0.246  0.081
sennheiser  0.776           0.495  0.486
sony        0.877           0.625  0.584
- share MAD vs spy_a: 0.248 -> 0.068 (72% of the gap explained by content mix)

Raking hum to spy_b's flag mix ({'form_factor': 0.78, 'wireless': 0.38, 'travel_context': 0.22, 'usage_music': 0.05}):
- effective sample size 7 of 143 human prompts
              hum  hum_reweighted  spy_b
anker       0.729           0.458  0.773
apple       0.485           0.411  0.470
bose        0.824           0.472  0.568
jbl         0.241           0.270  0.146
sennheiser  0.776           0.315  0.162
sony        0.877           0.578  0.335
- share MAD vs spy_b: 0.261 -> 0.165 (37% of the gap explained by content mix)

## C. Home turf — anchor share and rank by panel

bose:
- Human prompts (survey): share 0.824, rank 2/6
- Spyglasses panel — Bose anchor: share 0.551, rank 2/6
- Spyglasses panel — Soundcore anchor: share 0.568, rank 2/6
- Neutral generator panel: share 0.745, rank 3/6

anker:
- Human prompts (survey): share 0.729, rank 4/6
- Spyglasses panel — Bose anchor: share 0.346, rank 5/6
- Spyglasses panel — Soundcore anchor: share 0.773, rank 1/6
- Neutral generator panel: share 0.765, rank 2/6
Reading: bose ranks 2nd everywhere — it trails sony even on its own panel (the instrument does not flatter its anchor). anker swings from 1st on its own panel to 5th on the rival's; panel choice sets the leaderboard.

## What this supports, and what it does not
Supports: the conditional-share-of-voice reading of an anchored
panel (it asks the questions the brand's positioning claims; for
the Bose panel ~72% of the share gap is content mix), and the
asymmetric signal (winning at home is expected; bose trailing sony
at home is the notable finding).
Does not rescue: spy_b (37% explained, eff. n 7 — its mix largely
leaves human phrasing space; the catalog-tilt critique stands for
that draw), the neutral panel's H2 miss, or any absolute
market-share claim from an anchored panel.
