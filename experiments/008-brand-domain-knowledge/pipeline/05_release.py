"""Stage 05 — gate-checked public dataset -> data/public/.

One row per collected call, derived features only. What ships and what does
not (spec §3 + docs/data-policy.md):

- SHIPS: the study panel's brand name, tier, which template ran, wave,
  replicate slot, run date, model version, whether the call emitted a site:
  search and how many, the FIRST site: domain and its label/error kind, the
  any_* flags, and counts of third-party / consulted / cited domains. The
  panel is 48 non-customer brands chosen by us, and a domain is a public web
  fact, so spec §3 marks site_domain publishable for study brands.
- NEVER SHIPS: fan-out / search-query text (house rule — even study-generated
  fan-out text stays in data/raw), answer markdown, and the LISTS of
  consulted and cited domains (spec §3 marks those derived-only, so only
  their counts ship).

The technical gate (`aeo_research.release_dataset`) enforces the allow-list,
the forbidden-name patterns and the free-text scans; the human checklist
copied next to it enforces the judgment calls. Do not commit data/public/
until that checklist is signed.

Usage: uv run python experiments/008-brand-domain-knowledge/pipeline/05_release.py
"""

from __future__ import annotations

import pandas as pd
from common import EXP, PUBLIC, RESPONSES_CSV, RESULTS

from aeo_research import ColumnSpec, Datasheet, release_dataset

SLUG = "brand-domain-knowledge-chatgpt"
CHECKLIST_TEMPLATE = EXP.parents[1] / "templates" / "release-checklist.md"

TEMPLATE_DESCRIPTION = {
    "p1": "brand-identity",
    "p2": "comparison",
}

COLUMNS = [
    ColumnSpec("brand", "Study panel brand the call asked about (48 non-customer brands)"),
    ColumnSpec(
        "tier",
        "Panel tier: A guessable domain (brandname.com), B non-obvious domain, "
        "C migrated domain, D obscure brand",
    ),
    ColumnSpec(
        "template",
        "Which of the two frozen prompt shapes ran: 'brand-identity' (what is "
        "this brand, what does it offer, how is it priced) or 'comparison' "
        "(how does it compare to its main competitors). The wording itself is "
        "not released.",
    ),
    ColumnSpec("wave", "Daily collection wave, 1-10"),
    ColumnSpec(
        "replicate",
        "Same-day replicate slot: 0 every wave, 1 and 2 are the wave-1 "
        "afternoon and evening repeats",
    ),
    ColumnSpec("run_date", "Collection date (UTC)"),
    ColumnSpec("model_version", "Model identifier the API reported", public_fact=True),
    ColumnSpec("emitted_site_search", "1 if the call ran at least one site: search"),
    ColumnSpec(
        "emitted_brand_site_search",
        "1 if at least one site: search was about the asked brand's own domain "
        "rather than a competitor's or a reference site — the analysis set for "
        "every rate in the study",
    ),
    ColumnSpec("n_site_queries", "Count of site: searches the call ran"),
    ColumnSpec(
        "first_site_domain",
        "Registered domain of the first BRAND-ATTRIBUTABLE site: search — the "
        "model's first commitment to a domain FOR THIS BRAND, empty when the "
        "call only searched third-party sites (public web fact, study brands "
        "only)",
        public_fact=True,
    ),
    ColumnSpec(
        "first_search_domain_any",
        "Registered domain of the raw first site: search of any kind, "
        "competitor and reference sites included — lets readers reconstruct "
        "the unconditioned first-search reading (public web fact)",
        public_fact=True,
    ),
    ColumnSpec(
        "first_site_label",
        "correct (the brand's canonical domain), stale (a frozen old domain of "
        "the brand), wrong, or none (the call made no brand-attributable site: "
        "search)",
    ),
    ColumnSpec(
        "first_site_error_kind",
        "For a non-correct first domain: stale_old_domain, morphological_guess, "
        "name_bearing_other (another domain carrying the brand's name), "
        "third_party (a competitor or reference site — expected on comparison "
        "prompts), or nonexistent (did not resolve at the audit's check date)",
    ),
    ColumnSpec(
        "first_site_attribution",
        "For a first commitment on a domain carrying the brand's name: "
        "own_property (the brand's own site — a product, regional, developer "
        "or investor domain) or other_company (a different company sharing "
        "the name), or unreviewed. A HUMAN attribution recorded in this "
        "study's Audit D sign-off (results/audit-d-signoff.md, signed "
        "2026-09-11), not inferred by code; it labels a robustness layer and "
        "does not change first_site_label. Empty for every other case.",
    ),
    ColumnSpec("any_stale", "1 if any site: search in the call used a frozen old domain"),
    ColumnSpec("any_guess", "1 if any site: search used a morphological-guess domain"),
    ColumnSpec(
        "any_name_bearing",
        "1 if any site: search used another domain carrying the brand's name",
    ),
    ColumnSpec(
        "n_site_third_party",
        "Count of site: searches aimed at a domain that does not carry the "
        "brand's name (competitor and reference sites)",
    ),
    ColumnSpec(
        "n_consulted_domains",
        "Count of distinct registered domains the call's searches returned "
        "(the domain list itself is derived-only and not released)",
    ),
    ColumnSpec(
        "n_cited_domains",
        "Count of distinct registered domains the answer cited (the domain "
        "list itself is derived-only and not released)",
    ),
    ColumnSpec("n_web_search_calls", "Count of web_search_call items in the response"),
]

NOTES = [
    "One row per call evaluated in this study: 48 brands x 2 prompt templates "
    "x 10 daily waves, plus two spaced same-day replicates on wave 1.",
    "Collected through the direct OpenAI Responses API with the web_search "
    "tool (not a scraper and not the consumer UI), so the observable is the "
    "model's own search action, including the site: operator it types.",
    "The outcome is consultation-conditional: it exists only when the model "
    "elected to consult a site directly. Read every rate as 'when the model "
    "consulted a site...', never as 'the model believes...'.",
    "The primary outcome is the first BRAND-ATTRIBUTABLE site: search. A "
    "comparison prompt often opens on a competitor's site by design; that is "
    "not a claim about the asked brand's domain, so such calls are not "
    "counted as wrong (first_site_label = 'none' when a call made no "
    "brand-attributable search). first_search_domain_any preserves the raw "
    "first search for anyone who wants the other reading.",
    "Brands are a study-generated panel of non-customer companies; domains "
    "are public web facts. No customer prompts, responses, fan-out text or "
    "identifiers appear here.",
    "Search-query text (including the full site: query), answer text, and the "
    "lists of consulted and cited domains are derived-only and are not "
    "released; their counts are.",
    "A domain carrying the brand's name may be the brand's own property or a "
    "different company's; that call is a human judgment, signed and dated in "
    "the study's Audit D sign-off and carried here as first_site_attribution. "
    "It labels a robustness layer — the primary outcome treats a name-bearing "
    "domain as not canonical either way.",
    "Zero counts in a cell are upper bounds, not impossibility: the study "
    "reports rule-of-three (3/n) bounds for every empty cell.",
]


def write_checklist() -> None:
    """Copy the house release checklist next to the results, unfilled.

    Never overwrites: the file in results/ is the human's signed record, and
    the release gate re-runs after every wave. If it exists it is left alone.
    """
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "release-checklist.md"
    if path.exists():
        signed = "Name: ______________  Date:" not in path.read_text()
        print(f"checklist kept ({'signed' if signed else 'unsigned'}): {path}")
        return
    text = CHECKLIST_TEMPLATE.read_text()
    text = text.replace("<experiment slug>", "008-brand-domain-knowledge")
    lines = []
    for line in text.splitlines():
        if line.startswith("- Name:"):
            line = "- Name: ______________  Date: ______________"
        elif line.startswith("- Release gate run:"):
            line = "- Release gate run: `pipeline/05_release.py` exit 0 on ______________"
        lines.append(line)
    path.write_text("\n".join(lines) + "\n")
    print(f"checklist (unsigned): {path}")


def main() -> None:
    df = pd.read_csv(RESPONSES_CSV)
    if int(df.get("synthetic", pd.Series([0])).max()) == 1:
        raise SystemExit("refusing to release a SYNTHETIC frame")

    out = pd.DataFrame(
        {
            "brand": df["brand"],
            "tier": df["tier"],
            "template": df["template"].map(TEMPLATE_DESCRIPTION),
            "wave": df["wave"],
            "replicate": df["replicate"],
            "run_date": df["run_date"],
            "model_version": df["model"],
            "emitted_site_search": df["emitted_site_query"],
            "emitted_brand_site_search": df["emitted_brand_site_query"],
            "n_site_queries": df["n_site_queries"],
            "first_site_domain": df["first_site_domain"].fillna(""),
            "first_search_domain_any": df["first_search_domain_any"].fillna(""),
            "first_site_label": df["first_site_label"].fillna(""),
            "first_site_error_kind": df["first_site_error_kind"].fillna(""),
            "first_site_attribution": df["first_site_attribution"].fillna(""),
            "any_stale": df["any_stale"],
            "any_guess": df["any_guess"],
            "any_name_bearing": df["any_name_bearing"],
            "n_site_third_party": df["n_site_third_party"],
            "n_consulted_domains": df["n_consulted"],
            "n_cited_domains": df["n_cited"],
            "n_web_search_calls": df["n_web_search_call"],
        }
    )

    paths = release_dataset(
        out,
        COLUMNS,
        PUBLIC,
        Datasheet(
            title="Does ChatGPT know a brand's domain? 48 brands, 10 daily waves",
            dataset_slug=SLUG,
            study="008-brand-domain-knowledge",
            unit="calls",
            notes=NOTES,
        ),
    )
    print(f"released: {paths['csv']}\n          {paths['datasheet']}")
    write_checklist()
    print("Do not commit data/public/ until the release checklist is signed.")


if __name__ == "__main__":
    main()
