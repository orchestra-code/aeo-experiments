# 006 feasibility probe — results (corrected 2026-08-06)

Count-only, per the protocol in `feasibility.md`. No post text appears
here; raw payloads stay in gitignored `data/raw/`.

> **This file supersedes an earlier version that concluded NOT VIABLE.**
> That conclusion was an artifact of the frozen retrieval query, not a
> property of the material. The correction is documented below in full
> rather than quietly replaced.

**Outcome: VIABLE at the intent-matched tier** — an estimated **113**
qualifying posts, against a floor of 50. Treat it as viable-but-not-
comfortable: the sample numerator is small and the lower confidence bound
sits in the reduced-panel band.

## The error, and the correction

The frozen Tier A query required the literal word *"recommendation"*.
Recommendation **intent** is already enforced by frozen criterion 5
against the post body, so the query word was a redundant second filter
applied at retrieval — and it removed most of the population before the
criteria ever ran.

| Query | Matching items |
|---|---|
| `headphones travel site:reddit.com` | **9,676** |
| `headphones travel recommendation site:reddit.com` | 130 |
| `headphones gift site:reddit.com` | **5,110** |
| `headphones gift recommendation site:reddit.com` | 37 |

The same artifact produced an apparent B2B/health-tech scarcity that does
not exist:

| Category | Raw | With "recommendation" |
|---|---|---|
| CRM | 10,000+ | (query failed) |
| Helpdesk | 10,000+ | 23 |
| EHR | 10,000+ | 85 |
| `salesforce hubspot` (comparison form) | 6,774 | — |

**B2B is not thinner than consumer.** It is phrased differently: B2B
buyers compare named products rather than asking for a "recommendation".

## Measurements

| Tier | Pool | Sampled | Qualifying | Rate | Estimate |
|---|---|---|---|---|---|
| A1_travel (word-filtered) | 130 | 100 | 5 | 5.0% | 6 |
| A0_travel_broad (incl. comments) | 9,676 | 100 | 0 | 0.0% | 0 |
| **A0b_travel_posts** | **3,773** | 100 | 3 | 3.0% | **113** |
| B_category_advice | 3,690 | 100 | 9 | 9.0% | 332 |

`A0_travel_broad` returned zero because 60% of its items were comments,
not posts. Excluding comments at retrieval (`type:post`) is what makes the
measurement informative — the archive honours the filter, and it also
halves quota waste.

### Why A0b posts were excluded

| Reason | Count |
|---|---|
| length_out_of_band | 62 |
| no_recommendation_intent | 23 |
| no_question_marker | 9 |
| not_english | 3 |

## Decision

| Tier | Estimate | Rule | Decision |
|---|---|---|---|
| **A0b_travel_posts** | **113** | ≥ 50 → viable | **VIABLE** |

**Honest confidence:** 3 qualifying in 100 is a small numerator. The
binomial interval on 3% spans roughly 0.6–8.5%, so the plausible range is
about **23 to 320** qualifying posts. The point estimate clears the
threshold; the lower bound lands in the 20–49 "reduced panel" band. A
design built on this should either sample more before committing to a
panel size, or plan for a panel smaller than 005's 55.

**Length remains the dominant exclusion (62%)** and the band stays frozen
where it was. It was fixed in advance precisely because it is the knob
that could manufacture a pass, and that has not changed just because the
result moved in the other direction.

## Sampling caveat, unchanged

The archive returns **newest-first, not randomly**. Every 100-item sample
here spans roughly one week. Density looks stable across the window, but a
real panel build needs date-sliced sampling rather than the first N.

## Independent cross-check available

DataForSEO's SERP endpoint surfaces Reddit threads directly
(`r/HeadphoneAdvice`, `r/TravelHacks`, `r/onebag`, `r/oratory1990` all
appeared for `best headphones for travel`), so Google's index gives an
independent read on Syften's Reddit coverage. Worth running before any
claim about Reddit volume, since every count here measures **what one
commercial listening tool surfaced**, not what exists.

## Cost

427 of 1,000 monthly archive items, resetting 2026-09-01.

## What this changes about the proposed write-up

A post arguing "niche and B2B categories cannot source enough public
questions" is **not supported by this data**. Raw B2B volume hits the
API's reporting cap. What the data does support is a sharper and more
defensible point: **the material exists nearly everywhere, and whether you
can find it depends entirely on how you query for it** — a 74× swing from
one word. That is itself a representativeness problem, and it lands on
anyone following the "just source from real human conversations" advice
without specifying how.

Two distinct failure modes are worth naming separately in any write-up:

- **Volume failure** — the material genuinely is not there. We have not
  demonstrated this anywhere yet.
- **Shape failure** — the material exists in volume but is not
  question-shaped, not at a specific intent, or not the right register.
  This is what we actually measured: 3,773 travel-intent posts reduce to
  ~113 usable ones, with 62% failing on length alone.
