# Dataset release checklist — 005-subintent-matched-panels

Complete for every dataset release. The technical gate
(`aeo_research.release_dataset`) enforces most of this mechanically; this
checklist is the human sign-off on the judgment calls it can't make. A copy
of the completed checklist lives in `experiments/<slug>/results/`.

Two files are released, joined by `item_code`:
`subintent-matched-panels-chatgpt.csv` (1,230 runs, derived features only)
and `subintent-matched-panels-prompts.csv` (95 synthetic prompts: 55 mat +
40 neu2, verbatim text).

## Content

- [ X ] Every column is a **derived feature or a public fact** (allow-listed
      with a description in the pipeline's release step).
- [ X ] No customer prompt text, AI response text, or fan-out query text —
      including inside JSON blobs, "notes" columns, or example rows.
      (005: human + coffee prompt text is SparkToro's and is NOT in either
      file — verified, the prompts CSV contains mat/neu2 only, 55 + 40.)
- [ X ] No customer, property, organization, or execution identifiers.
      Grouping keys are pseudonymized (`item_0001`) per release.
- [ X ] Free-text columns marked `public_fact=True` were reviewed value-by-value
      (or verified to come from a public source like YouTube category names).
- [ X ] Synthetic prompt text ships only under the data policy's "Synthetic
      study prompts" exemption: study-generated, **no brand anchors at all**
      in this study (neither panel was anchored), styles publicly
      reproducible via the free spyglasses.io prompt generator; columns
      flagged `synthetic_study_text=True`; brand-leak scan passed
      (204 lexicon aliases × 95 released prompts, zero hits).

## Phrasing

- [ X ] The datasheet and every mention of the dataset report row counts as
      "runs evaluated in this study".
- [ X ] Nothing in the dataset, datasheet, or article states or implies totals
      for the Spyglasses database as a whole.

## Re-identification review

- [ X ] Could any set of rows be tied back to a specific customer? Consider:
      per-pseudonym row groups, distinctive domain sets, timestamps, rare
      categories. If plausibly yes: coarsen, drop the column, or drop rows.
      (005 note: human prompts are SparkToro's de-identified survey, not
      customer data, and their text is withheld regardless; synthetic prompt
      text is study-generated with no brand anchors and no identifiers.)

## Licensing

- [ X ] License line present in the datasheet (default CC BY 4.0).
- [ X ] Third-party data terms respected.

## Prerequisite

- [ X ] Audit-D manual spot-check signed (`results/audit-d-signoff.md`,
      precision ≥ 0.95 / recall ≥ 0.90).

## Sign-off

- Name: _______James Wrubel__________________  Date: _____6 AUG 2026____________________
- Release gate run: `pipeline/05_release.py` exit 0 on __6 August 2026__
