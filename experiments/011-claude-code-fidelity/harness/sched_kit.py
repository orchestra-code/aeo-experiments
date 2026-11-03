"""The frozen scheduled-task arm of experiment 011 (`sched_kit`).

Holds the task prompt, the seeded assignment of prompts to tasks, the request body for a
one-time task, the check a task must pass before it can fire, and the transcript pull.
Creating and clearing the task happens through the claude.ai routines API, which needs a
signed-in session, so a person or agent calls it with the body printed here.

Order for every task (spec, Arms): create it with a start time at least 3 minutes away,
clear its connectors with `{"clear_mcp_connections": true}`, read it back, and save that
reply to a file for `verify`. If `verify` reports a problem, disable the task. Never let it
fire with a connector attached: the server attaches all of the account's connectors to a
new task, even when the request lists none.

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/harness/sched_kit.py batches --wave 1
    uv run python .../sched_kit.py body --wave 1 --batch 1 --run-at 2026-11-03T18:00:00Z --environment-id env_...
    uv run python .../sched_kit.py verify --wave 1 --batch 1 --routine-json reply.json
    uv run python .../sched_kit.py pull --session cse_... --out data/raw/routine/w1_b1.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
PROMPTS = EXP.parent / "009-claude-model-fidelity" / "data" / "raw" / "prompts.csv"
BINARY = RAW / "bin" / "claude-2.1.316"

SEED = 20261103
MODEL = "claude-opus-5-5"
ALLOWED_TOOLS = ["Agent", "WebSearch", "WebFetch"]
DISALLOWED_TOOLS = ["PushNotification"]
BATCH_SIZE = 10

#: Given to each subagent, with nothing else. It holds the question text, copied exactly.
INSTRUCTION_PREFIX = (
    "Use web search to research this question, then answer it the way you would answer "
    "the person asking it: "
)

MAIN_PROMPT = (
    "This is a research collection run. Do not send notifications. Do not write files. "
    "Do not use any connector.\n\n"
    "For each question below, in the listed order and one at a time, launch one new "
    "general-purpose subagent with the Agent tool, using the same model as this session. "
    "Give each subagent this instruction and nothing else, with the question text copied "
    f"exactly:\n\n{INSTRUCTION_PREFIX}<question text>\n\n"
    "Do not research or answer the questions yourself. When a subagent finishes, print its "
    "complete final answer word for word, with no summary, edits or commentary, between "
    "these two lines, as its own message:\n=== ANSWER <id> ===\n=== END <id> ===\n\n"
    "Questions:\n\n"
)


def load_prompts(path: Path = PROMPTS) -> dict[str, str]:
    with path.open(newline="") as f:
        return {r["item_id"]: r["text"] for r in csv.DictReader(f)}


def batches(wave: int, item_ids: list[str]) -> list[list[str]]:
    """Prompts per task for a wave, shuffled by seed, in tasks of 10."""
    order = sorted(item_ids)
    random.Random(f"{SEED}:sched:{wave}").shuffle(order)
    return [order[i : i + BATCH_SIZE] for i in range(0, len(order), BATCH_SIZE)]


def build_prompt(items: list[str], prompts: dict[str, str]) -> str:
    return MAIN_PROMPT + "\n\n".join(f"{i}: {prompts[i]}" for i in items)


def create_body(wave: int, batch: int, items: list[str], prompts: dict[str, str], run_at: str,
                environment_id: str) -> dict:
    """Request body for a one-time task. `effort` is not set: the API drops it (spec, §A)."""
    return {
        "name": f"exp011 w{wave} batch {batch} (research, one-time)",
        "run_once_at": run_at,
        "enabled": True,
        "job_config": {
            "ccr": {
                "environment_id": environment_id,
                "session_context": {
                    "model": MODEL,
                    "sources": [],
                    "allowed_tools": ALLOWED_TOOLS,
                    "disallowed_tools": DISALLOWED_TOOLS,
                },
                "events": [
                    {
                        "data": {
                            "uuid": str(uuid.uuid4()),
                            "session_id": "",
                            "type": "user",
                            "parent_tool_use_id": None,
                            "message": {"content": build_prompt(items, prompts), "role": "user"},
                        }
                    }
                ],
            }
        },
    }


def routine_problems(routine: dict, expected_prompt: str) -> list[str]:
    """What stops a task from firing, read from the API's reply for that task."""
    problems = []
    if routine.get("mcp_connections"):
        names = [c.get("name") for c in routine["mcp_connections"]]
        problems.append(f"connectors attached: {names}")
    context = ((routine.get("job_config") or {}).get("ccr") or {}).get("session_context") or {}
    if context.get("model") != MODEL:
        problems.append(f"model is {context.get('model')}")
    if sorted(context.get("allowed_tools") or []) != sorted(ALLOWED_TOOLS):
        problems.append(f"allowed tools are {context.get('allowed_tools')}")
    if (context.get("disallowed_tools") or []) != DISALLOWED_TOOLS:
        problems.append(f"disallowed tools are {context.get('disallowed_tools')}")
    if context.get("sources"):
        problems.append("sources attached")
    prompt = (routine.get("derived_state") or {}).get("prompt")
    if prompt != expected_prompt:
        problems.append("prompt differs from the frozen text")
    return problems


def cmd_batches(args) -> None:
    prompts = load_prompts()
    for n, items in enumerate(batches(args.wave, list(prompts)), start=1):
        digest = hashlib.sha256(build_prompt(items, prompts).encode()).hexdigest()[:12]
        print(f"batch {n}: {' '.join(items)}  prompt sha256 {digest}")


def cmd_body(args) -> None:
    prompts = load_prompts()
    items = batches(args.wave, list(prompts))[args.batch - 1]
    print(json.dumps(create_body(args.wave, args.batch, items, prompts, args.run_at, args.environment_id), indent=1))


def cmd_verify(args) -> None:
    prompts = load_prompts()
    items = batches(args.wave, list(prompts))[args.batch - 1]
    text = Path(args.routine_json).read_text()
    routine, _ = json.JSONDecoder().raw_decode(text[text.index("{") :])
    routine = routine.get("data", routine) if "derived_state" not in routine else routine
    problems = routine_problems(routine, build_prompt(items, prompts))
    if problems:
        raise SystemExit(f"DO NOT FIRE, batch {args.batch}: {problems}")
    print(f"batch {args.batch} clean: no connectors, frozen prompt, frozen tools, {MODEL}")


def cmd_pull(args) -> None:
    """Pull a finished run's full transcript with a one-word Haiku turn from a scratch folder."""
    session = "session_" + re.sub(r"^(cse|session)_", "", args.session)
    out = Path(args.out)
    if not out.is_absolute():
        out = EXP / out
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.path.realpath(tmp)
        env = {k: os.environ[k] for k in ("HOME", "PATH", "USER", "LANG") if k in os.environ}
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        done = subprocess.run(
            [str(BINARY), "-p", "Reply with the single word: ok", "--teleport", session,
             "--model", "claude-haiku-5-5", "--tools", "", "--setting-sources", "",
             "--strict-mcp-config", "--disable-slash-commands", "--output-format", "json"],
            cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600,
        )
        if done.returncode:
            raise SystemExit(f"teleport failed ({done.returncode}): {done.stderr[:400]}")
        folder = Path.home() / ".claude" / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", cwd)
        found = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_size)
        if not found:
            raise SystemExit(f"no transcript in {folder}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(found[-1], out)
        shutil.rmtree(folder)
    print(f"{out}: {out.stat().st_size} bytes")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("batches")
    p.add_argument("--wave", type=int, required=True)
    p.set_defaults(fn=cmd_batches)
    p = sub.add_parser("body")
    p.add_argument("--wave", type=int, required=True)
    p.add_argument("--batch", type=int, required=True)
    p.add_argument("--run-at", required=True, help="RFC3339 UTC, at least 3 minutes away")
    p.add_argument("--environment-id", required=True, help="the account's default cloud environment")
    p.set_defaults(fn=cmd_body)
    p = sub.add_parser("verify")
    p.add_argument("--wave", type=int, required=True)
    p.add_argument("--batch", type=int, required=True)
    p.add_argument("--routine-json", required=True)
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("pull")
    p.add_argument("--session", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pull)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
