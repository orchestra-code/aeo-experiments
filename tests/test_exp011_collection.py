"""Experiment 011 collection: the mistakes that would silently corrupt the study's data."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "experiments" / "011-claude-code-fidelity" / "harness"


def load(name):
    spec = importlib.util.spec_from_file_location(f"exp011_{name}", HARNESS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


kit = load("sched_kit")
routine = load("ingest_routine")
export = load("ingest_claude_export")
sheet = load("make_ui_sheet")

ITEMS = {"b2b_01", "b2b_02"}


def chat(name, created="2026-11-03T18:00:00Z", uuid="u"):
    return {"name": name, "created_at": created, "uuid": uuid}


def test_chats_from_exp_009_never_enter_the_study():
    convs = [chat("w1-ui_default-b2b_01"), chat("e011-w1-ui_default-b2b_01", uuid="new")]
    matched, duplicates, refused = export.match(convs, 1, ITEMS)
    assert matched["b2b_01"]["uuid"] == "new"
    assert not duplicates
    assert not refused


def test_export_refuses_old_void_and_other_wave_chats():
    convs = [
        chat("e011-w1-ui_default-b2b_01", created="2026-09-28T12:00:00Z"),
        chat("e011-w1-ui_default-b2b_02-void"),
        chat("e011-w2-ui_default-b2b_02"),
    ]
    matched, _, refused = export.match(convs, 1, ITEMS)
    assert matched == {}
    assert len(refused) == 1
    assert "before the freeze" in refused[0]


def test_export_writes_neither_chat_when_two_share_a_name():
    convs = [chat("e011-w1-ui_default-b2b_01", uuid="a"), chat("e011-w1-ui_default-b2b_01", uuid="b")]
    matched, duplicates, _ = export.match(convs, 1, ITEMS)
    assert "b2b_01" not in matched
    assert duplicates == {"b2b_01": ["a", "b"]}


def test_sheet_names_match_the_export_rule_and_cover_every_prompt_once():
    prompts = [{"item_id": f"b2b_{i:02d}", "text": f"q{i}"} for i in range(1, 41)]
    rows = sheet.build_sheet(prompts, 1)
    assert sorted(r["item_id"] for r in rows) == sorted(p["item_id"] for p in prompts)
    assert all(export.NAME.match(r["chat_name"]) for r in rows)
    assert [r["item_id"] for r in rows] != [r["item_id"] for r in sheet.build_sheet(prompts, 2)]


def test_batches_cover_every_prompt_once_and_are_reproducible():
    ids = [f"b2b_{i:02d}" for i in range(1, 41)]
    first = kit.batches(1, ids)
    assert [len(b) for b in first] == [10, 10, 10, 10]
    assert sorted(i for b in first for i in b) == sorted(ids)
    assert first == kit.batches(1, list(reversed(ids)))
    assert first != kit.batches(2, ids)


def clean_routine(prompt):
    return {
        "mcp_connections": [],
        "derived_state": {"prompt": prompt},
        "job_config": {
            "ccr": {
                "session_context": {
                    "model": kit.MODEL,
                    "allowed_tools": list(kit.ALLOWED_TOOLS),
                    "disallowed_tools": list(kit.DISALLOWED_TOOLS),
                }
            }
        },
    }


def test_a_task_with_a_connector_or_other_prompt_must_not_fire():
    assert kit.routine_problems(clean_routine("p"), "p") == []
    attached = {**clean_routine("p"), "mcp_connections": [{"name": "Mail"}]}
    assert "connectors attached" in kit.routine_problems(attached, "p")[0]
    assert "prompt differs" in kit.routine_problems(clean_routine("other"), "p")[0]


def test_body_never_requests_a_connector_and_denies_notifications():
    body = kit.create_body(1, 1, ["b2b_01"], {"b2b_01": "q"}, "2026-11-03T18:00:00Z", "env_x")
    context = body["job_config"]["ccr"]["session_context"]
    assert "mcp_connections" not in body
    assert context["disallowed_tools"] == ["PushNotification"]
    assert "effort" not in context


def transcript(printed, report, tools=("ToolSearch", "WebSearch"), instruction=kit.INSTRUCTION_PREFIX):
    return [
        {
            "type": "user",
            "toolUseResult": {
                "toolsUsed": list(tools),
                "prompt": instruction + "A question",
                "handbackReport": {"text": report},
                "totalToolUseCount": 4,
                "resolvedModel": "claude-opus-5-5",
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": f"=== ANSWER b2b_01 ===\n{printed}\n=== END b2b_01 ==="}]
            },
        },
    ]


def test_transcript_checks_each_copy_search_and_instruction():
    prompts = {"b2b_01": "A question"}
    good = routine.parse_transcript(transcript("Same", "Same"), prompts)["b2b_01"]
    assert good["report_match"] is True
    assert good["searched"] is True
    assert good["instruction_exact"] is True
    assert good["resolved_model"] == "claude-opus-5-5"
    changed = routine.parse_transcript(transcript("Edited", "Same"), prompts)["b2b_01"]
    assert changed["report_match"] is False
    silent = routine.parse_transcript(transcript("A", "A", tools=("ToolSearch",)), prompts)["b2b_01"]
    assert silent["searched"] is False


def test_normalized_scheduled_record_never_claims_a_search_count():
    record = routine.normalized_record({"answer_text": "See [a](https://a.example/x).", "searched": True})
    assert record["n_searches"] is None
    assert record["cited_urls"] == ["https://a.example/x"]
    json.dumps(record)
