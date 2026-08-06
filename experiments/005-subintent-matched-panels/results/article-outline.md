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
5. **Ruling out the two easy explanations.** The frequency gap is neither
   a mix artifact nor noise:
   - **Not mix.** Conditioning on sub-intent does not shrink it (0.085
     travel, 0.110 music vs 0.089 unconditional) — so a client naming its
     own sub-intents would not rescue the number. *Post-hoc.* **Figure:
     F6 conditioning-mad.**
   - **Not noise, and this one is pre-registered.** R5 asks whether a
     synthetic prompt re-run five times is less self-consistent than a
     human one. Both arms come back **NULL**: mat −0.038 [−0.086, +0.009],
     neu2 −0.018 [−0.060, +0.029] against a 0.10 band. Synthetic panels
     are **as repeatable as the human panel**.

   That leaves a systematic shift in *what synthetic phrasing surfaces* —
   consistent in direction across every stratum (Apple −17 to −19 points,
   Sennheiser −13 to −18, Anker +6).

   **This is also a non-replication of our own prior study.** 003 measured
   all three of its panels as materially noisier than humans (spy_a
   −0.104, spy_b −0.111, neu −0.089, all REAL) and concluded synthetic
   prompts "occupy a less stable region of the response space." 005's
   `neu2` is an exact replication draw of that same generator and lands at
   −0.018 NULL, while the human baseline barely moved between studies
   (within-prompt overlap 0.724 → 0.704). Report it as a **non-replication,
   not a contradiction** — the two intervals overlap in [−0.060, −0.039],
   so the studies are not statistically distinguishable. What does not
   survive is the general claim that synthetic prompts are inherently
   noisier.

   *Deliberately not argued:* that LLM answers vary run-to-run. That is
   the audience's default assumption and restating it would read as
   excuse-making for the failed prediction. The per-brand stability
   numbers stay in `exploratory_subintent_residual.md` as measurement
   context, not as a narrative beat.
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
| R5 repeatability mat −0.038, neu2 −0.018, both NULL | `model_summary.txt` |
| 003's R5 for comparison: spy_a −0.104, spy_b −0.111, neu −0.089, all REAL | 003 `model_summary.txt` |
| within:hum 0.704 (005) vs 0.724 (003) — stable baseline | both `model_summary.txt` |
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
4. **R5 cuts against a claim we published four days ago.** 003's article
   said synthetic prompts are noisier run-to-run; 005 says they are not.
   State it in the body, not only in the caveats, and state the CI overlap
   that keeps it a non-replication rather than a refutation. A program
   whose credibility rests on pre-registration has to report its own
   non-replications first and loudest.

## Next section — no pre-announcement this time

**Decision (Jim, 2026-08-06): this article names no follow-up study.**

003 could name 005 with specificity because we knew we could run it — the
panels were already generated and the harness was built. Nothing is in that
position today, and a bet we cannot honour costs more credibility than
staying quiet earns. The section instead closes on what the result changes
about how we read our own product, and states plainly that the open
question is whether the recipe survives without a human panel to copy —
without promising a date or a design.

Held back until feasibility is proven (see `results/006-feasibility.md`
when it exists): public Q&A venues as a *neutral* sub-intent source,
designed as a 2×2 on intent-source × prompt-format so "is it the intent or
the register?" is separable.

## Companion blog post (EN + DE)

Shorter, practitioner-framed, per `templates/blog-brief.md`. Lead with the
operational takeaway rather than the pre-registration narrative:

> A synthetic prompt panel can tell you **which** brands you're competing
> with for a use case, and roughly **where you stand**. The one thing it
> does not reproduce is how *often* each brand comes up — so read the
> consideration set, not the percentage.

Supporting beat, because it is genuinely counterintuitive: a
sub-intent-matched synthetic prompt is **as self-consistent as a human
one** when re-run. The gap is not that synthetic prompts are flaky; it is
that they systematically surface the consensus picks and under-surface
everything else.

Links back to the research article for the evidence. No date prefix in
filenames. Both language versions required.
