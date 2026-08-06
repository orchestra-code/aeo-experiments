# 006 — viability confirmation and the sentence-clipping test

Date-sliced sample across the frozen window (5 slices × 100 posts), which
also removes the newest-first bias of the earlier pulls. Re-analysis of the
saved sample under three clip rules; no post text is published here.

## Funnel

| Stage | Count |
|---|---|
| Posts fetched (date-sliced, `type:post`) | 500 |
| Pass frozen criteria | 31 (6.2%) |
| Unique after cross-post collapse | 29 |
| **Usable verbatim** (no markup, no brands, no artifacts) | **6 (21%)** |
| **Usable via mechanical sentence clip** | **27 (93%)** |

Date-slicing roughly doubled the qualifying rate versus the recency-biased
pull (6.2% vs 3.0%), so the earlier estimate was pessimistic. Extrapolated:
~234 qualifying posts in the 3,773-post pool.

## The clipping counterclaim

**The objection:** you need not *rewrite* a Reddit post to use it — only
clip it at sentence boundaries, preserving the author's exact words. If a
contiguous run of a post's own sentences forms a viable brand-free prompt,
"editing makes it synthetic" is much weaker.

The clip rule is mechanical and identical for every post: strip markup,
drop a leading greeting, then take a contiguous sentence window containing
the ask that is brand-free, inside a word budget, and does not open with a
dangling connective. Three variants, from least to most charitable:

| Rule | Clip-usable | Median words | Lose **no** sub-intent flag | Lose ≥1 **stratified** flag |
|---|---|---|---|---|
| Shortest window | 27/29 (93%) | 20 | 4% | **93%** |
| Longest window (charitable) | 27/29 (93%) | 63 | 30% | **63%** |
| Longest, 150-word budget | 27/29 (93%) | 73 | 33% | **59%** |

### Verdict: the counterclaim is right about format and wrong about content

**On format it wins outright.** 93% of unique qualifying posts yield a
viable brand-free prompt through mechanical clipping alone, stable across
every rule tried. Nobody has to rewrite anything, and the "any edit makes
it synthetic" objection does not survive as stated.

**On content it fails, even at its strongest.** Under the most charitable
rule with a generous budget, **59% of clips have lost at least one of the
six sub-intent dimensions**, and only a third preserve the full profile.
`f_travel_context` — the defining intent of this study — is stripped from
9 of 27 clips even charitably, and from 25 of 27 under the tight rule.

**The mechanism is entanglement.** Brand mentions and sub-intent live in
the *same sentences*: "I have Bose QuietComfort for my flights" carries the
brand and the travel context together. A brand-free clip is therefore
frequently a context-free clip. You cannot remove the contaminant without
removing the signal.

Clipped prompts also run a median of 63–73 words against the human panel's
30 — roughly twice how people actually phrase a prompt.

### Why this matters, given 005

005 established that **sub-intent mix is what drives which brands come
back**, and that a synthetic panel's failure was precisely a mix failure.
A clipped Reddit panel inherits that same defect: the words are human, and
the sub-intent profile is not the profile of the humans who wrote them.

**Clipping converts a human post into something carrying a synthetic
panel's core flaw.** It preserves the words and loses the mix, and the mix
is the part that determines the measurement.

### The residual, and its selection problem

Roughly a third of clips preserve the full sub-intent profile. Scaled to
the pool that is ~65 prompts — nominally enough for a 55-prompt panel. But
that third is **not a random subset**: it is exactly the posts whose brand
mentions happen not to overlap their context sentences. A panel built from
them is selected on a property correlated with how the author writes, which
is a new representativeness problem in place of the old one.

## Cost

929 of 1,000 monthly archive items used; 71 remain, resetting 2026-09-01.
The trial ends before that reset, so no further collection is possible
without paying. None is needed — every analysis above is re-runnable
against the saved sample at zero cost.

## What is and is not established

**Established (one category, one intent, one tool, one window):**

- Public Reddit material at a specific commercial sub-intent is *abundant*,
  not scarce — the earlier "not viable" reading was a query artifact.
- Only ~21% of qualifying posts are usable as prompts verbatim.
- Mechanical sentence clipping raises that to ~93% — format is solvable.
- But 59–63% of clips lose stratified sub-intent, and only ~a third
  preserve it fully.
- Cross-posting inflates naive counts by 7–17%.

**Not established:**

- Anything about Quora, or about AlsoAsked/PAA beyond the observation that
  its questions are short, formulaic, and often not purchase-intent.
- Whether Syften's archive is representative of Reddit. Every count here
  measures what one commercial listening tool surfaced.
- Whether a clipped panel actually produces different answers. That is a
  response-level question and would need collection this probe never ran.
