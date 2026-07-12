// @ts-check
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://research.spyglasses.io",
  output: "static",
  trailingSlash: "never",
  integrations: [mdx(), sitemap()],
});
