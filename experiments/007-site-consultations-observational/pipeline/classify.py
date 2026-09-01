"""Read-time classification ports for the 007 pipeline.

Ports the semantics of spyglasses' `buildSiteScopeClassifier`
(packages/core/src/utils/site-scope.ts) and `promptClassFor`
(packages/core/src/types/discovery-query.ts) so prod rows are classified the
way the product classifies them:

- scope class: own = focal domain (property.domain, else seedUrl host) or
  additionalDomains, exact-or-subdomain; competitor = same test against the
  normalized Competitor.url host (skipped unless it contains a dot — drops
  `peer:` pseudo-urls); own wins over competitor; else third_party.
- named class (non-scoped rows): via aeo_research.brand_match, the pinned
  port of buildCompetitorNamedQueryMatcher.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "src"))

from aeo_research.brand_match import (  # noqa: E402
    CompetitorSource,
    build_competitor_named_query_matcher,
    normalize_domain_or_null,
)

BRAND_QUERY_TYPES = {"brand_identity"}
COMPARISON_QUERY_TYPES = {"brand_comparison"}


def prompt_class(query_type: str | None) -> str:
    """Port of promptClassFor: brand / comparison / discovery."""
    if query_type in BRAND_QUERY_TYPES:
        return "brand"
    if query_type in COMPARISON_QUERY_TYPES:
        return "comparison"
    return "discovery"


def parse_pg_array(raw: str | None) -> list[str]:
    """Parse a Postgres array literal (`{a,"b, c",d}`) from CSV output."""
    if raw is None or raw in ("", "{}"):
        return []
    s = raw.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    out: list[str] = []
    buf: list[str] = []
    in_quotes = False
    i = 0
    while i < len(s):
        ch = s[i]
        if in_quotes:
            if ch == "\\" and i + 1 < len(s):
                buf.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                in_quotes = False
            else:
                buf.append(ch)
        elif ch == '"':
            in_quotes = True
        elif ch == ",":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf or out:
        out.append("".join(buf))
    return [v for v in (x.strip() for x in out) if v and v.upper() != "NULL"]


def _host_matches(domain: str, base: str) -> bool:
    return domain == base or domain.endswith("." + base)


@dataclass
class PropertyContext:
    property_id: str
    company_name: str | None
    aliases: list[str]
    domain: str | None
    seed_url: str | None
    additional_domains: list[str]
    competitors: list[CompetitorSource]

    def focal_domain(self) -> str | None:
        return normalize_domain_or_null(self.domain) or normalize_domain_or_null(
            self.seed_url
        )

    def own_hosts(self) -> list[str]:
        hosts = [self.focal_domain()] + [
            normalize_domain_or_null(d) for d in self.additional_domains
        ]
        return [h for h in hosts if h]

    def competitor_hosts(self) -> list[str]:
        hosts = [normalize_domain_or_null(c.url) for c in self.competitors]
        return [h for h in hosts if h and "." in h]

    def scope_class(self, scoped_domain: str | None) -> str | None:
        if not isinstance(scoped_domain, str):  # NaN from a pandas map
            return None
        d = normalize_domain_or_null(scoped_domain)
        if not d:
            return None
        if any(_host_matches(d, h) for h in self.own_hosts()):
            return "own"
        if any(_host_matches(d, h) for h in self.competitor_hosts()):
            return "competitor"
        return "third_party"

    def named_matcher(self):
        return build_competitor_named_query_matcher(
            [self.company_name, *self.aliases, self.focal_domain()],
            self.competitors,
        )


def named_class(match) -> str:
    """own / competitor / both / none from a brand_match Match."""
    if match.names_our_brand and match.names_competitor:
        return "both"
    if match.names_competitor:
        return "competitor"
    if match.names_our_brand:
        return "own"
    return "none"


def load_context(context_csv: Path) -> dict[str, PropertyContext]:
    """context.csv (one row per property×competitor) → PropertyContext map."""
    import pandas as pd

    df = pd.read_csv(context_csv, dtype=str, keep_default_na=False)
    contexts: dict[str, PropertyContext] = {}
    for pid, group in df.groupby("property_id"):
        first = group.iloc[0]
        competitors = [
            CompetitorSource(
                id=row.competitor_id,
                name=row.competitor_name or None,
                aliases=parse_pg_array(row.competitor_aliases),
                url=row.competitor_url or None,
            )
            for row in group.itertuples()
            if row.competitor_id
        ]
        contexts[pid] = PropertyContext(
            property_id=pid,
            company_name=first["company_name"] or None,
            aliases=parse_pg_array(first["property_aliases"]),
            domain=first["property_domain"] or None,
            seed_url=first["property_seed_url"] or None,
            additional_domains=parse_pg_array(first["additional_domains"]),
            competitors=competitors,
        )
    return contexts
