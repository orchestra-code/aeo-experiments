# 006 feasibility probe — results

Count-only, per the frozen protocol in `feasibility.md`. No post text
appears here; raw payloads stay in gitignored `data/raw/`.

**Outcome: the intent-matched tier FAILS the kill criterion. 006 is not
viable as designed and no follow-up study is being designed or announced.**

## Tier counts

| Tier | Matching items | Query |
|---|---|---|
| A1_travel | 130 | `headphones travel recommendation site:reddit.com` |
| A2_gift | 37 | `headphones gift recommendation site:reddit.com` |
| A3_flight | 37 | `headphones flight recommendation site:reddit.com` |
| A4_travel_earbuds | 58 | `earbuds travel recommendation site:reddit.com` |
| B_category_advice | 3,690 | `headphones recommendation site:reddit.com` |
| C_category_any | 10,000+ | `headphones site:reddit.com` |

Counts overlap and are not summed. `type:post` is honoured by the archive
(Tier B: 3,690 → **1,727** posts), so roughly half of all matches are
comments; a real panel build would apply it and halve the quota cost.

## Qualifying rates — measured, not extrapolated

| Tier | Sampled | Qualifying | Rate | Estimated total |
|---|---|---|---|---|
| B_category_advice | 100 of 3,690 | 9 | 9.0% | **332** |
| **A1_travel** | **100 of 130** | **5** | **5.0%** | **6** |

Tier A was measured directly rather than inheriting Tier B's rate, because
Tier A is the only tier that preserves comparability with the human panel.
It qualifies at a *lower* rate than the general tier, not a higher one.

### Why Tier A posts were excluded

| Reason | Count |
|---|---|
| length_out_of_band | 56 |
| not_a_post | 23 |
| no_recommendation_intent | 13 |
| not_english | 2 |
| no_question_marker | 1 |

## Decision against the frozen kill criterion

| Tier | Estimate | Rule | Decision |
|---|---|---|---|
| A1_travel (intent-matched) | **6** | < 20 → stop | **STOP** |
| B_category_advice | 332 | ≥ 50 → viable | Viable, but see below |

**Tier B's pass does not rescue the study.** The design depends on a
contemporaneous human baseline at the *same* intent, and the only one we
have is SparkToro's 143 travel-gift phrasings. A Reddit panel drawn from
general headphone advice compared against a travel-gift human panel
confounds **source** with **intent** — precisely the confound the 2×2 was
built to separate. Running it would produce a number nobody could
interpret.

The blocker is a base rate, not query engineering: **people do not post
travel-gift headphone questions to Reddit in volume.** Roughly six
qualifying posts exist in seven months.

## What we are deliberately not doing

**Length was the dominant exclusion (56 of 100 Tier A posts), and we are
not relaxing the band.** Criteria 3–5 were frozen in `feasibility.md`
specifically because they are the knobs that could manufacture a pass
after seeing the counts. Widening the band now, having watched it be the
binding constraint, is the exact move the freeze exists to prevent.

If a future study wants a different band, it needs a fresh protocol with
the rationale stated *before* the counts are run.

The same applies to the 2026-01-01 window. Extending it backwards would
raise Tier A's count, and it was frozen for a stated reason (older posts
name discontinued products). Moving it now would be reverse-engineering
the frame to fit the answer.

## Sampling note for any future design

The archive returns results **newest-first, not randomly**: the 100-item
Tier B sample spanned only 2026-07-31 → 2026-08-06. Density is stable
(≈14 items/day sampled vs ≈17/day implied by the full-window total, which
supports the extrapolation), but a real panel would need date-sliced
sampling rather than the first N.

## Cost

215 of 1,000 monthly archive items, resetting 2026-09-01. The gate
returned a decisive answer for roughly a fifth of one month's allowance
and no study spend.

## What this leaves open

The researcher's claim that public Q&A venues are more representative of
human intent than synthetic prompts remains **untested by us**. This probe
does not refute it. What it establishes is narrower and more practical:
at a *specific* commercial sub-intent, Reddit does not carry enough
material to build a panel against, which makes the claim hard to test with
the human baseline we own.

A future line would need either a broader intent with a matching human
baseline we do not currently have, or a category where public Q&A volume
at a specific intent is much higher.
