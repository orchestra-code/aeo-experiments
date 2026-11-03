"""Run study prompts through unmodified Claude Code on a subscription (experiment 011).

One process per answer, in a new empty directory, from an empty environment.
See ``sketch.md``, "Instrument rules". Every rule there is enforced here:

- the binary is pinned and its sha256 checked before each run;
- no API key can reach the process, and a run counts only when the stream's
  ``init`` event reports ``apiKeySource: none``, no MCP servers and exactly the
  arm's tools;
- the run stops before starting an answer when the account is near a limit
  (never into overage).

Answers are written per arm in the shape of 009's ``responses`` tree. The raw
stream is kept next to them. All of it stays under the gitignored ``data/raw``.
Reruns skip answers already marked ``ok`` in the ledger.

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/harness/collect_cc.py check
    uv run python experiments/011-claude-code-fidelity/harness/collect_cc.py run --wave 0 \
        --items b2b_01,b2b_06 --arms cc_stock_full
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aeo_research.claude_answers import from_claude_code_stream

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
BINARY = RAW / "bin" / "claude-2.1.316"
BINARY_SHA256_FILE = RAW / "bin" / "claude-2.1.316.sha256"
PROMPTS = EXP.parent / "009-claude-model-fidelity" / "data" / "raw" / "prompts.csv"
LEDGER = RAW / "ledger_cc.jsonl"
RESPONSES = RAW / "responses"

MODEL = "claude-opus-5-5"
EFFORT = "medium"
SEED = 20261103
#: Pilot prompts: 009's pilot sheet, one per category.
PILOT_ITEMS = "b2b_01 b2b_06 b2b_09 b2b_14 b2b_17 b2b_22 b2b_25 b2b_30 b2b_33 b2b_38".split()
FIVE_HOUR_STOP = 0.60
SEVEN_DAY_STOP = 0.50
RUN_TIMEOUT_S = 900
ENV_KEEP = ("HOME", "PATH", "USER", "LANG")


@dataclass(frozen=True)
class Arm:
    name: str
    tools: tuple[str, ...]
    replace_system_prompt: bool


ARMS = {
    a.name: a
    for a in (
        Arm("cc_stock_full", ("WebFetch", "WebSearch"), False),
        Arm("cc_stock_search", ("WebSearch",), False),
        Arm("cc_none_full", ("WebFetch", "WebSearch"), True),
        Arm("cc_none_search", ("WebSearch",), True),
    )
}


class LimitReached(Exception):
    """The account is near a limit: stop the run, keep what is done."""


def clean_env() -> dict[str, str]:
    """The only environment a run sees. No key, token or session variable passes."""
    env = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    return env


def build_command(arm: Arm, prompt: str, binary: Path = BINARY) -> list[str]:
    tools = ",".join(arm.tools)
    cmd = [
        str(binary), "-p", prompt,
        "--model", MODEL,
        "--effort", EFFORT,
        "--tools", tools,
        "--allowedTools", tools,
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--output-format", "stream-json",
        "--verbose",
    ]
    if arm.replace_system_prompt:
        cmd += ["--system-prompt", ""]
    return cmd


def audit(normalized: dict, arm: Arm) -> list[str]:
    """Why this run does not count. Empty means it passes (sketch, G1)."""
    problems = []
    init = normalized["init"]
    if init.get("apiKeySource") != "none":
        problems.append(f"apiKeySource={init.get('apiKeySource')}")
    if init.get("mcp_servers"):
        problems.append("mcp_servers_present")
    if sorted(init.get("tools") or []) != sorted(arm.tools):
        problems.append(f"tools={init.get('tools')}")
    if init.get("model") != MODEL:
        problems.append(f"init_model={init.get('model')}")
    if normalized["main_models"] != [MODEL]:
        problems.append(f"main_models={normalized['main_models']}")
    if not normalized["answer_text"]:
        problems.append("no_answer")
    problems += normalized["warnings"]
    return problems


def limit_problem(windows: dict | None) -> str | None:
    """Why the next answer must not start, given the last utilization seen."""
    if not windows:
        return None
    if windows.get("is_using_overage"):
        return "using overage"
    if windows.get("status") not in (None, "allowed"):
        return f"status {windows.get('status')}"
    if (windows.get("five_hour") or 0) >= FIVE_HOUR_STOP:
        return f"five-hour window at {windows['five_hour']:.0%}"
    if (windows.get("seven_day") or 0) >= SEVEN_DAY_STOP:
        return f"seven-day window at {windows['seven_day']:.0%}"
    return None


def verify_binary() -> str:
    actual = hashlib.sha256(BINARY.read_bytes()).hexdigest()
    expected = BINARY_SHA256_FILE.read_text().strip()
    if actual != expected:
        raise SystemExit(f"binary sha256 mismatch: {actual} != {expected}")
    return actual


def load_prompts() -> dict[str, dict]:
    with PROMPTS.open(newline="") as handle:
        return {row["item_id"]: row for row in csv.DictReader(handle)}


def done_keys() -> set[tuple]:
    if not LEDGER.exists():
        return set()
    rows = [json.loads(line) for line in LEDGER.read_text().splitlines() if line]
    return {(r["wave"], r["arm"], r["item_id"]) for r in rows if r["status"] == "ok"}


def run_one(arm: Arm, item: dict, wave: int, binary_sha: str) -> dict:
    out_dir = RESPONSES / f"w{wave}" / arm.name
    out_dir.mkdir(parents=True, exist_ok=True)
    stream_path = out_dir / f"{item['item_id']}.stream.jsonl"
    started = dt.datetime.now(dt.UTC).isoformat()
    with tempfile.TemporaryDirectory(prefix="exp011-") as cwd:
        with stream_path.open("w") as out:
            try:
                proc = subprocess.run(
                    build_command(arm, item["text"]),
                    cwd=cwd,
                    env=clean_env(),
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=subprocess.PIPE,
                    timeout=RUN_TIMEOUT_S,
                    check=False,
                )
                exit_code, stderr = proc.returncode, proc.stderr.decode(errors="replace")[:2000]
            except subprocess.TimeoutExpired:
                exit_code, stderr = -1, "timeout"
    events = []
    for line in stream_path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    normalized = from_claude_code_stream(events)
    problems = audit(normalized, arm)
    if exit_code != 0:
        problems.append(f"exit_{exit_code}")
    record = {
        "source": "claude_code",
        "arm": arm.name,
        "item_id": item["item_id"],
        "wave": wave,
        "normalized": normalized,
    }
    (out_dir / f"{item['item_id']}.json").write_text(json.dumps(record, indent=1))
    return {
        "wave": wave,
        "arm": arm.name,
        "item_id": item["item_id"],
        "status": "ok" if not problems else "failed",
        "problems": problems,
        "started": started,
        "ended": dt.datetime.now(dt.UTC).isoformat(),
        "binary_sha256": binary_sha,
        "version": normalized["init"].get("claude_code_version"),
        "n_searches": normalized["n_searches"],
        "n_fetches": normalized["n_fetches"],
        "total_cost_usd": normalized["total_cost_usd"],
        "duration_ms": normalized["duration_ms"],
        "rate_limits": normalized["rate_limits"],
        "stderr": stderr if exit_code else "",
    }


def run_arm(arm: Arm, items: list[dict], wave: int, sha: str, workers: int) -> None:
    def job(item):
        return run_one(arm, item, wave, sha)

    last = None
    pending = list(items)
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        while pending:
            reason = limit_problem(last)
            if reason:
                raise LimitReached(reason)
            batch, pending = pending[:workers], pending[workers:]
            for row in pool.map(job, batch):
                with LEDGER.open("a") as ledger:
                    ledger.write(json.dumps(row) + "\n")
                print(
                    f"{row['arm']:16} {row['item_id']} {row['status']:6} "
                    f"s={row['n_searches']} f={row['n_fetches']} "
                    f"cost~{row['total_cost_usd']} {row['problems'] or ''}",
                    flush=True,
                )
                if row["rate_limits"]:
                    last = row["rate_limits"]["last"]


def cmd_check(_args) -> None:
    sha = verify_binary()
    version = subprocess.run(
        [str(BINARY), "--version"], env=clean_env(), capture_output=True, text=True, check=True
    ).stdout.strip()
    leaked = sorted(k for k in clean_env() if "KEY" in k or "TOKEN" in k or k.startswith("ANTHROPIC"))
    print(f"binary {version} sha256 {sha[:16]}…; env passed: {sorted(clean_env())}; leaked: {leaked}")
    if leaked:
        raise SystemExit("a credential would reach the process")
    print("prompts:", len(load_prompts()), "done:", len(done_keys()))


def cmd_run(args) -> None:
    sha = verify_binary()
    prompts = load_prompts()
    item_ids = args.items.split(",") if args.items else PILOT_ITEMS
    arm_names = list(ARMS) if args.arms == "all" else args.arms.split(",")
    rng = random.Random(f"{SEED}:{args.wave}")
    rng.shuffle(arm_names)
    done = done_keys()
    print(f"arm order: {arm_names}", flush=True)
    for name in arm_names:
        order = list(item_ids)
        rng.shuffle(order)
        items = [prompts[i] for i in order if (args.wave, name, i) not in done]
        if not items:
            continue
        try:
            run_arm(ARMS[name], items, args.wave, sha, args.workers)
        except LimitReached as stop:
            raise SystemExit(f"STOPPED before finishing {name}: {stop}") from stop


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    run = sub.add_parser("run")
    run.add_argument("--wave", type=int, required=True)
    run.add_argument("--arms", default="all")
    run.add_argument("--items", default=None, help="comma-separated, default the 10 pilot prompts")
    run.add_argument("--workers", type=int, default=3)
    run.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    if shutil.which(str(BINARY)) is None:
        raise SystemExit(f"pinned binary missing: {BINARY}")
    args.fn(args)


if __name__ == "__main__":
    main()
