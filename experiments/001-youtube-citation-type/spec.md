# What predicts whether an AI assistant cites a YouTube video inline vs. merely evaluating it? — study spec

**Status:** draft
**Frozen commit:** _(record BEFORE running sql/extract.sql)_
**Experiment slug:** `001-youtube-citation-type`
**Supersedes:** `archive/spec-v1.md` (written before video metadata was backfilled in-DB; its design rationale — TOST, collider control, §5a collinearity simulation — carries over)

> Freeze rule: §4 and §5 are fixed before anyone looks at the joined data.
> Count-only data-quality checks (`sql/counts.sql`) are allowed pre-freeze;
> joint distributions are not. Anything added later is labelled exploratory.

---

## 0. One-paragraph summary

For YouTube videos that an AI assistant has already retrieved while answering
a prompt, we test which video-level factors predict being **cited inline** in
the answer (`CITED_INLINE`) versus being **read but not referenced**
(`EVALUATED_SOURCE`): channel subscribers, video views, engagement, duration,
captions, category, and description structure (chapter markers, links,
length). Our mechanistic prior is that *none of the popularity metrics*
matter — at citation time the model sees the video's title + description
text, not its subscriber count — while semantic fit does all the work. The
study is powered to make that null claim affirmatively via TOST. A separate
descriptive section examines `&t=` timestamped citations as evidence about
transcript access, with a built-in comparison class.

## 1. The claim we can and cannot make

**What this design measures:** the citation step, *conditional on retrieval*.
Every row is a video the assistant already surfaced. The question is: given
the model retrieved this video, do its popularity/structure attributes change
the odds it ends up cited in the answer?

**What this design does NOT measure:** the retrieval step. If big channels
rank better in the underlying search index and get retrieved more often, this
study is blind to that.

**Defensible claim:** "Audience size may help you get *found*. Conditional on
an AI assistant retrieving a video, subscriber count has no detectable effect
on whether it is cited in the answer" (if the TOST comes back NULL).

**Indefensible claim:** "Subscriber count doesn't matter for AI citation."
We measure the second half of the funnel only.

### Mechanistic prior

At citation time the model is working from the video's **title + description
text** (that is what Spyglasses embeds and what the assistant's fetch
returns; transcripts are not part of the retrieved content). Subscriber
count, view count, and like counts are generally absent from that context.
So the *expected* result on H1–H3 is a null — the information is physically
absent at the decision point. Description *structure* (chapters, links,
length) IS visible to the model, so H6–H8 are genuinely open questions, and
a positive there would be actionable: description quality is a lever
creators control.

## 2. Data-quality audits — run BEFORE the model

- **Audit A — negative-class contamination.** `EVALUATED_SOURCE` rows whose
  CitedPage has `fetchStatus != 'fetched'` have no embedding → no similarity
  → they drop out of the primary model. This *silently implements* the
  failed-fetch exclusion; we make it explicit: report the count and share of
  negatives excluded this way, and run robustness #7 (the descriptive decile
  figure with and without them).
- **Audit B — what the outcome label means.** Quoting
  `packages/core/src/utils/citation-type.ts` (main repo): openai/gemini
  sources are checked against the answer markdown (SERP-appended extras are
  tagged `SEARCH_RESULT` at parse time); claude distinguishes cited URLs from
  everything web_search saw via the raw response; **google_ai_overview and
  perplexity report displayed citations only and NEVER produce
  `EVALUATED_SOURCE`**. Therefore the primary model is restricted to
  **openai, gemini, claude** — the only platforms where the contrast exists.
- **Audit C — independence.** The same video can appear across many
  executions, and (because URL normalization keeps `t=`) as several CitedPage
  rows. Unit of analysis is `(execution_id, video_id)` with `video_id` parsed
  from the URL; SEs cluster two-way by execution and video. Report distinct
  video counts and the repeat distribution.
- **Audit D — hostname-fallback misclassification.** For openai/gemini,
  inline detection falls back to hostname matching: in an execution whose
  answer links any youtube.com URL, *other* evaluated YouTube sources can be
  misclassified `CITED_INLINE`. Claude is clean (exact cited-URL sets).
  Count executions with >1 YouTube source per platform; robustness #9
  excludes them.

## 3. Data schema

One row per `(execution_id, video_id)` after collapsing `t=`-variant
CitedPages. Collapse rule (pre-registered): outcome = 1 if **any** variant is
`CITED_INLINE`; metadata taken from the variant with a non-null embedding,
else non-null `videoViewCount`.

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| `execution_id` | str | DiscoveryCitation | pseudonymized | cluster key 1 |
| `video_id` | str | parsed from URL | yes | cluster key 2; public fact |
| `cited` | 0/1 | citationType | yes | **outcome**; SEARCH_RESULT excluded |
| `platform` | cat | DiscoveryQueryExecution | yes | primary model: openai/gemini/claude |
| `similarity` | float | pgvector cosine, prompt embedding × page embedding | yes (rounded 3dp) | mandatory control, H4 |
| `audience_size` | int | Publisher.audienceSize via dc.publisherId (channel publisher) | yes | H1; null for handle-less channels |
| `video_view_count` | int | CitedPage | yes | H3 |
| `reactions_count`, `comments_count` | int | DiscoveryCitation (YouTube Data API snapshot) | yes | H2 engagement |
| `duration_seconds` | int | CitedPage | yes | control |
| `published_at` | date | CitedPage | month only | → `log_age`, placebo dow |
| `video_has_captions` | bool | CitedPage | yes | H6 |
| `video_category` | cat | CitedPage | yes | H7 (exploratory slices) |
| `chapter_count`, `has_chapters` | int/bool | regex on description | yes | H8 |
| `desc_link_count`, `desc_word_count` | int | regex/wordCount | yes | description features |
| `n_sources_evaluated` | int | dqe.totalCitations | yes | competition control |
| `n_youtube_in_execution` | int | window count | yes | Audit D |
| `fetch_ok` | 0/1 | fetchStatus == 'fetched' | yes | Audit A |
| `timestamp_seconds` | int? | `t=`/`#t=` in citation URL | yes | stretch |
| `chapter_times` | list | regex on description | derived-only | stretch cross-check; not released |
| `citation_type` | cat | raw, incl. SEARCH_RESULT | yes | stretch comparison class |

Never extracted at all: prompt text, fan-out text, answer text. Description
text stays in the database — only derived scalars leave it (the extraction
SQL computes them in-query).

### Derived variables

- `log_subs = log10(audience_size + 1)`, `log_views = log10(video_view_count + 1)`,
  `log_duration`, `log_age = log10(days(response_at − published_at) + 1)`
- `engagement_rate = log1p(100 × (reactions + comments) / (views + 1))` — a
  ratio, decorrelated from raw size, stays in every model as a control
- All continuous predictors z-scored so coefficients are per-SD and the SESOI
  is comparable across variables.

**Why logs:** subscriber/view counts are heavy-tailed over ~6 orders of
magnitude; raw counts would let a handful of mega-channels dictate the fit,
and "10× more subscribers" is the psychologically meaningful unit.

## 4. Pre-registered hypotheses

Primary (each fitted in its own model — see §5a):

- **H1:** `log_subs` has no effect on inline citation (null-form).
- **H2:** `engagement_rate` — same.
- **H3:** `log_views` — same.

Description-structure (visible to the model, so genuinely open):

- **H6:** `video_has_captions` — no directional prediction; TOST verdict reported.
- **H7:** `video_category` — global Wald test vs. "Other"; exploratory slices.
- **H8:** `has_chapters` — no directional prediction; TOST verdict reported.

Controls:

- **H4 (positive control):** `similarity` predicts citation, positive and
  p < 0.05. **If H4 fails the study stops** — the data cannot detect anything
  and a null on H1–H3 would be meaningless.
- **H5 (placebo):** publication day-of-week has no effect. If it "does", the
  SEs are too small (under-clustered); do not report results as-is.

## 5. Model and decision rule

Pooled logistic regression, **SEs clustered two-way by execution and video**
(CGM; pre-registered fallback if the combined matrix is degenerate: the
element-wise max of the two one-way SEs):

```
cited ~ similarity + <focal> + engagement_rate
        + log_duration + log_age + n_sources_evaluated + C(platform)
```

Sample restriction: `platform ∈ {openai, gemini, claude}`, `citation_type ∈
{CITED_INLINE, EVALUATED_SOURCE}`, non-null `similarity`.

**§5a — one size-variable per model.** `log_subs` and `log_views` measure the
same latent factor (v1 simulation: r ≈ 0.9, joint fit doubles both SEs and
makes the equivalence test unable to conclude anything, even when the truth
is exactly zero). One focal size variable per model; `engagement_rate` is a
ratio (VIF ≈ 1) and stays. Report `collinearity_report` in the write-up.

**SESOI:** odds ratio **1.10 per SD** of the (standardized) predictor — the
smallest effect that would plausibly change a content strategy.

**Decision rule (TOST, 90% CI):** as in the toolkit's `Verdict`:
CI inside [0.909, 1.10] → NULL; excludes 1.0 beyond band → REAL; excludes 1.0
inside band → NEGLIGIBLE; wide + includes 1.0 → **INCONCLUSIVE — no null
claim.**

**Power:** verified on the synthetic generator (collider structure included):
`true_effect=0` → NULL, `true_effect=0.25` → REAL (`tests/test_stats.py`).
Confirm achieved CI widths from the fitted models rather than trusting the
simulation; real class balance may differ from v1's assumption.

## 6. Known traps

- **Collider (admissions paradox).** Retrieval is caused by both semantic fit
  and channel prominence; conditioning on retrieval makes them spuriously
  negatively correlated in-sample, so *without* the similarity control, big
  channels would appear to get cited less. The naive model is fitted once,
  labelled "the number not to publish", to demonstrate the trap.
- **Effective sample = the rarer class.** Whichever of cited/not-cited is
  smaller is the information budget; report it and respect ~15+ events per
  parameter (category levels count).
- **Absence of evidence ≠ evidence of absence.** TOST or no null claim.
- **Similarity is title+description similarity.** The embedding covers the
  video's title + description (not the transcript). If a video is retrieved
  on transcript content invisible to our similarity measure, the control is
  imperfect; noted as a limitation.

## 7. Robustness checks

1. H4 first; fail → stop.
2. H5 placebo must be null.
3. Nonlinearity: subscriber deciles (the money chart) + 5-knot spline refit.
4. Collinearity report (corr + VIF).
5. Dedup refit: one row per distinct `video_id` (first appearance).
6. Per-platform refits (openai / gemini / claude) — watch power on the
   equivalence claim; detection is fine, equivalence may be marginal.
7. Audit-A sensitivity: descriptive rates with/without `fetch_ok = 0` rows.
8. Missingness: `audience_size` is null for handle-less channels and
   `reactions/comments` can be creator-hidden — neither is random. Fit with
   and without; compare cited-rates for null vs non-null groups.
9. Audit-D sensitivity: exclude executions with >1 YouTube source
   (openai/gemini only); claude subset is the clean benchmark.

## 8. Stretch goal (descriptive, own section in the article): timestamped citations

**Question:** do `&t=`/`#t=` timestamped YouTube citations indicate the
assistant read the transcript?

**Design:** row-level (not collapsed), all five platforms, **including
`SEARCH_RESULT` rows as a comparison class** — SERP-appended results carry
whatever timestamps Google's "key moments" surface, so they estimate the
timestamp rate *without* any model choice involved.

1. Share of citations with a timestamp, by platform × citation_type.
2. Hypothesis (directional, descriptive): Google-owned surfaces
   (gemini, google_ai_overview) show timestamps; others don't.
3. Cross-check: for each timestamped citation, does the timestamp coincide
   (±5 s) with a chapter marker in the video's description? Timestamps that
   match chapters could come from the *description*; only non-chapter,
   non-SERP timestamps are even candidate evidence of transcript access.

**Pre-committed caveat:** a timestamp proves the assistant had *some*
temporal anchor — transcript access, SERP key-moments, and description
chapters are all possible sources. We will report which sources the data can
and cannot rule out, and we do not claim transcript access unless
non-chapter timestamps appear at meaningful rates outside SERP-derived rows.

## 9. Deliverables and sequence

1. `sql/counts.sql` (pre-freeze, count-only) → confirm class balance + nulls
2. Freeze this spec (commit, record hash above)
3. `sql/extract.sql` → `data/raw/extract.csv` (psql `\copy` or Supabase MCP)
4. `pipeline/01_features.py` … `05_release.py`
5. Robustness suite; article + dataset + companion blog post

## 10. Notes for the write-up

- Money chart: citation rate across subscriber deciles with Wilson intervals.
- Frame as **funnel decomposition** — "audience gets you retrieved; relevance
  gets you cited" — not as a debunking.
- Sample sizes as "N citations evaluated (in this study)".
- Publish the achieved equivalence bound.
- Description-structure results (H6–H8) are the actionable-advice section for
  the companion blog post.
