# Companion blog post outline: 009-claude-model-fidelity

This is an outline, not a post. The post is written in the spyglasses repo,
`apps/web/content/posts/<slug>.mdx` plus `<slug>.de.mdx`, by whoever drafts
it, with the `marketing-strategy` skill. No date in the slug. Every claim
must stay inside the article's "What we can and cannot claim" section
(`site/src/content/articles/claude-api-vs-claude-ai.mdx`).

**Proposed slug:** `tracking-claude-with-sonnet`

**Working title (EN):** If you track Sonnet as a proxy for Claude users, you are tracking the wrong brands

**Working title (DE):** Wer Sonnet als Ersatz für Claude-Nutzer misst, misst die falschen Marken

**Excerpt (EN, no colon):** claude.ai now answers on Opus 5.5 by default. We
asked it 40 B2B software buying questions on three days and asked the same
questions through seven API setups. Every Sonnet setup named a different set
of brands. Opus 5.5 through the API came close, at about the same cost.

**Hero image:** `gap-vs-cost.png` from the study (watermarked). Use the
`brand-og-image` skill only if a branded OG card is wanted on top.

## Key takeaways (mandatory list after the intro, EN + DE)

The post references research, so the Key takeaways list is required in both
languages. Draft bullets:

- claude.ai now uses Opus 5.5 by default. Sonnet 5 through the API named a
  measurably different set of brands than claude.ai did on the same B2B
  software question, in every setup we tested.
- The closest Sonnet setup sat right at the edge of our tolerance. It could
  not be shown to match, and it may differ by up to 0.15 on a 0 to 1
  overlap scale.
- Opus 5.5 through the API stayed within the tolerance, with or without a
  copy of claude.ai's system prompt. With no system prompt it cost $0.071
  per call, close to Sonnet's $0.065.
- Adding the leaked claude.ai system prompt raised the Opus cost by about
  80% without a meaningful gain in which brands were named.
- claude.ai's High reasoning setting searched twice as often as the default
  but named the same brands.
- Spyglasses tracked Claude with Sonnet. We are switching to Opus 5.5
  because of this study.

## Structure

1. **Lead (the claim as advice).** "If you're tracking Sonnet as a proxy for
   real Claude users, you're getting the wrong brands." Frame it for anyone
   who tracks how Claude talks about brands, whatever tool or script they
   use. One paragraph: claude.ai's default moved to Opus 5.5 on 2026-09-22,
   and Sonnet answers a buying question with a different set of vendors.
   Do not name, describe or allude to any other tracking tool or vendor.
2. **Our own disclosure, early and plain.** Spyglasses' Claude tracking ran
   on Sonnet 5 with our own discovery prompt. The study tested that exact
   request. It was among the furthest from claude.ai on brands (a gap of
   0.165, second only to Haiku). We are switching our Claude tracking to
   Opus 5.5 because of these results. Do not quote or describe the content
   of our prompt. If the switch has a ship date or a customer-facing note
   by publication, link it; otherwise say "we are switching" without a date.
3. **What we did (no math).** 40 buying questions, 20 software categories,
   asked by hand in claude.ai on three days from a fresh account with
   memory off, and through seven API setups on the same days. We compared
   which brands each answer named and which sites it cited. The bar was
   claude.ai against itself: if an API setup agrees with claude.ai about as
   well as claude.ai agrees with itself from day to day, it passes.
4. **What we found.** Figure: `brand-gap.png` (which brands, and their
   order). Three short points, in this order:
   - Sonnet and Haiku name different brands from claude.ai.
   - Opus 5.5 through the API is close. The leaked system prompt mostly
     adds cost. It helps the order of the brands somewhat.
   - The reasoning setting in claude.ai does not change the brands.
5. **The cost surprise.** A short table or two sentences: Opus 5.5 with no
   system prompt $0.071 per call, Sonnet 5 with no system prompt $0.065, our
   former production Sonnet request $0.081, Opus with the leaked prompt
   $0.128. The cheaper stand-in is not much cheaper.
6. **What this means for your tracking.**
   - Ask which model your Claude numbers come from. If it is not Opus 5.5,
     the brands in the report are not the brands a claude.ai user sees by
     default. (Phrase this as a question for the reader, not as a statement
     about any provider.)
   - Cited sources move a lot from day to day, even within claude.ai (an
     overlap score of about 0.15 for the same question on different days). Read
     source data across repeated runs, never from one run.
   - Brand order matters. Opus without a system prompt gets the set right
     but the order slightly less so.
7. **Limits, in two sentences.** One fresh claude.ai account in one city,
   B2B software questions only, three days. Results describe claude.ai with
   personalization off.
8. **CTA.** Daily Prompt Tracking on Claude, now on Opus 5.5 (only once the
   switch has shipped; confirm with Jim before publishing). Link to the
   research article for the full method and data.

## Figures to reuse

- `gap-vs-cost.png`: hero and the cost point.
- `brand-gap.png`: the main finding.

Both are in `site/public/figures/009-claude-model-fidelity/` once the
research site is deployed; copy them into `apps/web/public/images/blog/` or
link the research-site URLs.

## House rules reminder

- American English in both the EN copy and any English quoted in DE.
- Follow the house banned-words list for customer copy (the copy rules in
  the spyglasses repo). No em or en dashes; ranges written with "to".
- Sample sizes as "answers evaluated in this study". Never a database total.
- No prompt text, answer text, search-query text or system prompt content,
  even as examples. No brand names from the answers.
- No competitor or other vendor named or alluded to, anywhere in the post.
- "Daily Prompt Tracking", not "Nightly".
- Link to research.spyglasses.io/articles/claude-api-vs-claude-ai as the
  source of the full method and data.
- Run `pnpm content:check` after adding the .mdx files (frontmatter must
  parse; quote or rewrite any excerpt with a colon followed by a space).
