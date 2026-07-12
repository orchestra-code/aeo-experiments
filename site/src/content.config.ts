import { glob } from "astro/loaders";
import { defineCollection, z } from "astro:content";

const articles = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/articles" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    authors: z
      .array(z.object({ name: z.string(), url: z.string().url().optional() }))
      .min(1),
    experiment: z.string(),
    heroFigure: z.string(),
    figures: z.array(z.string()).optional(),
    datasets: z
      .array(
        z.object({
          title: z.string(),
          path: z.string(),
          license: z.string().default("CC BY 4.0"),
          rows: z.number().optional(),
        }),
      )
      .default([]),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
  }),
});

// Governance docs live at the repo root so they're readable on GitHub too;
// the site renders them from there rather than keeping a copy.
const repoDocs = defineCollection({
  loader: glob({ pattern: ["methodology.md", "data-policy.md"], base: "../docs" }),
  schema: z.object({}).passthrough(),
});

export const collections = { articles, repoDocs };
