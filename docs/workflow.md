# Workflow: from research question to published study

The runbook below is the exact sequence used for experiment 001. Steps 4–8
are what you repeat per experiment; 1–3 happen while designing it.

## 1. Question → spec

Copy `templates/experiment-spec.md` into `experiments/NNN-slug/spec.md`.
Fill in the claim boundaries (§1), audits (§2), schema with per-field
publishability (§3), hypotheses (§4), and the model + SESOI + decision rule
(§5). Simulate power with `aeo_research.synthesize` — the pipeline must
return NULL on `true_effect=0` and REAL on an above-SESOI effect
(`uv run pytest` covers this for the standard design).

## 2. Data-quality peeks (pre-freeze)

Count-only queries are allowed before freezing: class balance, null counts
per column, distinct-entity counts, feasibility rates. Joint distributions
and models are not. Save them as `experiments/NNN-slug/sql/counts.sql`; run
read-only via the Supabase MCP (`execute_sql`).

**Expect the counts to change the design** — experiment 001's original
question died here (rarer class ≈ 41) and the counts surfaced a far better
one. That is the audit working, not failing. Record what the counts showed
in a `§A Pre-freeze findings` section of the spec and redesign *before*
freezing. If a coverage gate fails (e.g. enrichment backfill incomplete),
fix the data first and re-run the count.

## 3. Freeze

Freezing = two commits, because a commit can't contain its own hash:

```bash
# edit spec.md: status: frozen + record the coverage-gate numbers
git add experiments/NNN-slug/spec.md
git commit -m "Freeze experiment NNN spec"
FROZEN=$(git rev-parse HEAD)
# edit spec.md header: Frozen commit: `$FROZEN`
git commit -am "Record frozen-spec commit hash" && git push
```

After freeze, §4/§5 changes are off-limits. Bug fixes in extraction/code are
allowed but must be logged in a `## Deviations from the frozen spec` section
(experiment 001 has an example: a Postgres regex fix).

## 4. Extract

`sql/extract.sql` is committed **before** it runs. Derive text features
(counts, flags, chapter times) in-query so raw content never leaves the DB.

- **Postgres regex gotcha:** word boundary is `\y` in Postgres ARE — `\b`
  means backspace and silently matches nothing.
- **Via Supabase MCP** (no psql/DB URL locally): run the query; the
  oversized result is persisted to a tool-results file shaped
  `{"result": "...<untrusted-data-…>[JSON array]</untrusted-data-…>"}`.
  Parse mechanically: `json.load(...)["result"]`, slice from the first `[`
  after the boundary tag to the last `]`, `json.loads`, then
  `DataFrame.to_csv("experiments/NNN-slug/data/raw/extract.csv")`.
- **Via psql** (if a read-only role is configured):
  `\copy (<query>) TO 'experiments/NNN-slug/data/raw/extract.csv' CSV HEADER`.

`data/raw/` and `data/interim/` are gitignored; never commit them.

## 5. Pipeline

```bash
P=experiments/NNN-slug/pipeline
uv run python $P/01_features.py    # parse/derive/collapse -> data/interim/
uv run python $P/02_audit.py       # spec §2 audits -> results/audit.txt
uv run python $P/03_model.py       # hypotheses + robustness -> results/
uv run python $P/04_figures.py     # watermarked SVG+PNG -> figures/
uv run python $P/05_release.py     # anonymized CSV + datasheet -> data/public/
```

Rules of the road:

- `01 --synthetic` dry-runs the whole chain without touching production data
  — do this once before the real run.
- `02_audit.py` output must match the spec's expectations before modelling.
- `03_model.py` **exits non-zero if the positive control fails** — that is
  the study stopping, not a bug to work around. A singular-matrix crash
  usually means a constant column (check `value_counts()` of the focal).
- Every figure goes through `save_figure` (watermark + caption baked in).

## 6. Review results

Read `results/model_summary.txt` end to end. Check: positive control PASS,
placebo null, TOST verdicts (INCONCLUSIVE is a reportable outcome, not a
failure), robustness rows consistent with the primary fits, and the
collinearity report. Surprising directions are fine — that's why the spec
pre-registered the claim boundaries.

## 7. Release gate (dataset)

`05_release.py` writes `data/public/<slug>.csv` + datasheet through the
technical gate, but **do not commit `data/public/` until a human completes
`templates/release-checklist.md`** (copy it into `results/` with sign-off).
Committing to this public repo IS publication.

## 8. Publish

1. Article: `site/src/content/articles/NNN-slug.mdx` from
   `templates/article.mdx` (mandatory "What we can and cannot claim").
2. `uv run python scripts/sync_site_assets.py NNN-slug` — copies figures +
   public data into `site/public/`.
3. `uv run python scripts/lint_article.py site/src/content/articles/NNN-slug.mdx`
4. Flip `draft: false`, `cd site && pnpm build`, review `pnpm preview`.
5. Push — Vercel deploys `main` to research.spyglasses.io automatically.
6. Companion blog post in the main spyglasses repo per
   `templates/blog-brief.md` (EN + DE, no date prefix in filenames).
