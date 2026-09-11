"""Outcome scoring for experiment 008 — the definitions Audit B quotes.

Everything the study measures is derived here, from the raw OpenAI Responses
payload, so there is exactly one definition of each label and stages 01-05
and the unit tests all exercise the same code path.

Extraction
----------
``output[]`` items of type ``web_search_call`` carry an ``action``. For
``action.type == "search"`` the model's own search strings are in
``action.queries`` (a list); ``action.query`` repeats the FIRST of them, so
using both would double count — ``search_queries`` uses ``queries`` when
present and falls back to ``[query]``. ``action.sources[]`` (present when the
``include`` parameter worked) are the URLs the search returned; message
annotations of type ``url_citation`` are the URLs the answer cited.

Labels (spec §2 Audit B)
------------------------
For one consulted host, against the frozen panel entry for the brand asked
about:

- ``correct``  registered domain == registered domain of ``true_domain``
- ``stale``    the host, or its registered domain, is one of ``old_domains``
               (Meta lists ``about.fb.com``, so the whole ``fb.com`` family
               counts as stale, not as a wrong other domain)
- ``wrong``    anything else

and for a non-correct host, an ``error_kind``:

- ``stale_old_domain``    label == stale
- ``morphological_guess`` registered domain in the frozen ``expected_guess``
                          token set (``brandname.com``-style)
- ``name_bearing_other``  the registered domain's leftmost label contains the
                          brand's name or one of its aliases, letters and
                          digits only (gotomypc.com and logmeinrescue.com for
                          GoTo, atmeta.com for Meta, boseprofessional.com for
                          Bose) — a real site in the brand's own orbit
- ``third_party``         a domain that does not carry the brand's name at all
                          (a competitor or a reference site). The comparison
                          template produces these BY DESIGN; they are not
                          errors about the asked brand and are excluded from
                          the own-domain error set that H2/H3 analyse.
- ``nonexistent``         assigned at audit time only, to stale / guess /
                          name-bearing domains that fail to resolve, with the
                          check date recorded (02_audit.py --resolve).

``name_bearing_other`` + ``third_party`` together are the frozen spec's
``other_real`` bucket; the split is an analysis-time refinement recorded in
the Deviations section of results/audit.txt.

Call-level outcome (spec §5: "the domain of a site: fan-out naming the brand")
------------------------------------------------------------------------------
The primary outcome is the first BRAND-ATTRIBUTABLE ``site:`` query — the
first one whose target is a claim about the asked brand's own domain
(``correct``, ``stale``, ``morphological_guess``, ``name_bearing_other``).
A ``third_party`` ``site:`` query is definitionally not about the asked
brand, so it cannot be the call's commitment: the comparison template makes
the model open on a competitor's site by design (adyen.com while answering
about Stripe, vrbo.com about Airbnb), and counting that as a wrong domain
would measure the template, not the model's belief.

``first_site_label`` is therefore the label of the first brand-attributable
``site:`` query, or ``"none"`` when the call emitted only third-party ones;
such calls are NON-emitting for this outcome and drop out of the analysis
set, which H1 reports as a fourth funnel stage. The raw first ``site:``
query of any kind is kept as ``first_search_domain_any`` /
``first_any_label`` for robustness (e) and for the released dataset, so both
readings are reconstructable.

``any_*`` and ``n_site_*`` counters range over every ``site:`` query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from brands import BrandEntry
from common import join_list, normalize_host, registered_domain, slug

#: A site: operator token: everything up to the next whitespace.
SITE_RE = re.compile(r"site:(\S+)", re.IGNORECASE)
#: A host we are willing to score: labels, a dot, an alphabetic TLD.
HOST_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$")
#: Name tokens shorter than this are not used for name-bearing matching
#: (brand "X" would otherwise make every domain containing an x name-bearing).
MIN_NAME_TOKEN = 3

_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def alnum(name: str) -> str:
    """``GoTo (formerly LogMeIn)`` -> ``gotoformerlylogmein``."""
    return _ALNUM_RE.sub("", name.lower())


# --------------------------------------------------------------- scorer


@dataclass(frozen=True)
class BrandScorer:
    """The frozen panel entry, pre-normalized for scoring."""

    brand_slug: str
    canonical: str
    tier: str
    truth: str
    old_hosts: frozenset[str]
    old_domains: frozenset[str]
    guesses: frozenset[str]
    name_tokens: tuple[str, ...]

    def label(self, host: str) -> str:
        host = normalize_host(host)
        if registered_domain(host) == self.truth:
            return "correct"
        if host in self.old_hosts or registered_domain(host) in self.old_domains:
            return "stale"
        return "wrong"

    def error_kind(self, host: str, label: str | None = None) -> str:
        label = label or self.label(host)
        if label == "correct":
            return ""
        if label == "stale":
            return "stale_old_domain"
        domain = registered_domain(host)
        if domain in self.guesses:
            return "morphological_guess"
        leftmost = alnum(domain.split(".")[0])
        if any(token in leftmost for token in self.name_tokens):
            return "name_bearing_other"
        return "third_party"

    def score_host(self, host: str) -> tuple[str, str]:
        label = self.label(host)
        return label, self.error_kind(host, label)


def scorer_for(entry: BrandEntry) -> BrandScorer:
    truth = registered_domain(entry.true_domain)
    old_hosts = {normalize_host(d) for d in entry.old_domains}
    tokens = {alnum(entry.canonical), *(alnum(a) for a in entry.aliases)}
    return BrandScorer(
        brand_slug=slug(entry.canonical),
        canonical=entry.canonical,
        tier=entry.tier,
        truth=truth,
        old_hosts=frozenset(old_hosts),
        old_domains=frozenset(registered_domain(d) for d in old_hosts),
        guesses=frozenset(registered_domain(g) for g in entry.expected_guess),
        name_tokens=tuple(sorted(t for t in tokens if len(t) >= MIN_NAME_TOKEN)),
    )


def build_scorers(panel) -> dict[str, BrandScorer]:
    return {slug(b.canonical): scorer_for(b) for b in panel}


def frozen_candidate_set(entry: BrandEntry) -> frozenset[str]:
    """The wrong domains the FROZEN instrument says are plausible for a brand.

    ``old_domains`` (what a stale stored association would emit) plus
    ``expected_guess`` (what name morphology would generate), as registered
    domains, minus the true domain. This is the only external, pre-registered
    notion of "how many wrong domains could this brand have had", so it is the
    baseline the post-hoc H2 sensitivity uses (1/K under uniform guessing) and
    the set the pure-guess dry-run world samples from. K = 0 or 1 means the
    instrument cannot separate a repeated stored error from a repeated guess
    for that brand — reported, never papered over.
    """
    truth = registered_domain(entry.true_domain)
    candidates = {registered_domain(d) for d in entry.old_domains}
    candidates |= {registered_domain(g) for g in entry.expected_guess}
    return frozenset(candidates - {truth})


# ------------------------------------------------------------ extraction


def output_items(response: dict) -> list[dict]:
    return response.get("output") or []


def search_actions(response: dict) -> list[dict]:
    return [
        o.get("action") or {}
        for o in output_items(response)
        if o.get("type") == "web_search_call"
    ]


def search_queries(response: dict) -> list[str]:
    """Every search string the model typed, in output order, counted once.

    ``action.query`` is the first element of ``action.queries``; when both are
    present only ``queries`` is read, so a parallel search of four queries
    counts as four, not five.
    """
    out: list[str] = []
    for action in search_actions(response):
        if action.get("type") != "search":
            continue
        queries = action.get("queries")
        if queries is None:
            query = action.get("query")
            queries = [query] if query else []
        out.extend(q for q in queries if q)
    return out


def site_hosts(response: dict) -> tuple[list[str], list[str]]:
    """Hosts named by ``site:`` operators, in emission order.

    Returns (scorable hosts, malformed tokens) — the model occasionally types
    a ``site:`` operator with no host at all (``site:productguide?``), which
    is reported in Audit A rather than silently scored.
    """
    hosts: list[str] = []
    malformed: list[str] = []
    for query in search_queries(response):
        for token in SITE_RE.findall(query):
            host = normalize_host(token.strip("\"'"))
            (hosts if HOST_RE.match(host) else malformed).append(host or token)
    return hosts, malformed


def source_domains(response: dict) -> list[str]:
    """Registered domains of ``action.sources[]``, first-seen order."""
    out: list[str] = []
    for action in search_actions(response):
        for source in action.get("sources") or []:
            domain = registered_domain(source.get("url") or "")
            if domain and domain not in out:
                out.append(domain)
    return out


def cited_domains(response: dict) -> list[str]:
    """Registered domains of ``url_citation`` annotations, first-seen order."""
    out: list[str] = []
    for item in output_items(response):
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            for annotation in content.get("annotations") or []:
                if annotation.get("type") != "url_citation":
                    continue
                domain = registered_domain(annotation.get("url") or "")
                if domain and domain not in out:
                    out.append(domain)
    return out


def answer_text(response: dict) -> str:
    """Answer markdown — interim only, never published."""
    parts = []
    for item in output_items(response):
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)


# ----------------------------------------------------------- call scoring


def score_call(response: dict, scorer: BrandScorer) -> tuple[dict, list[dict]]:
    """Call-level outcome columns + one observation row per ``site:`` query."""
    actions = search_actions(response)
    hosts, malformed = site_hosts(response)

    observations = []
    for position, host in enumerate(hosts):
        label, kind = scorer.score_host(host)
        observations.append(
            {
                "host": host,
                "registered_domain": registered_domain(host),
                "position": position,
                "label": label,
                "error_kind": kind,
            }
        )

    labels = [o["label"] for o in observations]
    kinds = [o["error_kind"] for o in observations]
    # Primary: the first site: query that is a claim about THIS brand.
    attributable = [o for o in observations if o["error_kind"] != "third_party"]
    first = attributable[0] if attributable else None
    first_any = observations[0] if observations else None
    # The first wrong domain the call named for this brand, wherever in the
    # call it appeared — the unit of the H4 wrong-domain agreement companion,
    # which would otherwise see only the handful of calls that OPENED wrong.
    first_error = next((o for o in attributable if o["label"] != "correct"), None)
    usage = response.get("usage") or {}
    text = answer_text(response)
    consulted = source_domains(response)
    cited = cited_domains(response)

    call = {
        "model": response.get("model"),
        "created_at": response.get("created_at"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "n_web_search_call": len(actions),
        "n_search_actions": sum(1 for a in actions if a.get("type") == "search"),
        "n_open_page": sum(1 for a in actions if a.get("type") == "open_page"),
        "n_queries": len(search_queries(response)),
        "n_site_queries": len(observations),
        "n_site_attributable": len(attributable),
        "n_malformed_site_tokens": len(malformed),
        "emitted_site_query": int(bool(observations)),
        #: Emission for the primary outcome: at least one site: query that is
        #: about the asked brand at all.
        "emitted_brand_site_query": int(bool(first)),
        "first_site_host": first["host"] if first else "",
        "first_site_domain": first["registered_domain"] if first else "",
        "first_site_label": first["label"] if first else "none",
        "first_site_error_kind": first["error_kind"] if first else "",
        "first_site_correct": int(bool(first) and first["label"] == "correct"),
        #: The model's first commitment about this brand was a wrong domain.
        "first_site_own_error": int(bool(first) and first["label"] != "correct"),
        #: Robustness (e): the raw first site: query, competitor sites included.
        "first_error_domain": first_error["registered_domain"] if first_error else "",
        "first_error_kind_in_call": first_error["error_kind"] if first_error else "",
        "first_search_domain_any": first_any["registered_domain"] if first_any else "",
        "first_any_label": first_any["label"] if first_any else "none",
        "first_any_error_kind": first_any["error_kind"] if first_any else "",
        "first_any_correct": int(bool(first_any) and first_any["label"] == "correct"),
        "any_correct": int("correct" in labels),
        "any_stale": int("stale" in labels),
        "any_guess": int("morphological_guess" in kinds),
        "any_name_bearing": int("name_bearing_other" in kinds),
        #: Pre-declared robustness outcome: ANY non-correct, non-third-party
        #: site: query anywhere in the call (not just the first).
        "any_wrong_incl_stale": int(
            any(o["label"] != "correct" and o["error_kind"] != "third_party"
                for o in observations)
        ),
        "n_site_correct": labels.count("correct"),
        "n_site_stale": labels.count("stale"),
        "n_site_guess": kinds.count("morphological_guess"),
        "n_site_name_bearing": kinds.count("name_bearing_other"),
        "n_site_third_party": kinds.count("third_party"),
        "site_domains": join_list([o["registered_domain"] for o in observations]),
        "consulted_domains": join_list(consulted),
        "cited_domains": join_list(cited),
        "n_consulted": len(consulted),
        "n_cited": len(cited),
        "answer_word_count": len(text.split()),
        "answer_md": text,
        "fanout_raw": join_list(search_queries(response)),
    }
    return call, observations
