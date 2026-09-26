"""Arm registry and Messages API request builder for experiment 009.

Seven confirmatory API arms (the two claude.ai arms, ``ui_default`` and ``ui_think``, are
collected by hand; see ``ui_collection_protocol.md``):

| arm                    | model            | reasoning                  | system            |
|------------------------|------------------|----------------------------|-------------------|
| opus55_plain           | claude-opus-5-5  | effort medium (always on)  | none              |
| opus55_leak            | claude-opus-5-5  | effort medium (always on)  | trimmed leak      |
| sonnet5_plain          | claude-sonnet-5  | adaptive, default effort   | none              |
| sonnet5_leak_think     | claude-sonnet-5  | adaptive, default effort   | trimmed leak      |
| sonnet5_leak_low       | claude-sonnet-5  | adaptive, effort low       | trimmed leak      |
| sonnet5_prod           | claude-sonnet-5  | as production (omitted)    | Spyglasses prompt |
| haiku45_leak           | claude-haiku-4-5 | none (param omitted)       | trimmed leak      |

Pilot-only arms (``pilot_only=True``, never in ``--arms all``):
``sonnet5_leak_nothink``, ``opus55_leak_fetch``, ``opus55_leak_ws2026``,
``opus55_leak_raw``.

Research arms (all but ``sonnet5_prod``) share one request shape: the raw
prompt as the only user message, ``web_search`` with ``max_uses`` 10 and the
collector's approximate ``user_location``, ``max_tokens`` 16000, no
temperature, no refusal fallbacks (an answer is never produced by another
model). Opus 5.5 cannot disable thinking, so its arms omit ``thinking`` and set
``output_config.effort``; ``budget_tokens`` is never sent.

Caching (claude-api skill, shared/prompt-caching.md, "Automatic vs explicit
breakpoints"): one explicit 1-hour breakpoint on the system block (tools render
before system, so it caches tools + system for the whole wave), plus top-level
automatic caching at the default 5-minute TTL for the tail. A 1-hour marker
followed by a 5-minute automatic entry is the documented allowed order; the
reverse is a 400. Web search inserts its own 5-minute writes after tool
results once a request uses caching.

``sonnet5_prod`` is the production request, byte for byte, from the spyglasses
repo:
- ``packages/background-jobs/src/utils/discovery-query-execution.ts``
  ``buildDiscoveryPrompts`` (system prompt, user prompt = query + suffix; no
  location line because these prompts have no location). The text is loaded
  at run time from ``data/raw/`` via ``prod_prompt.load()``; see
  ``harness/prod_prompt.py``.
- ``packages/core/src/services/claude-direct.ts`` ``callClaudeDirectWithWebSearch``
  (``max_tokens`` 16000, ``system`` as a plain string, one user message,
  ``web_search_20250305`` with ``max_uses`` 5 and no ``user_location`` when the
  property has none, no thinking / effort / cache / temperature)
- model ``claude-sonnet-5`` from ``packages/core/src/config/llm-platforms.ts``
Verified against spyglasses commit fc02ee7279109c96865621d30acfeacc72d38e20.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import prod_prompt
from leak_prompt import fill_slots

# --------------------------------------------------------------- production
# The production prompt text is Spyglasses product IP and never lives in this
# repo. harness/prod_prompt.py extracts it from a local spyglasses checkout
# (buildDiscoveryPrompts in
# packages/background-jobs/src/utils/discovery-query-execution.ts) into the
# gitignored data/raw/system_prompts/spyglasses_prod.json, and
# prod_prompt.load() reads it here. The request shape below is not sensitive.

PROD_MAX_TOKENS = 16000  # claude-direct.ts maxTokens default
PROD_MAX_SEARCHES = 5  # claude-direct.ts maxSearches default

# --------------------------------------------------------------- research

RESEARCH_MAX_TOKENS = 16000
RESEARCH_MAX_SEARCHES = 10
WEB_SEARCH_VERSIONS = ("20250305", "20260209")
#: Dynamic filtering (20260209) is not offered on Haiku 4.5.
DYNAMIC_FILTERING_MODELS = ("claude-opus-5-5", "claude-sonnet-5")


#: web_fetch for the pilot-only fetch arm. The 20260209 version includes
#: dynamic filtering, so no separate code_execution tool is ever declared next
#: to it (claude-api skill, shared/tool-use-concepts.md, "Server-Side Tools").
#: max_uses and max_content_tokens bound the pilot's cost.
WEB_FETCH_TOOL = {
    "type": "web_fetch_20260209",
    "name": "web_fetch",
    "max_uses": 5,
    "max_content_tokens": 10000,
}


@dataclass(frozen=True)
class Arm:
    name: str
    model: str
    system: str  # "leak" | "none" | "prod"
    thinking: dict | None = None
    effort: str | None = None
    #: Pilot-only arms are never part of ``--arms all``; name them explicitly.
    pilot_only: bool = False
    #: Per-arm overrides of the run-level settings (None = use the run's).
    leak_variant: str | None = None
    web_search_version: str | None = None
    extra_tools: tuple = ()

    @property
    def uses_leak(self) -> bool:
        return self.system == "leak"


ARMS: dict[str, Arm] = {
    a.name: a
    for a in (
        # ---- confirmatory arms (decided after the pilot, 2026-09-26) ----
        Arm("opus55_plain", "claude-opus-5-5", "none", effort="medium"),
        Arm("opus55_leak", "claude-opus-5-5", "leak", effort="medium"),
        # Sonnet 5 with no system prompt; omitting thinking runs adaptive
        # thinking at the default effort, as sent explicitly by sonnet5_leak_think.
        Arm("sonnet5_plain", "claude-sonnet-5", "none", thinking={"type": "adaptive"}),
        Arm("sonnet5_leak_think", "claude-sonnet-5", "leak", thinking={"type": "adaptive"}),
        # Thinking on at effort low (replaces sonnet5_leak_nothink, which skipped
        # search on 3 of 3 smoke prompts and 3 of 10 pilot prompts).
        Arm("sonnet5_leak_low", "claude-sonnet-5", "leak", thinking={"type": "adaptive"},
            effort="low"),
        Arm("sonnet5_prod", "claude-sonnet-5", "prod"),
        Arm("haiku45_leak", "claude-haiku-4-5", "leak"),
        # ---- pilot only (plan step 2); never part of --arms all ----
        Arm("sonnet5_leak_nothink", "claude-sonnet-5", "leak", thinking={"type": "disabled"},
            pilot_only=True),
        # opus55_leak plus web_fetch (claude.ai also has web_fetch). 0 fetches in the pilot.
        Arm("opus55_leak_fetch", "claude-opus-5-5", "leak", effort="medium", pilot_only=True,
            extra_tools=(WEB_FETCH_TOOL,)),
        # Pilot check (c): the dynamic-filtering web_search version. Ruled out:
        # zero inline citations on 10 of 10 pilot prompts.
        Arm("opus55_leak_ws2026", "claude-opus-5-5", "leak", effort="medium", pilot_only=True,
            web_search_version="20260209"),
        # Pilot check (b): the untrimmed leak (per-user context still removed).
        Arm("opus55_leak_raw", "claude-opus-5-5", "leak", effort="medium", pilot_only=True,
            leak_variant="raw"),
    )
}

CORE_ARMS = tuple(name for name, arm in ARMS.items() if not arm.pilot_only)
PILOT_ARMS = tuple(name for name, arm in ARMS.items() if arm.pilot_only)

UI_ARMS = ("ui_default", "ui_think")


def parse_user_location(spec: str | None) -> dict | None:
    """``"Boston,Massachusetts,US"`` -> the web_search ``user_location`` object."""
    if not spec:
        return None
    parts = [p.strip() for p in spec.split(",")]
    loc: dict = {"type": "approximate"}
    for key, value in zip(("city", "region", "country"), parts):
        if value:
            loc[key] = value.upper() if key == "country" else value
    return loc


def prod_user_prompt(query: str, prod: dict | None = None) -> str:
    prod = prod or prod_prompt.load()
    return f"{query}{prod['user_suffix']}"


def build_params(
    arm: str | Arm,
    prompt_text: str,
    run_date: date,
    leak_text: str | None,
    user_location: dict | None,
    web_search_version: str = "20250305",
) -> dict:
    """Messages API params for one call.

    ``leak_text`` is the slotted template from ``leak_prompt.load_template``;
    its date and location slots are filled here. ``user_location`` is a
    ``{"type": "approximate", ...}`` object or None.
    """
    arm = ARMS[arm] if isinstance(arm, str) else arm
    web_search_version = arm.web_search_version or web_search_version

    if arm.system == "prod":
        # Production shape, key order as claude-direct.ts sends it.
        prod = prod_prompt.load()
        return {
            "model": arm.model,
            "max_tokens": PROD_MAX_TOKENS,
            "system": prod["system"],
            "messages": [{"role": "user", "content": prod_user_prompt(prompt_text, prod)}],
            "tools": [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": PROD_MAX_SEARCHES}
            ],
        }

    if web_search_version not in WEB_SEARCH_VERSIONS:
        raise ValueError(f"unknown web_search version {web_search_version!r}")
    if web_search_version != "20250305" and arm.model not in DYNAMIC_FILTERING_MODELS:
        raise ValueError(f"web_search_{web_search_version} is not available on {arm.model}")

    tool: dict = {
        "type": f"web_search_{web_search_version}",
        "name": "web_search",
        "max_uses": RESEARCH_MAX_SEARCHES,
    }
    if user_location:
        tool["user_location"] = dict(user_location)

    params: dict = {
        "model": arm.model,
        "max_tokens": RESEARCH_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt_text}],
        "tools": [tool, *(dict(t) for t in arm.extra_tools)],
        "cache_control": {"type": "ephemeral"},
    }
    if arm.uses_leak:
        if not leak_text:
            raise ValueError(f"arm {arm.name} needs the leaked prompt template")
        params["system"] = [
            {
                "type": "text",
                "text": fill_slots(leak_text, run_date, user_location),
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ]
    if arm.thinking is not None:
        params["thinking"] = dict(arm.thinking)
    if arm.effort is not None:
        params["output_config"] = {"effort": arm.effort}
    return params
