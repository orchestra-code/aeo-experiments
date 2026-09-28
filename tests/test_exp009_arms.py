"""Experiment 009 harness: request shapes per arm, the production reproduction,
leak-prompt trimming and slots, prompt validation, and the cost guard.

The harness lives outside the installed package, so its directory goes on
``sys.path`` (the 008 scoring tests do the same).
"""

from __future__ import annotations

import importlib
import re
import sys
from datetime import date
from pathlib import Path

import pytest

HARNESS = (
    Path(__file__).resolve().parents[1] / "experiments" / "009-claude-model-fidelity" / "harness"
)
sys.path.insert(0, str(HARNESS))
arms = importlib.import_module("arms")
leak_prompt = importlib.import_module("leak_prompt")
make_prompts = importlib.import_module("make_prompts")
collect = importlib.import_module("collect_anthropic")
make_ui_sheet = importlib.import_module("make_ui_sheet")

SPYGLASSES = Path(__file__).resolve().parents[2] / "spyglasses"
RUN_DATE = date(2026, 9, 29)
LOC = {"type": "approximate", "city": "Boston", "region": "Massachusetts", "country": "US"}
TEMPLATE = (
    "# claude_behavior\nThe date is {{RUN_DATE_LONG}}. Today is {{RUN_DATE}}.\n"
    "User's approximate location: {{USER_LOCATION}}. Only if relevant.\nEnd.\n"
)


def params(arm, **kw):
    return arms.build_params(arm, "best crm?", RUN_DATE, TEMPLATE, LOC, **kw)


# ------------------------------------------------------------- production
# The production prompt text never appears in this repo: shape tests use a
# fake prompt, and the byte-for-byte check reads the spyglasses checkout.

prod_prompt = importlib.import_module("prod_prompt")
FAKE_PROD = {"system": "FAKE SYSTEM PROMPT", "user_suffix": "\n\nFAKE SUFFIX."}
FAKE_TS = (
    "export function buildDiscoveryPrompts(query, location) {\n"
    "\tconst systemPrompt = `Line one.\n\nLine two.`;\n"
    "\tlet userPrompt = `${query}\\n\\nPlease do the thing.`;\n}\n"
)


@pytest.fixture
def fake_prod(monkeypatch):
    monkeypatch.setattr(prod_prompt, "load", lambda *a, **k: dict(FAKE_PROD))


def test_sonnet5_prod_matches_production_request_shape(fake_prod):
    p = params("sonnet5_prod")
    assert list(p) == ["model", "max_tokens", "system", "messages", "tools"]
    assert p["model"] == "claude-sonnet-5"
    assert p["max_tokens"] == 16000
    assert p["system"] == FAKE_PROD["system"]
    assert p["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
    assert p["messages"] == [{"role": "user", "content": "best crm?" + FAKE_PROD["user_suffix"]}]
    for absent in ("thinking", "output_config", "cache_control", "temperature"):
        assert absent not in p


def test_prod_prompt_parser_and_loader(tmp_path):
    system, suffix = prod_prompt.parse_source(FAKE_TS)
    assert system == "Line one.\n\nLine two."
    assert suffix == "\n\nPlease do the thing."
    with pytest.raises(SystemExit, match="prod_prompt.py"):
        prod_prompt.load(tmp_path / "missing.json")
    repo = tmp_path / "spyglasses"
    src = repo / prod_prompt.SOURCE_REL
    src.parent.mkdir(parents=True)
    src.write_text(FAKE_TS)
    out = tmp_path / "prod.json"
    rec = prod_prompt.extract(repo, out)
    assert prod_prompt.load(out) == rec
    assert rec["sha256"]["system"] == prod_prompt.sha256(system)


@pytest.mark.skipif(not SPYGLASSES.exists(), reason="spyglasses repo not checked out")
def test_extracted_prod_prompt_matches_spyglasses_source_byte_for_byte(tmp_path):
    src = (SPYGLASSES / prod_prompt.SOURCE_REL).read_text()
    seg = src[src.index("export function buildDiscoveryPrompts"):]
    system = re.search(r"const systemPrompt = `(.*?)`;", seg, re.S).group(1)
    user = re.search(r"let userPrompt = `(.*?)`;", seg, re.S).group(1)
    rec = prod_prompt.extract(SPYGLASSES, tmp_path / "prod.json")
    assert rec["system"] == system
    # JS template literal: \n escapes become newlines, ${query} is the prompt.
    assert "${query}" + rec["user_suffix"] == user.replace("\\n", "\n")
    if prod_prompt.OUT.exists():  # the copy the collector actually uses
        saved = prod_prompt.load()
        assert (saved["system"], saved["user_suffix"]) == (rec["system"], rec["user_suffix"])
    direct = (SPYGLASSES / "packages/core/src/services/claude-direct.ts").read_text()
    assert "maxSearches = 5" in direct and "maxTokens = 16000" in direct
    assert 'type: "web_search_20250305"' in direct


# ------------------------------------------------------------- research arms


def test_research_arm_common_shape():
    for name in ("opus55_leak", "opus55_plain", "sonnet5_plain", "sonnet5_leak_think",
                 "sonnet5_leak_low", "sonnet5_leak_nothink", "haiku45_leak"):
        p = params(name)
        assert p["max_tokens"] == 16000
        assert p["messages"] == [{"role": "user", "content": "best crm?"}]
        assert p["tools"] == [{"type": "web_search_20250305", "name": "web_search",
                               "max_uses": 10, "user_location": LOC}]
        assert p["cache_control"] == {"type": "ephemeral"}
        assert "temperature" not in p and "fallbacks" not in p
        if "thinking" in p:
            assert "budget_tokens" not in p["thinking"]


def test_per_arm_reasoning_and_system():
    o = params("opus55_leak")
    assert o["model"] == "claude-opus-5-5"
    assert o["output_config"] == {"effort": "medium"}
    assert "thinking" not in o  # Opus 5.5 cannot disable thinking; never send it
    assert o["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "system" not in params("opus55_plain")
    assert params("opus55_plain")["output_config"] == {"effort": "medium"}
    assert params("sonnet5_leak_think")["thinking"] == {"type": "adaptive"}
    assert "output_config" not in params("sonnet5_leak_think")
    assert params("sonnet5_leak_nothink")["thinking"] == {"type": "disabled"}
    sp = params("sonnet5_plain")
    assert sp["model"] == "claude-sonnet-5" and "system" not in sp
    assert sp["thinking"] == {"type": "adaptive"} and "output_config" not in sp
    h = params("haiku45_leak")
    assert h["model"] == "claude-haiku-4-5"
    assert "thinking" not in h and "output_config" not in h


def test_leak_slots_filled_in_system_text():
    text = params("sonnet5_leak_think")["system"][0]["text"]
    assert "Tuesday, September 29, 2026" in text
    assert "Today is September 29, 2026." in text
    assert "Boston, Massachusetts, US" in text
    assert "{{" not in text
    no_loc = arms.build_params("haiku45_leak", "q", RUN_DATE, TEMPLATE, None)
    assert "location" not in no_loc["system"][0]["text"]
    assert "user_location" not in no_loc["tools"][0]


def test_web_search_version_override():
    assert params("opus55_leak", web_search_version="20260209")["tools"][0]["type"] == (
        "web_search_20260209"
    )
    with pytest.raises(ValueError):
        params("haiku45_leak", web_search_version="20260209")
    with pytest.raises(ValueError):
        params("opus55_leak", web_search_version="20990101")


def test_parse_user_location():
    assert arms.parse_user_location("Boston, Massachusetts, us") == LOC
    assert arms.parse_user_location(None) is None


# ------------------------------------------------------------- leak trimming


def fake_leak() -> str:
    names = sorted(leak_prompt.KEEP_SECTIONS | leak_prompt.REMOVE_SECTIONS)
    parts = []
    for name in names:
        body = f"# {name}\n\ntext of {name}\n\n"
        if name == "search_instructions":
            body += ("keep this\n\n`<using_image_search_tool>`\nimages\n"
                     "`</using_image_search_tool>`\n\nYou also have `web_search_fast`, fast.\n"
                     "still fast\n\nafter fast\n\n")
        if name == "claude_behavior":
            body += "Date: Tuesday, September 22, 2026. Plain: September 22, 2026.\n\n"
        if name == "thinking_behavior":
            body += "think well\n\n`<userPreferences>`\nbe brief\n`</userPreferences>`\n"
        parts.append(body)
    parts.append("# Tools\n## web_search\n```json\n# not a heading\n{}\n```\n"
                 "The assistant is Claude, created by Anthropic.\n\n")
    parts.append("# anthropic_api_in_artifacts\nartifact api\n`<citation_instructions>`\ncite\n"
                 "`</citation_instructions>`\n\nUser's approximate location: "
                 "Reykjavík, Capital Region, IS. Only if relevant.\n")
    return "".join(parts)


def test_trim_keeps_behavior_and_citations_and_drops_tool_sections():
    full, trimmed, removed = leak_prompt.build_templates(fake_leak())
    assert "text of memory_filesystem" in full and "text of memory_filesystem" not in trimmed
    assert "keep this" in trimmed and "after fast" in trimmed
    assert "images" not in trimmed and "web_search_fast" not in trimmed
    assert "`<citation_instructions>`" in trimmed and "artifact api" not in trimmed
    assert "The assistant is Claude" in trimmed and "## web_search" not in trimmed
    assert "be brief" not in full and "be brief" not in trimmed  # per-user context, both
    assert "{{RUN_DATE_LONG}}" in trimmed and "{{RUN_DATE}}" in trimmed
    assert "{{USER_LOCATION}}" in trimmed
    labels = {r["section"] for r in removed}
    assert "memory_filesystem" in labels and "thinking_behavior/per-user context" in labels


def test_trim_refuses_unreviewed_sections():
    with pytest.raises(SystemExit):
        leak_prompt.build_templates(fake_leak() + "# brand_new_tool\nnew\n")


def test_split_sections_ignores_headings_inside_fences():
    names = [n for n, _ in leak_prompt.split_sections("# a\n```\n# b\n```\n# c\n")]
    assert names == ["a", "c"]


# ------------------------------------------------------------- prompts


def test_item_plan_is_deterministic():
    plan = make_prompts.item_plan()
    assert len(plan) == 40
    assert plan[0]["item_id"] == "b2b_01" and plan[0]["intent"] == "shortlist"
    assert plan[1]["intent"] == "evaluate" and plan[39]["item_id"] == "b2b_40"
    assert plan[39]["category"] == "applicant tracking system"


@pytest.mark.parametrize(
    "text,problem",
    [
        ("We are a 120-person fintech startup on Salesforce today; what are the best "
         "CRM options for a growing sales team like ours?", "brand term 'Salesforce'"),
        ("We are a US-based 50-person agency and need the best payroll options that "
         "handle contractors and full-time staff across several states.", "location term 'US'"),
        ("Too short, best?", "word count"),
        ("We need a tool that tracks inventory across several warehouses and flags "
         "stockouts early for our operations team.", "not a recommendation"),
        ("We are a 90-person startup in Denver and want the best expense management "
         "options for a team that travels constantly.", "capitalized token 'Denver'"),
    ],
)
def test_validate_catches(text, problem):
    assert any(p.startswith(problem) for p in make_prompts.validate(text, "CRM"))


def test_validate_passes_clean_prompt_with_lowercase_brand_words():
    text = ("I run a 300-person manufacturer and our sales teams need a CRM that plugs "
            "into our accounting software. What are the best options to shortlist?")
    assert make_prompts.validate(text, "CRM") == []


# ------------------------------------------------------------- collector


def test_custom_id_and_batch_prior():
    cid = collect.custom_id("sonnet5_leak_nothink", "b2b_01", 3)
    assert cid == "sonnet5_leak_nothink__b2b_01__w3"
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", cid)
    assert collect.prior_cost("opus55_leak", batch=False) == pytest.approx(0.35)
    assert collect.prior_cost("opus55_leak", batch=True) == pytest.approx(0.30 / 2 + 0.05)
    assert set(collect.PRIOR_USD) == set(arms.ARMS)


def test_ui_sheet_is_seeded_by_wave():
    prompts = [{"item_id": f"b2b_{i:02d}", "text": f"p{i}"} for i in range(1, 11)]
    a = make_ui_sheet.build_sheet(prompts, 1, ["ui_default", "ui_think"])
    b = make_ui_sheet.build_sheet(prompts, 1, ["ui_default", "ui_think"])
    c = make_ui_sheet.build_sheet(prompts, 2, ["ui_default", "ui_think"])
    assert a == b and a != c and len(a) == 20
    assert a[0]["chat_name"] == f"w1-{a[0]['arm']}-{a[0]['item_id']}"


# ------------------------------------------------------------- export ingest


def test_export_matching_by_name_then_prompt_text():
    ingest = importlib.import_module("ingest_claude_export")
    prompts = {"b2b_01": {"text": "best crm?"}, "b2b_02": {"text": "best ats?"}}

    def conv(uuid, name, text, created="2026-09-30T10:00:00Z"):
        return {"uuid": uuid, "name": name, "created_at": created,
                "chat_messages": [{"sender": "human", "text": text}]}

    convs = [
        conv("a", "w1-ui_default-b2b_01", "best crm?"),
        conv("b", "w1-ui_default-b2b_01", "best crm?", created="2026-09-30T11:00:00Z"),
        conv("c", "w1-ui_think-b2b_01", "best crm?"),
        conv("d", "Untitled", "best  ats?"),  # unnamed: both arms open -> ambiguous
        conv("e", "w2-ui_default-b2b_02", "best ats?"),  # other wave -> ignored
    ]
    matched, dups, ambiguous, ignored = ingest.match(
        convs, prompts, 1, ["ui_default", "ui_think"]
    )
    assert matched[("ui_default", "b2b_01")]["uuid"] == "a"
    assert dups == {("ui_default", "b2b_01"): ["a", "b"]}
    assert matched[("ui_think", "b2b_01")]["uuid"] == "c"
    assert len(ambiguous) == 1 and ignored == 1
    # With one arm, the unnamed chat is matched by its prompt text.
    matched, _, ambiguous, _ = ingest.match(convs[3:4], prompts, 1, ["ui_default"])
    assert matched[("ui_default", "b2b_02")]["uuid"] == "d" and not ambiguous


def test_clarifying_questions_score_the_first_reply_only():
    ingest = importlib.import_module("ingest_claude_export")

    def reply(text):
        return {"sender": "assistant", "content": [{"type": "text", "text": text}]}

    conv = {"uuid": "q", "name": "w1-ui_think-b2b_28", "chat_messages": [
        {"sender": "human", "text": "best sso?"},
        reply("Okta or Entra, depending on your stack."),
        {"sender": "human", "text": "Q: Platform?\nA: Microsoft 365"},
        reply("Use Entra ID."),
    ]}
    norm = ingest.normalize(conv)
    assert norm["clarifying_questions"] is True
    assert norm["answer_text"] == "Okta or Entra, depending on your stack."
    assert norm["full_chat"]["answer_text"].endswith("Use Entra ID.")
    assert "clarifying questions: scored the first reply only" in norm["warnings"]
    assert len(conv["chat_messages"]) == 4  # the stored conversation is untouched

    single = {"uuid": "s", "chat_messages": conv["chat_messages"][:2]}
    norm = ingest.normalize(single)
    assert norm["clarifying_questions"] is False and "full_chat" not in norm


def test_voided_chats_are_never_matched():
    ingest = importlib.import_module("ingest_claude_export")
    prompts = {"b2b_01": {"text": "best crm?"}}
    convs = [{"uuid": "v", "name": "w1-ui_default-b2b_01-void",
              "chat_messages": [{"sender": "human", "text": "best crm?"}]}]
    matched, _, _, ignored = ingest.match(convs, prompts, 1, ["ui_default"])
    assert matched == {} and ignored == 1


# ------------------------------------------------------------- pilot-only arms


def test_pilot_arms_are_excluded_from_all():
    assert arms.CORE_ARMS == ("opus55_plain", "opus55_leak", "sonnet5_plain",
                              "sonnet5_leak_think", "sonnet5_leak_low", "sonnet5_prod",
                              "haiku45_leak")
    assert set(arms.PILOT_ARMS) == {"sonnet5_leak_nothink", "opus55_leak_fetch",
                                    "opus55_leak_ws2026", "opus55_leak_raw"}
    assert collect.resolve_arms("all") == list(arms.CORE_ARMS)
    assert not set(arms.PILOT_ARMS) & set(collect.resolve_arms("all"))
    assert collect.resolve_arms("opus55_leak_raw") == ["opus55_leak_raw"]


def test_pilot_arm_shapes():
    low = params("sonnet5_leak_low")
    assert low["thinking"] == {"type": "adaptive"} and low["output_config"] == {"effort": "low"}
    fetch = params("opus55_leak_fetch")
    assert [t["type"] for t in fetch["tools"]] == ["web_search_20250305", "web_fetch_20260209"]
    assert fetch["tools"][1] == {"type": "web_fetch_20260209", "name": "web_fetch",
                                 "max_uses": 5, "max_content_tokens": 10000}
    assert not any("code_execution" in t["type"] for t in fetch["tools"])
    ws = params("opus55_leak_ws2026")
    assert [t["type"] for t in ws["tools"]] == ["web_search_20260209"]
    raw = params("opus55_leak_raw")
    assert raw["tools"] == params("opus55_leak")["tools"]
    assert arms.ARMS["opus55_leak_raw"].leak_variant == "raw"


# ------------------------------------------------------------- pilot report

pilot_report = importlib.import_module("pilot_report")


@pytest.mark.parametrize(
    "raw,canon",
    [
        ("Datadog APM", "datadog"),
        ("HubSpot Sales Hub", "hubspot"),
        ("Microsoft Dynamics 365 Business Central", "microsoft dynamics"),
        ("NetSuite", "oracle netsuite"),
        ("Rippling®", "rippling"),
        ("Dropbox Sign (formerly HelloSign)", "dropbox sign"),
        ("  Vanta ", "vanta"),
    ],
)
def test_canonical_brand(raw, canon):
    assert pilot_report.canonical_brand(raw) == canon


def test_pilot_domains_use_registered_domain():
    urls = ["https://www.g2.com/x?utm_source=a", "https://blog.hubspot.com/y",
            "https://news.bbc.co.uk/z"]
    assert pilot_report.domains(urls) == {"g2.com", "hubspot.com", "bbc.co.uk"}


def test_power_sim_brackets_the_band():
    eq = pilot_report.simulate_power(0.0, 0.5, 0.1, 0.1, reps=20, n_boot=200)
    far = pilot_report.simulate_power(0.3, 0.5, 0.1, 0.1, reps=20, n_boot=200)
    assert eq["p_equivalent"] >= 0.8
    assert far["p_equivalent"] == 0.0


def test_lexicon_extract_longest_first_case_modes_and_drops(tmp_path):
    lex = tmp_path / "lex.csv"
    lex.write_text(
        "canonical,aliases,category,decision,reason,match,n_answers\n"
        "acme,Acme|Acme Cloud Suite,CRM,keep,in category,ci,3\n"
        "close,Close,CRM,keep,in category,cs,2\n"
        "paysys,PaySys,CRM,drop,out of category: billing,ci,1\n"
        "acme,Acme,payroll,drop,out of category: ERP,ci,1\n"
    )
    pats = pilot_report.load_lexicon(lex)
    text = ("Consider **Close** or [Acme Cloud Suite](https://acme.com/x). If you close "
            "deals fast, ACME works; it syncs with PaySys.")
    assert pilot_report.lexicon_extract(text, pats["CRM"]) == ["close", "acme"]
    assert pilot_report.lexicon_extract(text, pats["payroll"]) == []
    amap = pilot_report.lexicon_alias_map(lex)
    assert pilot_report.haiku_via_lexicon(["PaySys", "Acme Cloud Suite", "Acme"], "CRM",
                                          amap) == ["acme"]


def test_strip_sources_drops_labelled_source_lists_only():
    strip = pilot_report.strip_sources
    listed = "Pick Acme.\n\n### Sources referenced:\n- beta.com review\n\n- Gamma blog\nNext step: call Acme."
    assert strip(listed) == "Pick Acme.\n\n\nNext step: call Acme."
    assert strip("Pick Acme.\n**Sources Referenced:** beta.com, Gamma\nDone.") == "Pick Acme.\n\nDone."
    assert strip("Pick Acme.\n## Sources\n1. beta.com") == "Pick Acme.\n"
    # Prose that starts with "Sources" is not a sources block.
    prose = "Sources for the table: Acme at $10.\nSources say Acme is fast."
    assert strip(prose) == prose
