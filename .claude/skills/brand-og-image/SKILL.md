---
name: brand-og-image
description: Turn a raw generated image into a branded 1200×630 Spyglasses OpenGraph card — cover-crop to 1200×630 and stamp the gold isotype in the lower-right, output WEBP. Use whenever a blog post (spyglasses repo, apps/web/content/posts) or a research article (aeo-experiments, research.spyglasses.io) needs its `image`/OG header, replacing the manual Canva → convert → rename → add-logo steps. Triggers: "make an OG image", "branded header image", "blog hero image", "open graph card", "add the logo to this image".
---

# Brand OG image

Automates the deterministic half of the Spyglasses article-header workflow: take a source image (usually generated via the Replicate API) and produce the branded 1200×630 card that goes in a post's `image:` frontmatter and on the research site.

## The house convention

Study the existing cards in `spyglasses/apps/web/public/images/blog/` (e.g. `ai-readiness-validate-seo.webp`). They share:

- **Abstract, no words.** Representative of the topic, not literal. Icons are OK; text is not.
- **Brand palette:** deep blues with copper/gold accents (`#5887DA` blue, `#C95920` copper).
- **Gold isotype, lower-right.** The brass Spyglasses lens mark, ~74 px on a 1200 px card, inset ~22 px. This tool stamps it for you.
- **Exactly 1200×630, WEBP.**

Recommended Replicate prompt shape (the user generates the source; adapt the subject):

> An abstract image representing &lt;the article's subject&gt;. Blue palette with copper accents. No words are in the image.

## Run it

The tool lives in the `aeo-experiments` toolkit (uv env with Pillow + cairosvg). Run from that repo root:

```bash
uv run python scripts/make_og_image.py <SOURCE_IMAGE> <OUTPUT.webp>
```

It cover-crops the source to 1200×630 (center, no distortion) and composites the gold isotype lower-right. Default stamp is `site/public/brand/spyglasses_isotype.svg`; override with `--logo`.

### Blog post (spyglasses repo)

Output straight into the blog images dir, named to match the post slug:

```bash
uv run python scripts/make_og_image.py ~/Downloads/raw.png \
  /Users/jcw/projects/spyglasses/apps/web/public/images/blog/<post-slug>.webp
```

Then set the post frontmatter (both `<slug>.mdx` and `<slug>.de.mdx`):

```yaml
image: /images/blog/<post-slug>.webp
```

Do not commit in the spyglasses repo unless the user asks — leave it for review.

### Research article (aeo-experiments)

Output into the experiment's figures dir, then sync + set `ogImage`:

```bash
uv run python scripts/make_og_image.py raw.png \
  experiments/<slug>/figures/hero-og.webp
uv run python scripts/sync_site_assets.py <slug>
```

Set the article frontmatter (`site/src/content/articles/<slug>.mdx`):

```yaml
ogImage: "/figures/<slug>/hero-og.webp"
```

`ogImage` becomes the OpenGraph/Twitter image, the `ScholarlyArticle` JSON-LD image, and the header shown on the article page and in the article list. If omitted, the site falls back to `heroFigure` (the lead chart) for OG only.

## Reuse the same art for both

A study and its companion blog post should share one card. Generate once, write it to both destinations (blog images dir and experiment figures dir), and reference it from both frontmatters.

## Verify

Open the output; confirm it is 1200×630, the isotype sits cleanly in the lower-right on a busy-but-not-cluttered corner (regenerate the source if the corner is noisy), and no text appears in the art. For research articles, `pnpm build` in `site/` and check the article's `og:image` and the header render.
