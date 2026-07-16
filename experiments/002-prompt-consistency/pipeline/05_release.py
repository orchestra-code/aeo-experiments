"""Stage 05 — gate-checked public dataset -> data/public/.

Derived features only. Survey prompt text is NEVER published (the prompts are
SparkToro's de-identified survey responses and are not ours to share — the
datasheet credits SparkToro and points reproducers at Rand Fishkin). Raw
answer markdown and fan-out query text never leave data/{raw,interim}.

Do not commit data/public/ until the human release checklist is signed.
"""

from __future__ import annotations

import pandas as pd
from common import PUBLIC, RESPONSES_CSV

from aeo_research import ColumnSpec, Datasheet, pseudonymize, release_dataset

SLUG = "prompt-consistency-chatgpt"

COLUMNS = [
    ColumnSpec("item_code", "Pseudonymized survey-prompt code (stable across waves)"),
    ColumnSpec("intent_class", "Prompt intent: headphones (primary) or coffee (contrast)"),
    ColumnSpec("wave", "Run wave, 1-7 (one per day)"),
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
            "intent_class": df["intent"],
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
            title="Prompt-phrasing consistency of ChatGPT recommendations",
            dataset_slug=SLUG,
            study="002-prompt-consistency",
            notes=[
                "Survey prompts were collected and de-identified by SparkToro "
                "(Rand Fishkin); prompt text is not included and is not ours to "
                "share — contact SparkToro to obtain it.",
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
