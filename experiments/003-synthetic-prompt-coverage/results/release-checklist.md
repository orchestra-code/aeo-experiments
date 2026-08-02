# Dataset release checklist — 003-synthetic-prompt-coverage

Complete for every dataset release. The technical gate
(`aeo_research.release_dataset`) enforces most of this mechanically; this
checklist is the human sign-off on the judgment calls it can't make. A copy
of the completed checklist lives in `experiments/<slug>/results/`.

## Content

- [ ] Every column is a **derived feature or a public fact** (allow-listed
      with a description in the pipeline's release step).
- [ ] No customer prompt text, AI response text, or fan-out query text —
      including inside JSON blobs, "notes" columns, or example rows.
- [ ] No customer, property, organization, or execution identifiers.
      Grouping keys are pseudonymized (`item_0001`) per release.
- [ ] Free-text columns marked `public_fact=True` were reviewed value-by-value
      (or verified to come from a public source like YouTube category names).
- [ ] Synthetic prompt text ships only under the data policy's "Synthetic
      study prompts" exemption: study-generated, non-customer brands
      (Bose/Soundcore are test anchors, not customers), styles publicly
      reproducible via the free spyglasses.io prompt generator; columns
      flagged `synthetic_study_text=True`; anchor-leak guard passed.

## Phrasing

- [ ] The datasheet and every mention of the dataset report row counts as
      "runs evaluated in this study".
- [ ] Nothing in the dataset, datasheet, or article states or implies totals
      for the Spyglasses database as a whole.

## Re-identification review

- [ ] Could any set of rows be tied back to a specific customer? Consider:
      per-pseudonym row groups, distinctive video/domain sets, timestamps,
      rare categories. If plausibly yes: coarsen (e.g. month-level dates),
      drop the column, or drop the rows.
      (003 note: human prompts are SparkToro's de-identified survey, not
      customer data; synthetic prompt text is withheld entirely.)

## Licensing

- [ ] License line present in the datasheet (default CC BY 4.0).
- [ ] Third-party data terms respected (e.g. YouTube metadata appears as
      derived scalars/aggregates, not bulk raw API payloads).

## Prerequisite

- [ ] Audit-D manual spot-check signed (`results/audit-d-signoff.md`,
      precision ≥ 0.95 / recall ≥ 0.90).

## Sign-off

- Name: ______________  Date: ______________
- Release gate run: `pipeline/05_release.py` exit 0 on __2 August 2026__
