# Dataset release checklist — 011-claude-code-fidelity

Complete for every dataset release. The technical gate
(`aeo_research.release_dataset`) enforces most of this mechanically; this
checklist is the human sign-off on the judgment calls it can't make. A copy
of the completed checklist lives in `experiments/<slug>/results/`.

## Content

- [x] Every column is a **derived feature or a public fact** (allow-listed
      with a description in the pipeline's release step).
      (011: 31 answer columns, each allow-listed with a description in
      `pipeline/05_release.py`. No prompt file is released: the 40 prompts are
      009's, already public as
      `/datasets/009-claude-model-fidelity/claude-api-vs-claude-ai-prompts.csv`.)
- [x] No customer prompt text, AI response text, or fan-out query text —
      including inside JSON blobs, "notes" columns, or example rows.
      (011: no answer text, answer hash, search-query text, full URLs, chat
      names, collector notes (only a 0/1 flag), account identifiers, or Max
      and Pro plan ledger readings or cost estimates.)
- [x] No customer, property, organization, or execution identifiers.
      Grouping keys are pseudonymized (`exec_0001`) per release.
      (011: no customer data was used. Brands ship as 475 `bNNNN` codes, and
      vendor, unmapped and brand-named domains as 2,836 `site_NNNN` codes,
      assigned in a seeded random order (seed 20261103); no mapping is
      published.)
- [x] Free-text columns marked `public_fact=True` were reviewed value-by-value
      (or verified to come from a public source like YouTube category names).
      (011: `model_version` holds `claude-opus-5-5` and `claude.ai`;
      `claude_code_version` holds `2.1.316`; `cited_domain_classes` holds the
      five 009 source-class labels plus `unclassified`. `cited_domains` and
      `evaluated_domains` hold `site_NNNN` codes and 544 registered domains in
      the clear, every one classed non-vendor by 009's frozen domain map and
      none matching a lexicon v1.2 name by the release step's rules. Those 544
      domains have not been read by a person. Tick only after a person reads
      the list and confirms none is a vendor's own site: 009's map was
      reviewed for 009's brands, and 011's answers name brands 009 never saw.
      2026-11-09: Jim Wrubel reviewed and approved shipping the 544 clear
      domains as is, under 009's policy. Many are blogs run by software
      companies; none is on the lexicon, so none links a brand code to a name.)
- [x] Every cell of the CSV and the datasheet passes the lexicon scan in
      `05_release.py` (each lexicon v1.2 alias, keep and drop rows, matched as
      the brand matcher matches it), and no clear domain's name equals, starts
      with or contains a lexicon name by the release step's rules. Repeated by
      `tests/test_exp011_release.py`.

## Phrasing

- [x] The datasheet and every mention of the dataset report row counts as
      "answers evaluated in this study".
      (011: 600 answers evaluated in this study.)
- [x] Nothing in the dataset, datasheet, or article states or implies totals
      for the Spyglasses database as a whole.
      (Re-checked against the article and the blog post on 2026-11-09: both
      count answers evaluated in this study and state no database totals.)
- [x] Spec §9: the article, the blog post and any setup guide say in plain
      words that this process is not suitable for tracking visibility when
      location matters, because the harness cannot control search location,
      and name the API (which can set a location) as the alternative. The
      datasheet carries a note. The article ("What we can and cannot claim")
      and the blog post ("What this means for your Claude tracking") both
      say it and name the Claude API. The setup guide is not written yet and
      must say it too.

## Re-identification review

- [x] Could any set of rows be tied back to a specific customer? Consider:
      per-pseudonym row groups, distinctive video/domain sets, timestamps,
      rare categories. If plausibly yes: coarsen (e.g. month-level dates),
      drop the column, or drop the rows.
      (011: no customer is involved; the accounts are a claude.ai Pro account
      and a Max plan owned by Spyglasses, and no account identifier ships.
      Brand names are withheld per 009's release instruction. Left for Jim:
      whether any combination of clear domains and codes lets a reader
      reconstruct a brand, for example a category where few vendors exist.
      2026-11-09: Jim Wrubel reviewed and approved the dataset as is.)

## Licensing

- [x] License line present in the datasheet (default CC BY 4.0).
- [x] Third-party data terms respected (e.g. YouTube metadata appears as
      derived scalars/aggregates, not bulk raw API payloads).

## Prerequisite

- [x] Audit D spot check signed (`results/audit_d_score.json`, Jim Wrubel,
      2026-11-09, against lexicon v1.2: precision 1.00, recall 1.00 on 30
      answers, against gates 0.95 / 0.90).
- [x] STOP 3 results review approved (spec §8 step 9: the release happens
      only if approved). Approved by Jim Wrubel, 2026-11-09.

## Sign-off

- Name: _____Jim Wrubel_________  Date: ___9 NOV 2026___________
- Release gate run: `pipeline/05_release.py` exit 0 on ___9 NOV 2026___________
