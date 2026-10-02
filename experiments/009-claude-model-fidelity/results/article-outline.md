# Experiment 009: article outline (approved framing, 2026-10-02)

Target: `site/src/content/articles/claude-api-vs-claude-ai.mdx` (EN, `draft: true`)
plus a companion blog post (EN and DE) in the spyglasses repo, outlined in
`results/blog-post-outline.md`.

Numbers are final: 1,080 answers evaluated in this study (240 claude.ai, 840
API), waves 1 to 3 (2026-09-27, 2026-09-29, 2026-10-01). Sources:
`results/model_summary.txt`, `results/audit_report.md`,
`results/audit_d_score.json`. Spec frozen at `1730d38` (2026-09-26);
deviations 1 to 10 in the spec.

## Title and description

**Title:** "Sonnet is not a stand-in for claude.ai. Opus 5.5 through the API is close."

**Hero:** `gap-vs-cost.png` (spec §9 lead figure).

## Order of the stories (Jim, 2026-10-02)

1. **Sonnet is not a proxy for claude.ai users on Opus 5.5.** Figure
   `brand-gap.png`. Every Sonnet 5 arm is a REAL gap on brands (+0.097 to
   +0.165); Haiku +0.224. Closest Sonnet arm (leak + thinking) +0.097
   [+0.044, +0.150]: "cannot be shown to match, may differ by up to 0.15",
   never "large". Order (RBO) gaps +0.136 to +0.176. Disclosure: `sonnet5_prod`
   is our own production request; we are switching to Opus 5.5.
2. **Opus 5.5 through the API is a reasonable substitute; the leaked prompt
   adds cost, not accuracy.** Both Opus arms NEGLIGIBLE on brands (+0.067,
   +0.042); H3b +0.025 brands, -0.022 cited domains (favors no prompt).
   $0.128 vs $0.071 per call (+80%). Caveats: RBO plain +0.097 REAL at the
   edge, leak +0.044; R5 without wave 2 makes both Opus arms REAL (CIs to
   0.13 and 0.11, points 0.05 to 0.08); R4 makes plain REAL at +0.070;
   panel (b) Opus 0.67 to 0.71 against the claude.ai High reference 0.82.
3. **Reasoning level does not change the brands.** Figure
   `reasoning-level.png`. H2 UI brands -0.014 [-0.034, +0.008] equivalent;
   cited equivalent; High searched 2.5 vs 1.2 per answer and cited 6.8 vs 4.4
   domains. Sonnet default vs low effort equivalent too.

Supporting: cited-domain overlap is low even for claude.ai against itself
(0.145), so domain tracking needs repeated runs; Jim's panel questions (a)
same vendors same order and (b) same vendors any order in
`panel-agreement.png`; the $/call table (Opus no prompt costs $0.071 against
$0.065 for Sonnet no prompt and $0.081 for our production Sonnet request).

## Mandatory content

- "What we can and cannot claim": fresh account, one city, B2B software
  only, 3 waves, 40 synthetic prompts, wave 2 batch next day, pipeline built
  after collection, lexicon built from the answers and reviewed by one
  person, leak = instrument divergence, search stack differs.
- Equivalence bound (0.10 Jaccard; 5-point share line with no verdict);
  inconclusive vs equivalent; placebo caveat for Haiku (INCONCLUSIVE).
- Pre-registration and deviations 1 to 10, plainly.
- Audit D (precision 1.00, recall 0.99), robustness R1 to R7.
- No brand names, no competitor or third-party vendor names, no answer,
  query or system prompt content.

## Open

- [ ] Jim: sign `results/release-checklist.md` (and confirm exemption
      condition 2) before data/public and the site dataset copy are committed.
- [ ] After signing: `uv run python scripts/sync_site_assets.py 009-claude-model-fidelity`
      (the draft synced figures only, with `--figures-only`).
- [ ] Jim: review the draft, flip `draft: false`.
- [ ] Blog post EN + DE from `results/blog-post-outline.md`.
