# aeo-experiments

Research experiments on the answer-engine-optimization (AEO) and AI-visibility field, published at [research.spyglasses.io](https://research.spyglasses.io). Supported by the [Spyglasses](https://spyglasses.io) AI Visibility and Analytics platform.

## What this repo is

A toolkit for designing, running, and publishing rigorous statistical studies of the Spyglasses citation dataset:

- **`src/aeo_research/`** — shared Python toolkit: branded/watermarked plotting, equivalence testing (TOST), cluster-robust models, dataset anonymization gate, YouTube URL parsing.
- **`experiments/<nnn-slug>/`** — one directory per study: pre-registered spec, extraction SQL, analysis pipeline, figures, and the anonymized public dataset.
- **`site/`** — the Astro static site deployed to research.spyglasses.io.
- **`templates/`** — pre-registration spec, article, blog-brief, and release-checklist templates.
- **`docs/`** — methodology, data policy, and workflow documentation.

## Quickstart

```bash
# Python toolkit (requires uv: https://docs.astral.sh/uv/)
uv sync
uv run pytest

# Site (requires pnpm)
cd site && pnpm install && pnpm dev
```

## The workflow

1. **Pose a research question** and draft a spec from `templates/experiment-spec.md`. Hypotheses, SESOI, and decision rules are fixed **before** looking at the data.
2. **Freeze the spec** — record the spec's commit hash in its header, then extract data (SQL saved to `experiments/<slug>/sql/`; raw extracts land in gitignored `data/raw/`).
3. **Run the pipeline** (`experiments/<slug>/pipeline/`), producing watermarked figures and results.
4. **Publish**: article in `site/src/content/articles/`, anonymized dataset through the release gate into `data/public/`, and a companion post on the [Spyglasses blog](https://spyglasses.io/blog).

## Rules that are never bent

See [`docs/data-policy.md`](docs/data-policy.md). In brief:

- Customer prompts, AI responses, and fan-out query text are **never published**.
- We never state or imply the total size of the Spyglasses citation database. Sample sizes are always "N citations evaluated (in this study)".
- Null claims require TOST equivalence bounds, not just non-significant p-values. Every article carries a "What we can and cannot claim" section.

## License

Code is licensed under the [MIT License](LICENSE). Published datasets carry their own license, stated in each dataset's datasheet (typically CC BY 4.0).
