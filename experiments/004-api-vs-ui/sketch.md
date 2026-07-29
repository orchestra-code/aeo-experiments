# 004 — How far does the API path diverge from the UI path? (design sketch)

**Status:** sketch — NOT a spec, nothing frozen. Full spec after 003 ships
(its human-prompt re-run and lexicon state are inputs here).

## The question

Most prompt-tracking vendors measure ChatGPT through one of two instruments:
a scraped consumer UI (what DataForSEO's LLM scraper emulates) or the OpenAI
API. The 31-questions article (Q16/Q18) asks what either has to do with what
users actually see. We can't observe logged-in personalized sessions — nobody
outside OpenAI can, and that stays a stated claim boundary — but we CAN
measure the gap between the two instruments vendors actually use, and how
much of that gap a best-effort UI approximation closes.

## Arms (same prompts, same days, interleaved)

| Arm | Instrument | Notes |
|---|---|---|
| `ui` | DataForSEO ChatGPT LLM scraper (`force_web_search: true`) | the 002/003 instrument; logged-out UI proxy |
| `api_bare` | OpenAI Responses API + `web_search` tool, no custom system prompt | the naive vendor build |
| `api_matched` | same + the leaked ChatGPT system prompt (github.com/asgeirtj/system_prompts_leaks, OpenAI dir — has current gpt-5.5/5.6-era files incl. web-tool instructions) | best-effort UI approximation |

Model matching: pin the API model to what the scraper reports in `result.model`
(003 smoke showed `gpt-5-5`; map to the closest public API id and log the
mismatch — it is part of the measured construct).

## Design skeleton

- Prompts: ~50 mention-bearing headphone prompts from 003's hum panel
  (subset chosen by pre-registered rule, e.g. every prompt with ≥1 extracted
  brand in ≥4 of 5 waves of 003 — no cherry-picking).
- Runs: each prompt × each arm × 3 repeats, interleaved within the same
  session window so day effects hit all arms equally (~450 runs; API arms
  billed per token, still trivial).
- Extraction: 003's frozen lexicon + extraction code, unchanged. API arms
  need a citation adapter (Responses API returns `url_citation` annotations →
  map into the same normalized-URL/registered-domain features; fan-out
  visibility differs by instrument and may be reportable for `ui` only —
  a stated measurement asymmetry, not a bug).
- **The noise floor is the yardstick**: within-arm run-to-run Jaccard (the 3
  repeats) is the baseline; between-arm divergence only means something in
  units of it. Primary contrast per family (brands/domains):
  Δ(ui, api_bare) and Δ(ui, api_matched) vs the within-ui repeat level, TOST
  with the house 0.10 band; secondary: does api_matched close a measurable
  fraction of the api_bare gap (that difference is the "system prompt
  matters this much" number)?
- Panel-share layer as in 003 (H2-style MAD + rank tau across the ~50
  prompts): do the instruments rank the same brands?

## Framing constraints (from the plan review)

- This measures **instrument divergence**, never "the effect of THE system
  prompt": the leak's provenance is unverifiable, its vintage may not match
  the scraped surface, and the UI's retrieval backend is not reproducible
  through the API's `web_search` tool. `api_matched` is a best-effort bound,
  and that caveat leads the write-up.
- DataForSEO is itself a logged-out UI *proxy* — so the honest headline is
  "the two instruments vendors actually use disagree by X", which is exactly
  the article's Q19-adjacent cross-instrument question scaled down to one
  vendor's choices.
- Personalization/logged-in behavior stays out of scope and is said so
  prominently (Q16 is answered with "here's the part nobody can measure").

## Open questions for spec time

1. Add a Gemini pair (DataForSEO gemini scraper vs Gemini API) to test
   whether the divergence pattern generalizes across platforms?
2. Repeats: 3 per prompt-arm or 5? (Power sim on 003's observed within-prompt
   variance decides.)
3. Does the Responses API expose enough grounding metadata to include the
   fan-out family, or do we drop that layer for API arms?
4. Streaming vs non-streaming and `reasoning_effort` defaults — pin whatever
   the scraper's surface most plausibly uses, document the rest.
