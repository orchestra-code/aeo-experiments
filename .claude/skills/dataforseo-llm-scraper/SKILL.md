---
name: dataforseo-llm-scraper
description: >
  Run prompts against ChatGPT (or Gemini) via DataForSEO's AI-Optimization LLM
  scraper and collect answer markdown, fan-out/grounding queries, and cited
  sources. Use whenever an experiment needs real LLM responses at scale —
  "run these prompts against ChatGPT", "submit a wave", "collect DataForSEO
  tasks", "LLM scraper". Uses the cheap async task API with a local ledger,
  never the live endpoint.
---

# DataForSEO LLM scraper (async, ledger-driven)

Toolkit: `src/aeo_research/dataforseo.py` (client + `Ledger`) and
`scripts/llm_scraper.py` (CLI). Everything is keyed off an append-only JSONL
ledger under the experiment's gitignored `data/raw/`.

## Hard rules

1. **Never call `tasks_ready`.** It is account-wide and the Spyglasses
   production poller consumes it every 5 minutes. We poll
   `task_get/advanced/{id}` with our own stored task ids — race-free in both
   directions. (Production matches ready ids against its own stored task ids,
   so our tasks never enter customer data either.)
2. **Never commit** the ledger, raw responses, or prompt CSVs — they live in
   `experiments/<slug>/data/raw/` which is gitignored repo-wide.
3. **Always smoke-test first**: 1–2 throwaway prompts with `--limit 2
   --tag <prefix>-smoke` before any real wave, and verify the response JSON has
   `.markdown`, `.fan_out_queries`, `.sources`, `.model`.
4. Tag every study distinctly: `aeo-exp<NNN>-w<wave>`.

## Auth

`DATAFORSEO_API_KEY` = base64 of `login:password`, sent as
`Authorization: Basic <key>`. It lives in the **spyglasses checkout's**
`.env.local` — pass `--env-file /path/to/spyglasses/.env.local` (same pattern
as the brand-og-image skill). Never write it into this repo.

## Platforms

`submit --platform {chatgpt,gemini}` (default `chatgpt`) picks the scraper
endpoint. The platform is stamped into each ledger record and `collect` polls
each task against the platform it was submitted to, so one ledger can mix
platforms. Pre-platform ledgers collect as `chatgpt`.

**Gemini caveat (CONFIRMED 2026-09-01):** the Gemini endpoint rejects the
`force_web_search` field's presence (40501) — the client omits it for Gemini —
and returns no fan-out surface at all.

**ChatGPT search-phase regression (observed 2026-09-01):** `fan_out_queries`,
`search_results`, and `model` came back EMPTY/null on every task in exp 008's
pilot (brand AND exp-005-style category prompts), while `sources` stayed
populated. Exp 005 (2026-08-05) had 100% fan-out coverage from the same
payload shape. Until DataForSEO restores search-phase extraction, this
scraper cannot support fan-out/grounding-query studies — smoke-test
`.fan_out_queries` before designing any study around it.

## Cost model (ChatGPT scraper, per task)

- Priority queue (`--priority 2`, default): ~$0.0024, results in ~5 min.
- Standard queue (`--priority 1`): half cost, ~45 min.
- Results stay retrievable via `task_get` for ~30 days. Collect same-day.
- The CLI refuses to grow a ledger past `--max-total-tasks` (default 1500)
  without `--force` — set it deliberately per study.

## Workflow

Prompts CSV needs columns `item_id, intent, text` (one row per prompt).

```bash
# 1. submit a wave (idempotent: re-run safely after partial failures;
#    failed tasks are automatically eligible for resubmission)
uv run python scripts/llm_scraper.py submit \
    --prompts experiments/<slug>/data/raw/prompts.csv \
    --intent headphones --wave 1 \
    --ledger experiments/<slug>/data/raw/ledger.jsonl \
    --tag-prefix aeo-exp002 \
    --env-file ../spyglasses/.env.local

# 2. ~5 minutes later: collect (writes data/raw/responses/w<N>/<task_id>.json;
#    --wait 60 keeps sweeping until nothing is pending)
uv run python scripts/llm_scraper.py collect \
    --ledger experiments/<slug>/data/raw/ledger.jsonl \
    --out-dir experiments/<slug>/data/raw/responses \
    --env-file ../spyglasses/.env.local --wait 60

# 3. verify
uv run python scripts/llm_scraper.py status \
    --ledger experiments/<slug>/data/raw/ledger.jsonl
```

Re-run `submit` + `collect` for each subsequent wave (`--wave 2` …). A
multi-day design = one wave per day, manually invoked.

## What comes back per task (`responses/w<N>/<task_id>.json`)

`result[0]` of `task_get/advanced`: `.markdown` (the answer),
`.fan_out_queries` (string array of grounding searches — requires
`force_web_search: true`, which `TaskSpec` sets by default), `.sources[]`
(`url`, `title`, `snippet`, `domain`, `source_name`, `publication_date`),
`.search_results[]`, `.model` (record it — model drift across days is real),
`.check_url`.

Ledger records carry `keyword_sha256`, never raw prompt text, so ledger frames
are safe to print in analysis notebooks. Task states: `submitted` →
`collected` | `failed` (4xxxx terminal codes, or stale >48h). In-queue codes
40601/40602 stay `submitted`.
