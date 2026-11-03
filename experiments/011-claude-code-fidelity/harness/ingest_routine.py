"""Turn a scheduled-task transcript into per-answer records (experiment 011).

Input: the session transcript pulled with ``claude --teleport <session>``, saved under
``data/raw/routine/``. The main session prints each answer between marker lines, as its
collection prompt tells it to. It retypes the subagent's report to do that. On the plumbing
run the copies matched the reports exactly (checked by hand, first 3,000 characters of each).

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/harness/ingest_routine.py \
        data/raw/routine/plumbing_b.jsonl --arm sched_kit --wave 0
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from aeo_research.claude_answers import _links_in_text

EXP = Path(__file__).resolve().parents[1]
MARKER = re.compile(r"=== ANSWER (\S+) ===\s*\n?(.*?)\n?\s*=== END \1 ===", re.S)
USAGE = re.compile(r"subagent_tokens:\s*(\d+)\s+tool_uses:\s*(\d+)\s+duration_ms:\s*(\d+)")


def parse_transcript(rows: list[dict]) -> dict[str, dict]:
    """Answers by item id, with the subagent's usage when the transcript reports it."""
    answers: dict[str, dict] = {}
    pending_usage: list[dict] = []
    for row in rows:
        kind = row.get("type")
        content = (row.get("message") or {}).get("content")
        if kind == "user" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    match = USAGE.search(json.dumps(row))
                    if match:
                        pending_usage.append(
                            {
                                "subagent_tokens": int(match.group(1)),
                                "subagent_tool_uses": int(match.group(2)),
                                "subagent_ms": int(match.group(3)),
                            }
                        )
        if kind == "assistant" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    for match in MARKER.finditer(block["text"]):
                        usage = pending_usage.pop(0) if pending_usage else {}
                        answers[match.group(1)] = {"answer_text": match.group(2).strip(), **usage}
    return answers


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcript")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--wave", type=int, required=True)
    args = ap.parse_args()
    path = Path(args.transcript)
    if not path.is_absolute():
        path = EXP / path
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    answers = parse_transcript(rows)
    out_dir = EXP / "data" / "raw" / "responses" / f"w{args.wave}" / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    for item, record in sorted(answers.items()):
        normalized = {
            "answer_text": record["answer_text"],
            "cited_urls": _links_in_text(record["answer_text"]),
            "cited_urls_source": "answer_links",
            "evaluated_urls": [],
            "search_queries": [],
            "n_searches": None,
            "source": "claude_code_scheduled_task",
            **{k: v for k, v in record.items() if k != "answer_text"},
        }
        payload = {"source": "claude_code_scheduled_task", "arm": args.arm, "item_id": item,
                   "wave": args.wave, "normalized": normalized}
        (out_dir / f"{item}.json").write_text(json.dumps(payload, indent=1))
    print(f"{len(answers)} answers written to {out_dir}")


if __name__ == "__main__":
    main()
