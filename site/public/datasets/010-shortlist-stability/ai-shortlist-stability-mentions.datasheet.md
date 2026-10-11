# AI shortlist stability, Stage 1: each lexicon brand in each answer

- **Study:** 010-shortlist-stability
- **Rows:** 14,726 (brand mentions evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-10-11

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `run_id` | Answer id; joins the answers file |
| `brand_code` | Pseudonymous brand code. One code is one brand everywhere in this file; codes shared with experiment 009's public dataset mean the same brand there. No mapping to names is published |
| `position` | First-mention order of the brand in the answer, 1 = named first |
| `status` | The judge's label for the brand in this answer: top_choice, one_of_many, generic_mention, cautioned_against, or unclassified (named but not labeled by the judge) |
| `n_best_for` | Count of best-for phrases the judge gave the brand (phrases are not released) |
| `segment_ids` | Recommended brands only: pipe-joined distinct use-case segments of the brand's best-for phrases (classifier pass a, used in the analysis), first-seen order. B2B ids join the segments file on category and segment_id; headphone and agency labels are not released. Phrases outside every segment are left out |
| `segment_ids_pass_b` | As segment_ids, from the second classifier pass (Audit G) |
| `n_caveats` | Count of caveats the judge attached to the brand |
| `caveat_types` | Pipe-joined reason type of each caveat, in the judge's order (price, reliability_quality, missing_capability, complexity, company_size_fit, integration, reputation, support_service, security_compliance, other). The reason text is not released |

## Notes

- One row per lexicon brand named in an answer evaluated in this study (14,726 rows from 2,770 answers; answers that name no lexicon brand have no rows). Join to ai-shortlist-stability-answers.csv on run_id.
- Brand codes. One code is one brand everywhere in this file. A brand that experiment 009's public dataset coded keeps 009's code, so the claude_b2b rows reproduce that file's brand_codes exactly. Every other brand in the frozen lexicons was coded from b0664 on, in a seeded order over the whole lexicon rather than in order of appearance. Headphone and agency brands have their own codes. No mapping to names is published.
- Position is first-mention order among lexicon brands. Exact-position retention (spec: Pk) compares (brand_code, position) pairs; rank 1 is position 1.
- Status is the judge's label: top_choice (singled out as the pick; answers with more than two are demoted to one_of_many), one_of_many (recommended alongside others), generic_mention (named without endorsement), cautioned_against (steered away from for this asker), unclassified (named but not labeled). The shortlist is top_choice plus one_of_many. When the judge listed one brand more than once, the strongest label counts (cautioned_against, then top_choice, one_of_many, generic_mention).
- Use-case segments. B2B: the 20 frozen taxonomies, built by the Spyglasses utility model (gpt-5.6-luna, reasoning effort medium) from 6,014 distinct best-for phrases, 7 or 8 segments plus 'general' per category. Headphones and agencies: the exploration taxonomies (sha256 505c5c2f0ae9b7dddfc8f2d00c8aaf8e6038c3296886d9a18e077a7015f275ff). Each phrase was classified twice (effort none); pass a is used in the analysis, and the two passes agree on 96% of distinct phrases (Audit G).
- Pre-registered: spec frozen at commit 6342963 (2026-10-03). Deviations 1 to 8 are listed in the spec's section 'Deviations from the frozen spec' (experiments/010-shortlist-stability/spec.md). Deviations 1 to 7 were made before any Stage 1 metric was computed; deviation 8 changes only the article's lead figure.
- Instruments: lexicon v3 sha256 6084f47ca1831474de9cb64d79425d522b75ac409d2b5080b24653ec9905cf5d; B2B best-for taxonomy sha256 b7fe060460d49e4ffdb6018d35c7feca74f461d6db06105ced6f3c6c5828e9f7 (both pinned in harness/instrument.py, frozen 2026-10-11 before any confirmatory metric).
- Collection. ChatGPT and Gemini: DataForSEO's LLM scraper (US location, English; web search forced on ChatGPT, which the Gemini endpoint does not accept; Gemini as served in the Gemini app). Claude: the Anthropic Batches API, Opus 5.5 at effort medium with no system prompt and the web search tool, user location Pittsburgh, Pennsylvania (experiment 009's opus55_plain arm). claude.ai: collected by hand in experiment 009 from one fresh Pro account. The headphone and agency answers are ChatGPT answers collected through DataForSEO in July and August 2026 by experiments 002, 003 and 005.
- Dates. A DataForSEO run date is the scraper's UTC timestamp, so answers submitted at 20:00 local time (US) carry the next day's date; a Claude API run date is its batch submission date. One ChatGPT task of wave 6 ran a day late and keeps its true date (deviation 2). ChatGPT reported gpt-5-6 in waves 1 to 5 and gpt-6 in waves 6 and 7.
- Brands. New collection: lexicon v3, experiment 009's lexicon v2.1 plus 40 curated brands or aliases, matched after removing citation links whose text is a domain (deviation 6); Audit D on 30 answers: precision 1.00, recall 1.00. claude_b2b keeps 009's frozen lexicon v2.1 and extraction; headphone and agency answers keep experiment 005's frozen lexicons.
- Statuses. The Spyglasses production recommendation judge, pinned (harness/judge_pin.json: sha256 34db50c5f32291eb8866e59b69c8df50f721af62c49e1971f437ee3152c43e78, Spyglasses commit 5e8f813, model gpt-5.6-luna, reasoning effort none, MENTION_ASSESSMENT_VERSION 2). Judge test-retest on a seeded 10% sample (Audit E): 96% category agreement, Cohen's kappa 0.89.
- Best-for phrases, judge evidence and caveat reason text are not released.
