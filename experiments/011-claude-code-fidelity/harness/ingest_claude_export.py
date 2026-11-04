"""Ingest one wave's claude.ai data export for experiment 011.

This is stricter than 009's ingest because the account also holds 009's chats, on the same
prompts. A chat counts only if its name is exactly ``e011-w<wave>-ui_default-<item_id>`` and it
was created on or after the freeze date. It never matches on prompt text, which would pick up
009's chats. Two chats with one name are reported and neither is written: rename the bad one
with ``-void`` and export again.

Parsing reuses 009's ``load_conversations`` and ``normalize``, so a chat that asks clarifying
questions is scored on its first reply.

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/harness/ingest_claude_export.py --wave 1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

from aeo_research.claude_answers import first_human_text

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
SOURCE_009 = EXP.parent / "009-claude-model-fidelity" / "harness" / "ingest_claude_export.py"
PROMPTS = EXP.parent / "009-claude-model-fidelity" / "data" / "raw" / "prompts.csv"
ARM = "ui_default"
FREEZE_DATE = "2026-11-03"
NAME = re.compile(r"^\s*e011-w(\d+)-ui_default-(b2b_\d+)\s*$")


def load_009():
    spec = importlib.util.spec_from_file_location("ingest_claude_export_009", SOURCE_009)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _norm(text: str | None) -> str:
    return " ".join((text or "").split())


def match(convs: list[dict], wave: int, item_ids: set[str]) -> tuple[dict, dict, list[str]]:
    """(one chat per item, items with several chats, chats refused with the reason)."""
    found: dict[str, list[dict]] = {}
    refused: list[str] = []
    for conv in convs:
        hit = NAME.match(conv.get("name") or "")
        if not hit or int(hit.group(1)) != wave or hit.group(2) not in item_ids:
            continue
        if (conv.get("created_at") or "")[:10] < FREEZE_DATE:
            refused.append(f"{conv.get('name')}: created {conv.get('created_at')}, before the freeze")
            continue
        found.setdefault(hit.group(2), []).append(conv)
    matched = {item: chats[0] for item, chats in found.items() if len(chats) == 1}
    duplicates = {item: [c.get("uuid") for c in chats] for item, chats in found.items() if len(chats) > 1}
    return matched, duplicates, refused


def injected_fingerprint(conv: dict) -> str:
    """What claude.ai added to the first message, as a stable string (spec, observation 3).

    Maps each ``injection_source`` to the sha256 of its text. The date note changes every day
    by design, so only its presence counts.
    """
    first = next((m for m in conv.get("chat_messages") or [] if m.get("sender") == "human"), {})
    blocks = [b for b in first.get("content") or [] if b.get("type") == "injected_prompt_block"]
    fingerprint = {
        b.get("injection_source"): "present" if b.get("injection_source") == "date_note"
        else hashlib.sha256((b.get("prompt") or "").encode()).hexdigest()
        for b in blocks
    }
    return json.dumps(fingerprint, sort_keys=True)


def injected_report(matched: dict[str, dict], wave: int, sheets: Path) -> list[str]:
    """Save this wave's fingerprints and compare them with the other waves. Report only."""
    counts = Counter(injected_fingerprint(conv) for conv in matched.values())
    lines = [f"injected blocks w{wave}: {len(counts)} distinct across {len(matched)} chats"]
    for fingerprint, n in counts.most_common():
        lines.append(f"  {n} chats: sources {sorted(json.loads(fingerprint))}")
    if len(counts) > 1:
        lines.append("  CHECK: chats in this wave differ")
    sheets.mkdir(parents=True, exist_ok=True)
    (sheets / f"w{wave}_injected.json").write_text(json.dumps(dict(counts), indent=1))
    for other in sorted(sheets.glob("w*_injected.json")):
        name = other.name.split("_")[0]
        if name == f"w{wave}":
            continue
        same = set(json.loads(other.read_text())) == set(counts)
        lines.append(f"  against {name}: {'same' if same else 'CHANGED, read the blocks before going on'}")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    args = ap.parse_args()
    source = load_009()
    with PROMPTS.open(newline="") as f:
        prompts = {r["item_id"]: r["text"] for r in csv.DictReader(f)}
    export_dir = RAW / "ui_exports" / f"w{args.wave}"
    convs = source.load_conversations(export_dir)
    print(f"{export_dir}: {len(convs)} conversations in the export")
    matched, duplicates, refused = match(convs, args.wave, set(prompts))
    out_dir = RAW / "responses" / f"w{args.wave}" / ARM
    out_dir.mkdir(parents=True, exist_ok=True)
    searched = cited = differs = 0
    for item, conv in sorted(matched.items()):
        norm = source.normalize(conv)
        if _norm(first_human_text(conv)) != _norm(prompts[item]):
            norm["warnings"].append("first human message differs from the prompt text")
            differs += 1
        searched += bool(norm.get("n_searches"))
        cited += bool(norm.get("cited_urls"))
        (out_dir / f"{item}.json").write_text(json.dumps(
            {"source": "claude_ai_export", "arm": ARM, "item_id": item, "wave": args.wave,
             "matched_by": "name", "conversation": conv, "normalized": norm},
            indent=1, ensure_ascii=False,
        ))
    missing = sorted(set(prompts) - set(matched))
    print(f"coverage w{args.wave}: {len(matched)}/{len(prompts)}; {searched} with searches, "
          f"{cited} with cited URLs, {differs} with a different prompt")
    print("missing:", missing or "none")
    print("\n".join(injected_report(matched, args.wave, RAW / "ui_sheets")))
    for item, uuids in duplicates.items():
        print(f"duplicate {item}, neither written: {uuids}")
    for line in refused:
        print(f"refused {line}")


if __name__ == "__main__":
    main()
