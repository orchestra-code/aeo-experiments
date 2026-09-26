"""Dollar cost of a Claude Messages API call, computed from its ``usage`` block.

Prices are USD per million tokens, as published for each model when experiment
009 was designed (2026-09). The Batches API bills every token category at half
price, and the discount stacks with the cache multipliers (a batch cache read
on Opus 5.5 is 0.5 x 0.20). Web search is billed per search, $10 per 1,000,
and the batch discount does not apply to it.

``usage`` is the Messages API ``usage`` object as a dict:

- ``input_tokens``: uncached input after the last cache breakpoint
- ``output_tokens``: output, thinking included
- ``cache_read_input_tokens``: input served from cache
- ``cache_creation_input_tokens``: input written to cache (all TTLs)
- ``cache_creation.ephemeral_5m_input_tokens`` / ``ephemeral_1h_input_tokens``:
  the same writes split by TTL, when the API reports the split. Without the
  split, every write is priced as a 5-minute write.
- ``server_tool_use.web_search_requests``: billed searches
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

#: USD per million tokens.
PRICES: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {
        "input": 4.0,
        "output": 20.0,
        "cache_write_5m": 5.0,
        "cache_write_1h": 8.0,
        "cache_read": 0.20,
    },
    "claude-opus-5": {
        "input": 5.0,
        "output": 25.0,
        "cache_write_5m": 6.25,
        "cache_write_1h": 10.0,
        "cache_read": 0.50,
    },
    "claude-sonnet-5": {
        "input": 2.0,
        "output": 10.0,
        "cache_write_5m": 2.50,
        "cache_write_1h": 4.0,
        "cache_read": 0.20,
    },
    "claude-haiku-4-5": {
        "input": 1.0,
        "output": 5.0,
        "cache_write_5m": 1.25,
        "cache_write_1h": 2.0,
        "cache_read": 0.10,
    },
}

BATCH_MULTIPLIER = 0.5
WEB_SEARCH_USD = 0.01  # per search; not discounted by batch

TOKEN_COMPONENTS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")


def price_row(model: str) -> dict[str, float]:
    """Prices for ``model``; dated snapshots resolve to their alias.

    ``claude-haiku-4-5-20251001`` resolves to ``claude-haiku-4-5``. The longest
    matching alias wins, so ``claude-opus-5-5`` never resolves to
    ``claude-opus-5``.
    """
    if model in PRICES:
        return PRICES[model]
    matches = [k for k in PRICES if model.startswith(k + "-")]
    if not matches:
        raise KeyError(f"no price for model {model!r}")
    return PRICES[max(matches, key=len)]


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def token_counts(usage: Mapping) -> dict[str, int]:
    """Billable token counts per price component, plus the search count."""
    creation = usage.get("cache_creation") or {}
    total_write = _int(usage.get("cache_creation_input_tokens"))
    w5 = _int(creation.get("ephemeral_5m_input_tokens"))
    w1h = _int(creation.get("ephemeral_1h_input_tokens"))
    if not creation or (w5 + w1h == 0 and total_write > 0):
        # No TTL split reported: price every write as a 5-minute write.
        w5, w1h = total_write, 0
    server = usage.get("server_tool_use") or {}
    return {
        "input": _int(usage.get("input_tokens")),
        "output": _int(usage.get("output_tokens")),
        "cache_write_5m": w5,
        "cache_write_1h": w1h,
        "cache_read": _int(usage.get("cache_read_input_tokens")),
        "web_search_requests": _int(server.get("web_search_requests")),
    }


def cost_from_usage(model: str, usage: Mapping, batch: bool = False) -> dict:
    """USD cost of one response, by component, with ``total``.

    Returns ``{"input", "output", "cache_write_5m", "cache_write_1h",
    "cache_read", "web_search", "total"}`` in dollars, plus ``tokens`` (the
    counts priced) and ``batch``.
    """
    row = price_row(model)
    counts = token_counts(usage)
    mult = BATCH_MULTIPLIER if batch else 1.0
    out: dict = {
        comp: counts[comp] * row[comp] / 1_000_000 * mult for comp in TOKEN_COMPONENTS
    }
    out["web_search"] = counts["web_search_requests"] * WEB_SEARCH_USD
    out["total"] = sum(out[c] for c in (*TOKEN_COMPONENTS, "web_search"))
    out["tokens"] = counts
    out["batch"] = batch
    return out


def sum_usage(usages: Iterable[Mapping]) -> dict:
    """Add several ``usage`` blocks (e.g. a paused turn and its continuations).

    Keeps the TTL split and the search count, so the sum prices the same as
    the parts.
    """
    total = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
        "server_tool_use": {"web_search_requests": 0},
    }
    for usage in usages:
        counts = token_counts(usage)
        total["input_tokens"] += counts["input"]
        total["output_tokens"] += counts["output"]
        total["cache_read_input_tokens"] += counts["cache_read"]
        total["cache_creation_input_tokens"] += counts["cache_write_5m"] + counts["cache_write_1h"]
        total["cache_creation"]["ephemeral_5m_input_tokens"] += counts["cache_write_5m"]
        total["cache_creation"]["ephemeral_1h_input_tokens"] += counts["cache_write_1h"]
        total["server_tool_use"]["web_search_requests"] += counts["web_search_requests"]
    return total
