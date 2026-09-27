"""Ingest one wave's claude.ai data export into the per-response schema.

Reads ``conversations.json`` from every export zip (or loose
``conversations.json``) in ``data/raw/ui_exports/w<wave>/``, matches each
expected (item, UI arm) chat, normalizes it with
``aeo_research.claude_answers.from_claude_export``, and writes
``data/raw/responses/w<wave>/<arm>/<item_id>.json`` with
``source: "claude_ai_export"``, the same layout the API collector uses.

Matching:
1. by chat name ``w<wave>-<arm>-<item_id>`` (the protocol's rename step);
2. fallback for unnamed chats: the first human message equals a prompt's text
   exactly (whitespace-normalized). That identifies the item but not the arm,
   so it is used only when a single UI arm is being ingested, or when exactly
   one arm for that item is still unmatched. Everything else is reported as
   ambiguous and left for a person to rename. A chat whose name starts with
   ``w<N>-`` but is not an exact protocol name (for example a voided
   ``...-void`` chat) is never matched.

The export format is unverified (see the TODO in claude_answers.py); the
coverage report lists parse warnings so the pilot can confirm it.

Usage (repo root):
    uv run python experiments/009-claude-model-fidelity/harness/ingest_claude_export.py \
        --wave 1 [--arms ui_default,ui_think] [--items ...]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parents[1]
RAW = EXP / "data" / "raw"
sys.path.insert(0, str(REPO / "src"))
from aeo_research.claude_answers import first_human_text, from_claude_export  # noqa: E402

UI_ARMS = ("ui_default", "ui_think")
NAME_RE = re.compile(r"^\s*w(\d+)-(ui_[a-z_]+)-(b2b_\d+)\s*$")
#: Any protocol-style name (including voided chats like ``w1-ui_default-b2b_01-void``)
#: is never matched by prompt text.
PROTOCOL_PREFIX_RE = re.compile(r"^\s*w\d+-")


def _norm(text: str | None) -> str:
    return " ".join((text or "").split())


def load_conversations(export_dir: Path) -> list[dict]:
    convs: list[dict] = []
    for path in sorted(export_dir.glob("*.zip")):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.endswith("conversations.json")]
            if not names:
                print(f"  WARNING {path.name}: no conversations.json inside")
            for n in names:
                data = json.loads(zf.read(n))
                convs.extend(data if isinstance(data, list) else data.get("conversations", []))
    for path in sorted(export_dir.glob("**/conversations.json")):
        data = json.loads(path.read_text())
        convs.extend(data if isinstance(data, list) else data.get("conversations", []))
    # The same chat can arrive twice (a zip and its unpacked copy).
    seen: set = set()
    unique = []
    for c in convs:
        key = c.get("uuid") or id(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def first_exchange(conv: dict) -> tuple[dict, bool]:
    """The chat up to (not including) the second human message.

    When claude.ai asks clarifying questions (``ask_user_input_v0``), the
    collector's answers arrive as a second human message and a second reply.
    The API arms never get that context, so only the first reply is scored
    (deviation 1, 2026-09-27). Returns (conversation copy, truncated?).
    """
    messages = conv.get("chat_messages") or []
    humans = [i for i, m in enumerate(messages) if m.get("sender") == "human"]
    if len(humans) < 2:
        return conv, False
    return {**conv, "chat_messages": messages[: humans[1]]}, True


def normalize(conv: dict) -> dict:
    """``from_claude_export`` on the first exchange; the full chat kept alongside."""
    first, truncated = first_exchange(conv)
    norm = from_claude_export(first)
    norm["clarifying_questions"] = truncated
    if truncated:
        norm["warnings"].append("clarifying questions: scored the first reply only")
        norm["full_chat"] = from_claude_export(conv)
    return norm


def match(convs: list[dict], prompts: dict[str, dict], wave: int, arms: list[str]):
    """Return (matched {(arm, item): conv}, duplicates, ambiguous, ignored count)."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    unnamed: list[dict] = []
    ignored = 0
    for c in convs:
        m = NAME_RE.match(c.get("name") or "")
        if m:
            w, arm, item = int(m.group(1)), m.group(2), m.group(3)
            if w == wave and arm in arms and item in prompts:
                by_key[(arm, item)].append(c)
            else:
                ignored += 1
        elif PROTOCOL_PREFIX_RE.match(c.get("name") or ""):
            ignored += 1
        else:
            unnamed.append(c)

    text_to_item = {_norm(p["text"]): item for item, p in prompts.items()}
    ambiguous: list[str] = []
    for c in unnamed:
        item = text_to_item.get(_norm(first_human_text(c)))
        if item is None:
            ignored += 1
            continue
        open_arms = [a for a in arms if (a, item) not in by_key]
        if len(open_arms) == 1:
            by_key[(open_arms[0], item)].append(c)
            c.setdefault("_matched_by", "prompt_text")
        else:
            ambiguous.append(f"{c.get('uuid')} ({c.get('name')!r}) -> {item}, arm unknown")

    matched, duplicates = {}, {}
    for key, cs in by_key.items():
        cs = sorted(cs, key=lambda c: c.get("created_at") or "")
        matched[key] = cs[0]
        if len(cs) > 1:
            duplicates[key] = [c.get("uuid") for c in cs]
    return matched, duplicates, ambiguous, ignored


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--arms", default=",".join(UI_ARMS))
    ap.add_argument("--items", default=None)
    ap.add_argument("--prompts", default=str(RAW / "prompts.csv"))
    ap.add_argument("--export-dir", default=None, help="default data/raw/ui_exports/w<wave>")
    ap.add_argument("--out-dir", default=str(RAW / "responses"))
    a = ap.parse_args()

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    with open(a.prompts, newline="") as f:
        prompts = {r["item_id"]: r for r in csv.DictReader(f)}
    if a.items:
        keep = {i.strip() for i in a.items.split(",")}
        prompts = {k: v for k, v in prompts.items() if k in keep}

    export_dir = Path(a.export_dir or RAW / "ui_exports" / f"w{a.wave}")
    convs = load_conversations(export_dir)
    print(f"{export_dir}: {len(convs)} conversations in the export")
    matched, duplicates, ambiguous, ignored = match(convs, prompts, a.wave, arms)

    out_dir = Path(a.out_dir) / f"w{a.wave}"
    warn_counts: Counter = Counter()
    for (arm, item), conv in sorted(matched.items()):
        norm = normalize(conv)
        if _norm(first_human_text(conv)) != _norm(prompts[item]["text"]):
            norm["warnings"].append("first human message differs from the prompt text")
        for w in norm["warnings"]:
            warn_counts[w.split(":")[0]] += 1
        path = out_dir / arm / f"{item}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {
                "source": "claude_ai_export",
                "arm": arm,
                "item_id": item,
                "wave": a.wave,
                "matched_by": conv.get("_matched_by", "name"),
                "conversation": conv,
                "normalized": norm,
            },
            indent=1,
            ensure_ascii=False,
        ))

    expected = [(arm, item) for item in prompts for arm in arms]
    missing = [k for k in expected if k not in matched]
    print(f"\ncoverage w{a.wave}: {len(matched)}/{len(expected)} matched "
          f"({sum(1 for c in matched.values() if c.get('_matched_by'))} by prompt text), "
          f"{len(missing)} missing, {len(duplicates)} duplicated, {len(ambiguous)} ambiguous, "
          f"{ignored} other conversations ignored")
    for arm in arms:
        got = [matched[(arm, i)] for i in prompts if (arm, i) in matched]
        norms = [normalize(c) for c in got]
        with_cites = sum(1 for n in norms if n["cited_urls"])
        with_search = sum(1 for n in norms if n["n_searches"])
        print(f"  {arm}: {len(got)} chats, {with_search} with searches, "
              f"{with_cites} with cited URLs")
    if missing:
        print("missing:", ", ".join(f"{arm}/{item}" for arm, item in missing))
    for (arm, item), uuids in duplicates.items():
        print(f"duplicate {arm}/{item}: kept the earliest of {uuids}")
    for line in ambiguous:
        print(f"ambiguous: {line}")
    if warn_counts:
        print("parse warnings:")
        for w, n in warn_counts.most_common():
            print(f"  {n:>4}  {w}")


if __name__ == "__main__":
    main()
