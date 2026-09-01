"""Python port of Spyglasses ``buildCompetitorNamedQueryMatcher``.

Classifies a grounding-search query as naming a tracked competitor, the
property's own brand, both, or neither — so observational studies label
production rows exactly the way the product does.

Source of truth: ``packages/core/src/utils/competitor-named-query.ts`` in the
spyglasses repo (plus ``wordBoundaryPattern`` in ``prompt-class-detection.ts``
and ``normalizeDomainOrNull`` in ``domain.ts``). Parity is pinned by
``tests/test_matcher_parity.py``, which mirrors the TS test suite case for
case; the source commit is recorded there. Change the TS matcher and this
port + the parity fixture must change with it.

Port notes (the two places Python can't be literal):

- TS ``(?<![\\p{L}\\p{N}])`` word boundaries become ``(?<![^\\W_])``:
  ``[^\\W_]`` is "word character minus underscore" = Unicode letters+digits,
  the same boundary class without needing the ``regex`` package.
- TS ``new URL()`` throws on an invalid authority (``https://peer:jane-doe``
  has a non-numeric port) and falls back to a hand split; Python's
  ``urlsplit`` doesn't validate the port on ``.hostname`` access. Both roads
  end at a dot-less token, which contributes no terms either way.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence
from urllib.parse import urlsplit

#: The shortest term this module will match on (brand-mention-scan convention;
#: machine-generated fan-out text + a 2-char alias would over-exclude).
MIN_TERM_LENGTH = 3

#: Hostname-shaped tokens: letters, digits, dots and dashes, nothing else.
_HOSTNAME_SHAPE = re.compile(r"^[a-z0-9.-]+$", re.IGNORECASE)

#: A ``site:`` operator and its argument, with or without a leading ``-``.
#: Stripped before matching: an operator argument is a directive about WHERE
#: to search, not part of what the search is about.
_SITE_OPERATOR_TOKEN = re.compile(r"(^|\s)-?site:\s?\S+", re.IGNORECASE)


@dataclass(frozen=True)
class CompetitorSource:
    """Mirror of the TS context's competitor entry."""

    id: str
    name: Optional[str] = None
    aliases: Optional[Sequence[str]] = None
    url: Optional[str] = None


@dataclass(frozen=True)
class Match:
    names_competitor: bool
    names_our_brand: bool
    matched_competitor_names: tuple[str, ...]

    @property
    def competitor_only(self) -> bool:
        """``names_competitor and not names_our_brand`` — THE exclusion predicate."""
        return self.names_competitor and not self.names_our_brand


_NO_MATCH = Match(False, False, ())


def normalize_domain_or_null(raw: Optional[str]) -> Optional[str]:
    """Port of spyglasses ``normalizeDomainOrNull``: bare lowercase host, no www."""
    if raw is None or not raw.strip():
        return None
    trimmed = raw.strip()
    with_protocol = trimmed if "://" in trimmed else f"https://{trimmed}"
    try:
        hostname = urlsplit(with_protocol).hostname or ""
    except ValueError:
        hostname = ""
    if not hostname:
        # Not URL-parseable — lop off any path/query by hand (TS fallback).
        hostname = trimmed.split("/")[0].split("?")[0]
    normalized = re.sub(r"^www\.", "", hostname.lower())
    return normalized if normalized.strip() else None


def word_boundary_pattern(term: str) -> Optional[re.Pattern[str]]:
    """Port of ``wordBoundaryPattern``: whole-word, case-insensitive, NFKC term."""
    trimmed = term.strip()
    if len(trimmed) < 2:
        return None
    escaped = re.escape(unicodedata.normalize("NFKC", trimmed))
    return re.compile(rf"(?<![^\W_]){escaped}(?![^\W_])", re.IGNORECASE)


def _host_terms(raw: Optional[str]) -> list[str]:
    """The host and its bare second-level label; [] for dot-less pseudo-hosts.

    Deliberately the naive two-label split: ``acme.co.uk`` yields "co", which
    dies on the length floor — a competitor we under-match, never a query we
    over-exclude.
    """
    host = normalize_domain_or_null(raw)
    if not host or "." not in host:
        return []
    labels = host.split(".")
    return [host, labels[-2] if len(labels) >= 2 else ""]


def _name_terms(raw: Optional[str]) -> list[str]:
    """Terms contributed by a brand/alias string, expanding it when it is a domain."""
    trimmed = (raw or "").strip()
    if not trimmed:
        return []
    if _HOSTNAME_SHAPE.match(trimmed) and "." in trimmed:
        return _host_terms(trimmed)
    return [trimmed]


def _compile_terms(terms: Iterable[str]) -> list[re.Pattern[str]]:
    seen: set[str] = set()
    patterns: list[re.Pattern[str]] = []
    for term in terms:
        trimmed = term.strip()
        if len(trimmed) < MIN_TERM_LENGTH:
            continue
        key = unicodedata.normalize("NFKC", trimmed).lower()
        if key in seen:
            continue
        seen.add(key)
        pattern = word_boundary_pattern(trimmed)
        if pattern is not None:
            patterns.append(pattern)
    return patterns


def build_competitor_named_query_matcher(
    our_brand_terms: Sequence[Optional[str]],
    competitors: Sequence[CompetitorSource],
) -> Callable[[Optional[str]], Match]:
    """Compile a matcher; call it per query (regexes are built once here)."""
    our_patterns = _compile_terms(
        term
        for raw in (our_brand_terms or [])
        for term in _name_terms(raw)
    )

    compiled: list[tuple[str, list[re.Pattern[str]]]] = []
    for competitor in competitors or []:
        patterns = _compile_terms(
            [
                *_name_terms(competitor.name),
                *(
                    term
                    for alias in (competitor.aliases or [])
                    for term in _name_terms(alias)
                ),
                *_host_terms(competitor.url),
            ]
        )
        if not patterns:
            continue
        display = (
            (competitor.name or "").strip()
            or normalize_domain_or_null(competitor.url)
            or competitor.id
        )
        compiled.append((display, patterns))

    if not compiled:
        return lambda _query: _NO_MATCH

    def match(query: Optional[str]) -> Match:
        if not isinstance(query, str):
            return _NO_MATCH
        text = _SITE_OPERATOR_TOKEN.sub(
            r"\1", unicodedata.normalize("NFKC", query)
        )
        if not text.strip():
            return _NO_MATCH
        matched = tuple(
            name
            for name, patterns in compiled
            if any(pattern.search(text) for pattern in patterns)
        )
        return Match(
            names_competitor=bool(matched),
            names_our_brand=any(p.search(text) for p in our_patterns),
            matched_competitor_names=matched,
        )

    return match
