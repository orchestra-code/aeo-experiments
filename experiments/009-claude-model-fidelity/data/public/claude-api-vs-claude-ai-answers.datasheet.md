# Claude API vs claude.ai: brands named and domains cited, 40 B2B software prompts, 9 configurations, 3 days

- **Study:** 009-claude-model-fidelity
- **Rows:** 1,080 (answers evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-10-02

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `item_id` | Study prompt id, b2b_01 to b2b_40; joins the prompts file |
| `category` | Software category the prompt is about (20 categories, 2 prompts each) |
| `intent` | shortlist (a buyer with a concrete company profile asks for options) or evaluate (a buyer describes a use case and asks how the top options compare) |
| `arm` | Configuration that produced the answer; see the datasheet notes for the nine arms |
| `surface` | claude.ai (collected by hand) or api (Anthropic Batches API) |
| `wave` | Collection day, 1 to 3 (2026-09-27, 2026-09-29, 2026-10-01) |
| `run_date` | Collection date of the wave |
| `model_version` | Model string the API reported, or 'claude.ai' for the hand-collected arms |
| `n_brands` | Count of distinct in-category brands the answer named (frozen lexicon v2.1) |
| `brand_codes` | Pipe-joined pseudonymous brand codes in first-mention order. One code is one brand everywhere in this file; the mapping to names is not published |
| `n_searches` | Count of web searches the answer ran |
| `no_search` | 1 if the answer ran no web search |
| `n_cited_urls` | Count of cited URLs (structured citations) |
| `n_cited_domains` | Count of distinct registered domains cited |
| `cited_domains` | Pipe-joined registered domains cited, first-seen order. Publisher, review-marketplace, analyst and other sources appear as domains (public web facts); vendor sites appear as site_NNNN codes |
| `cited_domain_classes` | Pipe-joined source class of each cited domain, aligned with cited_domains (frozen domain map v1) |
| `n_evaluated_urls` | Count of search-result URLs the answer's searches returned |
| `n_evaluated_domains` | Count of distinct registered domains in those search results |
| `evaluated_domains` | Pipe-joined registered domains in the search results. Domains the frozen map classes as non-vendor appear as domains; vendor and unclassified domains appear as site_NNNN codes (same code space as cited_domains) |
| `chars` | Length of the scored answer text in characters |
| `clarifying_questions` | 1 if claude.ai asked clarifying questions first; only its first reply is scored (spec deviation 1) |
| `collector_note` | 1 if the hand collector left a note on the chat (the R7 robustness check drops these); the note itself is not released |
| `other_tools` | 1 if the claude.ai chat used a tool other than web search |

## Notes

- One row per answer evaluated in this study: 40 synthetic B2B software prompts x 9 configurations (arms) x 3 waves. The prompt text is in claude-api-vs-claude-ai-prompts.csv; item_id joins the two files.
- The arms are: `ui_default`: claude.ai, Opus 5.5, Medium reasoning (the default); the reference; `ui_think`: claude.ai, Opus 5.5, High reasoning; `opus55_plain`: API, Opus 5.5, effort medium, no system prompt; `opus55_leak`: API, Opus 5.5, effort medium, trimmed leaked claude.ai system prompt; `sonnet5_plain`: API, Sonnet 5, adaptive thinking, no system prompt; `sonnet5_leak_think`: API, Sonnet 5, adaptive thinking, trimmed leaked prompt; `sonnet5_leak_low`: API, Sonnet 5, adaptive thinking at effort low, trimmed leaked prompt; `sonnet5_prod`: API, Sonnet 5, Spyglasses' production request at the time of the study; `haiku45_leak`: API, Haiku 4.5, no thinking, trimmed leaked prompt.
- The claude.ai arms come from one fresh Pro account with memory, chat search, preferences, styles, projects and connectors off, signed in from Pittsburgh, Pennsylvania. API arms used the web_search tool with the same city as user_location (except sonnet5_prod, which reproduces the production request: no location, at most 5 searches).
- The leaked system prompt is a publicly circulated copy of claude.ai's system prompt from the open-source repository asgeirtj/system_prompts_leaks, whose provenance and accuracy cannot be verified, trimmed by the rules in harness/leak_trim_rules.md. The trimmed version used in the study is released as claude-opus-5.5-trimmed-system-prompt.md (spec deviation 11). The production prompt's text is not released.
- Brands are the in-category brands an answer names, matched with the frozen lexicon v2.1 (Audit D: precision 1.00, recall 0.99 on 30 answers). They ship as bNNNN codes. Vendor sites and domains the frozen source-class map does not cover ship as site_NNNN codes. Codes are per release and no mapping is published.
- For the 9 claude.ai chats that asked clarifying questions, only the first reply is scored (spec deviation 1).
- Mean measured cost per API call, batch pricing, 1-hour cache writes included (USD): haiku45_leak 0.047, opus55_leak 0.128, opus55_plain 0.071, sonnet5_leak_low 0.047, sonnet5_leak_think 0.078, sonnet5_plain 0.065, sonnet5_prod 0.081. claude.ai reports subscription usage only as a share of plan limits, so there is no per-chat cost for its arms.
- Answer text, search-query text, full URLs, collector notes and per-answer cost are not released.
