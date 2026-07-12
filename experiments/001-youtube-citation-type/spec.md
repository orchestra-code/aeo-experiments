# Who cites YouTube *moments*? Timestamped citations across AI surfaces — study spec

**Status:** draft — awaiting video-metadata backfill completion + freeze sign-off
**Frozen commit:** _(record BEFORE running sql/extract.sql)_
**Experiment slug:** `001-youtube-citation-type`
**Supersedes:** `archive/spec-v1.md` and the v2 draft (see §A below — the
original inline-vs-evaluated design was killed by pre-freeze counts, exactly
as the audit step is designed to do)

> Freeze rule: §4 and §5 are fixed before anyone looks at the joined data.
> Count-only data-quality checks (`sql/counts.sql`) are allowed pre-freeze;
> joint distributions are not. Anything added later is labelled exploratory.

---

## A. Pre-freeze findings that reshaped this study (2026-07-12, count-only)

Class balance by platform × citationType for YouTube video citations:

| platform | CITED_INLINE | EVALUATED_SOURCE | SEARCH_RESULT | with `t=` timestamp |
|---|---|---|---|---|
| google_ai_overview | 5,405 | — (structural) | — | **2,369 (43.8%)** |
| gemini | 282 | 28 | — | 0 |
| perplexity | 281 | — (structural) | — | 0 |
| openai | 9 | 5 | 50 | 0 |
| claude | 0 | 8 | — | 0 |

1. **The planned inline-vs-evaluated study is not viable for YouTube**: the
   rarer class across openai/gemini/claude is ~41 units — no power for
   detection, hopeless for equivalence. (Why so few: assistants rarely list
   YouTube as an evaluated-but-uncited source; whether that reflects model
   behavior or source-list plumbing is itself platform-dependent and
   documented in §A.1 of the article.)
2. **Timestamped YouTube citations exist on exactly one surface**: Google AI
   Overviews (43.8% of its YouTube citations). Zero on Gemini, Perplexity,
   ChatGPT, and Claude. This answers the platform-level stretch question
   outright and sets up a well-powered primary study: within AIO, what
   predicts a *moment* citation vs a plain video citation? (2,369 vs 3,036 —
   nearly balanced.)
3. Coverage: 99.7% of YouTube citation rows have a channel publisher with
   `audienceSize`; 97.5% have engagement snapshots. Video metadata
   (duration/captions/category/views) covers only ~40% of video pages —
   **the video-metadata backfill must complete before extraction.**

## 0. One-paragraph summary

Google AI Overviews is the only major AI answer surface that cites YouTube
*moments* — deep links with a `t=` timestamp — and it does so for roughly
44% of the YouTube videos it cites (counts above; exact modelling sample
fixed at extraction). We test which video attributes predict receiving a
moment citation rather than a plain video citation: creator-provided
chapters, caption availability, duration, category, and — in null form —
channel size and video popularity. Mechanistic prior: AIO moment links come
from Google's "key moments" SERP feature, which is built from creator
chapters and video transcripts; so *structure* (chapters, captions,
duration) should predict moment citation, while *popularity* (subscribers,
views) should not once structure is controlled. Cross-checking cited
timestamps against description chapter markers separates chapter-sourced
moments from transcript-derived ones — evidence about whether Google's
pipeline reads the transcript where other assistants demonstrably do not.

## 1. The claim we can and cannot make

**What this design measures:** among YouTube videos *already cited* by AI
Overviews, the association between video attributes and the *form* of the
citation (moment vs plain).

**What it does NOT measure:** (a) whether an attribute gets a video cited at
all (that's conditioned away); (b) anything causal about Google's ranking;
(c) other platforms' transcript capabilities beyond the observed absence of
timestamps.

**Defensible claims:**
- "Among the AI answer surfaces we track, only Google AI Overviews cites
  YouTube moments; N citations evaluated in this study."
- "Conditional on being cited by AIO, videos with X are more/no more likely
  to be moment-cited" per the TOST verdicts.
- If non-chapter timestamps are common: "moment citations are not merely
  copied chapter markers — consistent with transcript-derived key moments."

**Indefensible claims:** "Chapters get you cited" (we don't measure
citation); "Gemini/ChatGPT can't read transcripts" (absence of timestamps is
absence of *this marker*, not proof of incapability).

### Mechanistic prior

Google documents key moments as coming from creator-provided chapters and
from automatic detection (transcript/visual analysis). AIO inherits SERP
video features. Therefore: `has_chapters` and `video_has_captions` should
raise moment-citation odds, `duration` should matter (very short videos have
no distinct moments), and channel/video popularity should be null once
structure is controlled — the moment-picker reads content structure, not
subscriber counts. A popularity effect surviving structure controls would be
the surprising, thesis-revising outcome.

## 2. Data-quality audits — run BEFORE the model

- **Audit A — metadata completeness.** Extraction waits until the
  video-metadata backfill covers ≥95% of AIO-cited video pages (currently
  ~40%). Post-extract, report coverage; if <95%, missingness analysis is
  mandatory (metadata presence may correlate with video age/popularity).
- **Audit B — outcome integrity.** `t=` in `DiscoveryCitation.url` for AIO
  rows only (`#t=` fragments too). Verify timestamps parse and, where
  duration is known, that `timestamp ≤ duration` (violations = parse bugs or
  hallucinated deep links — report either way; count-only sanity allowed
  pre-freeze).
- **Audit C — independence.** Same video cited across many executions; `t=`
  variants are distinct CitedPages. Unit = `(execution_id, video_id)`;
  two-way clustered SEs (execution, video); report repeat distribution.
- **Audit D — snapshot timing.** Engagement/audience metrics are
  enrichment-time snapshots, potentially weeks after the citation. Note as a
  limitation; metrics are slow-moving relative to effect sizes of interest.

## 3. Data schema

One row per `(execution_id, video_id)` among **AIO CITED_INLINE** rows.
Collapse rule (pre-registered): `moment_cited = 1` if any variant URL for
that video in that execution carries a parseable timestamp; video metadata
from the variant with a non-null embedding, else non-null `videoViewCount`.

| Field | Type | Source | Publishable? | Notes |
|---|---|---|---|---|
| `execution_id` | str | DiscoveryCitation | pseudonymized | cluster key 1 |
| `video_id` | str | parsed from URL | yes | cluster key 2 |
| `moment_cited` | 0/1 | `t=`/`#t=` in citation URL | yes | **outcome** |
| `timestamp_seconds` | int? | parsed | yes | descriptive + Audit B |
| `has_chapters`, `chapter_count` | bool/int | description regex (in-SQL) | yes | H1 |
| `video_has_captions` | bool | CitedPage | yes | H2 |
| `duration_seconds` | int | CitedPage | yes | H3 (positive control) |
| `audience_size` | int | channel Publisher via dc.publisherId | yes | H5 (null-form) |
| `video_view_count` | int | CitedPage | yes | H6 (null-form) |
| `reactions_count`, `comments_count` | int | DiscoveryCitation | yes | engagement control |
| `video_category` | cat | CitedPage | yes | H7 exploratory |
| `similarity` | float | pgvector cosine (prompt × title+description) | yes (3dp) | control |
| `published_at` | date | CitedPage | month only | `log_age`, placebo dow |
| `n_sources_evaluated` | int | dqe.totalCitations | yes | control |
| `desc_word_count`, `desc_link_count` | int | in-SQL | yes | controls |
| `chapter_times` | list | in-SQL | derived-only | H8 cross-check; not released |
| `citation_type`, `platform` | cat | raw | yes | cross-platform descriptives |

Never extracted: prompt text, fan-out text, answer text, description text
(scalars derived in-query).

### Derived variables

`log_subs`, `log_views`, `log_duration`, `log_age`,
`engagement_rate = log1p(100·(reactions+comments)/(views+1))`; continuous
predictors z-scored on the modelling frame. Same rationale as v1: sizes are
heavy-tailed; "10×" is the meaningful unit.

## 4. Pre-registered hypotheses

Structure (directional — the mechanism can see these):

- **H1:** `has_chapters` increases moment-citation odds.
- **H2:** `video_has_captions` increases moment-citation odds.
- **H3 (doubles as positive control):** `log_duration` increases
  moment-citation odds. **If H3 shows nothing, stop** — a moment-picker
  that ignores duration means our outcome or predictors are broken.

Popularity (null-form, TOST):

- **H5:** `log_subs` has no effect once structure is controlled.
- **H6:** `log_views` — same.

Controls & checks:

- **H4 (placebo):** publication day-of-week has no effect.
- **H7 (exploratory):** category differences — reported with intervals, no
  confirmatory claims.
- **H8 (mechanism check, descriptive):** share of cited timestamps matching
  a description chapter marker (±5 s). High → chapter-sourced; substantial
  non-matching share → transcript/visual-derived key moments.

## 5. Model and decision rule

Pooled logit, SEs clustered two-way by execution and video (CGM; fallback =
max of one-way SEs):

```
moment_cited ~ similarity + <focal> + engagement_rate
               + log_age + desc controls + n_sources_evaluated
```

`log_duration` joins the controls for every focal except H3 itself.
**§5a:** `log_subs` and `log_views` never share a model (v1 simulation:
r≈0.9 doubles both SEs). One focal per model.

**SESOI:** OR 1.10 per SD (binary predictors: per level).
**Decision rule:** toolkit `Verdict` — NULL / NEGLIGIBLE / REAL /
INCONCLUSIVE; no null claims without TOST.
**Power:** rarer class ≈ 2.4k from pre-freeze counts → supports ~150
parameters at 15 events each; comfortable. Confirm achieved CI widths.

## 6. Known traps

- **Conditioning on citation.** The frame is videos AIO chose to cite;
  attributes that drive *being cited* are partially conditioned away.
  Similarity stays as a control; claims are about the moment/plain contrast
  only.
- **Metadata missingness is not random** (Audit A): older/obscure videos are
  likelier to lack enrichment. Fit with and without imputation-by-exclusion;
  report both.
- **Chapters ⊂ descriptions we fetched.** `has_chapters` is derived from the
  fetched description; unfetched pages (≈3%) drop out — report.
- **Effective sample = rarer class**; respect events-per-parameter with
  category levels.

## 7. Robustness checks

1. H3 positive control first; fail → stop.
2. H4 placebo must be null.
3. Nonlinearity: duration deciles; subscriber deciles (money chart for the
   null claim).
4. Collinearity report (subs/views; chapters/duration).
5. Dedup refit: one row per video.
6. Metadata-missingness refits (Audit A).
7. Audit-B exclusion: drop `timestamp > duration` rows; conclusions must hold.
8. Time-split: first half vs second half of citation dates (AIO feature
   changes mid-window would show here).

## 8. Descriptive companions (no confirmatory claims)

- The platform table from §A — the "only AIO cites moments" headline.
- Timestamp *position*: distribution of `t / duration` (how deep into videos
  do AI answers point?) — likely the most shareable chart after the
  headline.
- H8 chapter-match share, split by `has_chapters`.
- Inline-vs-evaluated infeasibility note (§A) — one honest paragraph:
  evaluated-but-uncited YouTube is rare on every non-Google surface we
  track.

## 9. Deliverables and sequence

1. ✅ Pre-freeze counts (§A)
2. **Complete the video-metadata backfill** (main repo Inngest job) → re-run
   coverage count until ≥95%
3. Freeze this spec (commit, record hash above)
4. `sql/extract.sql` → `data/raw/extract.csv`
5. `pipeline/01…05` (H3 gate; robustness; figures; release)
6. Article + dataset + companion blog post

## 10. Notes for the write-up

- Lead: the platform table — one surface cites moments, four don't.
- Then the mechanism: what predicts *which* videos get moment-cited —
  chapters/captions/duration results are directly actionable for creators
  and PR teams ("structure your videos so Google can quote them").
- The H8 cross-check is the transcript-access evidence; phrase per §1.
- Popularity nulls get the TOST treatment with the achieved bound published.
- Sample sizes as "N citations evaluated (in this study)".
