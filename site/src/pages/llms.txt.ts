import type { APIRoute } from "astro";
import { getCollection } from "astro:content";
import { SITE_DESCRIPTION, SITE_TITLE, SITE_URL } from "../consts";

export const GET: APIRoute = async () => {
  const articles = (await getCollection("articles", ({ data }) => !data.draft)).sort(
    (a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf(),
  );

  const lines = [
    `# ${SITE_TITLE}`,
    "",
    `> ${SITE_DESCRIPTION}`,
    "",
    "Studies are pre-registered; each article states exactly what its design",
    "can and cannot claim, and publishes analysis code and (where possible) an",
    "anonymized dataset of derived features.",
    "",
    "## Articles",
    "",
    ...articles.map(
      (a) =>
        `- [${a.data.title}](${SITE_URL}/articles/${a.id}): ${a.data.description}`,
    ),
    "",
    "## Resources",
    "",
    `- [Methodology](${SITE_URL}/methodology): how studies are designed and reported`,
    `- [Datasets](${SITE_URL}/datasets): anonymized data downloads`,
    "- [Code and specs](https://github.com/orchestra-code/aeo-experiments): public repository",
    "- [Spyglasses](https://spyglasses.io): the AI visibility platform behind the research",
    "",
  ];
  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
