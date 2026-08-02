"""Stage 05 — gate-checked public datasets -> data/public/.

Two files, joined by ``item_code``:
- ``synthetic-prompt-coverage-chatgpt.csv`` — one row per collected run,
  derived features only.
- ``synthetic-prompt-coverage-prompts.csv`` — the verbatim synthetic prompt
  panels (spy_a / spy_b / neu), released under the data policy's
  "Synthetic study prompts" exemption (2026-08-02): study-generated, over
  non-customer brands, generation styles publicly reproducible via the free
  spyglasses.io prompt generator.

Human prompt text is SparkToro's and is NEVER published (that includes the
coffee contrast panel). Raw answer markdown and fan-out query text never
leave data/{raw,interim}.

Do not commit data/public/ until the human release checklist is signed.
"""

from __future__ import annotations

import pandas as pd
from common import ANCHORS, PROMPTS_CSV, PUBLIC, RESPONSES_CSV, SYNTH_ARMS

from aeo_research import ColumnSpec, Datasheet, pseudonymize, release_dataset

SLUG = "synthetic-prompt-coverage-chatgpt"
PROMPTS_SLUG = "synthetic-prompt-coverage-prompts"

#: The panels contain zero brand-name leaks (pre-freeze finding); enforce it
#: at release time anyway. "soundcore" covers the spy_b anchor's trade name
#: (its lexicon canonical is "anker").
LEAK_TERMS = sorted({*ANCHORS.values(), "soundcore"})

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

PROMPT_COLUMNS = [
    ColumnSpec("item_code", "Pseudonymized prompt code — joins the runs dataset"),
    ColumnSpec(
        "panel",
        "Prompt panel: spy_a / spy_b (brand-anchored generator), neu (neutral generator)",
    ),
    ColumnSpec("generation_framework", "Generator framework that produced the prompt"),
    ColumnSpec(
        "generation_query_type",
        "Generator query-type label within the framework",
        synthetic_study_text=True,
    ),
    ColumnSpec("n_words", "Word count of the prompt"),
    ColumnSpec(
        "prompt_text",
        "Verbatim study-generated synthetic prompt (data policy: Synthetic study prompts)",
        synthetic_study_text=True,
    ),
]


def release_prompts(mapping: dict[str, str]) -> None:
    prompts = pd.read_csv(PROMPTS_CSV)
    synth = prompts[prompts["arm"].isin(SYNTH_ARMS)].copy()

    unmapped = sorted(set(synth["item_id"]) - set(mapping))
    if unmapped:
        raise SystemExit(f"prompts without a run-dataset code: {unmapped}")
    leaks = [
        (r.item_id, term)
        for r in synth.itertuples()
        for term in LEAK_TERMS
        if term in r.text.lower()
    ]
    if leaks:
        raise SystemExit(f"anchor brand name leaked into prompt text: {leaks}")

    out = pd.DataFrame(
        {
            "item_code": synth["item_id"].map(mapping),
            "panel": synth["arm"],
            "generation_framework": synth["framework"],
            "generation_query_type": synth["query_type"],
            "n_words": synth["n_words"],
            "prompt_text": synth["text"],
        }
    )
    paths = release_dataset(
        out,
        PROMPT_COLUMNS,
        PUBLIC,
        Datasheet(
            title="Synthetic prompt panels — prompt text",
            dataset_slug=PROMPTS_SLUG,
            study="003-synthetic-prompt-coverage",
            notes=[
                "Rows are synthetic prompts evaluated in this study; each ran "
                "once per day for 5 days (see the runs dataset; item_code "
                "joins the two files).",
                "Panels were generated once on 2026-07-29 and frozen before "
                "any collection: spy_a by the production Spyglasses generator "
                "anchored on bose.com, spy_b anchored on soundcore.com, neu "
                "by a scenario-only generator with no brand context.",
                "Released under the research data policy's 'Synthetic study "
                "prompts' exemption: study-generated, over non-customer "
                "brands, and the generation styles are publicly reproducible "
                "with the free AI-visibility prompt generator on "
                "spyglasses.io.",
                "Text is verbatim as submitted, including one spy_b prompt "
                "with a visible generation artifact (the category phrased as "
                "a 'platform').",
                "Human survey prompts (hum panel) and the coffee contrast "
                "panel were collected and de-identified by SparkToro (Rand "
                "Fishkin); they are not ours to share — contact SparkToro to "
                "obtain them.",
            ],
        ),
    )
    print(f"released: {paths['csv']}\n          {paths['datasheet']}")


def main() -> None:
    df = pd.read_csv(RESPONSES_CSV)
    if int(df.get("synthetic", pd.Series([0])).max()) == 1:
        raise SystemExit("refusing to release a SYNTHETIC frame")

    codes = pseudonymize(df["item_id"], "item")
    out = pd.DataFrame(
        {
            "item_code": codes,
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
                "Synthetic prompt text (spy_a/spy_b/neu panels) is released "
                "in the companion dataset "
                "synthetic-prompt-coverage-prompts.csv; item_code joins the "
                "two files.",
                "One row per collected ChatGPT run (DataForSEO LLM scraper, "
                "en-US, location code 2840, web search forced).",
                "Rows are runs evaluated in this study.",
            ],
        ),
    )
    print(f"released: {paths['csv']}\n          {paths['datasheet']}")

    release_prompts(dict(zip(df["item_id"], codes)))
    print("Do not commit data/public/ until the release checklist is signed.")


if __name__ == "__main__":
    main()
