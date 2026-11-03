"""Experiment 011 harness: the rules in sketch.md that a bug could silently break."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "experiments" / "011-claude-code-fidelity" / "harness" / "collect_cc.py"
spec = importlib.util.spec_from_file_location("exp011_collect_cc", PATH)
cc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cc
spec.loader.exec_module(cc)


def normalized(**overrides):
    base = {
        "answer_text": "An answer.",
        "main_models": ["claude-opus-5-5"],
        "warnings": [],
        "init": {
            "apiKeySource": "none",
            "mcp_servers": [],
            "tools": ["WebSearch", "WebFetch"],
            "model": "claude-opus-5-5",
        },
    }
    base.update(overrides)
    return base


FULL = cc.ARMS["cc_stock_full"]


def test_no_credential_reaches_the_process(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-pass")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "should-not-pass")
    monkeypatch.setenv("CLAUDECODE", "1")
    env = cc.clean_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "CLAUDECODE" not in env
    assert set(env) <= set(cc.ENV_KEEP) | {"CLAUDE_CODE_DISABLE_AUTO_MEMORY"}


def test_clean_run_passes_the_audit():
    assert cc.audit(normalized(), FULL) == []


@pytest.mark.parametrize(
    ("init_change", "expected"),
    [
        ({"apiKeySource": "ANTHROPIC_API_KEY"}, "apiKeySource=ANTHROPIC_API_KEY"),
        ({"mcp_servers": [{"name": "claude.ai Gmail"}]}, "mcp_servers_present"),
        ({"tools": ["WebSearch"]}, "tools=['WebSearch']"),
        ({"model": "claude-sonnet-5"}, "init_model=claude-sonnet-5"),
    ],
)
def test_audit_rejects_a_contaminated_run(init_change, expected):
    n = normalized()
    n["init"] = {**n["init"], **init_change}
    assert expected in cc.audit(n, FULL)


def test_audit_rejects_a_silent_model_change_and_an_empty_answer():
    assert "main_models=['claude-sonnet-5']" in cc.audit(
        normalized(main_models=["claude-sonnet-5"]), FULL
    )
    assert "no_answer" in cc.audit(normalized(answer_text=""), FULL)


def test_stock_arms_keep_the_prompt_and_none_arms_replace_it():
    stock = cc.build_command(cc.ARMS["cc_stock_search"], "q")
    none = cc.build_command(cc.ARMS["cc_none_search"], "q")
    assert "--system-prompt" not in stock
    assert none[none.index("--system-prompt") + 1] == ""


def test_every_arm_carries_the_isolation_flags():
    for arm in cc.ARMS.values():
        cmd = cc.build_command(arm, "the prompt")
        assert cmd[cmd.index("-p") + 1] == "the prompt"
        assert cmd[cmd.index("--setting-sources") + 1] == ""
        assert cmd[cmd.index("--effort") + 1] == "medium"
        assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
        assert cmd[cmd.index("--tools") + 1] == ",".join(arm.tools)
        for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
            assert flag in cmd
        assert "--bare" not in cmd


@pytest.mark.parametrize(
    ("windows", "stops"),
    [
        (None, False),
        ({"status": "allowed", "five_hour": 0.59, "seven_day": 0.49}, False),
        ({"status": "allowed", "five_hour": 0.60, "seven_day": 0.1}, True),
        ({"status": "allowed", "five_hour": 0.1, "seven_day": 0.50}, True),
        ({"status": "allowed_warning", "five_hour": 0.1, "seven_day": 0.1}, True),
        ({"status": "allowed", "is_using_overage": True, "five_hour": 0.1, "seven_day": 0.1}, True),
    ],
)
def test_limit_guard_stops_before_overage(windows, stops):
    assert bool(cc.limit_problem(windows)) is stops


def test_usage_check_login_directory_passes_but_no_credential_does(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-pass")
    monkeypatch.setattr(cc, "CONFIG_DIR", "/tmp/pro-login")
    env = cc.clean_env()
    assert env["CLAUDE_CONFIG_DIR"] == "/tmp/pro-login"
    assert "ANTHROPIC_API_KEY" not in env


def test_usage_summary_reports_points_per_answer():
    rows = [
        {"status": "ok", "rate_limits": {"first": {"five_hour": 0.10, "seven_day": 0.20},
                                         "last": {"five_hour": 0.12, "seven_day": 0.20}}},
        {"status": "ok", "rate_limits": {"first": {"five_hour": 0.12, "seven_day": 0.20},
                                         "last": {"five_hour": 0.14, "seven_day": 0.21}}},
    ]
    text = cc.usage_summary(rows)
    assert "2.00 points per answer" in text
    assert "0.50 points per answer" in text
