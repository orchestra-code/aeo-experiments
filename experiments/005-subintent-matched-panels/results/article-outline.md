# Experiment 005 — article outline (for approval before drafting)

Target: `site/src/content/articles/subintent-matched-panels.mdx` (EN) +
companion blog post (EN/DE) in the spyglasses repo.

## The obligation this article inherits

003's article closed with a public, falsifiable bet:

> "a scenario generator whose output is *stratified to the human panel's
> sub-intent profile* … should mirror the human panel at **both** the
> response level and the share level. … Either way, we'll publish the
> number."

So this piece is not free to pick its favourite framing. It has to score
that bet first, plainly, and only then explain what the result turned out
to mean. **Half the bet paid.**

## Proposed title / description

**Title:** "We bet that matching sub-intent would make a synthetic panel
mirror a human one. It reproduced which brands compete — not how often."

**Description:** Experiment 005, pre-registered: a scenario panel stratified
to 143 human survey phrasings' sub-intent profile, run beside an
unstratified panel and the re-run human panel on ChatGPT for five days.
The stratified panel's answers are statistically indistinguishable from
human ones — the closest match in this program — and its brand-share vector
still misses by 8.9 points against a 5-point band. What that gap is, and
why part of it is unreachable by any panel.

**Hero / OG:** `pool-vs-consistency.png` (F5) — it *is* the finding.
Alternative if we want continuity with 003: `share-dotplot.png` (F1).
**Recommend F5.**

## Narrative arc

1. **The bet, and the scorecard.** Five predictions registered in public
   before collection; three held. Lead with the table. State immediately
   that the central one (P2) was falsified — no burying it below the good
   news.
2. **What passed, and it passed hard.** H1 brands −0.001 against a human
   baseline of 0.517: the cleanest exchangeability result in the program,
   better than we predicted. H3′ confirms 003's pilot (travel −0.009,
   music −0.038) — 003 predicted this from cells as small as 5 prompts and
   it replicated at 46 and 41.
3. **What failed, stated straight.** H2 MAD 0.089 [0.071, 0.125], band
   0.05. Unstratified 0.137; 003's neutral 0.112. Stratification helped
   and did not suffice. Figure: F1 share dot-plot.
4. **What the failure actually is** *(the turn — post-hoc, labelled)*.
   Panel share pools a binary per response, so "off by 8.9 points" hides
   which of two very different claims is true. Split it: within travel,
   82% vs 72% of prompts *ever* surface Apple, but 9.5% vs 0% surface it
   in *all five runs*. Same brands, same rough order (τ 0.867), different
   frequency. **Figure: F5 pool-vs-consistency.**
5. **Two results that constrain how much the failure can bear.**
   - Conditioning on sub-intent does not shrink the gap (0.085 travel,
     0.110 music vs 0.089 unconditional) — so it is not a mix artifact,
     and a client naming its own sub-intents would not rescue the number.
     **Figure: F6 conditioning-mad.**
   - The metric has a noise floor the human panel does not clear against
     itself: Apple flips run-to-run within 68% of human prompts; only 12%
     return it in all five. No tail brand is returned in all five runs by
     any meaningful share of human prompts. **Tail instability is a
     property of the medium, not of synthetic panels.**
6. **Where the residual lives.** Error 0.039 on the six stratified flags
   vs 0.135 on the nine unstratified; 13% of distinct human phrasing
   profiles reproduced; never asks about movie use, recipient age, output
   count or format; over-emits comfort 4×. Matching six marginals does not
   reconstruct the joint.
7. **Our own instrument's errors** *(mandatory, not a footnote)*. The
   Audit-D blind pass found our extractor counts brands used as platforms
   ("Apple Music", "Google Pixel") — differentially, 5.0% of human
   responses vs 1.1% of the stratified panel's. **~18% of the largest
   per-brand gap is our artifact, and it biases toward our own headline.**
   JLab was untracked at 6.7% of human responses, above the basket floor.
   Both corrections reported with verdicts unchanged.
8. **What we can and cannot claim** (mandatory section).
9. **What this means if you track a brand in AI answers.**
10. **Next**, honestly scoped — see below.

## Claims ledger — every number traceable

| Claim | Source |
|---|---|
| 1,230 runs evaluated in this study, $2.95, `gpt-5-5` throughout | `results/summary.md`, `results/audit.txt` |
| Gate 0.306, perm p = 0.0002; placebo −0.003 | `model_summary.txt` |
| H1 mat brands −0.001, domains −0.001, grounding −0.054 | `model_summary.txt` |
| H2 mat 0.089 [0.071, 0.125], τ 0.867; neu2 0.137, τ 0.733 | `model_summary.txt` |
| H3′ mat travel −0.009 (n=46), music −0.038 (n=41) | `model_summary.txt` |
| Pool vs consistency (82%/72% ever; 9.5%/0% always) | `exploratory_subintent_residual.md` §C |
| Within-sub-intent MAD 0.085 / 0.110 / 0.110 | `exploratory_subintent_residual.md` §B |
| Human noise floor (Apple unstable in 68% of prompts) | `exploratory_subintent_residual.md` §C |
| Flag error 0.039 vs 0.135; 13% profile coverage | `coverage_flags.txt`, §A |
| Extraction defects D1–D4 | `audit-d-signoff.md`, `spec.md` Deviations |
| R1 inverts (RBO −0.060) | `model_summary.txt` |

## Compliance checklist (house rules)

- [ ] Sample size phrased "1,230 runs evaluated in this study" — never a
      database total. `lint_article.py` gates this.
- [ ] **No human or coffee prompt text anywhere**, including as
      illustration (SparkToro's). Synthetic prompt text is releasable and
      already public in the dataset — quote from there if an example helps.
- [ ] No answer markdown or fan-out query text.
- [ ] "via DataForSEO's LLM scraper" on every platform claim; note it is
      not the logged-in consumer product.
- [ ] Pre-registered vs exploratory marked at every turn. Sections 4–6 are
      post-hoc and must say so in-line, not only in the caveats.
- [ ] Equivalence bounds published: detectable at 0.10 Jaccard / 5 share
      points; state what we could have detected and did not.
- [ ] INCONCLUSIVE ≠ null. No primary test hit that row; say so.
- [ ] SparkToro credited for the human panel.
- [ ] All figures from `pipeline/` via `save_figure` (watermark + caption
      baked in). No hand-made charts.
- [ ] Link the frozen spec at `80e6c09` and the analysis code.
- [ ] Q3/Q7 of the 31-questions article referenced as the scorecard, per
      spec §9.

## Honest-disclosure commitments

Three places this article must resist making itself look better:

1. **Report the falsified prediction before the reframe.** The turn in §4
   is genuinely interesting, which is exactly why it must not be used to
   soften §3.
2. **Our extraction artifact flatters our headline.** State the direction
   explicitly.
3. **P3 was a split, not a clean replication.** neu2's brand contrast came
   back REAL (−0.055) where 003 measured −0.041 NULL. Report it as a
   borderline CI landing on the other side of the rule, not as a failed
   replication — and not silently.

## Next section — scoped honestly

Two questions, in this order:

1. **Is the frequency gap even recoverable?** Establish the repeatability
   floor first: how far apart are two independent *human* panels on the
   same intent? Until that is known, "matching frequency" has no defined
   target. This is cheap and should come before any new panel design.
2. **Does the recipe survive without a human panel to copy?** The
   stratification targets came from a survey — the recipe's stated cost.
   006 sketch: public Q&A venues (Reddit / AlsoAsked) as a *neutral*
   sub-intent source, designed as a 2×2 on intent-source × prompt-format
   so "is it the intent or the register?" is separable. **Gated on Reddit
   access**, which is currently unsolved. Do not pre-announce 006 in this
   article with the specificity 003 used for 005 unless access is proven
   first — 003's bet was publishable because we could actually run it.

## Companion blog post (EN + DE)

Shorter, practitioner-framed, per `templates/blog-brief.md`. Lead with the
operational takeaway rather than the pre-registration narrative:

> A synthetic prompt panel can tell you **which** brands you're competing
> with for a use case, and roughly **where you stand**. Treat any
> share-of-voice *percentage* it produces as a soft number — partly because
> the panel is synthetic, and partly because the underlying metric moves
> run-to-run even for human prompts.

Links back to the research article for the evidence. No date prefix in
filenames. Both language versions required.
