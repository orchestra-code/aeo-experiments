# Data policy

The rules below apply to everything published from this repository — articles,
figures, datasets, social posts, and the companion posts on the Spyglasses
blog. They exist to protect Spyglasses customers and to keep our publications
precise about what they measure.

## Never published

1. **Customer prompts.** The prompts customers track are their competitive
   strategy. They never appear in any output, including as "examples".
2. **AI responses.** Response text is derived from customer prompts and is
   equally proprietary.
3. **Fan-out / grounding query text.** Generated from prompts, so treated the
   same as prompts.
4. **Customer identifiers.** No customer, organization, property, or
   execution IDs. Where a grouping key is analytically necessary, it is
   pseudonymized per release (`exec_0001`, …) with no published mapping.

## Always required

5. **Sample-size phrasing.** Row and sample counts are reported as
   "N citations evaluated (in this study)". We report study samples, not
   database inventories — publications say nothing about the overall size or
   contents of the Spyglasses database.
6. **Derived features only** in public datasets: scalars computed from
   content (counts, flags, scores) and verifiably public facts (e.g. a
   YouTube video's category). Raw page/transcript/description text does not
   ship.
7. **Release gate.** Every dataset goes through
   `aeo_research.release_dataset` (technical enforcement) and
   `templates/release-checklist.md` (human sign-off), including a
   re-identification review.

## Enforcement points

- `src/aeo_research/anonymize.py` — allow-list gate, forbidden-name patterns,
  cuid and free-text scans.
- `scripts/lint_article.py` — phrasing lint for articles.
- `templates/` — the rules are restated where the work happens.

If a rule blocks something you think should ship, the answer is to change the
analysis (coarsen, aggregate, derive), not to bypass the gate.
