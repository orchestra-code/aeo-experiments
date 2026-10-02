# Claude API vs claude.ai: the 40 synthetic B2B software prompts

- **Study:** 009-claude-model-fidelity
- **Rows:** 40 (prompts evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-10-02

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `item_id` | Study prompt id; joins the answers file |
| `category` | Software category |
| `intent` | shortlist or evaluate |
| `n_words` | Word count of the prompt |
| `prompt_text` | Verbatim study-generated synthetic prompt (data policy: Synthetic study prompts) |

## Notes

- Rows are the synthetic prompts evaluated in this study; each ran in all 9 arms on 3 days (see the answers file; item_id joins the two).
- Generated once by claude-haiku-4-5 (harness/make_prompts.py): 20 software categories x 2 intents, first-person buyer phrasing, 15 to 45 words, no vendor or product names, no location, no year; checked by rule, regenerated on failure, reviewed by a person and frozen with the spec.
- Released under the research data policy's 'Synthetic study prompts' exemption: study-generated, no brand anchors, never seeded from customer prompts.
- Text is verbatim as generated.
