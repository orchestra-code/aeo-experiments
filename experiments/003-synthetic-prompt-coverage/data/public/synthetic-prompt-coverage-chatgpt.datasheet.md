# Synthetic vs human prompt panels on ChatGPT

- **Study:** 003-synthetic-prompt-coverage
- **Rows:** 1,325 (citations evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-08-02

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `item_code` | Pseudonymized prompt code (stable across waves) |
| `panel` | Prompt panel: hum (human survey), spy_a / spy_b (brand-anchored generator), neu (neutral generator), coffee (cross-intent control) |
| `wave` | Run wave, 1-5 (one per day; coffee runs wave 1 only) |
| `run_date` | Collection date (UTC) |
| `model_version` | Model identifier reported by the scraper |
| `n_brands_recommended` | Count of distinct brands extracted from the reply |
| `brands_recommended` | Pipe-joined canonical brands, ordered by first mention |
| `top_brand` | First-mentioned brand |
| `n_domains_cited` | Count of distinct registered domains in cited sources |
| `domains_cited` | Pipe-joined registered domains of cited sources (public web facts) |
| `n_grounding_searches` | Count of grounding searches the model ran |
| `had_web_search` | 1 if the reply used web search (sources or grounding) |
| `reply_word_count` | Word count of the reply text |

## Notes

- Human prompts were collected and de-identified by SparkToro (Rand Fishkin); prompt text is not included and is not ours to share — contact SparkToro to obtain it.
- Synthetic prompt text (spy_a/spy_b/neu panels) is released in the companion dataset synthetic-prompt-coverage-prompts.csv; item_code joins the two files.
- One row per collected ChatGPT run (DataForSEO LLM scraper, en-US, location code 2840, web search forced).
- Rows are runs evaluated in this study.
