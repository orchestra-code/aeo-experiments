# Dataset release checklist — <experiment slug>

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
      Grouping keys are pseudonymized (`exec_0001`) per release.
- [ ] Free-text columns marked `public_fact=True` were reviewed value-by-value
      (or verified to come from a public source like YouTube category names).

## Phrasing

- [ ] The datasheet and every mention of the dataset report row counts as
      "citations evaluated in this study".
- [ ] Nothing in the dataset, datasheet, or article states or implies totals
      for the Spyglasses database as a whole.

## Re-identification review

- [ ] Could any set of rows be tied back to a specific customer? Consider:
      per-pseudonym row groups, distinctive video/domain sets, timestamps,
      rare categories. If plausibly yes: coarsen (e.g. month-level dates),
      drop the column, or drop the rows.

## Licensing

- [ ] License line present in the datasheet (default CC BY 4.0).
- [ ] Third-party data terms respected (e.g. YouTube metadata appears as
      derived scalars/aggregates, not bulk raw API payloads).

## Sign-off

- Name: ___Jim Wrubel_______  Date: __12 Jult 2026_____
- Release gate run: `pipeline/05_release.py` exit 0 on ___12 July 2026______
