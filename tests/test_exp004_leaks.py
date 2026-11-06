"""Experiment 004 leak adaptation: deterministic, and no tool syntax survives.

The fixtures are synthetic: they copy the pinned files' section headings and
block markers (which the adapters require) with made-up text, so no leak text is
committed. The real files are checked too when the gitignored raw data exists.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "experiments" / "004-api-vs-ui" / "harness"
sys.path.insert(0, str(HARNESS))
spec = importlib.util.spec_from_file_location("exp004_leaks", HARNESS / "leaks.py")
leaks = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = leaks
spec.loader.exec_module(leaks)

DAY = "2026-11-05"


def synthetic_chatgpt() -> str:
    body = {
        "## web": "",
        "### Description": "Use this tool to look things up on the web.",
        "### web Tool Usage and Triggering Rules": "",
        "#### Examples of different commands in this tool:": (
            "* slow: `slow|<q>|<recency?>`\n* product: `product|<search?>`\n"
            "```\nfast|example query\ngenui_run|widget|{}\n```"),
        "#### Tips and Requirements for Using the Web Tool": (
            "* You can search with two engines: `slow` and `fast`.\n"
            "* Consider `slow` when `fast` will not do.\n"
            "* For recent queries include \"recency\" in one (`fast` or `slow`).\n"
            "  - Common defaults: recency=1 for today.\n"
            "* If sources are stale, search again before finalizing.\n"
            "* Use `click` to follow links."),
        "#### When to use this web tool, and when not to": "Search when it helps the answer.",
        "### GenUI Widget Library": "Use genui_search for weather.",
        "### Example `genui_search` calls": "```\ngenui_search|weather\n```",
        "### Example `genui_run` calls": "```\ngenui_run|timer|{}\n```",
        "### Sources": ("Use the active spec for citations and rich UI formatting.\n"
                        "Results expose ids like 【turn0search1】 from \"web.run\".\n"
                        "  - News: 【turn0news1】\nCite statements from sources."),
        "### Product recommendation + shopping UI policy": (
            "Call `product` command when the user shops for goods.\n"
            "- Use `product` command plus (`fast` or `slow`) at once.\n"
            "- If results are weak, search again."),
        "### Local business search + UI policy": "Call `business` when local results help.",
        "### Reddit guidance": "- Draw on community threads.",
        "### Safety & Rules": ("Do not use `image` command records for these cases:\n"
                               "  - Low-value visuals.\nCopyright/word limits:\n* Cite sources."),
        "### Extra User Information": "User memory may be available.",
        "### Tool definitions": "// open|<ref_id>\n// schema for the tool",
    }
    return "\n".join(f"{h}\n{b}\n" for h, b in body.items())


def synthetic_gemini() -> str:
    return "\n".join([
        "# Saved Information", "Saved notes go here.", "", "[placeholder]", "",
        "**Capabilities**", "* Core Model: an example model.", "**End of Capabilities**", "",
        "`<system_instructions>`", "", "You are Gemini. Be clear.", "",
        "**I. Response Guiding Principles**", "* **Direct Opening:** lead with the answer.", "",
        "`<workflow>`", "1. **Gather:** When visual, always include image retrieval.",
        "5. **Follow-Up:**", "- **Path A:** next steps -> `<ElicitationsGroup>`.",
        "- **Path C:** omit follow-ups.", "`</workflow>`", "",
        "`<lmdx_syntax_protocol>`", "**Law 1:** `<Step title=\"x\">`", "`</lmdx_syntax_protocol>`",
        "", "`<tool_strategies>`", "Call tools when unsure.", "", "### Image Retrieval",
        "Use `image_agent:fetch_images` for pictures.", "", "`</tool_strategies>`", "",
        "`<format_selection>`", "**Markdown is your default.** Reach for a component rarely.",
        "**Visual elements:**", "- **Basekit components** help scanning.", "`</format_selection>`",
        "", "`<layout_rules>`", "**Flat siblings.** widgets.", "`</layout_rules>`", "",
        "`<component_library>`", "### `<Image>`", "```xml", "<Image src=\"t\" />", "```",
        "`</component_library>`", "", "`<examples>`", "`<example title=\"Markdown Only\">`",
        "**User:** tips?", "`</example>`", "`<example title=\"Image + Basekit Components\">`",
        "`<Image src=\"image_agent_tag_1\" />`", "`</example>`",
        "`<example title=\"Interactive Widget + FollowUp\">`", "```json",
        "{\"widgetSpec\": {}}", "```", "`</example>`", "`</examples>`", "",
        "`</system_instructions>`", "", "`<context>`", "",
        "It is Sunday, September 13, 2026 here.", "",
        "The user is in Somewhere, Nowhere.", "", "`</context>`", "",
        "# Tools", "", "## google:search", "```json", "{\"name\": \"google:search\"}", "```",
    ])


@pytest.mark.parametrize("platform,make", [("chatgpt", synthetic_chatgpt), ("gemini", synthetic_gemini)])
def test_adaptation_is_deterministic(platform, make):
    fn = leaks.ADAPTERS[platform]
    a, info_a = fn(make(), DAY)
    b, info_b = fn(make(), DAY)
    assert a == b and info_a == info_b
    assert a.encode() == b.encode()


@pytest.mark.parametrize("platform,make", [("chatgpt", synthetic_chatgpt), ("gemini", synthetic_gemini)])
def test_no_tool_syntax_survives(platform, make):
    raw = make()
    assert leaks.TOOL_SYNTAX.search(raw)  # the fixture does carry tool syntax
    text, _ = leaks.ADAPTERS[platform](raw, DAY)
    assert not leaks.TOOL_SYNTAX.findall(text)


def test_chatgpt_rules():
    text, info = leaks.adapt_chatgpt(synthetic_chatgpt(), DAY)
    assert text.startswith(f"{leaks.CHATGPT_IDENTITY}\nCurrent date: {DAY}\n")
    assert "### GenUI Widget Library" in info["dropped_sections"]
    assert "### Tool definitions" in info["dropped_sections"]
    assert "### Extra User Information" in info["dropped_sections"]
    assert "### Sources" in info["kept_sections"]
    # rule 3: a dropped tool's name becomes the web search tool
    assert "Call the web search tool when the user shops" in text
    assert "Call the web search tool when local results help" in text
    # rule 2: engine choice, recency field, click, image ops and combine-two-tools lines go
    for gone in ("`slow`", "`fast`", "recency=", "`click`", "`image`", "Low-value visuals",
                 "at once", "rich UI", "user memory"):
        assert gone not in text
    # kept guidance stays word for word
    assert "* If sources are stale, search again before finalizing." in text
    assert "Cite statements from sources." in text


def test_chatgpt_refuses_unknown_sections():
    with pytest.raises(SystemExit):
        leaks.adapt_chatgpt(synthetic_chatgpt() + "\n### A New Section\ntext\n", DAY)
    with pytest.raises(SystemExit):
        leaks.adapt_chatgpt(synthetic_chatgpt().replace("### Reddit guidance", "### Reddit"), DAY)


def test_gemini_rules():
    text, info = leaks.adapt_gemini(synthetic_gemini(), DAY)
    assert "Capabilities" not in text and "Core Model" not in text
    assert "placeholder" not in text and "Saved Information" not in text
    assert "It is Thursday, November 5, 2026 here." in text
    assert "September" not in text
    assert "Somewhere" not in text  # the leaker's location is per-user context
    assert "When visual, always include the web search tool" in text
    assert "Path A" not in text and "Path C" in text
    assert "**Markdown is your default.**" in text
    assert "Visual elements" not in text  # orphaned lead after its items were dropped
    assert "Markdown Only" in text and "Interactive Widget" not in text
    assert "# Tools" not in text and "google:search" not in text
    assert "**Capabilities**" in info["dropped_sections"]


def test_gemini_requires_markers():
    with pytest.raises(SystemExit):
        leaks.adapt_gemini(synthetic_gemini().replace("**End of Capabilities**", ""), DAY)


def test_dates_follow_the_run_date():
    a, _ = leaks.adapt_gemini(synthetic_gemini(), "2026-11-06")
    assert "Friday, November 6, 2026" in a
    c, _ = leaks.adapt_chatgpt(synthetic_chatgpt(), "2026-11-06")
    assert "Current date: 2026-11-06" in c


@pytest.mark.parametrize("platform", ["chatgpt", "gemini"])
def test_real_leaks_when_present(platform):
    path = leaks.raw_path(platform)
    if not path.exists():
        pytest.skip("leak sources not fetched (gitignored raw data)")
    raw = path.read_text()
    a, _ = leaks.ADAPTERS[platform](raw, DAY)
    b, _ = leaks.ADAPTERS[platform](raw, DAY)
    assert a == b
    assert not leaks.TOOL_SYNTAX.findall(a)


def test_answer_syntax_check():
    for hit in ("fast|crm tools", "see 【turn0search3】", "<FollowUp label=\"x\" />",
                "genui_run|w", "{\"widgetSpec\": 1}"):
        assert leaks.TOOL_SYNTAX.search(hit), hit
    # "genui" must not match inside an ordinary word that starts with it (seen in the Gemini leak)
    for clean in ("A " + "genu" + "ine comparison of tools.", "Fast setup | good support", "<b>bold</b>",
                  "Images (screenshots) help."):
        assert not leaks.TOOL_SYNTAX.search(clean), clean
