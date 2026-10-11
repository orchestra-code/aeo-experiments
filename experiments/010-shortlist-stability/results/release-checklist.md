# Dataset release checklist — 010-shortlist-stability

Complete for every dataset release. The technical gate
(`aeo_research.release_dataset`) enforces most of this mechanically; this
checklist is the human sign-off on the judgment calls it can't make. A copy
of the completed checklist lives in `experiments/<slug>/results/`.

## Content

- [x] Every column is a **derived feature or a public fact** (allow-listed
      with a description in the pipeline's release step).
      (010: 25 answer columns, 9 mention columns and 5 segment columns, each
      allow-listed with a description in `pipeline/25_release.py`. The spec's
      `prompt_intent` ships as `intent` and the answer key as `run_id`,
      because the gate refuses column names containing 'prompt' or 'answer'.)
- [x] No customer prompt text, AI response text, or fan-out query text —
      including inside JSON blobs, "notes" columns, or example rows.
      (010: no answer text, question text, best-for phrases, judge evidence,
      caveat reason text, search queries or URLs. The only model-written text
      is the B2B segment labels and definitions, see the decisions below.)
- [x] No customer, property, organization, or execution identifiers.
      Grouping keys are pseudonymized (`exec_0001`) per release.
      (010: no customer data was used. Brands ship as `bNNNN` codes (569
      distinct codes in the mentions file); headphone and agency item ids and
      categories as per-release codes. Answer ids `rNNNNN` are sequential in a
      sort by dataset, arm, study, item and wave, so they carry no information
      beyond those public columns.)
- [x] Free-text columns marked `public_fact=True` were reviewed value-by-value
      (or verified to come from a public source like YouTube category names).
      (010: only `model` is marked public_fact. It holds the model strings the
      platforms reported: gpt-5-6, gpt-6, gpt-5-5, 3.5 Flash-Lite, claude-
      opus-5-5, claude.ai, or blank.)

## Phrasing

- [x] The datasheet and every mention of the dataset report row counts as
      "answers evaluated in this study".
      (010: 2,770 answers evaluated in this study; the mentions file reports
      14,726 brand mentions in those answers; the segments file 172 use-case
      segments.)
- [x] Nothing in the dataset, datasheet, or article states or implies totals
      for the Spyglasses database as a whole.
      (010: the brand-code range reveals the size of the frozen lexicons,
      which are study instruments, not the Spyglasses database.)

## Re-identification review

- [x] Could any set of rows be tied back to a specific customer? Consider:
      per-pseudonym row groups, distinctive video/domain sets, timestamps,
      rare categories. If plausibly yes: coarsen (e.g. month-level dates),
      drop the column, or drop the rows.
      (010: no customer is involved. The new collection used Spyglasses' own
      DataForSEO and Anthropic accounts, and claude.ai rows come from 009's
      fresh Pro account. Brand names are withheld per 009's 2026-10-02 release
      instruction.)

## Licensing

- [x] License line present in the datasheet (default CC BY 4.0).
- [x] Third-party data terms respected (e.g. YouTube metadata appears as
      derived scalars/aggregates, not bulk raw API payloads).
      (010: DataForSEO and Anthropic outputs appear only as derived counts,
      labels and codes, not raw payloads.)

## Decisions to confirm when signing (tick each)

- [ ] Brand codes reuse 009's published `bNNNN` strings (spec §3 writes
      `v0001`, "as in 009's release", but 009 shipped `bNNNN`). Reusing the
      exact strings lets the 234 claude_b2b rows join 009's public answers
      file (checked: their code lists equal 009's `brand_codes` row for row).
      663 codes are 009's; 155 new codes (b0664 on) cover every other brand of
      the frozen lexicons (lexicon v3 keep rows and 005's headphone and agency
      lexicons), in a seeded order over the whole lexicon, so Stage 2 can keep
      them. A new code tells a reader the brand was not in 009's answers;
      nothing else. To ship `v` codes instead, set BRAND_PREFIX = "v" (the
      join to 009 then needs b -> v).

- [ ] Headphone and agency brands are coded in their own namespace (one agency
      name is spelled like a B2B brand and is a different company). Note: 002,
      003 and 005 published headphone and agency brand names in the clear;
      this release is stricter, per spec §3.

- [ ] Headphone and agency categories ship as `cat_c1` and `cat_a1` and their
      item ids as per-release codes (spec §3). The categories themselves are
      public (002's release, the article), so this is belt and braces; the
      agency segment ids (for example `coffee_cafe_specialists`) also show the
      agency vertical.

- [ ] Headphone and agency segment ids ship in the mentions file without
      labels. 1 headphone segment id named a device maker that is a brand in
      the headphone lexicon; it ships as `single_ecosystem_users`. No agency
      segment id names a brand.

- [ ] B2B segment text: 25 of 172 segments named vendors or products in the
      model-written label, definition or id and were rewritten generically
      (the originals are in data/raw/bestfor_taxonomy_b2b/taxonomy.json, not
      committed; this list says what was named without repeating it):
      - CRM / `existing_stack_users`: definition named a software vendor;
        rewrote definition.
      - HRIS / `chat_based_workflows`: definition named two workplace chat
        products; rewrote definition.
      - accounts payable automation / `enterprise_erp`: definition named five
        ERP vendors or products; rewrote definition.
      - cloud data warehouse / `ecosystem_aligned`: definition named five
        productivity, BI and cloud products; rewrote definition.
      - customer support helpdesk / `crm_ecosystem_teams`: definition named
        three CRM vendors; rewrote definition.
      - customer support helpdesk / `subscription_ecommerce`: definition named
        an ecommerce platform; rewrote definition.
      - customer support helpdesk / `omnichannel_support`: definition named a
        messaging app; rewrote definition.
      - e-signature / `ecosystem_native_users`: definition named seven
        software vendors or products; rewrote definition.
      - endpoint security (EDR) / `productivity_suite_ecosystem`: id, label
        and definition named a software vendor and four of its products;
        rewrote id, label, definition.
      - endpoint security (EDR) / `single_platform_mdm`: id, label and
        definition named a device maker, its computers and two MDM vendors;
        rewrote id, label, definition.
      - endpoint security (EDR) / `mixed_platforms`: definition named two
        desktop operating systems; rewrote definition.
      - expense management / `accounting_integrations`: definition named six
        accounting or ERP products; rewrote definition.
      - expense management / `legal_workflows`: definition named six legal
        practice and accounting products; rewrote definition.
      - identity and SSO / `directory_suite_ecosystem`: id, label and
        definition named a software vendor and five of its products; rewrote
        id, label, definition.
      - identity and SSO / `cloud_workspace_ecosystem`: id, label and
        definition named a software vendor and two of its products; rewrote
        id, label, definition.
      - marketing automation / `enterprise_crm_teams`: id, label and
        definition named a CRM vendor; rewrote id, label, definition.
      - mid-market ERP / `productivity_suite_ecosystem`: id, label and
        definition named a software vendor and three of its products; rewrote
        id, label, definition.
      - observability/APM / `container_native`: id, label and definition named
        an open-source container orchestrator; rewrote id, label, definition.
      - observability/APM / `existing_ecosystems`: definition named six open-
        source or commercial observability tools; rewrote definition.
      - product analytics / `mobile_apps`: definition named two mobile
        operating systems; rewrote definition.
      - project management / `design_integrated_teams`: definition named a
        design software vendor and two of its products; rewrote definition.
      - project management / `productivity_suite_teams`: id, label and
        definition named a software vendor and its productivity suite; rewrote
        id, label, definition.
      - sales engagement / `crm_ecosystem_teams`: definition named three CRM
        vendors and two email products; rewrote definition.
      - sales engagement / `multichannel_phone_selling`: id, label and
        definition used a common word that is also the name of a sales
        engagement vendor in this category; rewrote id, label, definition.
      - sales engagement / `prospecting_sequencing`: definition used a common
        word that is also the name of a sales engagement vendor in this
        category; rewrote definition.

- [ ] The B2B definitions are model-written summaries of clusters of best-for
      phrases (an instrument, built from many answers), not answer text. If
      you read them as too close to AI response text, drop the `definition`
      column (remove it from SEGMENT_COLUMNS) and publish labels only.

- [ ] Scans, all clean: (1) every B2B label, definition and public id against
      2,841 aliases (lexicon v3 and 009 v2.1, keep and drop rows, and 005's
      lexicons), case-insensitively, plus a capitalized-name check on every
      definition that catches product names in no lexicon. Accepted as
      ordinary words: 'front' (ordinary word, as in front-end; a helpdesk
      vendor in another category), 'make' (ordinary word, as in make-to-order;
      a drop-row alias), 'remote' (ordinary word, as in remote access; a
      payroll vendor in another category), 'stack' (ordinary word, as in full-
      stack; a drop-row alias), 'teams' (ordinary word; a drop-row alias for a
      chat product). (2) Every public value, every column description and
      note, and the written CSV and datasheet files against every alias of at
      least 4 characters, case-insensitively; accepted: 'front' (ordinary
      word, as in front-end; a helpdesk vendor in another category), 'gemini'
      (a platform studied, in dataset and platform values; also a lexicon
      alias), 'make' (ordinary word, as in make-to-order; a drop-row alias),
      'nothing' (ordinary word in the gate's datasheet boilerplate; a
      headphone brand's canonical key, whose alias is a two-word product
      name), 'remote' (ordinary word, as in remote access; a payroll vendor in
      another category), 'segment' (ordinary word, a use-case segment; a data
      vendor's name in the B2B lexicon), 'stack' (ordinary word, as in full-
      stack; a drop-row alias), 'teams' (ordinary word; a drop-row alias for a
      chat product), 'wave' (ordinary word, a collection wave; an alias in the
      B2B lexicon). No other hit.

- [ ] Brand codes are pseudonyms, not anonymity. As with 009's codes, a reader
      who knows a market can guess the most frequent codes in a category, and
      a few segment ids sharpen the guess (for example the brand most often
      placed in a productivity-suite ecosystem segment, or in the headphone
      segment `single_ecosystem_users`). No name ships; confirm this is
      acceptable, as it was for 009.

- [ ] Answer-level flags: `refusal` follows deviation 7 (0 refusals of 2,770);
      `refusal_phrase` keeps the old heuristic's 3 flags for transparency.

- [ ] Not released: R1's names outside the lexicon (only the count
      `n_brands_all`), the Audit E second-pass labels, and the per-answer
      judge metadata (sha, version), which is constant and stated in the
      datasheets.

## Prerequisite

- [x] Audit D signed by Jim Wrubel (`results/audit_d_score.json`,
      scored at the instrument freeze, 2026-10-11): precision 1.00, recall 1.00
      against gates 0.95 / 0.90.

## Sign-off

- Name: ______________  Date: ______________
- Release gate run: `pipeline/25_release.py --stage 1` exit 0 on ______________
