# Does audience size predict AI citation? — YouTube study spec

**Version:** 1.0
**Status:** Pre-analysis plan. Everything in §4 and §5 should be fixed *before* anyone looks at the enriched data.
**Scope:** YouTube only. LinkedIn is explicitly out of scope pending this result.

---

## 0. The one-paragraph summary

We have 5,500 YouTube sources that an AI assistant retrieved while answering prompts. 3,900 were cited inline in the response; 1,600 were read but not cited. We will enrich each with channel subscriber count and video engagement metrics, then test whether those predict citation *once the source has already been retrieved*. Our hypothesis is that they do not — that semantic fit does all the work. The study is powered to make that null claim affirmatively rather than merely fail to reject it.

---

## 1. The claim we can and cannot make

This is the most important section. Get this wrong and the blog post is indefensible.

**What this design measures:** the *citation step, conditional on retrieval.* Every row in our dataset is a video the model already pulled into context. So we are asking:

> Given that the model has already found and read this video, does the channel's subscriber count or the video's engagement make it more likely to be cited?

**What this design does NOT measure:** the *retrieval step.* If big channels rank better in the underlying search index and therefore get retrieved more often, this study is blind to that. Our dataset is conditioned on retrieval having already happened.

**Therefore the defensible claim is:**

> "Audience size may help you get *found*. It does not help you get *cited*. Conditional on an AI assistant retrieving a video, subscriber count has no detectable effect on whether it ends up in the answer."

**The indefensible claim is:** "Subscriber count doesn't matter for AI citation." Full stop. We have not measured the funnel, only its second half.

This is a feature, not a limitation. The decomposed claim is more interesting *and* more actionable than the lumped one, and it sets up an obvious follow-up study on the retrieval stage.

### The mechanistic prior

Worth stating up front because it makes the result explicable rather than merely surprising: **at citation time, the model probably cannot see the subscriber count.** It's working from a transcript or a page extract. Subscriber count is generally not in that context window.

So the *expected* result is a null — not because audience is irrelevant to the internet, but because the information is physically absent at the moment of decision. If we find a null, the story isn't "we were surprised." It's:

> "We predicted audience size couldn't matter at the citation step, because the model never sees it. The data confirms it. Which means all of the authority effect people attribute to AI citation is actually happening upstream, in retrieval — and that's a completely different lever."

If we find a *non-null*, that's the genuinely surprising outcome and it means subscriber count is proxying for something the model *can* see (production quality, transcript clarity, topical specialization). That's also a good blog post. Either way we have something.

---

## 2. Run this data-quality audit BEFORE enriching anything

A 71% citation rate among evaluated sources is high. Before we spend any effort, we need to know that the 1,600 non-citations are *real editorial decisions* and not artifacts. Two ways this study dies quietly:

**Audit A — the failed-fetch problem.** If a source is logged as "evaluated" when the model *attempted* to fetch it, then some fraction of the 1,600 non-citations are pages that returned an error, a paywall, a captcha, an age-gate, or an empty transcript. Those aren't the model declining to cite — they're the model never having read the thing. If those are in the negative class, we are partly modelling *page accessibility*, and any correlation we find with channel size is confounded (big channels have fewer dead videos).

*Action:* hand-audit a random sample of 100 of the 1,600 non-cited sources. Classify each: (a) content successfully retrieved, model chose not to cite; (b) fetch failed / empty / error / gated; (c) ambiguous. If (b) exceeds ~10%, we must either exclude them or model them separately — and we must be able to *detect* them programmatically, which means the pipeline may need a logging change before this study is viable at all.

**Audit B — what does "evaluated" actually mean in our logs?** Pin this down explicitly and write the answer here:

- [ ] Is "evaluated" a URL the search tool *returned in a result list*?
- [ ] Or a URL the model *actually fetched and read*?

These identify different steps and the interpretation in §1 changes accordingly. If it's the search result list, we are capturing "chose to open it" + "chose to cite it" together, which is closer to what we want. Document which.

**Audit C — deduplication.** Is the same video cited across multiple responses? If a single popular video appears 40 times, it will dominate the fit and violate independence. Count distinct `video_id`s. If there's heavy repetition, cluster standard errors by `video_id` as well as by `response_id`, or subsample to one row per video.

**Do not proceed to §3 until A, B, and C are answered.**

---

## 3. Data schema

One row per (response, video) pair.

| Field | Type | Source | Notes |
|---|---|---|---|
| `response_id` | str | Spyglasses | Grouping key for the random intercept |
| `video_id` | str | parsed from URL | Dedup / clustering key |
| `channel_id` | str | YouTube API `videos.list` | |
| `cited` | 0/1 | Spyglasses | **Outcome.** 1 = inline citation |
| `similarity` | float | Spyglasses | Semantic similarity to the fan-out query. **Mandatory — see §6.1** |
| `fanout_query` | str | Spyglasses | |
| `assistant` | cat | Spyglasses | ChatGPT / Gemini / Claude / AIO / Perplexity |
| `subscriber_count` | int | YouTube API `channels.list` | ⚠️ rounded to 3 sig figs by YouTube |
| `view_count` | int | YouTube API `videos.list` | |
| `like_count` | int | YouTube API `videos.list` | May be null (creator-hidden) |
| `comment_count` | int | YouTube API `videos.list` | May be null (comments disabled) |
| `published_at` | date | YouTube API `videos.list` | |
| `duration_sec` | int | YouTube API `contentDetails` | Control — long videos may chunk differently |
| `n_sources_evaluated` | int | Spyglasses | Response-level control: competition for citation slots |
| `n_youtube_evaluated` | int | Spyglasses | Also tells us how many discordant sets exist |
| `fetch_ok` | 0/1 | Spyglasses | **Add this if it doesn't exist.** See Audit A |

### Derived variables

- `log_subs = log10(subscriber_count + 1)` — the primary predictor
- `log_views = log10(view_count + 1)`
- `engagement_rate = (like_count + comment_count) / (view_count + 1)` — normalized engagement, decorrelated from raw popularity
- `log_engagement = log10(like_count + comment_count + 1)` — absolute engagement
- `age_days = response_date - published_at`
- All continuous predictors **standardized (z-scored)** so coefficients are comparable and the equivalence bounds in §5 are interpretable.

**Why logs:** subscriber counts and view counts are heavy-tailed (roughly log-normal, spanning 10² to 10⁸). Raw counts would let a handful of MrBeast-scale channels dictate the entire fit. On a log scale, "1 unit" = "10x more subscribers," which is also the right *psychological* scale — the difference between 1k and 10k subs is meaningful; the difference between 10.0M and 10.01M is not.

---

## 4. Pre-registered hypotheses

State these before looking at the data. Do not add predictors later without labelling them exploratory.

**H1 (primary, null-form):** Conditional on retrieval and controlling for semantic similarity, `log_subs` has no effect on the probability of inline citation.

**H2:** Same, for `engagement_rate`.

**H3:** Same, for `log_views`.

**H4 (positive control):** `similarity` *does* predict citation. **If H4 fails, the entire study is uninterpretable** — it means either our similarity metric is broken or our outcome variable is noise, and a null on H1 would be meaningless because we'd have no evidence the model can detect *anything*. H4 is the canary. Check it first.

**H5 (placebo control):** `published_at` day-of-week has no effect. This is a variable that *cannot* plausibly matter. If it shows an effect comparable in size to H1's, we're reading noise and our standard errors are too small — probably because we've under-clustered.

---

## 5. The model and the decision rule

### Model

Pooled logistic regression with **standard errors clustered by `response_id`**, fitted **separately for each focal predictor** (see §5a — this matters a lot):

```
# H1 (primary)
cited ~ similarity + log_subs + engagement_rate
        + log_duration + log_age + n_sources_evaluated + C(assistant)

# H3
cited ~ similarity + log_views + engagement_rate
        + log_duration + log_age + n_sources_evaluated + C(assistant)
```

**Why not conditional/fixed-effects logit:** we expect most responses to contain exactly one YouTube source. Fixed-effects conditional logit discards every stratum without within-stratum outcome variation — which would be nearly the whole dataset. Clustering the SEs handles the within-response dependence without throwing away the singletons.

**Why not a mixed model with a random intercept:** it's a defensible alternative and should agree, but with near-total singletons the random-intercept variance is barely identified and convergence gets flaky. Cluster-robust pooled logit is simpler, more robust, and gives the same fixed effects. Run the mixed model as a sensitivity check if you like; don't make it the primary.

---

### §5a. **Do not put `log_subs` and `log_views` in the same model**

This is the single biggest threat to the power of this study, and it is entirely self-inflicted. It was caught by running the analysis on simulated data before the real data existed.

Subscriber count and view count measure nearly the same latent thing — *how big is this channel*. In simulation they correlate at **r ≈ 0.90 (VIF ≈ 5.1)**. Put both in one model and each roughly **doubles the other's standard error**:

| Model | SE(log_subs) | 90% CI on OR | Verdict at SESOI 1.10 |
|---|---|---|---|
| `similarity + log_subs + log_views` | 0.082 | [0.957, 1.253] | ❌ **INCONCLUSIVE** |
| `similarity + log_subs` | **0.037** | **[0.934, 1.055]** | ✅ **NULL** |

Both rows are from data where the true effect is **exactly zero**. The first model *cannot conclude anything* — the CI is wider than the equivalence band. You would run the study, have the right answer sitting in the data, and be unable to say so.

**Rule:** fit one focal size-variable at a time. `engagement_rate` is a *ratio* (`(likes+comments)/views`), so it's already decorrelated from raw size (VIF ≈ 1.0) and can stay in every model as a control.

**Check the real correlation first.** If `corr(log_subs, log_views) < 0.7` in the actual data, a joint model is tolerable — but there's no upside, so fit separately regardless. `analysis.py` does this automatically and prints the correlation.

### Decision rule — how we're allowed to claim a null

A non-significant p-value does **not** establish absence of effect. We use **two one-sided tests (TOST)** against a pre-specified equivalence bound.

**Smallest effect size of interest (SESOI):** an odds ratio of **1.10** per standard deviation of the predictor. Rationale: a 10% shift in citation odds per SD of log-subscribers is the smallest effect that would change anyone's content strategy. Anything below that is a curiosity, not a lever.

**Decision rule for each of H1–H3:**

| Result | Conclusion |
|---|---|
| 90% CI on OR falls entirely within [0.909, 1.10] | **Practically equivalent to zero.** We can say it in public. |
| 90% CI excludes 1.0 and extends beyond the bound | **Real effect.** Report it, revise the thesis. |
| 90% CI excludes 1.0 but sits inside the bound | Statistically detectable, practically negligible. Report honestly as such. |
| 90% CI is wider than the bound and includes 1.0 | **Inconclusive.** Underpowered. Do not claim a null. |

That last row is the one people cheat on. We will not.

### Power

**Simulated, not hand-waved.** `analysis.py --synthetic` generates 5,500 rows with 3,900 cited, including the collider structure of §6.1, and runs the full pipeline. Results:

| True effect of `log_subs` | Observed OR [90% CI] | Verdict returned |
|---|---|---|
| **0.00** (exactly null) | 0.991 [0.933, 1.054] | ✅ NULL — practically equivalent to zero |
| **0.06** (real, below SESOI) | 1.016 [0.956, 1.080] | ✅ NULL — correctly judged negligible |
| **0.25** (real, above SESOI) | 1.095 [1.029, 1.164] | ✅ REAL EFFECT — correctly detected |

The test both **finds effects that are there** and **rules out effects that aren't**. It is not a rubber stamp for the hypothesis we want.

Achieved precision: **SE ≈ 0.037** on the standardized coefficient → the 90% CI bounds the odds ratio within roughly **±6–7% per SD of log-subscribers**. That fits comfortably inside the SESOI of 1.10.

**We are well powered to make the null claim** — *provided we follow §5a.* Ignore §5a and the SE more than doubles and we get nothing.

Caveats on the simulation: it assumes clean singleton responses and no fetch-failure contamination. Real clustering and real missingness will inflate the SEs somewhat. There's margin, but confirm the achieved CI from the fitted model rather than trusting this table.

---

## 6. Three things that will bite you (plain English)

These are the three ways this study produces a confident wrong answer. They're also good blog material in their own right.

### 6.1 The admissions paradox (collider bias)

**The trap:** if you regress citation on subscriber count *without* controlling for semantic similarity, you may find that **bigger channels get cited LESS.** This looks like a hot take. It is an artifact. Do not publish it.

**Why it happens.** Think about elite college admissions. A school admits students who are either academically outstanding *or* exceptional athletes. Now look only at the admitted class: you'll find test scores and athletic ability are *negatively* correlated. Not because sports make you worse at exams — but because you only needed to be strong on *one* dimension to get in. The recruited athletes got in on sports, so their scores are lower on average, and vice versa. Filtering on the *outcome* manufactured a correlation between the *causes* that doesn't exist in the general population.

**Now us.** A video gets retrieved if it's a great semantic match *or* if it's from a big channel that ranks well in search. Our dataset contains *only retrieved videos* — we're looking at the admitted class. So within our data, subscriber count and semantic similarity will be artificially negatively correlated. The big-channel videos got in "on subscribers," which means they're on average *worse* semantic matches. And since semantic match is what actually drives citation, big channels will appear to be cited less — when the real story is that they're carrying weaker content.

**The fix is one line of code:** put `similarity` in the model. Then the subscriber coefficient answers the question we actually care about — *among videos that fit the query equally well, does having more subscribers help?* — instead of secretly comparing well-matched small channels against poorly-matched big ones.

**The general lesson (blog-worthy):** whenever your dataset exists because something got *selected*, the traits that caused the selection get scrambled together. You must control for the other selection criteria or you'll measure the scrambling instead of the world.

### 6.2 Your sample size is not 5,500 — it's 1,600

**The trap:** looking at n = 5,500 and assuming you can throw twenty variables into the model.

**Why.** In a yes/no model, the thing that buys you precision isn't the total row count — it's the count of the **rarer outcome**. You have 3,900 citations and 1,600 non-citations. The 1,600 is your real budget. Intuition: if 5,499 sources were cited and one wasn't, you'd have 5,500 rows and would obviously know nothing about what makes something *not* get cited. All the information about the boundary between the two classes lives in the smaller class.

**The rule of thumb:** you want at least 10–20 events of the rarer class per variable in your model. We have 1,600 events and roughly 8 variables → **200 per variable.** That's ~10x the minimum. We are comfortable, and this is why we can afford the controls in §5 without straining.

**The related trap you already spotted:** the *matched* design (comparing cited vs. uncited videos within the same response) needs responses containing at least one of each — "discordant sets." If nearly every response has just one YouTube source, there are almost no discordant sets and that design collapses. That's why we're using a random intercept instead of conditional logit: it keeps the singleton responses in play. **Count `n_youtube_evaluated` early** — it tells you immediately which design you're in.

### 6.3 "We found nothing" is not the same as "there is nothing"

**The trap:** running the regression, getting p = 0.4 on subscriber count, and writing "subscriber count has no effect on AI citation."

**Why it's wrong.** A p-value above 0.05 means *you failed to detect an effect.* A study with twelve data points would also fail to detect an effect. Absence of evidence and evidence of absence are different claims, and only one of them is a blog post.

**The analogy.** Suppose you want to claim a box is empty. It isn't enough to say "I looked inside and didn't see anything." Someone will reasonably ask: *how good is your vision?* The credible version is: "My instrument can detect anything larger than a grain of rice, and it detects nothing." Your confidence interval **is** your instrument's sensitivity — and you have to report it, not just your p-value.

**The fix (TOST).** Decide *in advance* how small counts as zero — for us, an odds ratio inside [0.909, 1.10] (§5). Then show that your entire confidence interval fits inside that window. That converts "we didn't find anything" into the much stronger and genuinely publishable "**we would have found anything bigger than X, and there was nothing bigger than X.**"

State the bound before you see the data. Otherwise you'll pick a bound that happens to contain your result, and a hostile reader will notice.

---

## 7. Robustness checks

Run all of these. Any that flip the conclusion goes in the blog post as a limitation.

1. **Positive control (H4).** `similarity` must be significant and in the right direction. If not, **stop** — the data can't answer anything.
2. **Placebo (H5).** Day-of-week must be null. If it isn't, your SEs are too small; re-examine clustering.
3. **Nonlinearity.** Subscribers might matter only at the extremes. Refit with `log_subs` as a 5-knot spline, or bin into deciles and plot citation rate per decile. A flat line across deciles is the single most persuasive chart you can put in the blog post — more persuasive than any coefficient.
4. **Collinearity.** Handled by design in §5a — but still report `corr(log_subs, log_views)` and the VIFs in the write-up so readers can see why the models are fitted separately.
5. **Deduplication.** Refit on one row per distinct `video_id`. If the result moves, popular repeated videos were driving it.
6. **Per-assistant.** Refit separately for ChatGPT / Gemini / Claude / AIO. They have different retrieval stacks; a null in aggregate could hide opposing effects. Watch power here — splitting four ways cuts your 1,600 events to ~400 each, which is still fine for detection but marginal for the *equivalence* claim.
7. **Fetch-failure sensitivity.** Refit excluding any row where `fetch_ok = 0`. If the conclusion changes, Audit A was the whole study.
8. **Missingness.** `like_count` and `comment_count` are null when creators hide them. Hiding is not random — check whether hidden-like videos differ systematically. Do not silently drop; fit with and without.

---

## 8. Deliverables and sequence

1. **Audits A, B, C** (§2). ← *do this first; it may kill or reshape the study*
2. Count `n_youtube_evaluated` distribution → confirm the singleton assumption
3. Enrich all 5,500 rows via YouTube Data API v3 (`videos.list` + `channels.list`, 1 quota unit each, 50 IDs per batch → the whole job is ~220 quota units, comfortably inside the 10,000/day default)
4. Freeze this spec. Register H1–H5 and the SESOI.
5. Run `analysis.py`
6. Robustness suite (§7)
7. Write-up

---

## 9. Notes for the eventual blog post

- The flat-line-across-subscriber-deciles chart is the money graphic. Lead with it.
- Frame it as a **funnel decomposition**, not a debunking. "Audience gets you retrieved. Relevance gets you cited." That's constructive, it's true, it's what the data supports, and it doesn't require us to claim more than we measured.
- Be explicit that we only measured the second half of the funnel. Someone will point it out otherwise, and it's much better to be the one who says it.
- The mechanistic explanation (§1) is what makes this credible rather than merely statistical: the model *cannot* see subscriber count at citation time. We predicted the null from first principles and then confirmed it. That's a much stronger epistemic position than mining a correlation.
- Publish the equivalence bound. "We could have detected a 10% shift in odds and found none" is the sentence that makes this defensible.
