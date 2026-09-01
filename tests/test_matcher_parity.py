"""Parity fixture for the Spyglasses competitor-named-query matcher port.

Mirrors, case for case, the TS suite at
``packages/core/src/utils/__tests__/competitor-named-query.test.ts``
(spyglasses commit ``3f6c332c``, PR #198). If a case changes there, it must
change here — the observational studies classify production rows with this
port and must agree with the product exactly.
"""

from aeo_research.brand_match import (
    CompetitorSource,
    build_competitor_named_query_matcher,
)

OUR_BRAND = ["Acme", "Acme Corporation", "acme.com"]

COMPETITORS = [
    CompetitorSource(id="c-globex", name="Globex", url="https://globex.com"),
    CompetitorSource(
        id="c-initech",
        name="Initech",
        aliases=["Initech Software", "ITCH"],
        url="https://www.initech.io/products",
    ),
]


def matcher(our_brand_terms=None, competitors=None):
    return build_competitor_named_query_matcher(
        OUR_BRAND if our_brand_terms is None else our_brand_terms,
        COMPETITORS if competitors is None else competitors,
    )


class TestExclusionPredicate:
    def test_flags_competitor_only(self):
        m = matcher()("globex pricing")
        assert m.names_competitor is True
        assert m.names_our_brand is False
        assert m.matched_competitor_names == ("Globex",)
        assert m.competitor_only is True

    def test_does_not_flag_comparison_naming_us_too(self):
        m = matcher()("acme vs globex for teams")
        assert m.names_competitor is True
        assert m.names_our_brand is True
        assert m.matched_competitor_names == ("Globex",)
        assert m.competitor_only is False

    def test_names_nobody(self):
        m = matcher()("best crm software 2026")
        assert m.names_competitor is False
        assert m.names_our_brand is False
        assert m.matched_competitor_names == ()
        assert m.competitor_only is False

    def test_names_only_us(self):
        m = matcher()("acme pricing")
        assert m.names_competitor is False
        assert m.names_our_brand is True
        assert m.competitor_only is False

    def test_reports_every_competitor_named(self):
        assert matcher()("globex vs initech").matched_competitor_names == (
            "Globex",
            "Initech",
        )


class TestTermBuilding:
    def test_matches_an_alias(self):
        assert matcher()("initech software onboarding").competitor_only is True

    def test_url_host_when_no_name(self):
        m = matcher(
            competitors=[
                CompetitorSource(id="c-1", name=None, url="https://umbrella.dev/pricing")
            ]
        )
        result = m("umbrella.dev pricing")
        assert result.competitor_only is True
        assert result.matched_competitor_names == ("umbrella.dev",)

    def test_bare_second_level_label_of_url(self):
        assert matcher()("umbrella roadmap").competitor_only is False
        m = matcher(
            competitors=[CompetitorSource(id="c-1", name=None, url="https://umbrella.dev")]
        )
        assert m("umbrella roadmap").competitor_only is True

    def test_strips_www_and_path(self):
        assert matcher()("initech.io api limits").competitor_only is True
        assert matcher()("www.initech.io api limits").competitor_only is True

    def test_expands_name_written_as_domain(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name="asana.com", url=None)])
        assert m("asana pricing").competitor_only is True

    def test_punctuated_name_is_not_a_hostname(self):
        m = matcher(
            competitors=[CompetitorSource(id="c-1", name="Umbrella, Inc.", url=None)]
        )
        assert m("umbrella, inc. reviews").competitor_only is True
        assert m("inc magazine").competitor_only is False

    def test_our_brand_label_from_domain_term(self):
        m = matcher(our_brand_terms=["acme.com"])
        result = m("acme vs globex")
        assert result.names_our_brand is True
        assert result.competitor_only is False

    def test_peer_pseudo_url_contributes_nothing(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name=None, url="peer:jane-doe")])
        assert m("jane doe consulting").competitor_only is False


class TestThreeCharFloor:
    def test_ignores_two_char_name(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name="HP", url=None)])
        assert m("hp printers").competitor_only is False

    def test_ignores_two_char_alias_keeps_name(self):
        m = matcher(
            competitors=[CompetitorSource(id="c-1", name="Globex", aliases=["GX"], url=None)]
        )
        assert m("gx pricing").competitor_only is False
        assert m("globex pricing").competitor_only is True

    def test_keeps_three_char_name(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name="IBM", url=None)])
        assert m("ibm watson pricing").competitor_only is True

    def test_fails_safe_on_two_part_public_suffix(self):
        m = matcher(
            competitors=[CompetitorSource(id="c-1", name=None, url="https://widgets.co.uk")]
        )
        assert m("widgets.co.uk pricing").competitor_only is True
        assert m("widgets pricing").competitor_only is False
        assert m("co working spaces").competitor_only is False


class TestWordBoundaries:
    def test_common_word_competitor_whole_word(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name="Monday", url=None)])
        assert m("monday deals").competitor_only is True

    def test_no_match_inside_longer_word(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name="Monday", url=None)])
        assert m("mondays off policy").competitor_only is False

    def test_no_substring_match(self):
        m = matcher(
            competitors=[CompetitorSource(id="c-1", name="Hive", url="https://hive.com")]
        )
        assert m("beehive management").competitor_only is False
        assert m("hive pricing").competitor_only is True

    def test_punctuation_is_a_boundary(self):
        assert matcher()("globex-pricing 2026").competitor_only is True
        assert matcher()("(globex) review").competitor_only is True

    def test_case_insensitive(self):
        assert matcher()("GLOBEX Enterprise Pricing").competitor_only is True


class TestNormalization:
    def test_fullwidth_query_vs_ascii_term(self):
        assert matcher()("Ｇｌｏｂｅｘ pricing").competitor_only is True

    def test_ascii_query_vs_fullwidth_term(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name="Ｇｌｏｂｅｘ", url=None)])
        assert m("globex pricing").competitor_only is True


class TestDegenerateContexts:
    def test_no_competitors_never_matches(self):
        m = matcher(competitors=[])
        result = m("globex pricing")
        assert result.names_competitor is False
        assert result.names_our_brand is False
        assert result.matched_competitor_names == ()
        assert result.competitor_only is False

    def test_all_terms_below_floor(self):
        m = matcher(competitors=[CompetitorSource(id="c-1", name="GX", url=None)])
        assert m("gx pricing").competitor_only is False

    def test_empty_or_missing_query(self):
        assert matcher()("").competitor_only is False
        assert matcher()("   ").competitor_only is False
        assert matcher()(None).competitor_only is False

    def test_tolerates_blank_and_none_brand_terms(self):
        m = matcher(our_brand_terms=[None, "", "   ", "Acme"])
        assert m("acme vs globex").names_our_brand is True

    def test_flags_competitor_with_no_brand_terms(self):
        m = matcher(our_brand_terms=[])
        assert m("globex pricing").competitor_only is True


class TestSiteScopeInteraction:
    def test_keeps_negation_query(self):
        assert matcher()("best crm -site:globex.com").competitor_only is False
        assert matcher()("best crm -site: globex.com").competitor_only is False

    def test_ignores_positive_site_operator_argument(self):
        assert matcher()("site:globex.com pricing").competitor_only is False

    def test_still_reads_rest_of_scoped_query(self):
        result = matcher()("site:reddit.com globex review")
        assert result.names_competitor is True
        assert result.competitor_only is True
