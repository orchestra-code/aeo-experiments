# Does ChatGPT know a brand's domain? 48 brands, 10 daily waves

- **Study:** 008-brand-domain-knowledge
- **Rows:** 1,152 (calls evaluated in this study)
- **License:** CC BY 4.0
- **Released:** 2026-09-11

This dataset contains derived features only. It does not include any
customer prompts, AI responses, fan-out queries, or customer
identifiers, and it says nothing about the overall size of the
Spyglasses database.

## Columns

| Column | Description |
|---|---|
| `brand` | Study panel brand the call asked about (48 non-customer brands) |
| `tier` | Panel tier: A guessable domain (brandname.com), B non-obvious domain, C migrated domain, D obscure brand |
| `template` | Which of the two frozen prompt shapes ran: 'brand-identity' (what is this brand, what does it offer, how is it priced) or 'comparison' (how does it compare to its main competitors). The wording itself is not released. |
| `wave` | Daily collection wave, 1-10 |
| `replicate` | Same-day replicate slot: 0 every wave, 1 and 2 are the wave-1 afternoon and evening repeats |
| `run_date` | Collection date (UTC) |
| `model_version` | Model identifier the API reported |
| `emitted_site_search` | 1 if the call ran at least one site: search |
| `emitted_brand_site_search` | 1 if at least one site: search was about the asked brand's own domain rather than a competitor's or a reference site — the analysis set for every rate in the study |
| `n_site_queries` | Count of site: searches the call ran |
| `first_site_domain` | Registered domain of the first BRAND-ATTRIBUTABLE site: search — the model's first commitment to a domain FOR THIS BRAND, empty when the call only searched third-party sites (public web fact, study brands only) |
| `first_search_domain_any` | Registered domain of the raw first site: search of any kind, competitor and reference sites included — lets readers reconstruct the unconditioned first-search reading (public web fact) |
| `first_site_label` | correct (the brand's canonical domain), stale (a frozen old domain of the brand), wrong, or none (the call made no brand-attributable site: search) |
| `first_site_error_kind` | For a non-correct first domain: stale_old_domain, morphological_guess, name_bearing_other (another domain carrying the brand's name), third_party (a competitor or reference site — expected on comparison prompts), or nonexistent (did not resolve at the audit's check date) |
| `first_site_attribution` | For a first commitment on a domain carrying the brand's name: own_property (the brand's own site — a product, regional, developer or investor domain) or other_company (a different company sharing the name), or unreviewed. A HUMAN attribution recorded in this study's Audit D sign-off (results/audit-d-signoff.md, signed 2026-09-11), not inferred by code; it labels a robustness layer and does not change first_site_label. Empty for every other case. |
| `any_stale` | 1 if any site: search in the call used a frozen old domain |
| `any_guess` | 1 if any site: search used a morphological-guess domain |
| `any_name_bearing` | 1 if any site: search used another domain carrying the brand's name |
| `n_site_third_party` | Count of site: searches aimed at a domain that does not carry the brand's name (competitor and reference sites) |
| `n_consulted_domains` | Count of distinct registered domains the call's searches returned (the domain list itself is derived-only and not released) |
| `n_cited_domains` | Count of distinct registered domains the answer cited (the domain list itself is derived-only and not released) |
| `n_web_search_calls` | Count of web_search_call items in the response |

## Notes

- One row per call evaluated in this study: 48 brands x 2 prompt templates x 10 daily waves, plus two spaced same-day replicates on wave 1.
- Collected through the direct OpenAI Responses API with the web_search tool (not a scraper and not the consumer UI), so the observable is the model's own search action, including the site: operator it types.
- The outcome is consultation-conditional: it exists only when the model elected to consult a site directly. Read every rate as 'when the model consulted a site...', never as 'the model believes...'.
- The primary outcome is the first BRAND-ATTRIBUTABLE site: search. A comparison prompt often opens on a competitor's site by design; that is not a claim about the asked brand's domain, so such calls are not counted as wrong (first_site_label = 'none' when a call made no brand-attributable search). first_search_domain_any preserves the raw first search for anyone who wants the other reading.
- Brands are a study-generated panel of non-customer companies; domains are public web facts. No customer prompts, responses, fan-out text or identifiers appear here.
- Search-query text (including the full site: query), answer text, and the lists of consulted and cited domains are derived-only and are not released; their counts are.
- A domain carrying the brand's name may be the brand's own property or a different company's; that call is a human judgment, signed and dated in the study's Audit D sign-off and carried here as first_site_attribution. It labels a robustness layer — the primary outcome treats a name-bearing domain as not canonical either way.
- Zero counts in a cell are upper bounds, not impossibility: the study reports rule-of-three (3/n) bounds for every empty cell.
