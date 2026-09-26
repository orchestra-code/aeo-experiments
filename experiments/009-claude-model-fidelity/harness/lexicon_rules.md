# Brand lexicon rules (experiment 009)

The lexicon itself (`data/raw/lexicon_v0.csv` and its successors) is built
from AI answers, so it stays under the gitignored `data/raw/`. This file
records only the rules. It names no brand.

## Pipeline

1. **Candidates.** `harness/pilot_report.py` asks claude-haiku-4-5 (JSON schema
   output) to list, for each answer, the vendor or product brands in the
   prompt's software category that the answer presents as options, compares, or
   mentions as alternatives, in order of first mention. The prompt's category
   name is passed with the answer. Results are cached per (arm, item, wave,
   answer hash).
2. **Draft names.** Candidates are normalized: NFKC and lowercase (the
   `aeo_research.brand_match` term key), trademark signs and parentheticals
   removed, trailing category words stripped, a small alias map, and product
   lines collapsed onto a short list of multi-product vendors. Output:
   `data/raw/lexicon_draft.csv`.
3. **Curation (v0 onward).** A person-reviewable table with one row per
   (vendor, prompt category): `canonical, aliases, category, decision
   (keep|drop), reason, match (ci|cs), n_answers`.
4. **Extraction.** Deterministic, as in experiment 003's
   `brands.extract_brands`: markdown link targets, bare URLs and markup are
   stripped; the category's aliases are matched longest first on word
   boundaries; order is first mention. Matched spans are consumed, so a longer
   alias shadows a shorter one inside it. Drop rows consume their spans but are
   not counted. Only the rows for the answer's own prompt category are used.

## Curation rules

- **Unit is the vendor.** Product lines, editions, modules, renamed products
  and acquired products merge into the vendor that sells them today. A
  rebrand merges into the current name.
- **Suites.** A vendor that sells in many categories is one canonical name.
  Whether it counts is decided per category (next rule).
- **Keep** a vendor in a category when it sells a product in that category,
  even if the answer mentions it briefly or as an alternative.
- **Drop in one category only** when the brand is plainly a different kind of
  product there: the buyer's other systems (accounting, ERP, billing,
  payments, policy administration, device management), integration
  platforms, BI tools in a warehouse answer, design tools in a project
  management answer. The reason column says which. When it is unclear whether
  the vendor sells in the category, keep it and mark the reason for review.
- **Drop everywhere:** standards, protocols, regulations and certifications;
  open-source projects that no company sells as a product in the category
  (projects that a vendor sells as a hosted product merge into that vendor);
  publishers, review sites, analysts and forums; general AI assistants and
  office suites; names too ambiguous to attribute.
- **Matching mode.** Aliases that are ordinary English words are matched
  case-sensitively (`cs`); everything else is case-insensitive (`ci`).
  Aliases too generic to match safely are left out of the alias list.
- **Coverage.** v0 covers only the 10 categories in the pilot. The
  confirmatory panel has 20, so the lexicon is extended from wave 1
  candidates for all 40 prompts before it is frozen.

## Freezing

The lexicon is frozen after wave 1 answers are in and before any
confirmatory metric is computed: candidates from wave 1 (all arms) are merged
into the table, a person reviews every row, and the file's sha256 is recorded
in the spec. Audit D then checks extraction on a 30-response spot check
(brand precision at least 0.95, recall at least 0.90). Changes after the
freeze are logged as deviations.
