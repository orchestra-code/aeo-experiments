# Sub-intent-matched prompt panels — prompt text

- **Study:** 005-subintent-matched-panels
- **Rows:** 95 (citations evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-08-06

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `item_code` | Pseudonymized prompt code — joins the runs dataset |
| `panel` | Prompt panel: mat (profile-stratified scenario generator), neu2 (unstratified scenario generator) |
| `generation_framework` | 'stratified' (mat) or 'neutral' (neu2) |
| `generation_query_type` | mat only: the stratum cell — the sub-intent flags the prompt was generated to carry (e.g. 'travel+music+budget') |
| `n_words` | Word count of the prompt |
| `prompt_text` | Verbatim study-generated synthetic prompt (data policy: Synthetic study prompts) |

## Notes

- Rows are synthetic prompts evaluated in this study; each ran once per day for 5 days (see the runs dataset; item_code joins the two files).
- Panels were generated once on 2026-08-02 and frozen before any collection: mat by a scenario generator stratified to the 003 human panel's joint sub-intent profile (the generation_query_type column names each prompt's target stratum), neu2 by the same scenario generator unstratified (an exact replication of 003's neu arm).
- Released under the research data policy's 'Synthetic study prompts' exemption: study-generated, no brand anchors, and the generation styles are publicly reproducible with the free AI-visibility prompt generator on spyglasses.io.
- Text is verbatim as generated; validation was regenerate-until-valid, never hand-editing.
- Human survey prompts (hum panel) and the coffee contrast panel were collected and de-identified by SparkToro (Rand Fishkin); they are not ours to share — contact SparkToro to obtain them.
