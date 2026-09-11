"""Experiment 008 domain scoring — the labels every claim in that study rests on.

The pipeline lives outside the installed package (experiments are scripts, not
library code), so the module is loaded from its path; ``scoring`` imports its
siblings ``brands`` and ``common``, which is why the pipeline directory goes
on ``sys.path`` first.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PIPELINE = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "008-brand-domain-knowledge"
    / "pipeline"
)
sys.path.insert(0, str(PIPELINE))
scoring = importlib.import_module("scoring")
brands = importlib.import_module("brands")
annotations = importlib.import_module("annotations")


@pytest.fixture(scope="module")
def scorers() -> dict:
    return scoring.build_scorers(brands.DRAFT_PANEL)


def score(scorers: dict, slug: str, host: str) -> tuple[str, str]:
    return scorers[slug].score_host(host)


# ------------------------------------------------------------ GoTo (tier C)


@pytest.mark.parametrize(
    ("host", "label", "kind"),
    [
        ("goto.com", "correct", ""),
        ("www.goto.com", "correct", ""),
        ("support.goto.com", "correct", ""),
        ("logmein.com", "stale", "stale_old_domain"),
        # Another live domain in the brand's own orbit — a real site, but not
        # the canonical one and not the frozen old one.
        ("gotomypc.com", "wrong", "name_bearing_other"),
        ("logmeinrescue.com", "wrong", "name_bearing_other"),
        # A competitor: not a claim about GoTo's domain at all.
        ("teamviewer.com", "wrong", "third_party"),
    ],
)
def test_goto_labels(scorers, host, label, kind):
    assert score(scorers, "goto", host) == (label, kind)


# ------------------------------------------------------------ Meta (tier C)


def test_meta_old_domain_family_is_stale(scorers):
    """The panel lists about.fb.com, so the whole fb.com family is stale."""
    assert score(scorers, "meta", "about.fb.com") == ("stale", "stale_old_domain")
    assert score(scorers, "meta", "fb.com") == ("stale", "stale_old_domain")
    assert score(scorers, "meta", "facebook.com") == ("stale", "stale_old_domain")


def test_meta_name_bearing_and_correct(scorers):
    assert score(scorers, "meta", "investor.atmeta.com") == ("wrong", "name_bearing_other")
    assert score(scorers, "meta", "about.meta.com") == ("correct", "")


# ------------------------------------------------ Clockwise / Paymo (guesses)


def test_clockwise_morphological_guess(scorers):
    """getclockwise.com is canonical; clockwise.com is the frozen guess."""
    assert score(scorers, "clockwise", "getclockwise.com") == ("correct", "")
    assert score(scorers, "clockwise", "clockwise.com") == ("wrong", "morphological_guess")


def test_paymo_guess_beats_name_bearing(scorers):
    """paymo.com is in expected_guess, so it scores as the guess, not as
    'some other domain carrying the name' — the frozen set wins."""
    assert score(scorers, "paymo", "paymoapp.com") == ("correct", "")
    assert score(scorers, "paymo", "paymo.com") == ("wrong", "morphological_guess")


def test_bose_name_bearing(scorers):
    assert score(scorers, "bose", "boseprofessional.com") == ("wrong", "name_bearing_other")


def test_single_letter_brand_does_not_match_every_domain(scorers):
    """Tier-C brand 'X' must not make box.com a name-bearing domain."""
    assert score(scorers, "x", "box.com") == ("wrong", "third_party")
    assert score(scorers, "x", "twitter.com") == ("stale", "stale_old_domain")


# --------------------------------------------- Audit D attribution (human)


def test_attribution_is_the_signed_human_judgment():
    """Jim's 2026-09-11 sign-off, applied verbatim — never inferred."""
    # The brand's own orbit: an investor domain, a regional domain.
    assert annotations.attribution("Meta", "atmeta.com") == "own_property"
    assert annotations.attribution("Sony", "sony.co.jp") == "own_property"
    # A different company that happens to share the name.
    assert annotations.attribution("Amie", "amieapp.com") == "other_company"


def test_attribution_defaults_to_unreviewed():
    """A domain nobody has ruled on must surface, not pass silently."""
    assert annotations.attribution("Motion", "motionapp.com") == "unreviewed"
    # Right domain, wrong brand: the ruling is per (brand, domain) pair.
    assert annotations.attribution("Bose", "atmeta.com") == "unreviewed"
    assert annotations.attribution("Meta", "") == "unreviewed"


def test_signed_table_is_dated_and_covers_only_name_bearing_domains():
    assert annotations.SIGNED_ON == "2026-09-11"
    assert len(annotations.AUDIT_D_ATTRIBUTION) == 8
    values = set(annotations.AUDIT_D_ATTRIBUTION.values())
    assert values == {"own_property", "other_company"}


# ------------------------------------------------------------- extraction


def search_action(**action) -> dict:
    return {"type": "web_search_call", "action": {"type": "search", **action}}


def test_queries_and_query_are_not_double_counted():
    """action.query repeats queries[0]; counting both would inflate fan-out."""
    response = {
        "output": [
            search_action(
                query="site:goto.com pricing",
                queries=["site:goto.com pricing", "site:logmein.com legacy"],
            ),
            search_action(query="site:gotomypc.com support"),  # no queries list
        ]
    }
    assert scoring.search_queries(response) == [
        "site:goto.com pricing",
        "site:logmein.com legacy",
        "site:gotomypc.com support",
    ]
    hosts, malformed = scoring.site_hosts(response)
    assert hosts == ["goto.com", "logmein.com", "gotomypc.com"]
    assert malformed == []


def test_non_search_actions_contribute_no_queries():
    response = {
        "output": [
            {"type": "web_search_call", "action": {"type": "open_page",
                                                   "url": "https://goto.com/"}},
            {"type": "web_search_call", "action": {"type": "find_in_page"}},
        ]
    }
    assert scoring.search_queries(response) == []
    assert scoring.site_hosts(response) == ([], [])


def test_malformed_site_token_is_reported_not_scored():
    response = {"output": [search_action(queries=["site:productguide? Avaza competitors"])]}
    hosts, malformed = scoring.site_hosts(response)
    assert hosts == []
    assert malformed == ["productguide"]  # normalize_host drops the "?"


def test_third_party_site_query_is_not_the_commitment(scorers):
    """A comparison prompt opening on a competitor made no claim about Stripe.

    The primary outcome is the first BRAND-ATTRIBUTABLE site: query, so the
    competitor search is counted (n_site_third_party) but never scored as the
    call's wrong domain.
    """
    response = {
        "output": [
            search_action(queries=["site:adyen.com pricing", "site:stripe.com pricing"]),
        ]
    }
    call, _ = scoring.score_call(response, scorers["stripe"])
    assert call["first_search_domain_any"] == "adyen.com"   # raw first, robustness (e)
    assert call["first_any_correct"] == 0
    assert call["first_site_domain"] == "stripe.com"        # primary
    assert call["first_site_label"] == "correct"
    assert call["first_site_correct"] == 1
    assert call["n_site_third_party"] == 1
    assert call["emitted_site_query"] == call["emitted_brand_site_query"] == 1


def test_only_third_party_site_queries_is_non_emitting(scorers):
    """No brand-attributable search at all: 'none', out of the analysis set."""
    response = {
        "output": [search_action(queries=["site:vrbo.com fees", "site:booking.com fees"])]
    }
    call, observations = scoring.score_call(response, scorers["airbnb"])
    assert call["emitted_site_query"] == 1
    assert call["emitted_brand_site_query"] == 0
    assert call["first_site_label"] == "none"
    assert call["first_site_domain"] == ""
    assert call["first_site_correct"] == call["first_site_own_error"] == 0
    assert call["first_search_domain_any"] == "vrbo.com"
    assert call["n_site_queries"] == 2
    assert call["n_site_attributable"] == 0
    assert len(observations) == 2


def test_frozen_candidate_set_is_the_external_baseline(scorers):
    """K = old_domains + expected_guess minus the truth; K <= 1 is not separable."""
    by_name = {b.canonical: b for b in brands.DRAFT_PANEL}
    assert scoring.frozen_candidate_set(by_name["Meta"]) == {"facebook.com", "fb.com"}
    # GoTo's only candidate is its old domain — a repeated stored error and a
    # repeated guess are the same observation for this brand.
    assert scoring.frozen_candidate_set(by_name["GoTo"]) == {"logmein.com"}
    # Notion's expected_guess IS its true domain, so nothing but the old one.
    assert scoring.frozen_candidate_set(by_name["Notion"]) == {"notion.so"}
    # Tier A brands have neither: the instrument cannot express a wrong domain.
    assert scoring.frozen_candidate_set(by_name["Sony"]) == frozenset()


def test_score_call_first_commitment_and_counters(scorers):
    """The call-level outcome is the FIRST site: query, with any_* counters."""
    response = {
        "model": "gpt-5.6-terra",
        "created_at": 1788359879,
        "usage": {"input_tokens": 100, "output_tokens": 10},
        "output": [
            search_action(
                queries=["site:about.fb.com news", "site:meta.com quest"],
                sources=[{"type": "url", "url": "https://about.fb.com/news/x"}],
            ),
            search_action(queries=["site:investor.atmeta.com results"]),
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Meta is a social media company.",
                        "annotations": [
                            {"type": "url_citation", "url": "https://www.meta.com/quest/"},
                            {"type": "file_citation", "url": "ignored"},
                        ],
                    }
                ],
            },
        ],
    }
    call, observations = scoring.score_call(response, scorers["meta"])
    assert call["first_site_domain"] == "fb.com"   # attributable AND first
    assert call["first_search_domain_any"] == "fb.com"
    assert call["emitted_brand_site_query"] == 1
    assert call["first_site_label"] == "stale"
    assert call["first_site_error_kind"] == "stale_old_domain"
    assert call["first_site_correct"] == 0
    assert call["first_site_own_error"] == 1
    assert (call["any_stale"], call["any_correct"], call["any_name_bearing"]) == (1, 1, 1)
    assert call["n_site_queries"] == 3
    assert call["n_site_stale"] == call["n_site_correct"] == call["n_site_name_bearing"] == 1
    assert call["any_wrong_incl_stale"] == 1
    assert call["consulted_domains"] == "fb.com"
    assert call["cited_domains"] == "meta.com"
    assert call["n_cited"] == 1
    assert [o["position"] for o in observations] == [0, 1, 2]
    assert call["answer_word_count"] == 6
