# Experiment 008 — article outline (approved framing, 2026-09-11)

Target: `site/src/content/articles/brand-domain-knowledge.mdx` (EN) +
companion blog post (EN/DE) in the spyglasses repo.

Numbers are final: waves 1–10, 1,152 calls, 7,117 `site:` searches, one
model (gpt-5.6-terra) on every call. Source: `results/model_summary.txt`
and `results/audit.txt`, regenerated 2026-09-11 10:44 ET after wave 10.

## The headline (Jim, 2026-09-11)

**ChatGPT carries a stored list of brand domains and uses it when it scopes
a search with `site:`. It does not predict the domain from the name.**

Obvious to people who study the field, never confirmed under a
pre-registered design. That confirmation is the article. The migrated-domain
persistence is a real, useful, secondary finding and is told second.

## Proposed title / description

**Title:** "ChatGPT knows your domain. It is not guessing."

**Description:** Experiment 008, pre-registered: 48 brands in four tiers
(guessable, non-obvious, migrated, obscure) asked about daily for ten days
through the OpenAI Responses API with web search, recording the `site:`
operator the model types. When it consulted a brand's own site it used the
canonical domain in 98.5–100% of calls in every tier, including the
tier whose domains cannot be derived from the name. A brand that changed
domains still gets its old one consulted alongside the new one.

**Hero / OG:** `tier-accuracy.png` — four tiers, all at the ceiling. The
flat line is the finding. `tier-c-persistence.png` carries section 6.

## Narrative arc

1. **Why anyone asks.** Production data (007) shows AI assistants consult
   brand sites directly with `site:` searches. If the domain the model types
   is a stored fact, a brand can verify and fix it once; if it is generated
   from the name each run, nothing a brand does to its own site changes the
   odds, and non-obvious domains (linear.app, usemotion.com, culturedcode.com)
   are permanently exposed. State the mechanistic prior from spec §1 as
   written before collection: stored → errors concentrate in migrated brands
   and repeat the old domain; guess → errors concentrate in non-obvious
   domains, look like brandname.com, and flip between runs.
2. **The instrument, briefly, and what it is not.** Direct Responses API,
   `web_search` tool, the same path Spyglasses harvests `site:` queries from
   in production, so the observable is the model's own typed search, not a
   scraped UI. One model (gpt-5.6-terra on every call, Audit E). The pilot's
   DataForSEO scraper lost the search phase between August and September;
   say so, it is why the instrument changed pre-freeze (§8b).
3. **The result: a flat line at the ceiling.** Figure: `tier-accuracy.png`.
   Tier A 279/279, B 282/286, C 267/271, D 281/281; H_pos passes at 1.000.
   Every brand-identity call in every tier in every wave consulted the true
   domain (576 of 576). The two tiers built to trap a guesser are the proof:
   tier B (non-obvious domains, where brandname.com is a real site owned by
   someone else — bear.com, motion.com) produced 2 morphological guesses in
   ten days, both Clockwise on one comparison call;
   tier D (obscure brands, the pure-guess condition) produced none. Rule of
   three: a guess rate on brand-identity prompts above ~0.5–1.1% per tier
   would have been detected and was not. The pre-registered tier
   ordering (A ≥ B, A ≥ C) is not separated by the CIs because there is
   nothing to separate.
4. **What the few errors are, and what they are not.** Figure:
   `error-content.png`. Own-domain errors: 109 observations. 78 are a
   migrated brand's previous real domain; 2 are morphological guesses; 29
   are domains carrying the brand's own name, and after human review
   (Audit D sign-off) 26 of those are sites the brand itself owns
   (about.meta.com's investor host atmeta.com, gotomypc.com, shopify.dev,
   sony.co.jp). The one exception is Amie: three comparison calls opened on
   amieapp.com, a different company. So the genuinely wrong first
   commitments in ten days are four of 1,152 calls: Amie ×3, Clockwise ×1,
   all tier B comparison prompts; the migrated tier's old domains are
   consulted alongside the canonical one and are never the first
   commitment. H3: stale share tier C vs B +0.81 [0.77, 1.00]; guess share
   B vs C not estimable at n = 5.
5. **The pre-registered repeat test, said plainly.** H2 asked whether wrong
   domains repeat above an independence baseline estimated from the brand's
   own wrong-domain distribution. That baseline is the quantity being
   estimated: under any per-run guessing model the observed agreement is an
   unbiased estimate of Σp² itself, so the contrast cannot separate the
   mechanisms on any data. Reported as NOT IDENTIFIABLE, bands kept, verdict
   rests on H3 (error content: old real domains, not name-shaped tokens) and
   H4 (temporal structure). Two labelled supplements: cross-brand permutation
   (exploratory — wrong domains are brand-specific, which both mechanisms
   predict) and a post-hoc baseline of a uniform draw over each brand's
   frozen candidate set, identifying only where K ≥ 2, which the panel gave
   to 2 of the 8 erring brands. State the limitation once and move on: for a
   brand whose only plausible wrong domain is its old one, a repeated stored
   error and a repeated guess are the same observation.
6. **Secondary finding: a changed domain leaves a second entry in the
   list.** Figure: `tier-c-persistence.png`. Meta consulted facebook.com or
   fb.com on 31–58% of its daily `site:` searches, all ten days (52
   observations); GoTo consulted logmein.com on six of ten days (24); Zoom
   consulted zoom.us on one day (2). In
   every one of those calls the canonical domain was ALSO consulted: the old
   domain is additive, never a substitute. This is the stored-association
   signature on exactly the tier the spec predicted, with exactly the error
   content it predicted, and it is the practical takeaway for anyone who has
   migrated: keep the old domain resolving and redirecting, because the
   model will keep asking it.
7. **Self-correction (H4).** Figure: `transitions.png`. Among brands that
   erred at least once, P(correct tomorrow | wrong today) 0.89 vs
   P(correct tomorrow | correct today) 0.91, gap +0.02 [−0.10, +0.21] — no
   self-correction signal, and 18 wrong-today transitions support nothing
   beyond "not large". Within-day replicate agreement 0.965 on the label and
   0.962 on the first domain (286 wave-1 pairs).
8. **Exploratory, replicating 007.** Comparison prompts open on competitors'
   sites by design (adyen.com for Stripe, vrbo.com for Airbnb); 23 calls
   never consulted the asked brand at all. Same comparison-trigger
   pattern 007 found in the customer corpus, on a controlled non-customer
   panel. One paragraph, labelled exploratory.

## What we can and cannot claim (mandatory section — draft bullets)

- Every rate is **consultation-conditional**: "when the model consulted a
  site directly for this brand", never "the model believes". The funnel
  (calls → search → `site:` → brand-attributable `site:`) is printed.
- **One model family, API surface**, not the consumer UI; nothing about
  Perplexity, Gemini or AI Overviews.
- **Absence is an upper bound.** Every zero cell carries its 3/n bound; a
  guess-free ten days does not mean guessing cannot happen.
- **Our prompts are not your traffic.** Two templates, 48 brands; no claim
  about how often real users would be sent to a wrong site.
- **H2 as pre-registered was not identifiable**; the mechanism verdict
  rests on error content and temporal structure, and on a panel that gave
  the identifying post-hoc test only two brands.
- **Name-bearing domains** are scored non-canonical by the frozen rules;
  the human-reviewed attribution (Audit D sign-off) is applied as a labelled
  robustness layer, and accuracy is shown both ways.
- No per-brand shaming: Meta, GoTo and Zoom appear because they are the
  study's migrated tier, and their old domains still redirect. Amie appears
  because it is the one case where the model's name-bearing consult was a
  different company.

## Data and reproducibility

- Dataset: `brand-domain-knowledge-chatgpt.csv`, 1,152 calls evaluated in
  this study, derived features only; `site:` query text, answer
  text and consulted/cited domain lists are not released (counts are).
- Frozen spec at commit 891a5ab; deviations in spec §11 and
  `results/audit.txt`; Audit D sign-off in `results/audit-d-signoff.md`.
- Companion blog post: EN + DE, "Key takeaways" list after the intro, no
  dates in the slug.

## Open before drafting

- [x] Jim: Audit D review table (2026-09-11: all own-property except
      Amie/amieapp.com).
- [x] Jim: headline = stored-list confirmation; hero = tier-accuracy.
- [x] Jim: release checklist signed.
- [x] Wave 10 collected 2026-09-11 10:42 ET; pipeline re-run 10:44; no
      conclusion moved.
- [x] Committed bdeb821 (pipeline, results, data/public) and the article
      draft + site assets in the follow-up commit, 2026-09-11.
- [ ] Jim: review the draft, flip `draft: false`, push (Vercel deploys main).
- [ ] Blog post EN + DE from `results/blog-post-outline.md` in the
      spyglasses repo.
