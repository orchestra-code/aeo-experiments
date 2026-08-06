# 006 — feasibility probe: can a public Q&A venue supply a neutral sub-intent panel?

**Status:** protocol frozen 2026-08-06, before any query was run.
**This is not a study.** It is the count-only gate that decides whether a
study is possible, per `docs/workflow.md` §2. No response data is
collected; nothing is published from it.

## The question this gate answers

005 established that a synthetic panel stratified to a human panel's
sub-intent profile reproduces the consideration set but not the per-brand
frequencies — and that the recipe's stated cost is a **human panel to
stratify from**. That panel came from SparkToro's survey. For the method to
generalize, the sub-intent targets have to come from somewhere neutral:
not a survey we cannot commission per category, and not the client (whose
declared use cases are their home field, the bias 003 measured).

Public Q&A venues are the candidate. A researcher's claim that Reddit,
Quora and AlsoAsked are more representative of human intent than synthetic
prompts is, as far as we know, untested. Before designing that test we need
to know whether enough qualifying material exists.

**Access is solved.** Syften's archive API returns Reddit post bodies in
full (`/api/0.1/archive/search`), which sidesteps the 403 wall that makes
Reddit unreachable for us directly. Smoke test 2026-08-06: HTTP 200, full
text, and coverage extends well beyond tech subreddits.

## Kill criterion — frozen before looking

Estimated qualifying posts = (tier `total`) × (qualifying rate measured on
a 100-post sample).

| Estimate | Decision |
|---|---|
| **≥ 50** | 006 is viable. Proceed to a pre-registered design. |
| **20–49** | Viable only with a panel smaller than 005's `mat` (55). Report the reduced power honestly and decide. |
| **< 20** | **Stop.** No follow-up study is designed or announced. |

Per Jim (2026-08-06): if this fails, we hold off mentioning any further
study and pick up a fresh line later. The 005 article deliberately
pre-announces nothing, so nothing is owed publicly either way.

## Sampling frame — frozen

- **Source:** Syften archive, Reddit backend only. Other platforms are out
  of scope for this probe.
- **Window:** posts from 2026-01-01 onward. Recency matters: older posts
  name discontinued products, which would confound any panel built from
  them.
- **Language:** `lang == "en"`.
- **No subreddit allow-list.** Restricting to hand-picked subreddits is a
  researcher degree of freedom and would bias the frame toward wherever we
  expect to find good material. The query is category-based; whatever
  subreddits it surfaces are the frame.

### Three specificity tiers, queried in this order

| Tier | Intent | Comparable to |
|---|---|---|
| **A** | Headphone purchase advice carrying a travel, flight, or gift frame | Directly comparable to the 002/003/005 human panel |
| **B** | Headphone purchase or recommendation advice, any frame | Same category, broader intent |
| **C** | Any headphone discussion | Upper bound on available material |

Tier A is the one that matters. A panel built from Tier B or C is still
publishable but is **no longer a like-for-like comparison** against the
existing human panel, and the write-up must say so.

## Mechanical inclusion criteria — frozen

Applied by code, never by hand. A post qualifies when **all** hold:

1. `item.type == "post"` (not a comment)
2. `item.lang == "en"`
3. Body length between 40 and 1200 characters — a question, not a
   one-line title and not an essay
4. Contains a question mark, or matches the frozen advice-seeking phrase
   list (`looking for`, `recommend`, `suggestions`, `which should i`,
   `help me choose`, `any advice`)
5. Matches the frozen product-recommendation intent pattern
6. Body is not `[deleted]`, `[removed]`, or empty
7. `item.analysis.nsfw == false`
8. Survives dedup on a normalized-text hash

Criteria 3–5 are the ones that could be tuned to hit the threshold, so they
are fixed here, before the first count, and any change is logged as a
deviation.

## Quota discipline

The PRO archive allowance is **1,000 fetched items per month** (the
documentation's "unlimited" is not what the API reports), resetting
2026-09-01. `total` is returned without fetching the matching items, so
counts are nearly free.

| Step | Items |
|---|---|
| Smoke test (already spent) | 3 |
| Three tier counts at `limit: 1` | 3 |
| Qualifying-rate sample, 100 posts from the narrowest viable tier | 100 |
| **Probe total** | **~106 of 1,000** |

That leaves roughly 890 for an actual panel build, which is comfortable
against a 55-prompt target even at a low qualifying rate.

## Publication decision — recorded, resolved at release, not now

**Jim's call (2026-08-06): include the source posts.** Reddit content is
public and is not customer data, and a study arguing about representativeness
is much weaker if its panel cannot be inspected.

Recorded structure for whenever a release happens:

- **Ships:** permalink, subreddit, post date, and the **exact prompt text
  submitted** — which, after the design's mechanical brand-redaction, is our
  derivative rather than a verbatim Reddit corpus.
- **Never ships:** usernames, full original thread bodies, comment text.
- **Open before release, not before this probe:** a read of Reddit's User
  Agreement and Syften's terms on redistributing API-obtained content, and
  a `docs/data-policy.md` amendment adding a third-party-public-content
  exemption alongside the synthetic-study-prompts one. The existing policy
  protects customers and is silent on third-party public content.

None of this gates the probe, which publishes nothing.

## Deviations from this protocol

### D1 — tier queries rewritten for the archive's actual syntax (2026-08-06)

The three tier queries as frozen used parenthesised `OR` groups. The
archive uses **Community Monitoring syntax**, where a space is an implicit
AND and **parentheses are matched as literal characters rather than
treated as grouping**. The frozen queries therefore silently under-matched
rather than erroring:

| Query | Result |
|---|---|
| `(headphones OR headphone OR earbuds) site:reddit.com` | 991 |
| `headphones site:reddit.com` | 10,000+ |
| Frozen Tier A, fully parenthesised | **0** |

A Tier A count of zero would have tripped the kill criterion and ended the
line of work on a syntax bug. The tiers were rewritten as pure
conjunctions, with the travel/gift/flight frames split into separate
queries because `OR` precedence without parentheses is unreliable.

**Unchanged:** inclusion criteria 1–8, the kill criterion, the date window,
the language restriction, the no-subreddit-allow-list rule, and the quota
budget. Only retrieval syntax moved. The criteria that could be tuned to
manufacture a pass are exactly the ones left alone.

### D2 — rate limiting is waited out, never swallowed (2026-08-06)

The archive rate-limits aggressively (observed: "try again in 2m13s" after
roughly a dozen rapid calls) and returns the error as a body payload, not
only as an HTTP status. An early probe batch returned what looked like
null results that were in fact 429s. The harness now parses the retry
delay, waits it out, paces requests 30s apart, and **raises on any response
without a `total` field** rather than defaulting to zero. A rate-limited
response must never be readable as "no matching material".

## What a passing result unlocks

The design sketched in conversation, not yet specified: a 2×2 on
**intent source × prompt format**, so that "is it the intent or the
register?" is separable — a Reddit post is a different speech act from a
prompt, and conflating the two is the obvious way to get a wrong answer.

| | Native format | Synthetic format |
|---|---|---|
| **Survey intent** | 005 `hum` | 005 `mat` (anchor) |
| **Reddit intent** | `red` | `mat3`, stratified to Reddit's mix |

Deliberately deferred until the counts come back.
