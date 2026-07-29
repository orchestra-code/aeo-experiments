# The "31 Methodology Questions" article → research agenda map

A widely-shared 2026 article poses 31 methodology questions to AI-visibility
/ prompt-tracking vendors, arguing the burden of proof is on vendors making
the positive claim. The tone is adversarial; the questions are mostly
empirically testable. This note maps them onto this program's experiments —
what's answered, what's planned, what's out of reach — so specs and articles
can cite question numbers directly.

## Answered (at least partially) by shipped work

| Q | Question (short) | Where |
|---|---|---|
| 8 | When is one run per prompt sufficient? | 002: within-prompt Jaccard levels (brands 0.736) + exploratory 92 panel simulation (70 phrasings once ≈ ±7 pts vs 10 phrasings daily ≈ ±15 pts) |
| 12 | Is daily cadence meaningful vs stochastic variation? | 002 R5: across-wave vs same-wave between-prompt levels — no day drift over the week |
| 18 | Test–retest reliability? | 002: within-prompt condition IS test–retest at 24h spacing; per-family levels published with CIs |
| 3/7 (partially) | Do tracked prompts resemble real usage / does scale add validity? | 002: phrasing effect is REAL (equivalence rejected) — phrasing choice moves brand sets more than run-to-run noise, so prompt selection is not free |

## In flight

| Q | Question (short) | Where |
|---|---|---|
| 3 | How were prompts shown to represent the population? | **003** H1/H2: synthetic panels vs 143 contemporaneous human phrasings, response- and share-level |
| 6 | Can prompt selection determine the result? | **003** H3: anchor-bias difference-in-differences across two brand-anchored panels |
| 7 | Scale vs representativeness | **003** H1×H2 dissociation: fluent prompts, wrong sampling frame |
| 17 | What does synthetic persona/prompt text represent? | **003** H4: phrasing-flag coverage per panel (pre-freeze look: panels emit 5–8% of human flag-profiles; anchored panels almost never mention the actual scenario) |
| 16 / 18 | Execution environment vs real sessions; reproducibility outside the platform | **004 (sketch)**: UI-proxy vs API-bare vs API-matched instrument divergence, judged against the run-to-run noise floor |

## Good future candidates

- **Q19 cross-vendor agreement**: same prompts, same window, N tracking
  platforms — publishable disagreement matrix. Needs accounts/cooperation;
  methodology is 004's noise-floor logic across vendors.
- **Q4/Q11 effective sample size**: estimate intra-portfolio correlation from
  002/003 pair data → publish "N configurations ≈ K independent intents"
  shrinkage factors.
- **Q29 external outcomes**: does visibility movement predict AI referral
  traffic? Uniquely answerable here — Spyglasses has first-party
  crawler/referral analytics. Longitudinal, needs careful confounding
  controls (brand size, seasonality); the strongest possible answer to the
  article and the hardest.
- **Q26 methodology-change honesty**: not an experiment — a product/docs
  practice audit (mark instrument changes on trend charts; llm-platforms.ts
  model bumps already sync to the public methodology doc).

## Out of reach (say so, don't fudge)

- Q16 fully (logged-in personalized sessions — unobservable from outside).
- Q2/Q5/Q20-25 as research: they are product-disclosure questions (what the
  score means, weighting, entity resolution, failure handling, auditability)
  — answered by documentation and product behavior, not studies.
- Q29 causal chain to revenue (Q27): correlational designs only, without a
  randomized content intervention.

## Posture

Publish the numbers whatever they say (002 published its own thesis
reversal). Cite question numbers explicitly in articles so readers can score
the answers. Never claim beyond the instrument ("via DataForSEO's scraper"
travels with every ChatGPT claim).
