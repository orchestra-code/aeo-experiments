"""Turn scheduled-task transcripts into per-answer records (experiment 011, `sched_kit`).

Input: session transcripts pulled with ``harness/sched_kit.py pull``. The main session prints
each answer between marker lines, which is what a reader of the run would collect. The
transcript also holds each subagent's own report and the instruction it was given, so every
answer is checked: did the instruction match exactly, did the subagent search, which model
ran it, and is the printed copy identical to its report (spec §6, "Retyped answers").

An answer is written only when its printed copy exists. The coverage line lists what is
missing, so a task that died can be rerun for those prompts the same day.

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/harness/ingest_routine.py \
        data/raw/routine/w1_b1.jsonl data/raw/routine/w1_b2.jsonl --arm sched_kit --wave 1
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from aeo_research.claude_answers import _links_in_text

EXP = Path(__file__).resolve().parents[1]
PROMPTS = EXP.parent / "009-claude-model-fidelity" / "data" / "raw" / "prompts.csv"
INSTRUCTION_PREFIX = (
    "Use web search to research this question, then answer it the way you would answer "
    "the person asking it: "
)
MARKER = re.compile(r"=== ANSWER (\S+) ===\s*\n?(.*?)\n?\s*=== END \1 ===", re.S)


def load_prompts(path: Path = PROMPTS) -> dict[str, str]:
    with path.open(newline="") as f:
        return {r["item_id"]: r["text"] for r in csv.DictReader(f)}


def _report_text(result: dict) -> str | None:
    report = (result.get("handbackReport") or {}).get("text")
    if report:
        return report
    blocks = [b.get("text", "") for b in result.get("content") or [] if isinstance(b, dict)]
    return "\n".join(blocks) or None


def parse_transcript(rows: list[dict], prompts: dict[str, str]) -> dict[str, dict]:
    """Answers by item id, joined with what the transcript records about each subagent."""
    item_by_question = {q.strip(): item for item, q in prompts.items()}
    reports: dict[str, dict] = {}
    answers: dict[str, dict] = {}
    for row in rows:
        result = row.get("toolUseResult")
        if isinstance(result, dict) and "toolsUsed" in result:
            given = result.get("prompt") or ""
            question = given.removeprefix(INSTRUCTION_PREFIX).strip()
            item = item_by_question.get(question)
            if item:
                reports[item] = {
                    "report": _report_text(result),
                    "instruction_exact": given.startswith(INSTRUCTION_PREFIX),
                    "searched": "WebSearch" in (result.get("toolsUsed") or []),
                    "fetched": "WebFetch" in (result.get("toolsUsed") or []),
                    "subagent_tool_uses": result.get("totalToolUseCount"),
                    "subagent_ms": result.get("totalDurationMs"),
                    "subagent_tokens": result.get("totalTokens"),
                    "resolved_model": result.get("resolvedModel"),
                }
        content = (row.get("message") or {}).get("content")
        if row.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    for match in MARKER.finditer(block["text"]):
                        answers[match.group(1)] = {"answer_text": match.group(2).strip()}
    for item, answer in answers.items():
        meta = reports.get(item, {})
        report = meta.get("report")
        answer["report_match"] = None if report is None else answer["answer_text"] == report.strip()
        answer.update({k: v for k, v in meta.items() if k != "report"})
    return answers


def normalized_record(record: dict) -> dict:
    return {
        "answer_text": record["answer_text"],
        "cited_urls": _links_in_text(record["answer_text"]),
        "cited_urls_source": "answer_links",
        "evaluated_urls": [],
        "search_queries": [],
        "n_searches": None,
        "source": "claude_code_scheduled_task",
        **{k: v for k, v in record.items() if k != "answer_text"},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcripts", nargs="+")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--wave", type=int, required=True)
    args = ap.parse_args()
    prompts = load_prompts()
    answers: dict[str, dict] = {}
    for name in args.transcripts:
        path = Path(name)
        if not path.is_absolute():
            path = EXP / path
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        answers.update(parse_transcript(rows, prompts))
    out_dir = EXP / "data" / "raw" / "responses" / f"w{args.wave}" / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    for item, record in sorted(answers.items()):
        payload = {"source": "claude_code_scheduled_task", "arm": args.arm, "item_id": item,
                   "wave": args.wave, "normalized": normalized_record(record)}
        (out_dir / f"{item}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    records = list(answers.values())
    print(f"{len(records)} answers written to {out_dir}")
    print("searched:", sum(bool(r.get("searched")) for r in records),
          "fetched:", sum(bool(r.get("fetched")) for r in records),
          "exact instruction:", sum(bool(r.get("instruction_exact")) for r in records),
          "exact copy:", sum(r.get("report_match") is True for r in records),
          "models:", sorted({str(r.get("resolved_model")) for r in records}))
    missing = sorted(set(prompts) - set(answers))
    if args.wave > 0:
        print(f"coverage w{args.wave}: {len(records)}/{len(prompts)}; missing: {missing or 'none'}")


if __name__ == "__main__":
    main()
