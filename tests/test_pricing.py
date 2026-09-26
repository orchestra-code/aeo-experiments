"""Claude API cost arithmetic: per-component prices, batch discount, cache TTL split."""

import pytest

from aeo_research.pricing import (
    PRICES,
    WEB_SEARCH_USD,
    cost_from_usage,
    price_row,
    sum_usage,
)


def test_plain_input_output_prices():
    cost = cost_from_usage("claude-sonnet-5", {"input_tokens": 1_000_000, "output_tokens": 100_000})
    assert cost["input"] == pytest.approx(2.0)
    assert cost["output"] == pytest.approx(1.0)
    assert cost["total"] == pytest.approx(3.0)
    assert cost["batch"] is False


def test_batch_halves_every_token_category_but_not_search():
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
        "cache_creation_input_tokens": 2_000_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 1_000_000,
            "ephemeral_1h_input_tokens": 1_000_000,
        },
        "server_tool_use": {"web_search_requests": 4},
    }
    rt = cost_from_usage("claude-opus-5-5", usage, batch=False)
    bt = cost_from_usage("claude-opus-5-5", usage, batch=True)
    row = PRICES["claude-opus-5-5"]
    assert rt["input"] == pytest.approx(row["input"])
    assert rt["cache_write_5m"] == pytest.approx(row["cache_write_5m"])
    assert rt["cache_write_1h"] == pytest.approx(row["cache_write_1h"])
    assert rt["cache_read"] == pytest.approx(row["cache_read"])
    for comp in ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read"):
        assert bt[comp] == pytest.approx(rt[comp] / 2)
    assert bt["web_search"] == rt["web_search"] == pytest.approx(4 * WEB_SEARCH_USD)
    assert rt["total"] == pytest.approx(4 + 20 + 5 + 8 + 0.20 + 0.04)
    assert bt["total"] == pytest.approx((4 + 20 + 5 + 8 + 0.20) / 2 + 0.04)


def test_cache_writes_without_ttl_split_price_as_5m():
    usage = {"cache_creation_input_tokens": 1_000_000}
    cost = cost_from_usage("claude-haiku-4-5", usage)
    assert cost["cache_write_5m"] == pytest.approx(1.25)
    assert cost["cache_write_1h"] == 0
    # An all-zero split next to a nonzero total is treated the same way.
    usage["cache_creation"] = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}
    assert cost_from_usage("claude-haiku-4-5", usage)["cache_write_5m"] == pytest.approx(1.25)


def test_missing_and_null_fields_are_zero():
    cost = cost_from_usage(
        "claude-sonnet-5",
        {"input_tokens": None, "output_tokens": 10, "server_tool_use": None, "cache_creation": None},
    )
    assert cost["total"] == pytest.approx(10 * 10 / 1_000_000)


def test_dated_snapshot_resolves_to_alias_and_longest_match_wins():
    assert price_row("claude-haiku-4-5-20251001") is PRICES["claude-haiku-4-5"]
    assert price_row("claude-opus-5-5") is PRICES["claude-opus-5-5"]
    assert price_row("claude-opus-5-20260101") is PRICES["claude-opus-5"]
    with pytest.raises(KeyError):
        price_row("gpt-5.6-terra")


def test_sum_usage_prices_like_the_parts():
    a = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 300,
        "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 200},
        "server_tool_use": {"web_search_requests": 3},
    }
    b = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 300,
         "cache_creation_input_tokens": 40}
    total = sum_usage([a, b])
    assert total["server_tool_use"]["web_search_requests"] == 3
    assert total["cache_creation"]["ephemeral_5m_input_tokens"] == 140
    parts = (cost_from_usage("claude-opus-5-5", a)["total"]
             + cost_from_usage("claude-opus-5-5", b)["total"])
    assert cost_from_usage("claude-opus-5-5", total)["total"] == pytest.approx(parts)
