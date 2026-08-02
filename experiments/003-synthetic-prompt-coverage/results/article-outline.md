# Article outline — experiment 003 (synthetic prompt coverage)

Targets:
- Research article (EN): `site/src/content/articles/synthetic-prompt-coverage.mdx`
- Companion blog post (EN + DE): `apps/web/content/posts/` in the spyglasses
  repo, linking to the research article
- Hero image needed (cf. 002's `hero-source.jpg` treatment)

**Thesis.** An anchored synthetic prompt panel is not a market census, and
nobody should sell it as one. It is a test of whether you win the
conversations your positioning claims. We measured both readings against 143
human prompts, pre-registered, and published the effect sizes for our own
generator. No other vendor has done this.

**Posture.** Concede the critics' premise and out-measure it. Never argue
"synthetic panels do reflect human usage"; the data says they don't (H1/H2
for anchored panels). The counter is: the divergence is structured, it has a
mechanism, one reading of anchored panels stays valid (conditional share of
voice), one generation frame closes the response-level gap (scenario-first),
and we published our number. Ask other vendors for theirs.

## Narrative arc

1. **Cold open.** The industry's critics say synthetic prompt tracking can't
   reflect real human usage. We tested our own production prompt generator
   against 143 real human prompts to find out by how much. They're half
   right; here's the number, and here's what it changes about how to read
   share of voice.
2. **Setup.** Four panels, one intent (headphones as a travel gift), same
   platform (ChatGPT via DataForSEO's scraper), same five days, one run per
   prompt per day. 1,325 runs evaluated in this study. Pre-registered
   (frozen commit 8ab4519); human prompts courtesy of SparkToro (credit
   prominently; reproducers go to Rand Fishkin for raw prompts). Promise
   the scorecard: Q3, Q6, Q7, Q17 of the 31-questions article, cited by
   number so readers can score us.
3. **The instrument replicates.** Positive-control gate passed (0.295 vs
   002's 0.289); human-panel geometry within a point or two of last month
   (between-prompt 0.528 vs 0.537, within-prompt 0.724 vs 0.736). Whatever
   follows is not measurement noise.
4. **Headline: the anchored panels diverge at every layer (Q3, Q7).**
   H1 REAL on brands/domains/grounding for both anchored panels (−0.12 to
   −0.23 Jaccard beyond the ±0.10 band); H2 REAL for all three panels
   (MAD 0.248 / 0.261 / 0.112 vs the 0.05 band). State the equivalence
   bounds explicitly: we could have detected a 0.10 Jaccard shift and a
   5-point share shift; we found multiples of both. Figures: F1
   share-dotplot (lead), ECDFs optional appendix.
5. **The leaderboard scramble.** spy_b rank tau 0.200: Sony at 33% of
   responses where humans see 88%. A customer reading that panel is looking
   at a different market.
6. **The anchor swap (Q6).** DiD +0.411 [+0.189, +0.638]; decision-stage
   subset +0.571. Mechanism is rival suppression, not self-inflation:
   neither panel lifts its own anchor above the human baseline; each fails
   to surface the rival (Anker at 35% on the Bose panel vs 73% human).
   Figure F4. Client takeaway seeded here: competitive gaps read off an
   anchored panel are biased by construction.
7. **Why: the panel asks your positioning's questions.** The generator's
   snapshot provably encodes the anchor's promoted features and segments
   (Bose: noise cancelling, wireless, battery, frequent flyers; Soundcore:
   earbud product lines from a homepage crawl). The panels' phrasing tilt
   mirrors it (H4: spy_b +67 points form-factor). Raking the human panel to
   the panel's content mix explains 72% of the Bose panel's share gap
   (eff. n 15; state the caveat) and 37% of Soundcore's (eff. n 7 — that
   draw largely leaves human phrasing space; say so plainly). 002's budget
   flip replicates (Bose −25 / JBL +32 points on budget-mention prompts).
   Figure F5.
8. **The reframe: conditional share of voice.** An anchored panel measures
   the buying situations your positioning claims, not the market. Both
   readings, stated for clients: leading on your own anchored panel needs
   the conditional label ("among the conversations you've claimed"); losing
   on your own anchored panel is the alarm bell. Live demonstration: Bose
   ranks #2 behind Sony on every panel *including its own*; Anker swings
   1st ↔ 5th purely by anchor choice. The instrument does not flatter its
   anchor — which is also the rebuttal to "vanity metrics." Figure F6.
9. **The neutral panel and what we're changing.** Scenario-only generation
   is response-level exchangeable (H1 NULL on brands/domains) but its mix
   still misses shares by 11 points (H2 REAL) and it never emits recipient
   ages, budgets, or format asks (Q17). Synthetic prompts are also noisier
   run-to-run (R5). Product implications, stated as commitments: funnel
   stage already excluded from SoV today; scenario-first generation frame;
   phrasing diversification toward observed human behaviors; SoV labeling
   as brand-conditioned.
10. **Scorecard + limits + challenge.** Q3 fail (anchored) / pass
    (neutral, sets); Q6 real effect; Q7 fail everywhere; Q17 5–8% profile
    coverage. Limits: one intent, one platform, one locale, via scraper,
    one generator draw per anchor, single-turn phrasings on both sides
    (neither panel captures multi-turn research), raw generator output vs
    the curated panels customers actually run. Close: the burden of proof
    is on vendors, ours is published; here is the dataset; publish yours.

## Figure map

| Beat | Figure | File |
|---|---|---|
| 4 | F1 share dot-plot (lead) | `figures/share-dotplot` |
| 4 (appendix) | ECDFs | `figures/{brand,domain}-jaccard-ecdf` |
| 6 | F4 anchor bias | `figures/anchor-bias` |
| 7 | F5 content-mix reweighting | `figures/content-mix-reweight` |
| 8 | F6 rank swing | `figures/panel-rank-swing` |

## Compliance checklist (before draft review)

- [ ] Counts phrased as "1,325 runs evaluated in this study"; no database
      totals anywhere.
- [ ] SparkToro credited in the body and the acknowledgments; raw human
      prompts directed to Rand Fishkin, never republished.
- [ ] Synthetic prompt text is RELEASED (decided 2026-08-02, data-policy
      "Synthetic study prompts" exemption) as
      `synthetic-prompt-coverage-prompts.csv`; link it in the article and
      note that reproducers can re-run the panels verbatim.
- [ ] Equivalence bounds stated in prose (0.10 Jaccard / 5 share points).
- [ ] Post-hoc analyses (funnel subset, raking, home turf) explicitly
      labelled exploratory, separate from the pre-registered verdicts.
- [ ] All figures through `save_figure` (watermark + source line); no
      hand-made charts.
- [ ] "Via DataForSEO's scraper" attached to every platform claim; model
      era (`gpt-5-5`) stated.
- [ ] Voice: casual, contractions, 9th-grade level; no em-dashes; no
      "honest/genuine(ly)"; no named competitors; "AI visibility platform"
      not "AI SEO tool"; prompt tracking framed as table stakes, never
      useless.
- [ ] Q3/Q6/Q7/Q17 cited by number with links to the 31-questions article.
- [ ] `scripts/lint_article.py` passes.
- [ ] DE companion post mirrors claims exactly (no drift in numbers).

## Prerequisites

1. Audit-D spot-check sign-off (Jim) — blocks release checklist.
2. Release checklist sign-off (Jim) — blocks committing `data/public/` and
   publishing the dataset link in the article.
3. ~~Decision on releasing synthetic prompt text~~ — decided 2026-08-02:
   released via the data-policy "Synthetic study prompts" exemption.
