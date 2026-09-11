# Companion blog post outline — 008-brand-domain-knowledge

Where: spyglasses repo, `apps/web/content/posts/<slug>.mdx` + `<slug>.de.mdx`.
No date in the slug. Draft with the `marketing-strategy` skill. Claims must
stay inside the article's "What we can and cannot claim" section.

**Proposed slug:** `does-chatgpt-know-your-domain`

**Working title (EN):** ChatGPT already knows your domain. Here is what
that changes.

**Working title (DE):** ChatGPT kennt Ihre Domain bereits. Was das für
Sie ändert.

**Excerpt (EN, no colon):** We asked ChatGPT about 48 brands twice a day for
ten days and recorded which site it chose to search. It picked the right
domain in over 98% of calls in every tier, including brands whose domain
has nothing to do with their name. The one thing it does not forget is a
domain you used to have.

**Hero image:** `tier-accuracy.png` from the study (watermarked, via the
`brand-og-image` skill only if a branded OG card is wanted on top).

## Key takeaways (mandatory list after the intro, EN + DE)

- When ChatGPT scopes a search to a brand's site, it uses the canonical
  domain in 98.5% to 100% of calls, in every tier of the study.
- It does not derive the domain from the name. Brands with non-obvious
  domains (linear.app, usemotion.com) were consulted at the right domain
  every time on brand-identity prompts.
- If you changed domains, the old one stays in the model's list. Meta's
  facebook.com and GoTo's logmein.com were consulted alongside the new
  domain on most days. Keep old domains resolving and redirecting.
- The rare wrong-company consultations happened on comparison prompts,
  where the model opens on competitors first. Comparison pages are where
  your domain identity is tested.
- Counts are calls evaluated in this study, on one model, through the API.
  A quiet ten days is an upper bound, not a guarantee.

## Structure

1. **The finding as advice.** Stop worrying that AI will "guess" your
   domain wrong. It knows it. Spend the worry on what it knows about you
   once it gets there.
2. **Why the intuitive alternative is wrong (no math).** People assume the
   model reconstructs brandname.com each time, because that is how a
   human would guess. The study built two traps for exactly that
   behavior, brands with non-obvious domains and obscure brands, and
   neither caught anything. Two name-shaped guesses in over seven
   thousand searches, both for one brand on one call.
3. **What to change this quarter.**
   - Migrated recently? Audit every old domain you ever used. Keep DNS,
     TLS and redirects alive. The model will keep asking the old address,
     and it asks it in the same breath as the new one.
   - Share a name with a bigger company? Your comparison content is where
     the model decides which of you it means. Category anchors in your own
     copy ("Amie, the AI calendar") are cheap insurance.
   - Check what the model finds when it arrives. It arrives at the right
     door; the question is whether the pricing page, the product
     descriptions and the comparison pages are ready to be read.
4. **The lead chart.** `tier-accuracy.png`, one sentence: four tiers, all
   at the ceiling.
5. **One limitation, stated plainly.** Every rate is "when the model chose
   to consult the brand's site". One model, one API surface, ten days.
   The old-domain finding is three brands; it is a pattern, not a law.
6. **CTA.** Run an AI Visibility report to see which of your pages the
   model consults directly, and whether it reaches the right domain.

## House rules reminder

- No "honest/genuine(ly)", no em or en dashes, ranges written with "to".
- Sample sizes as "calls evaluated in this study". Never a database total.
- No prompt text, answer text or search-query text, even as examples.
- Link to research.spyglasses.io/articles/brand-domain-knowledge as the
  source of the full methodology and data.
- "Daily Prompt Tracking", not "Nightly". MCP is not "read-only".
