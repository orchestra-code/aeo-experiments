# 003 harness — synthetic prompt panel generation

Three synthetic arms, generated ONCE and frozen before the spec freeze
(generation is nondeterministic; the frozen artifact is the JSON output in
`../data/raw/generator/`, which records model ids, commit hashes, and the full
prompts). Prompt text never leaves `data/raw` (see data policy).

| Arm | Generator | Anchor | Script |
|---|---|---|---|
| `spy_a` | Spyglasses `DiscoveryQueryService.generateExpandedPrompts` (production code path: crawl → BrandSnapshot → 5 discovery frameworks) | incumbent headphone brand (bose.com) | `generate_spyglasses.ts` |
| `spy_b` | same | mid-tier headphone brand (soundcore.com) | `generate_spyglasses.ts` |
| `neu` | plain `claude-haiku-4-5` call, survey scenario only, no brand context | — | `generate_neutral.py` |

Both generators use `claude-haiku-4-5`, so SPY-vs-NEU isolates the prompting
strategy, not the model. `brand_prompts` is excluded from the SPY arms (must
name the brand; excluded from share of voice in the product too).

## Running

SPY arms (from the spyglasses checkout; react-server condition avoids the
`server-only` import guard — same pattern as `create:user`):

```bash
cd /Users/jcw/projects/spyglasses
NODE_OPTIONS=--conditions=react-server pnpm --filter @repo/scripts exec tsx \
  /Users/jcw/projects/aeo-experiments/experiments/003-synthetic-prompt-coverage/harness/generate_spyglasses.ts \
  --domain bose.com --arm spy_a
NODE_OPTIONS=--conditions=react-server pnpm --filter @repo/scripts exec tsx \
  /Users/jcw/projects/aeo-experiments/experiments/003-synthetic-prompt-coverage/harness/generate_spyglasses.ts \
  --domain soundcore.com --arm spy_b
```

NEU arm (from this repo's root):

```bash
uv run python experiments/003-synthetic-prompt-coverage/harness/generate_neutral.py \
  --env-file /Users/jcw/projects/spyglasses/.env.local
```

Env: `ANTHROPIC_API_KEY` (both), `OPENAI_API_KEY` (brand snapshot),
`DATABASE_URL` (satisfies the Prisma import chain only — nothing is queried
or written; the harness makes zero DB calls).

## Reproducibility record

Each `<arm>.json` stores: spyglasses commit hash (SPY arms), generator model
id, crawled page URLs, the full BrandSnapshot, frameworks + per-framework cap,
and every generated prompt with its queryType/framework. Reruns will produce
different prompts (no seed support in the APIs) — which is why the panel is
frozen as data, not as code.
