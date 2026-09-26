"""Normalize a Claude answer, from the API or from claude.ai, into one shape.

Both instruments in experiment 009 reduce to the same record::

    {
      "answer_text":    str,        # the text blocks, joined
      "cited_urls":     [str],      # URLs cited inline, first-seen order, unique
      "evaluated_urls": [str],      # URLs the searches returned, first-seen order, unique
      "search_queries": [str],      # the model's own search strings, in order
      "n_searches":     int,
      "stop_reason":    str | None,
      "model":          str | None,
      "source":         "api" | "claude_ai_export",
      "warnings":       [str],
    }

API semantics mirror ``packages/core/src/services/claude-direct.ts`` in the
spyglasses repo, so a study number means the same thing as a product number:

- ``extractSourcesAndQueries``: ``server_tool_use`` blocks with
  ``name == "web_search"`` give the queries (``input.query``);
  ``web_search_tool_result`` blocks give the retrieved results, keeping items
  of ``type == "web_search_result"`` with a string ``url``, deduplicated by
  exact URL in first-seen order. Those are the *evaluated* URLs.
- ``extractInlineCitedUrls``: every text block's ``citations[].url``. Those
  are the *cited* URLs. Production keeps duplicates and normalizes later; here
  they are deduplicated by exact URL, first-seen order, and normalization is
  left to the analysis pipeline.
- ``extractMarkdownFromContent``: the answer is the text blocks joined with no
  separator.

Arms that also attach ``web_fetch`` get ``fetched_urls`` (the ``url`` of each
``web_fetch_tool_result`` of type ``web_fetch_result``, first-seen order,
unique) and ``n_fetches`` (``server_tool_use`` blocks named ``web_fetch``).
Production attaches no fetch tool, so there is no production counterpart.

A turn that stopped on ``pause_turn`` is continued by re-sending it, and the
continuation's content follows the paused content. ``from_api_message``
therefore accepts a list of messages and reads their content as one sequence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")


def _unique(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if isinstance(url, str) and url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _as_dict(obj) -> dict:
    """Accept SDK objects as well as dicts."""
    if isinstance(obj, Mapping):
        return dict(obj)
    for attr in ("to_dict", "model_dump"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            return fn()
    raise TypeError(f"cannot read {type(obj).__name__} as a message")


# ------------------------------------------------------------------ API


def _api_blocks(messages: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    for msg in messages:
        blocks.extend(b for b in (msg.get("content") or []) if isinstance(b, Mapping))
    return blocks


def from_api_message(msg) -> dict:
    """Normalize one Messages API response, or a paused turn plus continuations.

    ``msg`` is a response dict (``Message.to_dict()``), an SDK ``Message``, or a
    list of either in turn order.
    """
    messages = [_as_dict(m) for m in (msg if isinstance(msg, list) else [msg])]
    if not messages:
        raise ValueError("no messages")
    blocks = _api_blocks(messages)
    warnings: list[str] = []

    answer_parts: list[str] = []
    cited: list[str] = []
    queries: list[str] = []
    evaluated: list[str] = []
    other_server_tools: list[str] = []
    fetched: list[str] = []
    fetch_calls = 0
    search_errors = 0
    fetch_errors = 0

    for block in blocks:
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str):
            answer_parts.append(block["text"])
            for citation in block.get("citations") or []:
                if isinstance(citation, Mapping) and isinstance(citation.get("url"), str):
                    cited.append(citation["url"])
        elif kind == "server_tool_use":
            if block.get("name") == "web_search":
                query = (block.get("input") or {}).get("query")
                if isinstance(query, str) and query.strip():
                    queries.append(query)
            elif block.get("name") == "web_fetch":
                fetch_calls += 1
            else:
                other_server_tools.append(str(block.get("name")))
        elif kind == "web_fetch_tool_result":
            inner = block.get("content")
            if isinstance(inner, Mapping) and inner.get("type") == "web_fetch_result":
                if isinstance(inner.get("url"), str):
                    fetched.append(inner["url"])
            else:
                # web_fetch_tool_result_error / web_fetch_tool_error (url_not_accessible, ...)
                fetch_errors += 1
                code = inner.get("error_code") if isinstance(inner, Mapping) else None
                warnings.append(f"web_fetch error: {code}")
        elif kind == "web_search_tool_result":
            inner = block.get("content")
            if not isinstance(inner, list):
                # web_search_tool_result_error (max_uses_exceeded, too_many_requests, ...)
                search_errors += 1
                code = inner.get("error_code") if isinstance(inner, Mapping) else None
                warnings.append(f"web_search error: {code}")
                continue
            for item in inner:
                if (
                    isinstance(item, Mapping)
                    and item.get("type") == "web_search_result"
                    and isinstance(item.get("url"), str)
                ):
                    evaluated.append(item["url"])

    billed = 0
    for m in messages:
        server = (m.get("usage") or {}).get("server_tool_use") or {}
        billed += int(server.get("web_search_requests") or 0)

    if other_server_tools:
        warnings.append(f"other server tools used: {sorted(set(other_server_tools))}")

    return {
        "answer_text": "".join(answer_parts),
        "cited_urls": _unique(cited),
        "evaluated_urls": _unique(evaluated),
        "search_queries": queries,
        # One server_tool_use block is one search; fall back to the billed count
        # when a tool version reports searches without echoing the blocks.
        "n_searches": len(queries) or billed,
        "web_search_requests": billed,
        "n_search_errors": search_errors,
        # Pages opened with the web_fetch server tool (arms that attach it).
        "fetched_urls": _unique(fetched),
        "n_fetches": fetch_calls,
        "n_fetch_errors": fetch_errors,
        "n_turns": len(messages),
        "stop_reason": messages[-1].get("stop_reason"),
        "model": messages[0].get("model"),
        "source": "api",
        "warnings": warnings,
    }


# ------------------------------------------------------- claude.ai export

# TODO(exp009 pilot): the claude.ai data-export schema below is inferred, not
# verified. Confirm every field against a real conversations.json in the pilot
# (plan step 2a) and update this parser plus tests/test_claude_answers.py:
#   - where citations live (text-block ``citations[]``; ``url`` at top level or
#     under ``details``) and whether they survive the export at all
#   - the search tool's name(s) in ``tool_use`` / ``tool_result`` (web_search,
#     web_search_fast, web_fetch)
#   - the result item shape (``type: "knowledge"`` with ``url``)
#   - whether ``content`` is empty on older messages (then only ``text`` exists)

#: Tool names treated as web search in the export. claude.ai offers
#: ``web_search_fast`` next to ``web_search`` (leaked prompt, 2026-09-22).
EXPORT_SEARCH_TOOLS = frozenset({"web_search", "web_search_fast"})


def _export_citation_url(citation) -> str | None:
    if not isinstance(citation, Mapping):
        return None
    for holder in (citation, citation.get("details") or {}, citation.get("source") or {}):
        if isinstance(holder, Mapping) and isinstance(holder.get("url"), str):
            return holder["url"]
    sources = citation.get("sources")
    if isinstance(sources, list):
        for src in sources:
            if isinstance(src, Mapping) and isinstance(src.get("url"), str):
                return src["url"]
    return None


def _export_result_urls(content) -> list[str]:
    urls: list[str] = []
    if not isinstance(content, list):
        return urls
    for item in content:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url") or (item.get("metadata") or {}).get("url")
        if isinstance(url, str) and url.startswith("http"):
            urls.append(url)
    return urls


def first_human_text(conversation: Mapping) -> str | None:
    """The first human message's text (used to match a chat to its prompt)."""
    for m in conversation.get("chat_messages") or []:
        if not isinstance(m, Mapping) or m.get("sender") != "human":
            continue
        text = m.get("text")
        if isinstance(text, str) and text.strip():
            return text
        parts = [
            b.get("text")
            for b in m.get("content") or []
            if isinstance(b, Mapping) and b.get("type") == "text"
        ]
        joined = "".join(p for p in parts if isinstance(p, str))
        return joined or None
    return None


def from_claude_export(conversation: Mapping) -> dict:
    """Normalize one conversation from a claude.ai data export.

    Reads every assistant message in the conversation (the protocol allows one
    prompt and one answer per chat, so there is normally exactly one).
    Tolerates missing fields; anything it had to guess goes into ``warnings``.
    """
    warnings: list[str] = []
    messages = [m for m in conversation.get("chat_messages") or [] if isinstance(m, Mapping)]
    assistant = [m for m in messages if m.get("sender") == "assistant"]
    humans = [m for m in messages if m.get("sender") == "human"]
    if not assistant:
        warnings.append("no assistant message")
    if len(assistant) > 1:
        warnings.append(f"{len(assistant)} assistant messages (protocol expects 1)")
    if len(humans) > 1:
        warnings.append(f"{len(humans)} human messages (protocol expects 1)")

    answer_parts: list[str] = []
    cited: list[str] = []
    queries: list[str] = []
    evaluated: list[str] = []
    other_tools: list[str] = []
    saw_citation_field = False

    for m in assistant:
        content = m.get("content")
        if not isinstance(content, list) or not content:
            text = m.get("text")
            if isinstance(text, str):
                answer_parts.append(text)
                warnings.append("assistant message had no content blocks; used text")
            continue
        for block in content:
            if not isinstance(block, Mapping):
                continue
            kind = block.get("type")
            if kind == "text" and isinstance(block.get("text"), str):
                answer_parts.append(block["text"])
                if "citations" in block:
                    saw_citation_field = True
                for citation in block.get("citations") or []:
                    url = _export_citation_url(citation)
                    if url:
                        cited.append(url)
            elif kind == "tool_use":
                name = block.get("name")
                if name in EXPORT_SEARCH_TOOLS:
                    query = (block.get("input") or {}).get("query")
                    if isinstance(query, str) and query.strip():
                        queries.append(query)
                else:
                    other_tools.append(str(name))
            elif kind == "tool_result":
                if block.get("name") in EXPORT_SEARCH_TOOLS:
                    evaluated.extend(_export_result_urls(block.get("content")))

    answer_text = "".join(answer_parts)
    cited_source = "citations"
    if not cited:
        md_links = _MD_LINK_RE.findall(answer_text)
        if md_links:
            cited = md_links
            cited_source = "markdown_links"
            warnings.append("no structured citations; cited_urls taken from markdown links")
        elif assistant and not saw_citation_field:
            warnings.append("no citations field on any text block")
    if other_tools:
        warnings.append(f"other tools used: {sorted(set(other_tools))}")

    return {
        "answer_text": answer_text,
        "cited_urls": _unique(cited),
        "cited_urls_source": cited_source,
        "evaluated_urls": _unique(evaluated),
        "search_queries": queries,
        "n_searches": len(queries),
        "stop_reason": (assistant[-1].get("stop_reason") if assistant else None),
        "model": conversation.get("model")
        or next((m.get("model") for m in assistant if m.get("model")), None),
        "source": "claude_ai_export",
        "conversation_uuid": conversation.get("uuid"),
        "conversation_name": conversation.get("name"),
        "created_at": conversation.get("created_at"),
        "warnings": warnings,
    }
