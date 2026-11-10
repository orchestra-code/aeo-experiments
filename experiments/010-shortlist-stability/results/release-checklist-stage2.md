# Dataset release checklist — 010-shortlist-stability

Complete for every dataset release. The technical gate
(`aeo_research.release_dataset`) enforces most of this mechanically; this
checklist is the human sign-off on the judgment calls it can't make. A copy
of the completed checklist lives in `experiments/<slug>/results/`.

## Content

- [x] Every column is a **derived feature or a public fact** (allow-listed
      with a description in the pipeline's release step).
      (010 Stage 2: the same 25 answer, 9 mention and 5 segment columns, names
      and order as the signed Stage 1 release, each allow-listed in
      `pipeline/25_release.py`. Only the descriptions of `run_id` and `wave`
      changed, to cover waves 8 to 11.)
- [x] No customer prompt text, AI response text, or fan-out query text —
      including inside JSON blobs, "notes" columns, or example rows.
      (010 Stage 2: as at Stage 1, no answer text, question text, best-for
      phrases, judge evidence, caveat reason text, search queries or URLs. The
      segments file, the only model-written text, is unchanged.)
- [x] No customer, property, organization, or execution identifiers.
      Grouping keys are pseudonymized (`exec_0001`) per release.
      (010 Stage 2: no customer data was used. Brands ship as `bNNNN` codes
      from the Stage 1 code table (597 distinct codes in the mentions file,
      569 at Stage 1). Answer ids: Stage 1 rows keep r00001 to r02770; the 480
      new answers are r02771 to r03250, sequential in the same sort (dataset,
      arm, study, item, wave), so they carry no information beyond those
      public columns.)
- [x] Free-text columns marked `public_fact=True` were reviewed value-by-value
      (or verified to come from a public source like YouTube category names).
      (010 Stage 2: only `model` is marked public_fact. Its values, reviewed
      one by one: 3.5 Flash-Lite, 3.6 Flash, claude-opus-5-5, claude.ai,
      gpt-5-5, gpt-5-6, gpt-6, or blank. New since Stage 1: 3.6 Flash (one
      wave 8 Gemini answer). ChatGPT reports gpt-6 in waves 6 to 11, as Audit
      F found.)

## Phrasing

- [x] The datasheet and every mention of the dataset report row counts as
      "answers evaluated in this study".
      (010 Stage 2: 3,250 answers evaluated in this study (2,770 at Stage 1,
      480 added); the mentions file reports 17,965 brand mentions in those
      answers (3,239 added); the segments file 172 use-case segments,
      unchanged.)
- [x] Nothing in the dataset, datasheet, or article states or implies totals
      for the Spyglasses database as a whole.
      (010 Stage 2: as at Stage 1, the brand-code range reveals the size of
      the frozen lexicons, which are study instruments, not the Spyglasses
      database. The Audit G phrase count in the datasheets counts phrases in
      this study's answers.)

## Re-identification review

- [x] Could any set of rows be tied back to a specific customer? Consider:
      per-pseudonym row groups, distinctive video/domain sets, timestamps,
      rare categories. If plausibly yes: coarsen (e.g. month-level dates),
      drop the column, or drop the rows.
      (010 Stage 2: no customer is involved. Waves 8 to 11 used Spyglasses'
      own DataForSEO and Anthropic accounts, as waves 1 to 7 did. Brand names
      are withheld per 009's 2026-10-02 release instruction.)

## Licensing

- [x] License line present in the datasheet (default CC BY 4.0).
- [x] Third-party data terms respected (e.g. YouTube metadata appears as
      derived scalars/aggregates, not bulk raw API payloads).
      (010 Stage 2: DataForSEO and Anthropic outputs appear only as derived
      counts, labels and codes, not raw payloads.)

## Decisions to confirm when signing (tick each)

- [ ] Scope: this is an update of the signed Stage 1 release
      (results/release-checklist.md, 2026-10-11), not a new dataset. Same
      three file names, same columns; the files in data/public/ are replaced.
      The Stage 1 version stays in git history (commit 4432548) and on the
      site until the datasets are synced, and each datasheet's Changelog says
      how to filter back to it. Alternative not taken: versioned file names (a
      separate `-stage1` set), which would leave two copies of the same rows
      on the site.

- [ ] Stage 1 rows unchanged and first: the 2,770 Stage 1 answers keep run_id
      r00001 to r02770 and their position; the 480 answers of waves 8 to 11
      are appended as r02771 to r03250, in the same sort among themselves. So
      the answers file is not in one global dataset order (chatgpt_b2b rows of
      waves 8 to 11 come after the holdouts). Alternative not taken:
      re-sorting and renumbering, which would change most Stage 1 run_ids and
      break any join a reader built on the Stage 1 files.

- [ ] Proof that Stage 1 rows are unchanged, run by the gate itself: it
      rebuilds the Stage 1 release in-process from the Stage 1 frame and
      checks it against the sha256 of the signed files
      (`ai-shortlist-stability-answers.csv` 829a4ca17e2d,
      `ai-shortlist-stability-mentions.csv` 0390179f1830,
      `ai-shortlist-stability-segments.csv` ac564322df9f); each Stage 2 CSV
      must start with exactly those bytes (checked before writing and again on
      the written files); the rows after the prefix must be waves 8 to 11
      only; the segments file must be identical. Result: answers 2,770 of
      3,250 rows are the Stage 1 bytes, mentions 14,726 of 17,965, segments
      identical. Filtering the new files to wave 7 or less (mentions: by
      run_id) gives the signed files back byte for byte.

- [ ] Brand codes: the code table is unchanged (checked: identical to the
      Stage 1 table, 663 codes from 009 and 155 seeded codes from b0664 on).
      No brand needed a new code: the Stage 1 table already covered every
      brand of the frozen lexicons, and firewall rule 4 keeps them frozen, so
      a brand that first appears in waves 8 to 11 outside the lexicons is
      counted only in `n_brands_all` (R1), never coded. The gate refuses to
      release if an observed brand has no code, rather than inventing one. 28
      codes appear for the first time in waves 8 to 11 (26 of them 009 codes,
      2 from the seeded range); the datasheet states the count, not the codes.

- [ ] Best-for segment ids: phrases classified at Stage 1 keep their Stage 1
      classifications (deviation 10b; checked: no Stage 1 phrase changes
      segment in the merged maps); the 3,671 phrases first seen at Stage 2
      were classified twice with the frozen taxonomies. Audit G over all
      18,279 distinct phrases Stage 2 uses: 96% (pass). The datasheets give
      these two phrase counts; they count phrases in this study's answers, not
      anything in the Spyglasses database. Confirm, or drop the counts from
      the notes.

- [ ] Segments file unchanged, so the 25 segment rewrites and the definition
      decision signed at Stage 1 carry over as they are; nothing in REWRITES
      changed.

- [ ] Datasheets: titles now read 'Stages 1 and 2'; 'Released' is the Stage 2
      date (2026-11-09) and the Changelog keeps the Stage 1 date (2026-10-11);
      the deviations pointer covers 1 to 10; a Stage 2 run notes item records
      deviation 9 (ChatGPT gpt-6 in waves 6 to 11, one Gemini answer reporting
      3.6 Flash, wave 9's late start, the 7 Gemini tasks of wave 8 dated
      2026-10-18); Audit E adds the Stage 2 sample (96%, kappa 0.89, 48
      answers). The gate's datasheet writer has no changelog field, so
      `25_release.py` appends the Changelog section after the gate writes each
      datasheet; the alias scan and an em dash check then run on the finished
      files. The model notes are checked against the data (the gate refuses if
      a wave's model differs from what the notes say).

- [ ] Wave dates: the datasheets give scheduled local dates (waves 8 to 11:
      2026-10-16, 2026-10-23, 2026-10-30 and 2026-11-06); run_date carries the
      true dates, through 2026-11-07 for ChatGPT and Gemini (UTC). Late tasks
      keep their true dates, as at Stage 1.

- [ ] Scans, all clean: the segment scan as at Stage 1 (unchanged file); every
      public value, column description, note and Changelog line, and the
      written CSV and datasheet files, against every alias of at least 4
      characters, case-insensitively; accepted: 'front' (ordinary word, as in
      front-end; a helpdesk vendor in another category), 'gemini' (a platform
      studied, in dataset and platform values; also a lexicon alias), 'make'
      (ordinary word, as in make-to-order; a drop-row alias), 'nothing'
      (ordinary word in the gate's datasheet boilerplate; a headphone brand's
      canonical key, whose alias is a two-word product name), 'remote'
      (ordinary word, as in remote access; a payroll vendor in another
      category), 'segment' (ordinary word, a use-case segment; a data vendor's
      name in the B2B lexicon), 'stack' (ordinary word, as in full-stack; a
      drop-row alias), 'teams' (ordinary word; a drop-row alias for a chat
      product), 'wave' (ordinary word, a collection wave; an alias in the B2B
      lexicon). No other hit.

- [ ] Brand codes are pseudonyms, not anonymity, as signed at Stage 1. Four
      more runs per question add frequency information, so a reader who knows
      a market guesses the most frequent codes a little more easily; no name
      ships. Confirm this is still acceptable.

- [ ] Answer-level flags: 0 refusals and 0 empty answers of 3,250;
      `refusal_phrase` flags 3 answers (3 at Stage 1).

- [ ] Not released, as at Stage 1: R1's names outside the lexicon (only the
      count `n_brands_all`), the Audit E second-pass labels (now including the
      Stage 2 sample of waves 8 to 11), and the per-answer judge metadata,
      which is constant and stated in the datasheets.

- [ ] Site: the Stage 2 figures were synced with `sync_site_assets.py
      --figures-only` for the article 2 draft; the datasets are not synced.
      After signing: commit data/public/ and this checklist, then run `uv run
      python scripts/sync_site_assets.py 010-shortlist-stability`.

## Prerequisites

- [x] Stage 1 release checklist signed by Jim Wrubel (`results/release-checklist.md`,
      2026-10-11); its decisions carry over except where listed above.
- [x] Audit D signed (precision 1.00, recall 1.00); Stage 2 audits pass
      (`results/stage2_audits.md`): Audit A every wave 40 of 40, Audit E
      96% on the waves 8 to 11 sample, Audit G 96%.
- [ ] STOP 4: Stage 2 results reviewed by Jim (`results/stage2_model.md`,
      `results/stage2_robustness.md`).

## Sign-off

- Name: ______________  Date: ______________
- Release gate run: `pipeline/25_release.py --stage 2` exit 0 on ______________
