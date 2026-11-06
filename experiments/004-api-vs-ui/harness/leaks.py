"""Fetch and adapt the two leaked UI system prompts for experiment 004 (sketch.md).

Both files come from public GitHub repositories at PINNED commits, fetched with
``gh api``. Everything this script writes lives under ``data/raw/leaks/`` in the
main checkout (gitignored). No leak text goes anywhere git tracks: the code
below names section headings and tool-record prefixes, never sentences.

Subcommands:

- ``fetch``: download both files, write ``data/raw/leaks/<name>.raw`` and
  ``fetch_manifest.json`` (repo, path, commit sha, blob sha, sha256, size).
- ``adapt``: apply the sketch's adaptation rule, by script and with no hand
  edits, and write ``adapted_chatgpt.txt``, ``adapted_gemini.txt`` and
  ``adapt_manifest.json`` (sha256 of inputs and outputs, kept and dropped
  sections by heading). Same input and run date give the same bytes.

The rule (sketch, "Adaptation rule"):

1. Keep guidance on when to search, using results, citing, formatting, and
   product recommendations.
2. Drop tool syntax the API cannot run (ChatGPT's ``slow|``/``fast|``/
   ``product|``/``business|`` records and ``genui_*``; Gemini's tool JSON
   definitions), plus image generation, widgets, memory and saved-information
   placeholders.
3. Where kept text names a dropped tool, replace the name with "the web search
   tool". No other wording changes.
4. Prepend the identity line with the run date. ChatGPT's ``web_tool.txt`` has
   none, so the generic line every ChatGPT leak uses, with no model clause
   (decided before any data). Gemini: drop the Capabilities block and set any
   hard-coded date to the run date.

Usage (repo root):
    uv run python experiments/004-api-vs-ui/harness/leaks.py fetch
    uv run python experiments/004-api-vs-ui/harness/leaks.py adapt [--date 2026-11-05]
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exp004  # noqa: E402

LEAKS = exp004.RAW / "leaks"

SOURCES = {
    "chatgpt": {
        "repo": "tomek-gpu/system-prompts",
        "path": "web_tool.txt",
        # gh api 'repos/tomek-gpu/system-prompts/commits?path=web_tool.txt&per_page=1'
        # (2026-10-09T09:11:26Z "Create web_tool.txt"), resolved 2026-11-05.
        "commit": "7d8a00294e1dadc82844b56bb120600853d444ed",
    },
    "gemini": {
        "repo": "asgeirtj/system_prompts_leaks",
        "path": "Google/gemini-3.8-flash.md",
        # (2026-09-13T18:26:53Z "Add Gemini 3.8 Flash"), resolved 2026-11-05.
        "commit": "b3002e0c049cada19924b26f2bad57774fa77211",
    },
}

CHATGPT_IDENTITY = "You are ChatGPT, a large language model trained by OpenAI."
REPLACEMENT = "the web search tool"

#: Leak syntax: tool records, reference ids, UI components and tool JSON that the API
#: cannot execute. No adapted file may contain it (checked on write), and the pilot
#: report counts it in leak-arm answers (G2).
TOOL_SYNTAX = re.compile(
    r"\b(?:slow|fast|product|business|availability|genui_\w+)\|"  # ChatGPT records
    r"|(?i:\bgenui(?:_|\b))"
    r"|\u3010turn\d"  # ChatGPT reference ids, as in 【turn0search1】
    r"|\bweb\.run\b"
    r"|<(?:Image|Carousel|ElicitationsGroup|Elicitation|FollowUp|GenerateWidget|Sequence|Step|"
    r"Timeline|TimelineEvent)\b"  # Gemini web app components
    r"|\bimage_agent"
    r"|\"widgetSpec\""
    r"|\"name\"\s*:\s*\"(?:google:search|image_agent|image_generation|file_gen|web_code_canvas)"
    r"|\bgoogle:search\b",
)


def raw_path(platform: str) -> Path:
    return LEAKS / f"{platform}.raw"


def gh_fetch(repo: str, path: str, commit: str) -> tuple[bytes, str]:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/{path}?ref={commit}"],
        capture_output=True, check=True,
    ).stdout
    meta = json.loads(out)
    return base64.b64decode(meta["content"]), meta["sha"]


def cmd_fetch(_a) -> None:
    LEAKS.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for platform, src in SOURCES.items():
        data, blob = gh_fetch(src["repo"], src["path"], src["commit"])
        raw_path(platform).write_bytes(data)
        manifest[platform] = {**src, "blob_sha": blob, "sha256": exp004.sha256_text(data.decode()),
                              "bytes": len(data), "file": raw_path(platform).name,
                              "fetched_at": exp004.now_iso()}
        print(f"{platform}: {src['repo']}/{src['path']} @ {src['commit'][:12]} "
              f"{len(data)} bytes sha256 {manifest[platform]['sha256'][:12]}")
    (LEAKS / "fetch_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")


# ---------------------------------------------------------------- helpers
# Both adapters are written against the PINNED files. Every section heading or
# block marker they rely on must be present, and every ChatGPT section must be
# classified, or the script stops: a new commit must be reviewed, not adapted
# by accident.

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _is_item(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s", line))


def drop_lines(lines: list[str], drop) -> tuple[list[str], int]:
    """Drop each line where ``drop(line)``; a dropped lead line takes its sub-items.

    A sub-item is a following list item indented deeper than the dropped line,
    or, when the dropped line ends with a colon, the list items right after it.
    """
    out, n, i = [], 0, 0
    while i < len(lines):
        line = lines[i]
        if not drop(line):
            out.append(line)
            i += 1
            continue
        n += 1
        base, lead = _indent(line), line.rstrip().rstrip("*").endswith(":")
        i += 1
        while i < len(lines) and lines[i].strip() and _is_item(lines[i]) and (
                _indent(lines[i]) > base or (lead and not _is_item(line))):
            n += 1
            i += 1
    return out, n


def drop_orphan_leads(lines: list[str]) -> tuple[list[str], int]:
    """Drop a lead line ending in a colon whose list items were all dropped."""
    out, n = [], 0
    for i, line in enumerate(lines):
        if line.rstrip().rstrip("*").endswith(":") and line.strip():
            nxt = next((x for x in lines[i + 1:] if x.strip()), "")
            if not _is_item(nxt) and re.match(r"^\s*\*\*[^*]+:\*\*\s*$", line):
                n += 1
                continue
        out.append(line)
    return out, n


def _squeeze(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


# ---------------------------------------------------------------- ChatGPT

CG_HEADING = re.compile(r"^#{1,4} ")
#: Every section of the pinned web_tool.txt, by heading: keep or drop (rule 2).
CG_SECTIONS = {
    "## web": "keep",
    "### Description": "keep",
    "### web Tool Usage and Triggering Rules": "keep",
    "#### Examples of different commands in this tool:": "drop",  # record syntax for every op
    "#### Tips and Requirements for Using the Web Tool": "keep",
    "#### When to use this web tool, and when not to": "keep",
    "### GenUI Widget Library": "drop",
    "### Example `genui_search` calls": "drop",
    "### Example `genui_run` calls": "drop",
    "### Sources": "keep",
    "### Product recommendation + shopping UI policy": "keep",
    "### Local business search + UI policy": "keep",
    "### Reddit guidance": "keep",
    "### Safety & Rules": "keep",
    "### Extra User Information": "drop",  # memory
    "### Tool definitions": "drop",  # tool syntax
}
#: Rule 3: a dropped tool's name in kept text. "(`fast` or `slow`)" names web search
#: as such; `product` and `business` are the shopping and local search commands.
CG_TOOL_NAME = re.compile(r"\((?:`fast` or `slow`|`slow` or `fast`)\)"
                          r"|`(?:product|business)`(?: command)?(?: records)?")
#: Rule 2 inside kept sections: a line about tool mechanics the API cannot execute.
#: Record syntax; GenUI and widgets; reference ids and web.run; rich UI; ops that are
#: not web search (click, find, screen, length, image, availability, open); the choice
#: between the slow and fast engines (`slow` or `fast` named outside the alternation
#: above); and the recency field.
CG_MECHANICS = re.compile(
    r"\b(?:slow|fast|product|business|availability|image|click|find|screen|length|open|"
    r"genui_\w+)\|"
    r"|\bgenui(?:_|\b)|widget|【|web\.run|rich UI"
    r"|`(?:click|find|screen|length|image|availability|open)`"
    r"|\"recency\"|recency="
    , re.I)
CG_ENGINE = re.compile(r"`(?:slow|fast)`")


def _cg_drop(line: str) -> bool:
    if CG_MECHANICS.search(line):
        return True
    if CG_ENGINE.search(CG_TOOL_NAME.sub("", line)):
        return True
    # An instruction to combine two dropped tools means nothing with one tool.
    return len(CG_TOOL_NAME.findall(line)) >= 2


def adapt_chatgpt(raw: str, run_day: str) -> tuple[str, dict]:
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in raw.split("\n"):
        if CG_HEADING.match(line):
            sections.append((line.rstrip(), [line]))
        else:
            sections[-1][1].append(line)
    if "".join(sections[0][1]).strip():
        raise SystemExit("chatgpt: text before the first heading; review the leak")
    seen = [h for h, _ in sections[1:]]
    unknown = [h for h in seen if h not in CG_SECTIONS]
    missing = [h for h in CG_SECTIONS if h not in seen]
    if unknown or missing:
        raise SystemExit(f"chatgpt: sections differ from the pinned file: "
                         f"unknown {unknown}, missing {missing}")
    kept, dropped, body, n_lines = [], [], [], 0
    for head, lines in sections[1:]:
        if CG_SECTIONS[head] == "drop":
            dropped.append(head)
            continue
        kept.append(head)
        lines, n = drop_lines(lines, _cg_drop)
        n_lines += n
        body.append("\n".join(CG_TOOL_NAME.sub(REPLACEMENT, x) for x in lines))
    text = f"{CHATGPT_IDENTITY}\nCurrent date: {run_day}\n\n" + "\n".join(body)
    return _squeeze(text), {"kept_sections": kept, "dropped_sections": dropped,
                            "dropped_lines": n_lines}


# ---------------------------------------------------------------- Gemini

#: Blocks dropped whole, by (start marker, end marker, inclusive end). Markers are
#: whole stripped lines of the pinned file. ``None`` as end = end of file.
GM_DROP_BLOCKS = (
    ("# Saved Information", "**Capabilities**", False),  # saved-information placeholder
    ("**Capabilities**", "**End of Capabilities**", True),  # rule 4
    ("`<lmdx_syntax_protocol>`", "`</lmdx_syntax_protocol>`", True),  # component syntax
    ("### Image Retrieval", "`</tool_strategies>`", False),  # image tool
    ("`<layout_rules>`", "`</layout_rules>`", True),  # visuals and widgets
    ("`<component_library>`", "`</component_library>`", True),  # widgets
    ('`<example title="Image + Basekit Components">`', "`</example>`", True),
    ('`<example title="Interactive Widget + FollowUp">`', "`</example>`", True),
    ("# Tools", None, True),  # tool JSON definitions (google:search, image, files, canvas)
)
#: Section markers reported as kept (headings and block tags of what stays).
GM_HEADING = re.compile(r"^(?:#{1,4} .+|\*\*[^*]+\*\*|`</?[a-z_]+[^`]*>`)\s*$")
#: Rule 2 inside kept blocks: lines that name a web app component, the component
#: library, a widget or image display. A passing mention of "a component" stays.
GM_COMPONENT = re.compile(
    r"<(?:Image|Carousel|ElicitationsGroup|Elicitation|FollowUp|GenerateWidget|Sequence|Step|"
    r"Timeline|TimelineEvent)\b|[Cc]omponent library|Component preference|Basekit|widget"
    r"|[Ii]mage galler|[Ii]mage routing",
)
#: Rule 3: the image tool named in kept text.
GM_TOOL_NAME = re.compile(r"`image_agent(?::fetch_images)?`|\bimage retrieval\b|\bthe image tool\b")
#: The ``<context>`` block holds the leaker's session context: the time (kept, its
#: date set to the run date, rule 4) and the leaker's location, which is per-user
#: context like the saved-information placeholder and is dropped (rule 2). The API
#: grounding tool has no location setting. Rule: inside the block, every non-blank
#: line without a date literal is dropped.
GM_CONTEXT = ("`<context>`", "`</context>`")
GM_DATE = re.compile(
    r"\b(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+)?"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+20\d\d\b"
)


def adapt_gemini(raw: str, run_day: str) -> tuple[str, dict]:
    lines = raw.split("\n")
    stripped = [x.strip() for x in lines]
    drop = [False] * len(lines)
    dropped = []
    for start, end, inclusive in GM_DROP_BLOCKS:
        if start not in stripped:
            raise SystemExit(f"gemini: marker missing from the pinned file: {start!r}")
        i = stripped.index(start)
        if end is None:
            j = len(lines)
        else:
            try:
                j = stripped.index(end, i + 1) + (1 if inclusive else 0)
            except ValueError:
                raise SystemExit(f"gemini: end marker missing after {start!r}: {end!r}") from None
        for k in range(i, j):
            drop[k] = True
        dropped.append(start)
    kept_lines = [x for x, d in zip(lines, drop, strict=True) if not d]
    stripped = [x.strip() for x in kept_lines]
    if GM_CONTEXT[0] not in stripped or GM_CONTEXT[1] not in stripped:
        raise SystemExit("gemini: <context> block missing from the pinned file")
    c0, c1 = stripped.index(GM_CONTEXT[0]), stripped.index(GM_CONTEXT[1])
    ctx_dropped = [k for k in range(c0 + 1, c1) if stripped[k] and not GM_DATE.search(kept_lines[k])]
    if len(ctx_dropped) != 1:
        raise SystemExit(f"gemini: expected one non-date context line, found {len(ctx_dropped)}")
    kept_lines = [x for k, x in enumerate(kept_lines) if k not in ctx_dropped]
    kept_lines, n_comp = drop_lines(kept_lines, lambda x: bool(GM_COMPONENT.search(x)))
    kept_lines, n_orphan = drop_orphan_leads(kept_lines)
    long_day = date.fromisoformat(run_day).strftime("%A, %B %-d, %Y")
    n_dates = 0

    def dated(_m):
        nonlocal n_dates
        n_dates += 1
        return long_day

    text = "\n".join(GM_TOOL_NAME.sub(REPLACEMENT, GM_DATE.sub(dated, x)) for x in kept_lines)
    if n_dates < 1:
        raise SystemExit("gemini: no date literal found to set")
    kept = [x.strip() for x in kept_lines if GM_HEADING.match(x.strip())]
    return _squeeze(text), {"kept_sections": kept, "dropped_sections": dropped,
                            "dropped_component_lines": n_comp, "dropped_orphan_leads": n_orphan,
                            "dropped_context_lines": len(ctx_dropped), "dates_set": n_dates}


ADAPTERS = {"chatgpt": adapt_chatgpt, "gemini": adapt_gemini}


def adapted_path(platform: str) -> Path:
    return LEAKS / f"adapted_{platform}.txt"


def load_adapted(platform: str) -> str:
    path = adapted_path(platform)
    if not path.exists():
        raise SystemExit(f"{path} missing: run leaks.py fetch, then adapt")
    return path.read_text()


def cmd_adapt(a) -> None:
    run_day = a.date or exp004.run_date()
    fetch = json.loads((LEAKS / "fetch_manifest.json").read_text())
    manifest = {"run_date": run_day, "rule": "sketch.md, Adaptation rule (4 steps)",
                "script_sha256": exp004.sha256_file(Path(__file__))}
    for platform, fn in ADAPTERS.items():
        raw = raw_path(platform).read_text()
        if exp004.sha256_text(raw) != fetch[platform]["sha256"]:
            raise SystemExit(f"{platform}: raw file differs from the fetch manifest")
        text, info = fn(raw, run_day)
        hits = TOOL_SYNTAX.findall(text)
        if hits:
            raise SystemExit(f"{platform}: {len(hits)} tool-syntax hits survive adaptation")
        adapted_path(platform).write_text(text)
        manifest[platform] = {"source": fetch[platform], "out": adapted_path(platform).name,
                              "sha256": exp004.sha256_text(text), "chars": len(text),
                              "raw_chars": len(raw), **info}
        print(f"{platform}: {len(raw)} -> {len(text)} chars; kept {len(info['kept_sections'])} "
              f"sections, dropped {len(info['dropped_sections'])}; sha256 "
              f"{manifest[platform]['sha256'][:12]}")
    (LEAKS / "adapt_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    ad = sub.add_parser("adapt")
    ad.add_argument("--date", default=None, help="run date YYYY-MM-DD (default: today, US Eastern)")
    ad.set_defaults(fn=cmd_adapt)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
