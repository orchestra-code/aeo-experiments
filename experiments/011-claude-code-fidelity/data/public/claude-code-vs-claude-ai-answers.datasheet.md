# Claude Code vs claude.ai: brands named and domains cited, 40 B2B software prompts, 5 setups, 3 days

- **Study:** 011-claude-code-fidelity
- **Rows:** 600 (answers evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-11-09

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `item_id` | Study prompt id, b2b_01 to b2b_40; joins 009's prompts file |
| `category` | Software category the prompt is about (20 categories, 2 prompts each) |
| `intent` | shortlist (a buyer with a concrete company profile asks for options) or evaluate (a buyer describes a use case and asks how the top options compare) |
| `arm` | Setup that produced the answer; see the notes for the five arms |
| `surface` | claude.ai (by hand), local (Claude Code on a computer), scheduled (Claude Code scheduled task in the cloud) or api (Claude API) |
| `wave` | Collection day, 1 to 3 |
| `run_date` | Collection date of the wave. For sched_kit, the date the scheduled tasks were set to fire |
| `model_version` | Model string the run reported, or 'claude.ai' for the hand-collected arm |
| `claude_code_version` | Claude Code version of the pinned binary (local arms only; empty elsewhere) |
| `n_brands` | Count of distinct in-category brands the answer named (frozen lexicon v1.2) |
| `brand_codes` | Pipe-joined pseudonymous brand codes in first-mention order. One code is one brand everywhere in this file; the mapping to names is not published |
| `searched` | 1 if the answer ran at least one web search (for sched_kit, from the subagent's reported tool list) |
| `n_searches` | Count of web searches the answer ran. Empty for sched_kit, whose subagent searches are not in the transcript |
| `n_backend_searches` | Count of searches the search tool reported running behind the calls (local arms only) |
| `n_fetches` | Count of web page fetches (local arms and the API arm; empty where not observed) |
| `subagent_tool_uses` | Tool calls the subagent reported (sched_kit only) |
| `fetched` | 1 if the subagent fetched a web page (sched_kit only) |
| `copied_exactly` | 1 if the scheduled task printed the subagent's result unchanged (sched_kit only) |
| `instruction_exact` | 1 if the scheduled task gave the subagent the frozen instruction exactly (sched_kit only) |
| `cited_source` | Where cited URLs come from: citations (structured citation objects), answer_links (links written in the final text) or markdown_links |
| `n_cited_urls` | Count of cited URLs |
| `n_cited_domains` | Count of distinct registered domains cited |
| `cited_domains` | Pipe-joined registered domains cited, first-seen order. Domains 009's frozen map classes as publisher, review marketplace, analyst or other appear as domains (public web facts); vendor, unmapped and brand-named domains appear as site_NNNN codes |
| `cited_domain_classes` | Pipe-joined source class of each cited domain, aligned with cited_domains (009's frozen domain map v1; 'unclassified' when the map does not cover it) |
| `n_evaluated_urls` | Count of search-result URLs the answer's searches returned. Empty for sched_kit (not observed) |
| `n_evaluated_domains` | Count of distinct registered domains in those search results. Empty for sched_kit |
| `evaluated_domains` | Pipe-joined registered domains in the search results, same coding as cited_domains. Empty for sched_kit |
| `chars` | Length of the scored text in characters |
| `coding_flag` | 1 if the pattern check for coding behavior fired (Audit A; every flagged case was read and cleared) |
| `clarifying_questions` | 1 if claude.ai asked clarifying questions first |
| `collector_note` | 1 if the hand collector left a note on the chat; the note itself is not released |

## Notes

- One row per answer evaluated in this study: 40 synthetic B2B software prompts x 5 setups (arms) x 3 waves (wave 1: 2026-11-03, wave 2: 2026-11-05, wave 3: 2026-11-09).
- The prompts are the 40 synthetic prompts of experiment 009, already published as /datasets/009-claude-model-fidelity/claude-api-vs-claude-ai-prompts.csv. They are not repeated here; item_id joins the two files.
- The arms are: `ui_default`: claude.ai, Opus 5.5, Medium reasoning (the default), typed by hand on one Pro account (the reference); `cc_stock_full`: Claude Code run locally with claude -p on a Max plan, Opus 5.5, effort medium, Claude Code's own system prompt, web search and web fetch; `sched_kit`: a scheduled Claude Code task in the cloud on the same Max plan, which starts one new subagent per prompt with a fixed instruction to research the question with web search and answer it; `cc_none_search`: Claude Code run locally, the system prompt replaced by a 136-character one, web search only; `opus55_plain`: Claude API (Batches), Opus 5.5, effort medium, no system prompt, web search with the user location set to Pittsburgh, Pennsylvania (replicates 009).
- Brands are the in-category brands an answer names, matched with the frozen lexicon v1.2 (Audit D on 30 answers: precision 1.00, recall 1.00). They ship as bNNNN codes (475 codes). Vendor sites, domains 009's frozen source-class map does not cover, and domains whose name matches a lexicon name ship as site_NNNN codes (2836 codes). Codes are per release and no mapping is published.
- Cited URLs are structured citation objects for claude.ai and the API, and the links written in the final text for the three Claude Code arms (cited_source), so part of any difference in cited domains may come from the measure.
- sched_kit runs each prompt in a subagent whose searches are not in the transcript the study can pull, so its search count and evaluated URLs are empty (unknown), not zero.
- The Claude Code arms and claude.ai cannot be told where the user is, so this data says nothing about location-specific answers. The API arm set Pittsburgh, Pennsylvania as the user location.
- Mean estimated cost per call for opus55_plain (token and search counts at list prices, batch pricing; not reconciled with billing): USD 0.070. The Claude Code and claude.ai arms run on subscription plans, whose usage is not released.
- Answer text, answer hashes, search-query text, full URLs, chat names, collector notes and account identifiers are not released.
