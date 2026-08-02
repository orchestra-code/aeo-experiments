# Synthetic prompt panels — prompt text

- **Study:** 003-synthetic-prompt-coverage
- **Rows:** 114 (citations evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-08-02

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `item_code` | Pseudonymized prompt code — joins the runs dataset |
| `panel` | Prompt panel: spy_a / spy_b (brand-anchored generator), neu (neutral generator) |
| `generation_framework` | Generator framework that produced the prompt |
| `generation_query_type` | Generator query-type label within the framework |
| `n_words` | Word count of the prompt |
| `prompt_text` | Verbatim study-generated synthetic prompt (data policy: Synthetic study prompts) |

## Notes

- Rows are synthetic prompts evaluated in this study; each ran once per day for 5 days (see the runs dataset; item_code joins the two files).
- Panels were generated once on 2026-07-29 and frozen before any collection: spy_a by the production Spyglasses generator anchored on bose.com, spy_b anchored on soundcore.com, neu by a scenario-only generator with no brand context.
- Released under the research data policy's 'Synthetic study prompts' exemption: study-generated, over non-customer brands, and the generation styles are publicly reproducible with the free AI-visibility prompt generator on spyglasses.io.
- Text is verbatim as submitted, including one spy_b prompt with a visible generation artifact (the category phrased as a 'platform').
- Human survey prompts (hum panel) and the coffee contrast panel were collected and de-identified by SparkToro (Rand Fishkin); they are not ours to share — contact SparkToro to obtain them.
