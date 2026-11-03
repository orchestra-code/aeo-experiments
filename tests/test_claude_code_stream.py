"""Claude Code stream-json normalization, on the event shapes seen in the 2026-11-03 smoke run."""

from aeo_research.claude_answers import from_claude_code_stream

INIT = {
    "type": "system",
    "subtype": "init",
    "tools": ["WebFetch", "WebSearch"],
    "mcp_servers": [],
    "model": "claude-opus-5-5",
    "apiKeySource": "none",
    "claude_code_version": "2.1.316",
}


def call(name, **tool_input):
    return {
        "type": "assistant",
        "message": {
            "model": "claude-opus-5-5",
            "content": [{"type": "tool_use", "name": name, "input": tool_input}],
        },
    }


def search_result(*urls):
    return {
        "type": "user",
        "message": {"content": []},
        "tool_use_result": {
            "query": "q",
            "results": [
                {"tool_use_id": "t", "content": [{"title": u, "url": u} for u in urls]},
                "A summary from the backend, with https://not-a-result.example/ in its text.",
            ],
        },
    }


def rate(five, seven, status="allowed", overage=False):
    return {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": status,
            "isUsingOverage": overage,
            "unifiedWindows": {
                "five_hour": {"utilization": five},
                "seven_day": {"utilization": seven},
            },
        },
    }


def result(text, **extra):
    return {
        "type": "result",
        "is_error": False,
        "result": text,
        "stop_reason": "end_turn",
        "total_cost_usd": 0.37,
        "num_turns": 3,
        "duration_ms": 1000,
        "modelUsage": {
            "claude-opus-5-5": {"webSearchRequests": 0},
            "claude-haiku-5-5": {"webSearchRequests": 2},
        },
        **extra,
    }


def test_full_run_normalizes_to_the_shared_record():
    out = from_claude_code_stream(
        [
            INIT,
            rate(0.01, 0.15),
            call("WebSearch", query="best crm", mode="standard"),
            search_result("https://a.example/x", "https://b.example/y", "https://a.example/x"),
            call("WebFetch", url="https://a.example/x", prompt="p"),
            rate(0.02, 0.16),
            result("See [A](https://a.example/x), and https://c.example/z."),
        ]
    )
    assert out["evaluated_urls"] == ["https://a.example/x", "https://b.example/y"]
    assert out["cited_urls"] == ["https://a.example/x", "https://c.example/z"]
    assert out["cited_urls_source"] == "answer_links"
    assert out["search_queries"] == ["best crm"]
    assert (out["n_searches"], out["n_fetches"], out["n_backend_searches"]) == (1, 1, 2)
    assert out["fetched_urls"] == ["https://a.example/x"]
    assert out["main_models"] == ["claude-opus-5-5"]
    assert out["init"]["apiKeySource"] == "none"
    assert out["rate_limits"]["first"]["five_hour"] == 0.01
    assert out["rate_limits"]["last"]["seven_day"] == 0.16
    assert out["warnings"] == []


def test_backend_summary_text_is_not_an_evaluated_url():
    out = from_claude_code_stream([INIT, search_result("https://a.example/"), result("x")])
    assert out["evaluated_urls"] == ["https://a.example/"]


def test_missing_result_event_warns_and_leaves_the_answer_empty():
    out = from_claude_code_stream([INIT, call("WebSearch", query="q")])
    assert out["answer_text"] == ""
    assert out["warnings"] == ["no_result_event"]
    assert out["rate_limits"] is None


def test_error_result_never_counts_as_an_answer():
    out = from_claude_code_stream(
        [INIT, {"type": "result", "is_error": True, "result": "API Error: 400"}]
    )
    assert out["answer_text"] == ""
    assert out["cited_urls"] == []
    assert out["warnings"] == ["result_is_error"]


def test_empty_answer_is_flagged():
    assert from_claude_code_stream([INIT, result("")])["warnings"] == ["empty_answer"]
