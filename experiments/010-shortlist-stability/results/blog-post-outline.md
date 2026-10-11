# Companion blog post outline: 010-shortlist-stability (Stage 1)

This is the outline the companion post follows. The post lives in the
spyglasses repo at `apps/web/content/posts/ai-shortlist-stability.mdx` plus
`ai-shortlist-stability.de.mdx` (branch `content/ai-shortlist-stability`),
written with the `marketing-strategy` skill. No date in the slug; the date
(2026-10-13) is in frontmatter only. Every claim stays inside the article's
"What we can and cannot claim" section and the framing in
`results/article-outline.md` (approved 2026-10-11). Research article:
https://research.spyglasses.io/articles/ai-shortlist-stability

**Slug:** `ai-shortlist-stability`

**Title (EN):** Getting Shortlisted by AI Is Stable. Your Rank Isn't.

**Title (DE):** Auf die KI-Shortlist zu kommen ist stabil. Ihr Rang ist es nicht.

**Excerpt (EN, no colon):** We asked ChatGPT, Gemini and Claude the same 40
B2B software buying questions every day for a week. When ChatGPT or Claude
recommended a vendor, it recommended that vendor again about four times in
five. Exact rank and the top pick moved far more. Chase the shortlist, not
the position.

**Header image:** `apps/web/public/images/blog/ai-shortlist-stability.webp`,
made with the `brand-og-image` skill (abstract, no text, gold isotype).

**Figures (copied from `results/figures/`, already watermarked):**
`stage1_shortlist.png` -> `ai-shortlist-repeat-rate.png` (lead),
`stage1_shortlist_runs.png` -> `ai-shortlist-stable-core.png`,
`stage1_platform_agreement.png` -> `ai-shortlist-platform-agreement.png`.
The all-status figures (`stage1_retention.png`, `stage1_gaps.png`) are not used.

## Key takeaways (mandatory list after the intro, EN + DE, no statistics)

- When ChatGPT or Claude recommends a B2B software vendor for a buying
  question, it usually recommends that vendor again when the same question
  is asked on another day.
- Gemini's shortlist changes more from day to day than ChatGPT's or
  Claude's, so a single Gemini answer tells you less.
- A vendor's exact position in an answer moves a lot from run to run.
  Whether it makes the shortlist mostly doesn't.
- The top pick rotates, but usually among vendors that stay on the
  shortlist. Losing the top spot rarely means losing the recommendation.
- What AI says a vendor is "best for" changes more than whether AI
  recommends the vendor at all.
- ChatGPT, Gemini and Claude often recommend different vendors for the same
  question on the same day, so each platform needs its own tracking.

## Structure

1. **Lead.** The familiar problem: the same question gives different
   answers and the vendor order shuffles. Which part can you count on? The
   shortlist: ChatGPT 81%, Claude close behind, Gemini less consistent;
   position moves far more. "Chasing rank is futile. Chasing a place on the
   shortlist isn't." Link to the research article.
2. **Key takeaways** (above).
3. **The study (no math).** The 40 B2B questions from 009 (link the 009
   blog post), 20 categories, once a day Oct 3 to 9 on ChatGPT, Gemini and
   Claude (Opus 5.5 API), plus claude.ai answers from 009 collected by hand.
   "2,770 answers were evaluated in this study", including the consumer and
   agency side test. The classifier labels each vendor (top choice, one of
   many, mention, cautioned against); same classifier Spyglasses uses in
   production; shortlist = top choice or one of many. Tests and margins set
   before data collection.
4. **What we found.**
   - The shortlist repeats (lead figure): 81 / 78 / 75 / 64. Stable core
     (figure): every-run share 60 / 56 / 32; one-run-only 4 / 4 / 9. Market
     concentration: two different questions in a category share 59% on
     ChatGPT vs 81% for the same question. Side test: headphones about as
     stable as B2B software; brand-design agencies far less (small sample).
     The shortlist is exactly as stable as the mention set and tells you more.
   - "Best for" moves more: about half the time on ChatGPT and Claude, less
     on Gemini; possible follow-up study. (Do NOT cite the phrase-wording
     repeat rate.)
   - Platforms disagree (figure): 63 / 63 / 55; ChatGPT and Claude agree
     with themselves more than with any other platform; Gemini's
     self-agreement equals its agreement with ChatGPT.
   - Short late note on rank and top pick: position 35 / 27 / 22; top pick
     55% on ChatGPT, lower elsewhere; top pick still shortlisted 95 to 99%
     on ChatGPT and Claude; part of the rotation is the labeling (re-labeled
     identical answers changed the top pick more than the shortlist). Link
     the earlier rank-stability article: rank slip is weather, leaving the
     shortlist is news.
5. **What this means for your tracking.** Make the shortlist the goal;
   don't report a rank change from one run; track each platform on its own
   (Gemini needs more runs); read "best for" across runs.
6. **What this doesn't mean.** One question is not a category; 40
   synthetic B2B questions, US, seven consecutive days; logged-out ChatGPT
   and Gemini, Claude API, claude.ai by hand from one account; AI
   classifier; nothing about buyer behavior; ChatGPT model change on day six
   (first model alone 83%, conclusions unchanged).
7. **What's next.** Stage 2: weekly through Nov 6, same questions,
   platforms and time of day; tests whether the shortlist holds a month
   apart; plan already set; results in November.
8. **Product tie-in (light).** Daily Prompt Tracking checks every day
   whether each platform recommends you (top choice or one of many) on your
   buyers' questions, the measure this study found reliable, and reports
   each platform separately: ChatGPT, Gemini and Google AI Overviews, with
   Claude as an add-on. Link `/en/prompt-tracking` (`/de/prompt-tracking`).

## House rules applied

- American English (EN); German is a natural translation with the same
  structure and Sie form.
- No em or en dashes; banned words checked (honest, genuine, carry, plain
  English, simply put; DE ehrlich, aufrichtig); no eyebrow kicker.
- Sample sizes as "answers evaluated in this study", never a database total.
- No vendor names from the answers, no prompt or answer text.
- No weakness of any Spyglasses feature described (no mention of the
  "Where AI picks you" phrase-grouping result).
- `pnpm content:check` passes.
