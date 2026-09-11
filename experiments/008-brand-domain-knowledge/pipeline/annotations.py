"""Audit D entity-attribution decisions — HUMAN judgments, frozen and dated.

Scoring (``scoring.py``) can tell that a consulted domain carries the brand's
name; it cannot tell whether the brand OWNS that domain. atmeta.com is Meta's
own investor site and sony.co.jp is Sony's own Japanese site, while
amieapp.com belongs to a different company that happens to share the name
Amie. That distinction changes what an error means, and no rule the pipeline
could apply would get it right — so it is made by a person, recorded here
verbatim, and applied as a LABELLED ROBUSTNESS LAYER on top of an unchanged
primary outcome (see the Deviations section of results/audit.txt).

Reviewed and signed: **Jim Wrubel, 2026-09-11**, against the Audit D review
table in ``results/audit.txt`` (waves 1-9). The prose record of the decision
is ``results/audit-d-signoff.md``; this module is its machine-readable twin.

Values:
  ``own_property``   the domain is the brand's own site — a different
                     property of the same company, not a wrong answer about
                     who the brand is.
  ``other_company``  the domain belongs to someone else. Objectively wrong.
  ``unreviewed``     a name-bearing domain that reached the data AFTER the
                     sign-off. Never assumed benign: it is printed in
                     capitals as an Audit D action item, counts as genuinely
                     wrong in robustness (f), and reopens the review.

Only ``name_bearing_other`` observations need an attribution. ``stale`` and
``morphological_guess`` are already unambiguous, and ``third_party`` domains
are not claims about the asked brand at all.
"""

from __future__ import annotations

SIGNED_BY = "Jim Wrubel"
SIGNED_ON = "2026-09-11"
SIGNOFF_DOC = "results/audit-d-signoff.md"

OWN_PROPERTY = "own_property"
OTHER_COMPANY = "other_company"
UNREVIEWED = "unreviewed"

#: (brand canonical name, registered domain) -> attribution. Verbatim from
#: the 2026-09-11 sign-off; do not add a row without a new signature.
AUDIT_D_ATTRIBUTION: dict[tuple[str, str], str] = {
    ("Bose", "boseprofessional.com"): OWN_PROPERTY,
    ("Shopify", "shopify.dev"): OWN_PROPERTY,
    ("Sony", "sony.co.jp"): OWN_PROPERTY,
    ("Sony", "sony-semicon.com"): OWN_PROPERTY,
    ("GoTo", "gotomypc.com"): OWN_PROPERTY,
    ("GoTo", "logmeinrescue.com"): OWN_PROPERTY,
    ("Meta", "atmeta.com"): OWN_PROPERTY,
    # The only one that is somebody else's: a different product/company that
    # shares the name Amie. Stays wrong in every robustness reading.
    ("Amie", "amieapp.com"): OTHER_COMPANY,
}


def attribution(brand: str, registered_domain: str) -> str:
    """Signed attribution for a name-bearing domain, else ``unreviewed``.

    Defaults to ``unreviewed`` rather than to anything benign, so a domain
    that first appears in a later wave surfaces as an action item instead of
    silently inheriting a judgment nobody made about it.
    """
    return AUDIT_D_ATTRIBUTION.get((brand, registered_domain), UNREVIEWED)


def signed_rows() -> list[dict]:
    """The table as records, for printing in Audit D."""
    return [
        {"brand": brand, "registered_domain": domain, "attribution": value}
        for (brand, domain), value in AUDIT_D_ATTRIBUTION.items()
    ]
