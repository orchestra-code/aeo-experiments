"""Fetch, trim and slot the leaked claude.ai system prompt for experiment 009.

The prompt comes from github.com/asgeirtj/system_prompts_leaks at a PINNED
commit, so every wave uses the same bytes. Everything this script writes lives
under ``data/raw/system_prompts/`` (gitignored). The prompt text never goes
anywhere git tracks; ``harness/leak_trim_rules.md`` names the removed sections
and nothing else.

Outputs (``data/raw/system_prompts/``):

- ``claude-opus-5.5.raw.md``: the file exactly as fetched
- ``claude-opus-5.5.full.template.md``: the whole prompt with the leaker's
  per-user context removed (their saved preference and memory snapshot) and
  the date and location slotted. This is the ``--leak-variant raw`` arm input.
- ``claude-opus-5.5.trimmed.template.md``: the full template minus the
  sections for tools the API arms do not attach. ``--leak-variant trimmed``.
- ``manifest.json``: source URL and SHA, sha256 of every file, removed
  sections with char counts, and ``count_tokens`` results per model.

Templates hold ``{{RUN_DATE_LONG}}``, ``{{RUN_DATE}}`` and ``{{USER_LOCATION}}``
slots (the prompt itself contains thousands of braces, so ``str.format`` is not
used). :func:`fill_slots` fills them at request-build time.

Usage (repo root):
    uv run python experiments/009-claude-model-fidelity/harness/leak_prompt.py \
        [--sha <commit>] [--env-file /Users/jcw/projects/spyglasses/.env.local] [--no-count]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
OUT_DIR = EXP / "data" / "raw" / "system_prompts"

REPO_SLUG = "asgeirtj/system_prompts_leaks"
PATH_IN_REPO = "Anthropic/claude-opus-5.5.md"
#: Resolved 2026-09-25 with
#: gh api 'repos/asgeirtj/system_prompts_leaks/commits?path=Anthropic/claude-opus-5.5.md&per_page=1'
#: (commit "Add Claude Opus 5.5 system prompt (claude.ai)", 2026-09-22T20:00:37Z).
PINNED_SHA = "17200e1475ae6ecfa55383f7988efcb706c48bb3"

RAW_NAME = "claude-opus-5.5.raw.md"
FULL_NAME = "claude-opus-5.5.full.template.md"
TRIMMED_NAME = "claude-opus-5.5.trimmed.template.md"
VARIANT_FILES = {"raw": FULL_NAME, "trimmed": TRIMMED_NAME}

COUNT_MODELS = ("claude-opus-5-5", "claude-sonnet-5", "claude-haiku-4-5")

# --------------------------------------------------------------- slots

LEAK_DATE_LONG = "Tuesday, September 22, 2026"
LEAK_DATE = "September 22, 2026"
LEAK_LOCATION = "Reykjavík, Capital Region, IS"

SLOT_DATE_LONG = "{{RUN_DATE_LONG}}"
SLOT_DATE = "{{RUN_DATE}}"
SLOT_LOCATION = "{{USER_LOCATION}}"

# --------------------------------------------------------------- rules
# Every top-level ("# name") section of the pinned file must appear in exactly
# one of these sets, or trimming stops: a new SHA with new sections must be
# reviewed, not trimmed by accident.

#: Kept whole (apart from the excisions below).
KEEP_SECTIONS = frozenset(
    {"claude_behavior", "preferences_info", "search_instructions", "thinking_behavior"}
)

#: Removed whole in the trimmed variant: memory, artifacts, end_conversation,
#: past chats, computer use / skills / files, visualizer, MCP and plugin
#: suggestions. None of these tools is attached to an API arm.
REMOVE_SECTIONS = frozenset(
    {
        "memory_filesystem",
        "privacy_requirements",
        "memory_application_instructions",
        "forbidden_memory_phrases",
        "appropriate_boundaries_re_memory",
        "memory_application_examples",
        "preferences_guardrails",
        "end_conversation_tool_info",
        "persistent_storage_for_artifacts",
        "mcp_app_suggestions",
        "suggest_catalog_plugins_and_skills",
        "past_chats_tools",
        "computer_use",
        "publishing_artifacts",
        "request_evaluation_checklist",
        "when_to_use_visualizer_for_inline_visuals",
        "available_skills",
        "network_configuration",
        "filesystem_configuration",
    }
)

#: Sections that are mostly removed but hold a piece that is kept.
#: "Tools" is ~6,200 lines of claude.ai tool JSON definitions (the API supplies
#: its own web_search definition); its tail is the identity preamble ("The
#: assistant is Claude ...", the current date, the chat-surface line), kept.
#: "anthropic_api_in_artifacts" is about calling the API from artifacts; its
#: tail holds the web-search citation instructions and the user-location line,
#: both kept.
PARTIAL_SECTIONS = {
    "Tools": "The assistant is Claude, created by Anthropic.",
    "anthropic_api_in_artifacts": "`<citation_instructions>`",
}

#: Blocks cut inside kept sections in the trimmed variant: (section, start
#: marker, end marker or None for "end of paragraph", label).
TOOL_EXCISIONS = (
    (
        "search_instructions",
        "`<using_image_search_tool>`",
        "`</using_image_search_tool>`",
        "search_instructions/using_image_search_tool",
    ),
    (
        "search_instructions",
        "You also have `web_search_fast`",
        None,
        "search_instructions/web_search_fast paragraph",
    ),
)

#: The leaker's own per-user context (a saved preference and a memory
#: snapshot naming them), cut from BOTH variants: it is not part of the base
#: prompt and would bias answer length.
PER_USER_EXCISION = ("thinking_behavior", "`<userPreferences>`", "per-user context")


# ------------------------------------------------------------ parsing


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split into (name, body) by top-level ``# name`` headings, fence-aware.

    Text before the first heading is returned under the name ``""``.
    """
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else re.match(r"^# (\S.*?)\s*$", line)
        if m:
            sections.append((m.group(1), [line]))
        else:
            sections[-1][1].append(line)
    return [(name, "".join(lines)) for name, lines in sections if name or "".join(lines).strip()]


def _cut(body: str, start: str, end: str | None, label: str) -> tuple[str, int]:
    i = body.find(start)
    if i < 0:
        raise SystemExit(f"trim anchor not found: {label!r} ({start!r})")
    if end is None:
        j = body.find("\n\n", i)
        j = len(body) if j < 0 else j
    else:
        j = body.rfind(end)
        if j < i:
            raise SystemExit(f"trim end anchor not found: {label!r} ({end!r})")
        j += len(end)
    return body[:i] + body[j:], j - i


def slot(text: str) -> str:
    for literal in (LEAK_DATE_LONG, LEAK_DATE, LEAK_LOCATION):
        if literal not in text:
            raise SystemExit(f"slot literal not found: {literal!r}")
    text = text.replace(LEAK_DATE_LONG, SLOT_DATE_LONG)
    text = text.replace(LEAK_DATE, SLOT_DATE)
    return text.replace(LEAK_LOCATION, SLOT_LOCATION)


def _tidy(text: str) -> str:
    return re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"


def build_templates(raw: str) -> tuple[str, str, list[dict]]:
    """(full template, trimmed template, removal log) from the raw file."""
    sections = split_sections(raw)
    names = [n for n, _ in sections]
    known = KEEP_SECTIONS | REMOVE_SECTIONS | set(PARTIAL_SECTIONS)
    unknown = [n for n in names if n not in known]
    if unknown:
        raise SystemExit(f"unreviewed top-level sections: {unknown}")
    missing = sorted(k for k in known if k not in names)
    if missing:
        raise SystemExit(f"expected sections missing: {missing}")

    removed: list[dict] = []
    full_parts: list[str] = []
    trim_parts: list[str] = []
    per_sec, per_start, per_label = PER_USER_EXCISION
    for name, body in sections:
        if name == per_sec:
            i = body.find(per_start)
            if i < 0:
                raise SystemExit(f"per-user anchor not found in {per_sec}")
            removed.append(
                {"section": f"{per_sec}/{per_label}", "chars": len(body) - i, "variants": "both"}
            )
            body = body[:i]
        full_parts.append(body)

        if name in REMOVE_SECTIONS:
            removed.append({"section": name, "chars": len(body), "variants": "trimmed"})
            continue
        if name in PARTIAL_SECTIONS:
            anchor = PARTIAL_SECTIONS[name]
            i = body.find(anchor)
            if i < 0:
                raise SystemExit(f"partial-keep anchor not found in {name}: {anchor!r}")
            removed.append(
                {"section": f"{name} (all but the tail kept)", "chars": i, "variants": "trimmed"}
            )
            body = body[i:]
        for sec, start, end, label in TOOL_EXCISIONS:
            if sec == name:
                body, n = _cut(body, start, end, label)
                removed.append({"section": label, "chars": n, "variants": "trimmed"})
        trim_parts.append(body)

    full = _tidy(slot("".join(full_parts)))
    trimmed = _tidy(slot("".join(trim_parts)))
    return full, trimmed, removed


# -------------------------------------------------------------- filling


def location_text(user_location: dict | None) -> str | None:
    if not user_location:
        return None
    parts = [user_location.get(k) for k in ("city", "region", "country")]
    parts = [p for p in parts if p]
    return ", ".join(parts) or None


def fill_slots(template: str, run_date: date, user_location: dict | None = None) -> str:
    """Fill the date and location slots. Without a location, the line that
    states the user's location is dropped (claude.ai omits it when unknown)."""
    text = template.replace(SLOT_DATE_LONG, run_date.strftime("%A, %B ") + f"{run_date.day}, {run_date.year}")
    text = text.replace(SLOT_DATE, run_date.strftime("%B ") + f"{run_date.day}, {run_date.year}")
    loc = location_text(user_location)
    if loc:
        return text.replace(SLOT_LOCATION, loc)
    return "".join(line for line in text.splitlines(keepends=True) if SLOT_LOCATION not in line)


def load_template(variant: str = "trimmed", out_dir: Path = OUT_DIR) -> str:
    path = out_dir / VARIANT_FILES[variant]
    if not path.exists():
        raise SystemExit(f"{path} missing; run harness/leak_prompt.py first")
    return path.read_text()


def sha256(text: str | bytes) -> str:
    data = text.encode() if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


# -------------------------------------------------------------- network


def fetch(sha: str) -> bytes:
    url = f"https://raw.githubusercontent.com/{REPO_SLUG}/{sha}/{PATH_IN_REPO}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def count_tokens(client, model: str, system: str | None) -> int | str:
    """Input tokens of the system prompt alone (a one-word message subtracted)."""
    import anthropic

    msgs = [{"role": "user", "content": "hi"}]
    try:
        base = client.messages.count_tokens(model=model, messages=msgs).input_tokens
        if system is None:
            return base
        with_sys = client.messages.count_tokens(model=model, system=system, messages=msgs)
        return with_sys.input_tokens - base
    except anthropic.APIStatusError as e:
        return f"error {e.status_code}: {str(e.message)[:160]}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sha", default=PINNED_SHA)
    ap.add_argument("--env-file", default="/Users/jcw/projects/spyglasses/.env.local")
    ap.add_argument("--no-count", action="store_true", help="skip count_tokens")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    a = ap.parse_args()

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_bytes = fetch(a.sha)
    (out / RAW_NAME).write_bytes(raw_bytes)
    raw = raw_bytes.decode("utf-8")
    full, trimmed, removed = build_templates(raw)
    (out / FULL_NAME).write_text(full)
    (out / TRIMMED_NAME).write_text(trimmed)

    manifest = {
        "source_url": f"https://raw.githubusercontent.com/{REPO_SLUG}/{a.sha}/{PATH_IN_REPO}",
        "repo": REPO_SLUG,
        "path": PATH_IN_REPO,
        "sha": a.sha,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {
            RAW_NAME: {"sha256": sha256(raw_bytes), "chars": len(raw), "words": len(raw.split())},
            FULL_NAME: {"sha256": sha256(full), "chars": len(full), "words": len(full.split())},
            TRIMMED_NAME: {
                "sha256": sha256(trimmed),
                "chars": len(trimmed),
                "words": len(trimmed.split()),
            },
        },
        "slots": [SLOT_DATE_LONG, SLOT_DATE, SLOT_LOCATION],
        "removed": removed,
        "token_counts": {},
    }

    if not a.no_count:
        sys.path.insert(0, str(HERE))
        from anthropic_client import make_client  # noqa: E402

        client = make_client(a.env_file)
        filled_day = date.today()
        loc = {"type": "approximate", "city": "Boston", "region": "Massachusetts", "country": "US"}
        texts = {
            "raw": raw,
            "full_filled": fill_slots(full, filled_day, loc),
            "trimmed_filled": fill_slots(trimmed, filled_day, loc),
        }
        for model in COUNT_MODELS:
            manifest["token_counts"][model] = {
                name: count_tokens(client, model, text) for name, text in texts.items()
            }
            print(f"  {model}: {manifest['token_counts'][model]}")
        manifest["token_counts_note"] = (
            "system-prompt tokens only: count_tokens(system + 'hi') minus count_tokens('hi'); "
            f"filled with run date {filled_day.isoformat()} and Boston, Massachusetts, US"
        )

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"sha {a.sha}")
    for name, meta in manifest["files"].items():
        print(f"  {name}: {meta['chars']:,} chars, {meta['words']:,} words")
    print("removed:")
    for r in removed:
        print(f"  {r['section']}: {r['chars']:,} chars ({r['variants']})")
    print(f"wrote {out}/manifest.json")


if __name__ == "__main__":
    main()
