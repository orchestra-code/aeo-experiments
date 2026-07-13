# Dataset release checklist — 001-youtube-citation-type

Completed copy of `templates/release-checklist.md` for the record.

## Content

- [x] Every column is a **derived feature or a public fact** (allow-listed
      with a description in `pipeline/05_release.py`).
- [x] No customer prompt text, AI response text, or fan-out query text
      (enforced by the release gate: forbidden-name, cuid, and free-text scans).
- [x] No customer, property, organization, or execution identifiers.
      Grouping keys are pseudonymized (`exec_0001`) per release.
- [x] Free-text columns marked `public_fact=True` (`video_id`, `video_category`)
      come from public YouTube data.

## Phrasing

- [x] The datasheet reports row counts as "citations evaluated in this study".
- [x] Nothing in the dataset, datasheet, or article states or implies totals
      for the Spyglasses database as a whole.

## Re-identification review

- [x] Reviewed. Rows carry no customer identifier; grouping keys are
      pseudonymized; dates are coarsened to month. Video/category values are
      public YouTube facts, not customer-linked.

## Licensing

- [x] License line present in the datasheet (CC BY 4.0).
- [x] Third-party data terms respected — YouTube data appears as derived
      scalars only, not bulk raw API payloads.

## Sign-off

- Name: Jim Wrubel   Date: 12 July 2026
- Release gate run: `pipeline/05_release.py` exit 0 on 12 July 2026

Note: the release step was re-run on 2026-07-13 for a datasheet-title
correction only (the title still carried the pre-pivot study name). The
released rows and columns are identical to the reviewed dataset.
