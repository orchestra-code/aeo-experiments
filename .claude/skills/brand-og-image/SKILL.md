---
name: brand-og-image
description: Generate and/or brand a 1200×630 Spyglasses OpenGraph card. Writes a prompt from the article's topic, generates abstract art via Replicate, cover-crops to 1200×630, and stamps the gold isotype lower-right → WEBP. Use whenever a blog post (spyglasses repo, apps/web/content/posts) or a research article (aeo-experiments, research.spyglasses.io) needs its `image`/OG header, replacing the manual Replicate → Canva → convert → rename → add-logo steps. Triggers: "make an OG image", "generate the header image", "branded blog hero", "open graph card", "add the logo to this image".
---

# Brand OG image

Automates the article-header workflow: from the written post, craft an abstract prompt, generate the art, and produce the branded 1200×630 card that goes in the post's `image:` frontmatter and on the research site. Two entry points: generate-and-brand (one command) or brand-an-existing-image.

## The house convention

Study the existing cards in `spyglasses/apps/web/public/images/blog/` (e.g. `ai-readiness-validate-seo.webp`). They share:

- **Abstract, no words.** Representative of the topic, not literal. Icons OK; text is not.
- **Brand palette:** deep blues with copper/gold accents (`#5887DA` blue, `#C95920` copper).
- **Gold isotype, lower-right.** The tool stamps it (~74 px on a 1200 px card, ~22 px inset).
- **Exactly 1200×630, WEBP.**

## Writing the prompt

When invoked, read the article and write a prompt in this shape (you fill in the subject):

> An abstract image representing &lt;the article's subject or its key finding&gt;. Blue palette with copper accents. No words are in the image.

Keep it a single conceptual scene, not a literal illustration. Prefer the study's *idea* (e.g. "AI scanning a video timeline to surface the single best moment") over its charts.

## Path A — generate and brand (default)

Requires a Replicate token. The script reads `REPLICATE_API_TOKEN` from the environment, or from `--env-file` pointing at a dotenv that defines it — the token in the **spyglasses checkout's `.env.local`** works. Generation costs a small Replicate credit.

```bash
# from the aeo-experiments repo root
uv run python scripts/generate_og_image.py <DST>.webp \
  --prompt "An abstract image representing <subject>. Blue palette with copper accents. No words are in the image." \
  --env-file <path-to-spyglasses>/.env.local \
  --source-out <keep the raw art here for reproducibility>
```

Default model `google/nano-banana-2` at 21:9 (crops cleanly to 1200×630). After it writes the card, **open it and check** it is on-brand, abstract, word-free, and the isotype sits over a calm corner. If not, rerun (image gen varies) or adjust the prompt.

## Path B — brand art you already have

Skip generation; just crop + stamp an existing image:

```bash
uv run python scripts/make_og_image.py <SOURCE_IMAGE> <DST>.webp
```

## Wiring the output

### Blog post (spyglasses repo)

Name the card by post slug and set both `<slug>.mdx` and `<slug>.de.mdx`:

```bash
uv run python scripts/generate_og_image.py \
  <path-to-spyglasses>/apps/web/public/images/blog/<post-slug>.webp \
  --prompt "..." --env-file <path-to-spyglasses>/.env.local
```
```yaml
image: /images/blog/<post-slug>.webp
```

Do not commit in the spyglasses repo unless asked — leave it for review.

### Research article (aeo-experiments)

```bash
uv run python scripts/generate_og_image.py experiments/<slug>/figures/hero.webp \
  --prompt "..." --env-file <path-to-spyglasses>/.env.local \
  --source-out experiments/<slug>/hero-source.jpg
uv run python scripts/sync_site_assets.py <slug>
```
```yaml
ogImage: "/figures/<slug>/hero.webp"
```

`ogImage` becomes the OpenGraph/Twitter image, the `ScholarlyArticle` JSON-LD image, the header on the article page, and the article-list thumbnail. Omit it and the site falls back to `heroFigure` (the lead chart) for OG only.

## Reuse the same art for both

A study and its companion blog post should share one card. Generate once with `--source-out`, then run Path B (`make_og_image.py`) on that saved source for the second destination — no second Replicate call.

## Verify

Open the output: 1200×630, on-brand, no text, isotype clean in the lower-right. For research articles, `pnpm build` in `site/` and check the article's `og:image` and header render.
