# Audit D — entity-attribution sign-off

**Result: SIGNED** — 8 name-bearing domains reviewed, 7 are the brand's own
property, 1 belongs to another company. Applied as a labelled robustness
layer; the pre-registered primary outcome is unchanged.

## What was decided and why it needs a human

`scoring.py` labels a consulted domain `name_bearing_other` when the
registered domain's leftmost label carries the brand's name or one of its
aliases (Audit B quotes the rule). That test answers "does this domain carry
the name"; it cannot answer "does the brand own it". Both of these are
name-bearing, and they mean opposite things:

- `atmeta.com` — Meta's own investor-relations domain. The model consulting
  it has not misidentified Meta; it has gone to another Meta property.
- `amieapp.com` — a different product and company that happens to share the
  name Amie. The model consulting it for the tier-B brand Amie (amie.so) has
  gone to the wrong company's site.

No rule the pipeline could apply separates those. So the judgment is made by
a person, recorded verbatim, dated, and never inferred by code.

## Method

- **Source:** the Audit D REVIEW TABLE in `results/audit.txt`, regenerated
  from waves 1-9 (1,056 calls, 6,538 `site:` observations). It lists every
  stale, name-bearing and morphological-guess domain per brand, with counts
  and the template that produced it.
- **Scope:** `name_bearing_other` rows only. `stale_old_domain` rows are
  already unambiguous (the domain is in the frozen `old_domains` map) and
  `morphological_guess` rows are matched against the frozen `expected_guess`
  set, so neither needs an attribution. `third_party` domains are not claims
  about the asked brand at all.
- **Reviewer:** Jim Wrubel, 2026-09-11.
- **Recorded in:** `pipeline/annotations.py` (`AUDIT_D_ATTRIBUTION`), the
  machine-readable twin of this document.

## Decisions

| Brand | Domain | Tier | Template | n | Attribution |
|---|---|---|---|---|---|
| Bose | boseprofessional.com | A | p1 | 2 | `own_property` |
| Shopify | shopify.dev | A | p2 | 3 | `own_property` |
| Sony | sony.co.jp | A | p2 | 1 | `own_property` |
| Sony | sony-semicon.com | A | p2 | 1 | `own_property` |
| GoTo | gotomypc.com | C | p1 | 1 | `own_property` |
| GoTo | logmeinrescue.com | C | p1 | 1 | `own_property` |
| Meta | atmeta.com | C | p1 + p2 | 14 | `own_property` |
| Amie | amieapp.com | B | p2 | 3 | `other_company` |

Seven of the eight are the brand's own orbit — a product domain, a regional
domain, a developer domain, an investor domain. One, `amieapp.com`, is
objectively wrong.

## How it is applied

The primary outcome does **not** change: a name-bearing consultation is still
not the canonical domain, and `first_site_label` still reads `wrong`. The
attribution enters as:

- an `attribution` column on `data/interim/site_observations.csv` and
  `first_site_attribution` on the call frame and the released dataset;
- the H3 error-content table, where `name_bearing_other` splits into
  own-property / other-company / unreviewed;
- **robustness (f)**, which recounts call-level accuracy with own-property
  first commitments treated as correct ("the brand's own orbit"). Amie stays
  wrong there;
- a per-tier count of **genuinely wrong** first commitments (stale +
  morphological guess + other company + unreviewed), with rule-of-three
  upper bounds on the zero cells.

## Re-opening rule

Any `name_bearing_other` domain not in the signed table attributes as
`unreviewed`. Unreviewed is **not** a synonym for benign:

- it is printed in capitals in Audit D as an action item;
- it counts as genuinely wrong in robustness (f) and in the genuinely-wrong
  counts;
- it means this sign-off is incomplete until a reviewer rules on it.

Wave 10 lands after this signature. If it introduces a new name-bearing
domain, Audit D reopens: rule on the new row, add it to
`AUDIT_D_ATTRIBUTION`, extend the table above, and re-date the signature.

- Name: ___Jim Wrubel______  Date: __2026-09-11______
