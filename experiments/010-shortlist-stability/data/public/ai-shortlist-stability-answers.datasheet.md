# AI shortlist stability, Stage 1: answers on ChatGPT, Gemini and Claude

- **Study:** 010-shortlist-stability
- **Rows:** 2,770 (answers evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-10-11

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `run_id` | Id of one answer evaluated in this study; joins the mentions file |
| `dataset` | chatgpt_b2b, gemini_b2b, claude_api_b2b (new collection); claude_b2b (experiment 009 holdout); chatgpt_consumer (headphones) and chatgpt_agency (brand-design agencies), holdouts of experiments 002, 003 and 005 |
| `platform` | chatgpt, gemini or claude |
| `collection` | dataforseo (LLM scraper), anthropic_api (Batches API) or claude_ai_by_hand (claude.ai, collected by hand in experiment 009) |
| `arm` | Configuration: chatgpt, gemini, claude (Opus 5.5 API, effort medium, no system prompt); for claude_b2b, ui_default (claude.ai default), ui_think (claude.ai High reasoning) or opus55_plain (the API arm, as in 009) |
| `test_arm` | 1 if the arm is the one the dataset's tests use (claude_b2b: ui_default); the other claude_b2b arms are for robustness and the arm comparison |
| `model` | Model string the platform reported (DataForSEO model field, Anthropic model id), 'claude.ai' for the hand-collected arms; blank where the source study did not record it |
| `study` | Experiment that collected the answer |
| `item_id` | Question id. B2B: b2b_01 to b2b_40, as in experiment 009's public prompts file (claude-api-vs-claude-ai-prompts.csv, which has the question text). Headphone and agency questions: per-release codes (consumer_NNN, agency_NNN); their text is never published |
| `category` | B2B software category (20 categories, 2 questions each); cat_c1 (consumer) and cat_a1 (agency) are per-release codes |
| `intent` | B2B only: shortlist (a buyer with a concrete company profile asks for options) or evaluate (a buyer describes a use case and asks how the top options compare) |
| `wave` | Run number within the study: 1 to 7 for the new collection (daily from 2026-10-03), 1 to 3 for claude_b2b, and the source study's wave for the consumer and agency answers |
| `run_date` | Date of the run (see the datasheet notes on time zones) |
| `n_lexicon_brands` | Count of distinct lexicon brands the answer named |
| `n_recommended` | Lexicon brands the judge labeled top choice or one of many (the shortlist) |
| `n_top_choice` | Lexicon brands labeled top choice (after the cap of two) |
| `n_cautioned` | Lexicon brands labeled cautioned against |
| `has_top_choice` | 1 if any lexicon brand is a top choice |
| `has_caution` | 1 if any lexicon brand is cautioned against |
| `n_top_choice_raw` | Brands (any, inside or outside the lexicon) the judge's raw output labeled top choice, before answers with more than two were demoted to one of many |
| `n_brands_all` | Brands the judge listed, inside or outside the lexicon (the R1 robustness view); names outside the lexicon are not released |
| `empty` | 1 if the answer was empty |
| `refusal` | 1 if the answer is a refusal: a refusal-shaped opening and no lexicon brand (spec deviation 7). Refusals and empty answers are excluded from the analysis |
| `refusal_phrase` | 1 if the first 600 characters open like a refusal, whatever follows |
| `judge_ok` | 1 if the judge returned a valid classification |

## Notes

- One row per answer evaluated in this study at Stage 1 (2,770): 840 new answers to 40 synthetic B2B software questions, asked once a day for 7 days (2026-10-03 to 2026-10-09) on ChatGPT, Gemini and Claude (280 each); 234 answers from experiment 009's holdout (26 questions x 3 runs x 3 arms, of which ui_default is the tested arm); 1,615 ChatGPT headphone answers (95 questions, 17 runs each) and 81 brand-design agency answers (27 questions, 3 runs each) from the holdouts of experiments 002, 003 and 005. The per-brand rows are in ai-shortlist-stability-mentions.csv (join on run_id).
- The B2B question text is public in experiment 009's release (claude-api-vs-claude-ai-prompts.csv; item_id joins). Headphone and agency question text is never published; those item ids and categories are per-release codes with no published mapping.
- Pre-registered: spec frozen at commit 6342963 (2026-10-03). Deviations 1 to 8 are listed in the spec's section 'Deviations from the frozen spec' (experiments/010-shortlist-stability/spec.md). Deviations 1 to 7 were made before any Stage 1 metric was computed; deviation 8 changes only the article's lead figure.
- Instruments: lexicon v3 sha256 6084f47ca1831474de9cb64d79425d522b75ac409d2b5080b24653ec9905cf5d; B2B best-for taxonomy sha256 b7fe060460d49e4ffdb6018d35c7feca74f461d6db06105ced6f3c6c5828e9f7 (both pinned in harness/instrument.py, frozen 2026-10-11 before any confirmatory metric).
- Collection. ChatGPT and Gemini: DataForSEO's LLM scraper (US location, English; web search forced on ChatGPT, which the Gemini endpoint does not accept; Gemini as served in the Gemini app). Claude: the Anthropic Batches API, Opus 5.5 at effort medium with no system prompt and the web search tool, user location Pittsburgh, Pennsylvania (experiment 009's opus55_plain arm). claude.ai: collected by hand in experiment 009 from one fresh Pro account. The headphone and agency answers are ChatGPT answers collected through DataForSEO in July and August 2026 by experiments 002, 003 and 005.
- Dates. A DataForSEO run date is the scraper's UTC timestamp, so answers submitted at 20:00 local time (US) carry the next day's date; a Claude API run date is its batch submission date. One ChatGPT task of wave 6 ran a day late and keeps its true date (deviation 2). ChatGPT reported gpt-5-6 in waves 1 to 5 and gpt-6 in waves 6 and 7.
- Brands. New collection: lexicon v3, experiment 009's lexicon v2.1 plus 40 curated brands or aliases, matched after removing citation links whose text is a domain (deviation 6); Audit D on 30 answers: precision 1.00, recall 1.00. claude_b2b keeps 009's frozen lexicon v2.1 and extraction; headphone and agency answers keep experiment 005's frozen lexicons.
- Statuses. The Spyglasses production recommendation judge, pinned (harness/judge_pin.json: sha256 34db50c5f32291eb8866e59b69c8df50f721af62c49e1971f437ee3152c43e78, Spyglasses commit 5e8f813, model gpt-5.6-luna, reasoning effort none, MENTION_ASSESSMENT_VERSION 2). Judge test-retest on a seeded 10% sample (Audit E): 96% category agreement, Cohen's kappa 0.89.
- Use-case segments. B2B: the 20 frozen taxonomies, built by the Spyglasses utility model (gpt-5.6-luna, reasoning effort medium) from 6,014 distinct best-for phrases, 7 or 8 segments plus 'general' per category. Headphones and agencies: the exploration taxonomies (sha256 505c5c2f0ae9b7dddfc8f2d00c8aaf8e6038c3296886d9a18e077a7015f275ff). Each phrase was classified twice (effort none); pass a is used in the analysis, and the two passes agree on 96% of distinct phrases (Audit G).
- Usable answers: 2,770 of 2,770. Under deviation 7 a refusal needs a refusal-shaped opening and no lexicon brand; 3 answers open like a refusal and then answer, and none is a refusal.
- Answer text, best-for phrases, judge evidence, caveat reason text, search queries and cited URLs are not released.
