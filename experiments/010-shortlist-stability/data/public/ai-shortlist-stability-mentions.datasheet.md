# AI shortlist stability, Stages 1 and 2: each lexicon brand in each answer

- **Study:** 010-shortlist-stability
- **Rows:** 17,965 (brand mentions evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-11-10

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

- One row per lexicon brand named in an answer evaluated in this study (17,965 rows from 3,250 answers; answers that name no lexicon brand have no rows). Join to ai-shortlist-stability-answers.csv on run_id.
- Brand codes. One code is one brand everywhere in this file. A brand that experiment 009's public dataset coded keeps 009's code, so the claude_b2b rows reproduce that file's brand_codes exactly. Every other brand in the frozen lexicons was coded from b0664 on, in a seeded order over the whole lexicon rather than in order of appearance. Headphone and agency brands have their own codes. No mapping to names is published. The Stage 2 update uses the same code table, so every code means the same brand as in the Stage 1 release, and adds no code: the table already covered every brand of the frozen lexicons, which stay frozen for Stage 2 (spec firewall rule 4), so a brand outside them is counted only in the answers file's n_brands_all. 28 codes appear for the first time in waves 8 to 11.
- Position is first-mention order among lexicon brands. Exact-position retention (spec: Pk) compares (brand_code, position) pairs; rank 1 is position 1.
- Status is the judge's label: top_choice (singled out as the pick; answers with more than two are demoted to one_of_many), one_of_many (recommended alongside others), generic_mention (named without endorsement), cautioned_against (steered away from for this asker), unclassified (named but not labeled). The shortlist is top_choice plus one_of_many. When the judge listed one brand more than once, the strongest label counts (cautioned_against, then top_choice, one_of_many, generic_mention).
- Use-case segments. B2B: the 20 frozen taxonomies, built by the Spyglasses utility model (gpt-5.6-luna, reasoning effort medium) from 6,014 distinct best-for phrases, 7 or 8 segments plus 'general' per category. Headphones and agencies: the exploration taxonomies (sha256 505c5c2f0ae9b7dddfc8f2d00c8aaf8e6038c3296886d9a18e077a7015f275ff). Each phrase was classified twice (effort none); pass a is used in the analysis, and the two passes agree on 96% of the 18,279 distinct phrases Stage 2 uses (Audit G). The 14,608 phrases already classified at Stage 1 keep their Stage 1 classifications; the 3,671 phrases first seen at Stage 2 were classified twice with the same frozen taxonomies (deviation 10), so no Stage 1 row's segment ids change.
- Pre-registered: spec frozen at commit 6342963 (2026-10-03). Deviations 1 to 10 are listed in the spec's section 'Deviations from the frozen spec' (experiments/010-shortlist-stability/spec.md). Deviations 1 to 7 were made before any Stage 1 metric was computed; deviation 8 changes only the first article's lead figure; deviation 9 records the Stage 2 collection (waves 8 to 11) and deviation 10 the Stage 2 implementation choices, recorded before any Stage 2 metric was computed.
- Instruments: lexicon v3 sha256 6084f47ca1831474de9cb64d79425d522b75ac409d2b5080b24653ec9905cf5d; B2B best-for taxonomy sha256 b7fe060460d49e4ffdb6018d35c7feca74f461d6db06105ced6f3c6c5828e9f7 (both pinned in harness/instrument.py, frozen 2026-10-11 before any confirmatory metric, and used unchanged for both stages).
- Collection. ChatGPT and Gemini: DataForSEO's LLM scraper (US location, English; web search forced on ChatGPT, which the Gemini endpoint does not accept; Gemini as served in the Gemini app). Claude: the Anthropic Batches API, Opus 5.5 at effort medium with no system prompt and the web search tool, user location Pittsburgh, Pennsylvania (experiment 009's opus55_plain arm). claude.ai: collected by hand in experiment 009 from one fresh Pro account. The headphone and agency answers are ChatGPT answers collected through DataForSEO in July and August 2026 by experiments 002, 003 and 005.
- Dates. A DataForSEO run date is the scraper's UTC timestamp, so answers submitted at 20:00 local time (US) carry the next day's date; a Claude API run date is its batch submission date. Tasks that failed and ran late keep their true dates: one ChatGPT task of wave 6 (deviation 2) and 7 Gemini tasks of wave 8, dated 2026-10-18 (deviation 9).
- Stage 2 run notes (deviation 9). All 40 questions were collected on every platform in every wave, with no empty answer and no refusal. Wave 9 started 1 to 2.5 hours late; no run date changed. ChatGPT reported gpt-5-6 in waves 1 to 5 and gpt-6 in waves 6 to 11, so ChatGPT comparisons across the weekly waves span that model change. Gemini reported 3.5 Flash-Lite on every answer but one, a wave 8 answer that reports 3.6 Flash. Every Claude API answer reports claude-opus-5-5.
- Brands. New collection: lexicon v3, experiment 009's lexicon v2.1 plus 40 curated brands or aliases, matched after removing citation links whose text is a domain (deviation 6); Audit D on 30 answers: precision 1.00, recall 1.00. claude_b2b keeps 009's frozen lexicon v2.1 and extraction; headphone and agency answers keep experiment 005's frozen lexicons.
- Statuses. The Spyglasses production recommendation judge, pinned (harness/judge_pin.json: sha256 34db50c5f32291eb8866e59b69c8df50f721af62c49e1971f437ee3152c43e78, Spyglasses commit 5e8f813, model gpt-5.6-luna, reasoning effort none, MENTION_ASSESSMENT_VERSION 2). Judge test-retest (Audit E) on seeded 10% samples: 96% category agreement, Cohen's kappa 0.89 at Stage 1; 96% agreement, kappa 0.89 on the 48 answers sampled from waves 8 to 11.
- Best-for phrases, judge evidence and caveat reason text are not released.

## Changelog

- 2026-10-11, Stage 1 release: new-collection waves 1 to 7 (2026-10-03 to 2026-10-09) and the holdouts; 2,770 answers (run_id r00001 to r02770), 14,726 brand mentions and 172 use-case segments.
- 2026-11-10, Stage 2 update: adds waves 8 to 11 of the new collection (2026-10-16, 2026-10-23, 2026-10-30 and 2026-11-06): 480 answers (run_id r02771 to r03250) and 3,239 brand mentions. The holdout rows and the segments file are unchanged. Every Stage 1 row is unchanged, byte for byte, and comes first in its file, with the same run_id, brand codes and segment ids.
- Stage 1 data only: keep the answers with wave 7 or less (no holdout row has a later wave; these are run_id r00001 to r02770) and the mentions whose run_id is among them. That gives back the Stage 1 CSV files exactly.
