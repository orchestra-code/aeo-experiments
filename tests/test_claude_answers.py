"""Claude answer normalization: API responses (incl. pause_turn) and claude.ai exports.

The export fixtures follow the INFERRED export schema; see the TODO in
aeo_research/claude_answers.py. Replace them with a trimmed real export once
the pilot confirms the shape.
"""

from aeo_research.claude_answers import first_human_text, from_api_message, from_claude_export


def search_pair(tool_id, query, urls):
    return [
        {"type": "server_tool_use", "id": tool_id, "name": "web_search", "input": {"query": query}},
        {
            "type": "web_search_tool_result",
            "tool_use_id": tool_id,
            "content": [
                {"type": "web_search_result", "url": u, "title": u, "encrypted_content": "x"}
                for u in urls
            ],
        },
    ]


def text(t, cited=()):
    return {
        "type": "text",
        "text": t,
        "citations": [
            {"type": "web_search_result_location", "url": u, "title": "", "cited_text": ""}
            for u in cited
        ]
        or None,
    }


def message(content, stop="end_turn", searches=0, model="claude-sonnet-5"):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "stop_reason": stop,
        "content": content,
        "usage": {"input_tokens": 1, "output_tokens": 1,
                  "server_tool_use": {"web_search_requests": searches}},
    }


def test_api_message_extracts_queries_evaluated_and_cited():
    content = [
        {"type": "thinking", "thinking": "", "signature": "s"},
        *search_pair("srvtoolu_1", "best crm small saas", ["https://a.com/1", "https://b.com/2"]),
        *search_pair("srvtoolu_2", "crm billing integration", ["https://b.com/2", "https://c.com/3"]),
        text("Here are options. "),
        text("Option A is good.", cited=["https://a.com/1", "https://a.com/1"]),
        text(" Option C too.", cited=["https://c.com/3"]),
    ]
    out = from_api_message(message(content, searches=2))
    assert out["search_queries"] == ["best crm small saas", "crm billing integration"]
    assert out["n_searches"] == 2
    assert out["evaluated_urls"] == ["https://a.com/1", "https://b.com/2", "https://c.com/3"]
    assert out["cited_urls"] == ["https://a.com/1", "https://c.com/3"]
    assert out["answer_text"] == "Here are options. Option A is good. Option C too."
    assert out["stop_reason"] == "end_turn"
    assert out["model"] == "claude-sonnet-5"
    assert out["source"] == "api"
    assert out["warnings"] == []


def test_pause_turn_continuations_are_read_as_one_answer():
    first = message(search_pair("s1", "q1", ["https://a.com"]), stop="pause_turn", searches=1)
    second = message(
        [*search_pair("s2", "q2", ["https://b.com"]), text("Done.", cited=["https://b.com"])],
        searches=1,
    )
    out = from_api_message([first, second])
    assert out["search_queries"] == ["q1", "q2"]
    assert out["web_search_requests"] == 2
    assert out["n_turns"] == 2
    assert out["stop_reason"] == "end_turn"
    assert out["cited_urls"] == ["https://b.com"]
    assert out["evaluated_urls"] == ["https://a.com", "https://b.com"]


def test_search_error_and_other_server_tools_are_reported_not_crashing():
    content = [
        {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "q"}},
        {"type": "web_search_tool_result", "tool_use_id": "s1",
         "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}},
        {"type": "server_tool_use", "id": "c1", "name": "code_execution", "input": {}},
        text("No results."),
    ]
    out = from_api_message(message(content))
    assert out["n_search_errors"] == 1
    assert out["evaluated_urls"] == []
    assert any("max_uses_exceeded" in w for w in out["warnings"])
    assert any("code_execution" in w for w in out["warnings"])


def test_n_searches_falls_back_to_billed_count():
    out = from_api_message(message([text("hi")], searches=3))
    assert out["n_searches"] == 3


def export_conversation():
    return {
        "uuid": "conv-1",
        "name": "w1-ui_default-b2b_01",
        "created_at": "2026-09-30T14:00:00Z",
        "chat_messages": [
            {"sender": "human", "text": "What CRM should we pick?", "content": [
                {"type": "text", "text": "What CRM should we pick?"}]},
            {
                "sender": "assistant",
                "text": "",
                "content": [
                    {"type": "tool_use", "name": "web_search", "input": {"query": "best crm"}},
                    {"type": "tool_result", "name": "web_search", "content": [
                        {"type": "knowledge", "title": "A", "url": "https://a.com/x"},
                        {"type": "knowledge", "title": "B", "url": "https://b.com/y",
                         "metadata": {"site_domain": "b.com"}},
                        {"type": "knowledge", "title": "A again", "url": "https://a.com/x"},
                    ]},
                    {"type": "tool_use", "name": "web_search_fast", "input": {"query": "crm pricing"}},
                    {"type": "text", "text": "Consider A.", "citations": [
                        {"uuid": "c1", "details": {"type": "web_search_citation",
                                                   "url": "https://a.com/x"}},
                        {"url": "https://b.com/y"},
                    ]},
                ],
            },
        ],
    }


def test_export_parser_reads_inferred_shape():
    out = from_claude_export(export_conversation())
    assert out["search_queries"] == ["best crm", "crm pricing"]
    assert out["n_searches"] == 2
    assert out["evaluated_urls"] == ["https://a.com/x", "https://b.com/y"]
    assert out["cited_urls"] == ["https://a.com/x", "https://b.com/y"]
    assert out["cited_urls_source"] == "citations"
    assert out["answer_text"] == "Consider A."
    assert out["source"] == "claude_ai_export"
    assert out["conversation_name"] == "w1-ui_default-b2b_01"
    assert out["warnings"] == []
    assert first_human_text(export_conversation()) == "What CRM should we pick?"


def test_export_parser_tolerates_missing_fields_and_falls_back_to_markdown_links():
    conv = {
        "chat_messages": [
            {"sender": "human", "text": "hi"},
            {"sender": "assistant", "text": "See [A](https://a.com) and [B](https://b.com)."},
        ]
    }
    out = from_claude_export(conv)
    assert out["cited_urls"] == ["https://a.com", "https://b.com"]
    assert out["cited_urls_source"] == "markdown_links"
    assert out["n_searches"] == 0
    assert out["warnings"]


def test_export_parser_flags_protocol_violations():
    conv = export_conversation()
    conv["chat_messages"] += [
        {"sender": "human", "text": "follow up"},
        {"sender": "assistant", "content": [{"type": "text", "text": " More."}]},
    ]
    out = from_claude_export(conv)
    assert any("2 assistant messages" in w for w in out["warnings"])
    assert any("2 human messages" in w for w in out["warnings"])
    assert from_claude_export({})["warnings"] == ["no assistant message"]


def test_web_fetch_results_are_recorded_separately():
    content = [
        *search_pair("s1", "q", ["https://a.com/1"]),
        {"type": "server_tool_use", "id": "f1", "name": "web_fetch",
         "input": {"url": "https://a.com/1"}},
        {"type": "web_fetch_tool_result", "tool_use_id": "f1",
         "content": {"type": "web_fetch_result", "url": "https://a.com/1",
                     "content": {"type": "document", "source": {"type": "text", "data": "x"}},
                     "retrieved_at": "2026-09-26T12:00:00Z"}},
        {"type": "server_tool_use", "id": "f2", "name": "web_fetch",
         "input": {"url": "https://b.com"}},
        {"type": "web_fetch_tool_result", "tool_use_id": "f2",
         "content": {"type": "web_fetch_tool_result_error", "error_code": "url_not_accessible"}},
        text("A.", cited=["https://a.com/1"]),
    ]
    out = from_api_message(message(content, searches=1))
    assert out["fetched_urls"] == ["https://a.com/1"]
    assert out["n_fetches"] == 2
    assert out["n_fetch_errors"] == 1
    assert out["n_searches"] == 1
    assert out["evaluated_urls"] == ["https://a.com/1"]
    assert not any("other server tools" in w for w in out["warnings"])
    assert any("url_not_accessible" in w for w in out["warnings"])
