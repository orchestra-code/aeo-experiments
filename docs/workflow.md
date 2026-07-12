# Workflow: from research question to published study

## 1. Question → spec

Copy `templates/experiment-spec.md` into `experiments/NNN-slug/spec.md`.
Fill in the claim boundaries (§1), audits (§2), schema with per-field
publishability (§3), hypotheses (§4), and the model + SESOI + decision rule
(§5). Simulate power with `aeo_research.synthesize` — the pipeline must
return NULL on `true_effect=0` and REAL on an above-SESOI effect.

## 2. Data-quality peeks (pre-freeze)

Count-only queries are allowed before freezing: class balance, null counts
per column, distinct-entity counts. Joint distributions and models are not.
Exploration runs read-only against the production replica via the Supabase
MCP (`execute_sql`) or the Spyglasses MCP.

## 3. Freeze → extract

Commit the spec, record the commit hash in its header, set status `frozen`.
Then write `experiments/NNN-slug/sql/extract.sql` (committed **before** it
runs) and extract:

- Small extracts (≲ a few thousand rows, scalar columns): Supabase MCP.
- Full extracts: read-only Postgres role + `psql -f sql/extract.sql --csv`
  (MCP responses truncate at scale). Derive text features in SQL where
  possible so raw content never leaves the database.

Raw extracts land in `data/raw/` (gitignored). Nothing under `data/raw/` or
`data/interim/` can be committed.

## 4. Pipeline

Numbered steps in `experiments/NNN-slug/pipeline/`:

- `01_features.py` — parse, derive, collapse to the unit of analysis → `data/interim/`
- `02_audit.py` — the spec's §2 audits, printed and saved to `results/`
- `03_model.py` — hypotheses + robustness suite → `results/`
- `04_figures.py` — every figure through `save_figure` (watermark + caption baked in)
- `05_release.py` — allow-listed columns through `release_dataset` → `data/public/`

Run with `uv run python experiments/NNN-slug/pipeline/01_features.py` etc.
Positive control fails → stop, per spec.

## 5. Publish

1. Article: `site/src/content/articles/NNN-slug.mdx` from `templates/article.mdx`.
2. `uv run python scripts/sync_site_assets.py` — copies figures + public data
   into `site/public/`.
3. `uv run python scripts/lint_article.py site/src/content/articles/NNN-slug.mdx`
4. Human sign-off on `templates/release-checklist.md` (copy into `results/`).
5. `cd site && pnpm build` — verify locally, then push (Vercel deploys main).
6. Companion blog post in the main spyglasses repo per `templates/blog-brief.md`.
