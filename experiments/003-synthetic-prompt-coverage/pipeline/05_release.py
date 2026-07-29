"""Stage 05 — gate-checked public dataset -> data/public/.

Derived features only. Human prompt text is SparkToro's and is NEVER
published; synthetic prompt text is product-derived and is likewise withheld
(prompts and fan-outs are proprietary per the research data policy). Raw
answer markdown and fan-out query text never leave data/{raw,interim}.

Do not commit data/public/ until the human release checklist is signed.
"""

from __future__ import annotations

import pandas as pd
from common import PUBLIC, RESPONSES_CSV

from aeo_research import ColumnSpec, Datasheet, pseudonymize, release_dataset

SLUG = "synthetic-prompt-coverage-chatgpt"

COLUMNS = [
    ColumnSpec("item_code", "Pseudonymized prompt code (stable across waves)"),
    ColumnSpec(
        "panel",
        "Prompt panel: hum (human survey), spy_a / spy_b (brand-anchored "
        "generator), neu (neutral generator), coffee (cross-intent control)",
    ),
    ColumnSpec("wave", "Run wave, 1-5 (one per day; coffee runs wave 1 only)"),
    ColumnSpec("run_date", "Collection date (UTC)"),
    ColumnSpec("model_version", "Model identifier reported by the scraper", public_fact=True),
    ColumnSpec("n_brands_recommended", "Count of distinct brands extracted from the reply"),
    ColumnSpec(
        "brands_recommended",
        "Pipe-joined canonical brands, ordered by first mention",
        public_fact=True,
    ),
    ColumnSpec("top_brand", "First-mentioned brand", public_fact=True),
    ColumnSpec("n_domains_cited", "Count of distinct registered domains in cited sources"),
    ColumnSpec(
        "domains_cited",
        "Pipe-joined registered domains of cited sources (public web facts)",
        public_fact=True,
    ),
    ColumnSpec("n_grounding_searches", "Count of grounding searches the model ran"),
    ColumnSpec("had_web_search", "1 if the reply used web search (sources or grounding)"),
    ColumnSpec("reply_word_count", "Word count of the reply text"),
]


def main() -> None:
    df = pd.read_csv(RESPONSES_CSV)
    if int(df.get("synthetic", pd.Series([0])).max()) == 1:
        raise SystemExit("refusing to release a SYNTHETIC frame")

    out = pd.DataFrame(
        {
            "item_code": pseudonymize(df["item_id"], "item"),
            "panel": df["arm"],
            "wave": df["wave"],
            "run_date": df["run_date"],
            "model_version": df["model"],
            "n_brands_recommended": df["n_brands"],
            "brands_recommended": df["brands"].fillna(""),
            "top_brand": df["top_brand"].fillna(""),
            "n_domains_cited": df["domains"].fillna("").str.split(r"\|").map(
                lambda x: len([d for d in x if d])
            ),
            "domains_cited": df["domains"].fillna(""),
            "n_grounding_searches": df["n_fanout"],
            "had_web_search": df["had_web_search"],
            "reply_word_count": df["reply_word_count"],
        }
    )

    paths = release_dataset(
        out,
        COLUMNS,
        PUBLIC,
        Datasheet(
            title="Synthetic vs human prompt panels on ChatGPT",
            dataset_slug=SLUG,
            study="003-synthetic-prompt-coverage",
            notes=[
                "Human prompts were collected and de-identified by SparkToro "
                "(Rand Fishkin); prompt text is not included and is not ours "
                "to share — contact SparkToro to obtain it.",
                "Synthetic prompt text (spy_a/spy_b/neu panels) is withheld; "
                "panels are described by their generation method in the study.",
                "One row per collected ChatGPT run (DataForSEO LLM scraper, "
                "en-US, location code 2840, web search forced).",
                "Rows are runs evaluated in this study.",
            ],
        ),
    )
    print(f"released: {paths['csv']}\n          {paths['datasheet']}")
    print("Do not commit data/public/ until the release checklist is signed.")


if __name__ == "__main__":
    main()
