"""Anthropic Messages / Batches collector for experiment 009's API arms.

Modeled on ``008/harness/collect_openai.py``: ledger-driven and idempotent on
(arm, item_id, wave). An (arm, item, wave) that is ``submitted`` or
``collected`` in the ledger is never sent again; a ``failed`` one may be
retried. The ledger stores ``keyword_sha256``, never prompt text.

Subcommands:

- ``realtime``: run the selected arms x prompts now (concurrency 4). The first
  call of each arm runs before the rest, so the arm's cached system prompt is
  written once and then read.
- ``submit``: the same requests as one Message Batch (50% token price).
- ``status``: batch progress for pending batches, then spend by arm.
- ``collect``: download ended batches. A result that stopped on
  ``pause_turn`` is continued in real time and flagged in the ledger.

Every turn's full JSON goes to
``<out-dir>/w<wave>/<arm>/<item_id>.json`` with the normalized answer
(``aeo_research.claude_answers.from_api_message``).

Spend guard: before sending anything, the estimated cost of the new calls
(per-arm priors below) plus the ledger's spend so far (collected cost, plus
the prior for still-pending batch calls) must stay under ``--max-cost``.

Usage (repo root):
    uv run python experiments/009-claude-model-fidelity/harness/collect_anthropic.py \
        realtime --wave 0 --items b2b_01 --arms all \
        --max-cost 6 \
        --ledger experiments/009-claude-model-fidelity/data/raw/smoke_ledger.jsonl
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import sys
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from aeo_research.claude_answers import from_api_message  # noqa: E402
from aeo_research.dataforseo import Ledger  # noqa: E402 (generic JSONL ledger)
from aeo_research.pricing import cost_from_usage, sum_usage  # noqa: E402
from anthropic_client import DEFAULT_ENV_FILE, make_client  # noqa: E402
from arms import ARMS, CORE_ARMS, build_params, parse_user_location  # noqa: E402
from leak_prompt import load_template, sha256  # noqa: E402

RAW = EXP / "data" / "raw"
DEFAULT_USER_LOCATION = "Pittsburgh,Pennsylvania,US"
CONCURRENCY = 4
RETRIES = 3
BACKOFF_S = 20.0
MAX_CONTINUATIONS = 3
TAG = "aeo-exp009"

#: Prior realtime USD per call (tokens + searches), from the plan's cost model.
PRIOR_USD = {
    "opus55_leak": 0.35,
    "opus55_plain": 0.30,
    "sonnet5_plain": 0.10,
    "sonnet5_leak_think": 0.18,
    "sonnet5_leak_low": 0.15,
    "sonnet5_prod": 0.13,
    "haiku45_leak": 0.10,
    # pilot-only arms (the raw leak is ~158k tokens; a 1h cache write is ~$1.27)
    "sonnet5_leak_nothink": 0.15,
    "opus55_leak_fetch": 0.50,
    "opus55_leak_ws2026": 0.40,
    "opus55_leak_raw": 1.40,
}
#: Share of each prior that is web search ($0.01 per search; ~5 per call,
#: at most 5 on sonnet5_prod). Batch halves only the token share.
SEARCH_SHARE_USD = {arm: (0.04 if arm == "sonnet5_prod" else 0.05) for arm in PRIOR_USD}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def custom_id(arm: str, item_id: str, wave: int) -> str:
    return f"{arm}__{item_id}__w{wave}"


def prior_cost(arm: str, batch: bool) -> float:
    total, search = PRIOR_USD[arm], SEARCH_SHARE_USD[arm]
    return (total - search) * 0.5 + search if batch else total


# ------------------------------------------------------------ ledger helpers


class SafeLedger(Ledger):
    """Ledger with a lock around appends (realtime runs 4 threads)."""

    _lock = threading.Lock()

    def append(self, record: dict) -> None:
        with self._lock:
            super().append(record)


def latest(ledger: Ledger):
    return ledger.frame()


def done_keys(ledger: Ledger) -> set[tuple[str, str, int]]:
    df = latest(ledger)
    if df.empty or "arm" not in df:
        return set()
    live = df[df["status"].isin(["submitted", "collected"])]
    return {(r.arm, r.item_id, int(r.wave)) for r in live.itertuples()}


def ledger_spend(ledger: Ledger) -> tuple[float, float]:
    """(collected USD, prior USD of calls still pending in batches)."""
    df = latest(ledger)
    if df.empty:
        return 0.0, 0.0
    spent = 0.0
    if "cost_usd" in df:
        spent = float(df.loc[df["status"] == "collected", "cost_usd"].fillna(0).sum())
    pending = df[df["status"] == "submitted"]
    pend = sum(prior_cost(r.arm, True) for r in pending.itertuples())
    return spent, pend


def spend_by_arm(ledger: Ledger) -> None:
    df = latest(ledger)
    if df.empty or "arm" not in df:
        print("ledger empty")
        return
    print(f"{'arm':22} {'n':>4} {'failed':>6} {'pending':>7} {'usd':>9} {'usd/call':>9} "
          f"{'searches':>8}")
    for arm, g in df.groupby("arm"):
        col = g[g["status"] == "collected"]
        usd = float(col["cost_usd"].fillna(0).sum()) if "cost_usd" in col else 0.0
        n = len(col)
        searches = col["n_searches"].fillna(0).mean() if n and "n_searches" in col else 0
        print(f"{arm:22} {n:>4} {int((g['status'] == 'failed').sum()):>6} "
              f"{int((g['status'] == 'submitted').sum()):>7} {usd:>9.4f} "
              f"{(usd / n if n else 0):>9.4f} {searches:>8.1f}")
    spent, pend = ledger_spend(ledger)
    print(f"total collected ${spent:.4f}; pending batch prior ${pend:.2f}")


# ------------------------------------------------------------ requests


def load_prompts(path: str) -> dict[str, dict]:
    with open(path, newline="") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def resolve_arms(spec: str) -> list[str]:
    if spec == "all":
        return list(CORE_ARMS)  # pilot-only arms must be named explicitly
    arms = [a.strip() for a in spec.split(",") if a.strip()]
    bad = [a for a in arms if a not in ARMS]
    if bad:
        raise SystemExit(f"unknown arms {bad}; API arms are {list(ARMS)}")
    return arms


class Context:
    """Everything needed to (re)build a request, recorded in the ledger."""

    def __init__(self, a: argparse.Namespace):
        self.wave = a.wave
        self.run_date = date.fromisoformat(a.run_date) if a.run_date else date.today()
        self.user_location = parse_user_location(a.user_location)
        self.web_search_version = a.web_search_version
        self.leak_variant = a.leak_variant
        self._leaks: dict[str, str] = {}

    def leak(self, variant: str) -> str:
        if variant not in self._leaks:
            self._leaks[variant] = load_template(variant)
        return self._leaks[variant]

    def effective(self, arm: str) -> tuple[str, str | None]:
        """(web_search_version, leak_variant) after the arm's own overrides."""
        spec = ARMS[arm]
        ws = spec.web_search_version or self.web_search_version
        if spec.system == "prod":
            ws = "20250305"
        variant = (spec.leak_variant or self.leak_variant) if spec.uses_leak else None
        return ws, variant

    def params(self, arm: str, text: str) -> dict:
        _, variant = self.effective(arm)
        leak = self.leak(variant) if variant else None
        return build_params(arm, text, self.run_date, leak, self.user_location,
                            self.web_search_version)

    def meta(self, arm: str | None = None) -> dict:
        ws, variant = self.effective(arm) if arm else (self.web_search_version, self.leak_variant)
        return {
            "run_date": self.run_date.isoformat(),
            "user_location": json.dumps(self.user_location) if self.user_location else None,
            "web_search_version": ws,
            "leak_variant": variant if arm else self.leak_variant,
        }


def system_sha(params: dict) -> str | None:
    system = params.get("system")
    if system is None:
        return None
    if isinstance(system, list):
        system = "".join(b.get("text", "") for b in system)
    return sha256(system)


def create_with_retry(client, params: dict):
    import anthropic

    retryable = (
        anthropic.RateLimitError,
        anthropic.InternalServerError,
        anthropic.APIConnectionError,  # includes APITimeoutError
    )
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            return client.messages.create(**params)
        except retryable as e:
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code < 500 and e.status_code != 429:
                raise
            last = e
        time.sleep(BACKOFF_S * (attempt + 1))
    raise RuntimeError(f"gave up after {RETRIES} attempts: {last}")


def continue_paused(client, params: dict, first) -> tuple[list, int]:
    """Resume ``pause_turn`` turns: re-send with the assistant content appended
    (no extra user message; claude-api skill, tool-use-concepts.md). Returns
    (continuation messages, continuations used)."""
    turns = []
    content = list(first.content)
    resp = first
    n = 0
    while resp.stop_reason == "pause_turn" and n < MAX_CONTINUATIONS:
        n += 1
        p = dict(params)
        p["messages"] = list(params["messages"]) + [{"role": "assistant", "content": content}]
        resp = create_with_retry(client, p)
        turns.append(resp)
        content = content + list(resp.content)
    return turns, n


def record_result(
    ledger: Ledger,
    out_dir: Path,
    base: dict,
    params: dict,
    turns: list,
    sources: list[str],
    elapsed: float | None,
    extra: dict | None = None,
) -> dict:
    """Write the response file and the ``collected`` ledger record."""
    dicts = [t.to_dict(mode="json") if hasattr(t, "to_dict") else t for t in turns]
    norm = from_api_message(dicts)
    model = dicts[0].get("model") or params["model"]
    costs = [
        cost_from_usage(model, d.get("usage") or {}, batch=(src == "batch"))
        for d, src in zip(dicts, sources)
    ]
    comp = defaultdict(float)
    for c in costs:
        for k in ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read",
                  "web_search", "total"):
            comp[k] += c[k]
    usage = sum_usage(d.get("usage") or {} for d in dicts)

    path = out_dir / f"w{base['wave']}" / base["arm"] / f"{base['item_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in params.items() if k not in ("messages", "system")}
    path.write_text(json.dumps(
        {
            "custom_id": base["task_id"],
            **{k: base.get(k) for k in ("arm", "item_id", "wave", "mode", "run_date",
                                         "user_location", "web_search_version",
                                         "leak_variant")},
            "system_sha256": system_sha(params),
            "params_meta": meta,
            "turn_sources": sources,
            "turns": dicts,
            "normalized": norm,
            "cost": dict(comp),
        },
        indent=1,
        ensure_ascii=False,
    ))
    rec = base | {
        "status": "collected",
        "collected_at": now_iso(),
        "model": model,
        "stop_reason": norm["stop_reason"],
        "n_turns": len(dicts),
        "paused": len(dicts) > 1,
        "usage": usage,
        "n_searches": norm["n_searches"],
        "web_search_requests": norm["web_search_requests"],
        "n_cited": len(norm["cited_urls"]),
        "n_evaluated": len(norm["evaluated_urls"]),
        "answer_chars": len(norm["answer_text"]),
        "cost_usd": round(comp["total"], 6),
        "cost_breakdown": {k: round(v, 6) for k, v in comp.items()},
        "elapsed_s": round(elapsed, 1) if elapsed is not None else None,
        "result_path": str(path),
    }
    if "batch" in sources and len(sources) > 1:
        rec["continued_realtime"] = True
    rec.update(extra or {})
    ledger.append(rec)
    return rec


# ------------------------------------------------------------ subcommands


def plan_todo(a, ledger: Ledger, prompts: dict) -> list[tuple[str, dict]]:
    arms = resolve_arms(a.arms)
    items = [i.strip() for i in a.items.split(",")] if a.items else list(prompts)
    missing = [i for i in items if i not in prompts]
    if missing:
        raise SystemExit(f"unknown item ids {missing}")
    per_arm = {arm: items for arm in arms}
    for spec in getattr(a, "arm_items", None) or []:
        arm, _, ids = spec.partition("=")
        if arm not in per_arm:
            raise SystemExit(f"--arm-items for {arm!r}, which is not in --arms")
        sub = [i.strip() for i in ids.split(",") if i.strip()]
        bad = [i for i in sub if i not in prompts]
        if bad:
            raise SystemExit(f"unknown item ids {bad}")
        per_arm[arm] = sub
    done = done_keys(ledger)
    todo = [(arm, prompts[i]) for arm in arms for i in per_arm[arm]
            if (arm, i, a.wave) not in done]
    skipped = sum(len(v) for v in per_arm.values()) - len(todo)
    print(f"wave {a.wave}: {len(todo)} calls to make, {skipped} already done")
    return todo


def guard_cost(a, ledger: Ledger, todo, batch: bool) -> None:
    est = sum(prior_cost(arm, batch) for arm, _ in todo)
    spent, pend = ledger_spend(ledger)
    total = spent + pend + est
    print(f"cost guard: spent ${spent:.2f} + pending ${pend:.2f} + estimate ${est:.2f} "
          f"= ${total:.2f} (cap ${a.max_cost:.2f})")
    if total > a.max_cost:
        raise SystemExit("refusing: estimate exceeds --max-cost")


def base_record(a, ctx: Context, arm: str, row: dict, mode: str) -> dict:
    return {
        "task_id": custom_id(arm, row["item_id"], a.wave),
        "tag": f"{TAG}-w{a.wave}",
        "wave": a.wave,
        "item_id": row["item_id"],
        "arm": arm,
        "prompt_intent": row.get("intent"),
        "category": row.get("category"),
        "model": ARMS[arm].model,
        "mode": mode,
        "keyword_sha256": hashlib.sha256(row["text"].encode()).hexdigest(),
        "submitted_at": now_iso(),
        **ctx.meta(arm),
    }


def cmd_realtime(a) -> None:
    ledger = SafeLedger(a.ledger)
    prompts = load_prompts(a.prompts)
    todo = plan_todo(a, ledger, prompts)
    if not todo:
        return
    guard_cost(a, ledger, todo, batch=False)
    ctx = Context(a)
    client = make_client(a.env_file)
    out_dir = Path(a.out_dir)

    def work(job) -> None:
        arm, row = job
        base = base_record(a, ctx, arm, row, "realtime")
        params = ctx.params(arm, row["text"])
        base["system_sha256"] = system_sha(params)
        t0 = time.time()
        try:
            first = create_with_retry(client, params)
            more, _ = continue_paused(client, params, first)
        except Exception as e:  # noqa: BLE001 (recorded, not fatal to the wave)
            ledger.append(base | {"status": "failed", "error": f"{type(e).__name__}: {e}"[:400]})
            print(f"  FAILED {arm} {row['item_id']}: {type(e).__name__}: {str(e)[:200]}")
            return
        turns = [first, *more]
        rec = record_result(ledger, out_dir, base, params, turns,
                            ["realtime"] * len(turns), time.time() - t0)
        print(f"  {arm:22} {row['item_id']} {rec['stop_reason']:>10} turns={rec['n_turns']} "
              f"searches={rec['n_searches']} cited={rec['n_cited']} "
              f"evaluated={rec['n_evaluated']} ${rec['cost_usd']:.4f} {rec['elapsed_s']}s")

    # First call per arm first, so each arm's cache entry is written once.
    firsts, rest, seen = [], [], set()
    for job in todo:
        (rest if job[0] in seen else firsts).append(job)
        seen.add(job[0])
    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        list(pool.map(work, firsts))
        list(pool.map(work, rest))
    spend_by_arm(ledger)


def cmd_submit(a) -> None:
    ledger = SafeLedger(a.ledger)
    prompts = load_prompts(a.prompts)
    todo = plan_todo(a, ledger, prompts)
    if not todo:
        return
    guard_cost(a, ledger, todo, batch=True)
    ctx = Context(a)
    client = make_client(a.env_file)

    requests, bases = [], []
    for arm, row in todo:
        params = ctx.params(arm, row["text"])
        base = base_record(a, ctx, arm, row, "batch")
        base["system_sha256"] = system_sha(params)
        requests.append({"custom_id": base["task_id"], "params": params})
        bases.append(base)
    batch = client.messages.batches.create(requests=requests)
    manifest = RAW / "batches" / f"{batch.id}.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(
        {"batch_id": batch.id, "created_at": now_iso(), "wave": a.wave,
         "custom_ids": [b["task_id"] for b in bases], **ctx.meta()}, indent=1))
    for base in bases:
        ledger.append(base | {"status": "submitted", "batch_id": batch.id})
    print(f"submitted batch {batch.id} with {len(requests)} requests "
          f"({batch.processing_status})")


def pending_batches(ledger: Ledger) -> dict[str, list]:
    df = latest(ledger)
    if df.empty or "batch_id" not in df:
        return {}
    pend = df[(df["status"] == "submitted") & df["batch_id"].notna()]
    return {bid: list(g.itertuples()) for bid, g in pend.groupby("batch_id")}


def cmd_status(a) -> None:
    ledger = Ledger(a.ledger)
    batches = pending_batches(ledger)
    if batches:
        client = make_client(a.env_file)
        for bid, recs in batches.items():
            b = client.messages.batches.retrieve(bid)
            c = b.request_counts
            print(f"{bid}: {b.processing_status} ({len(recs)} pending in ledger) "
                  f"processing={c.processing} succeeded={c.succeeded} errored={c.errored} "
                  f"canceled={c.canceled} expired={c.expired}")
    else:
        print("no pending batches")
    spend_by_arm(ledger)


def cmd_collect(a) -> None:
    ledger = SafeLedger(a.ledger)
    batches = pending_batches(ledger)
    if not batches:
        print("no pending batches")
        return
    prompts = load_prompts(a.prompts)
    client = make_client(a.env_file)
    out_dir = Path(a.out_dir)
    for bid, recs in batches.items():
        b = client.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            print(f"{bid}: {b.processing_status}, skipping")
            continue
        by_id = {r.task_id: r for r in recs}
        n_ok = n_bad = n_paused = 0
        for result in client.messages.batches.results(bid):
            rec = by_id.get(result.custom_id)
            if rec is None:
                continue
            base = {k: v for k, v in rec._asdict().items()
                    if k in ("task_id", "tag", "wave", "item_id", "arm", "prompt_intent",
                             "category", "model", "mode", "keyword_sha256", "submitted_at",
                             "run_date", "user_location", "web_search_version",
                             "leak_variant", "system_sha256", "batch_id")}
            base["wave"] = int(base["wave"])
            kind = result.result.type
            if kind != "succeeded":
                err = getattr(getattr(result.result, "error", None), "error", None)
                ledger.append(base | {"status": "failed", "error": f"batch {kind}: {err}"[:400]})
                n_bad += 1
                continue
            msg = result.result.message
            turns, sources = [msg], ["batch"]
            params = None
            if msg.stop_reason == "pause_turn":
                n_paused += 1
                params = rebuild_params(rec, prompts)
                more, _ = continue_paused(client, params, msg)
                turns += more
                sources += ["realtime"] * len(more)
            if params is None:
                params = rebuild_params(rec, prompts)
            record_result(ledger, out_dir, base, params, turns, sources, None,
                          extra={"paused_in_batch": msg.stop_reason == "pause_turn"})
            n_ok += 1
        print(f"{bid}: collected {n_ok}, failed {n_bad}, paused-and-continued {n_paused}")
    spend_by_arm(ledger)


def rebuild_params(rec, prompts: dict) -> dict:
    """Rebuild the exact request from the ledger record (for continuations)."""
    ns = argparse.Namespace(
        wave=int(rec.wave),
        run_date=rec.run_date,
        user_location=None,
        web_search_version=rec.web_search_version
        if isinstance(rec.web_search_version, str) else "20250305",
        leak_variant=rec.leak_variant if isinstance(rec.leak_variant, str) else "trimmed",
    )
    ctx = Context(ns)
    ctx.user_location = json.loads(rec.user_location) if isinstance(rec.user_location, str) else None
    params = ctx.params(rec.arm, prompts[rec.item_id]["text"])
    if system_sha(params) != (rec.system_sha256 if isinstance(rec.system_sha256, str) else None):
        raise SystemExit(f"{rec.task_id}: rebuilt system prompt differs from the submitted one")
    return params


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--prompts", default=str(RAW / "prompts.csv"))
    common.add_argument("--ledger", default=str(RAW / "ledger.jsonl"))
    common.add_argument("--out-dir", default=str(RAW / "responses"))
    common.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    common.add_argument("--max-cost", type=float, default=250.0,
                        help="USD cap on ledger spend plus this run's estimate")

    send = argparse.ArgumentParser(add_help=False)
    send.add_argument("--wave", type=int, required=True)
    send.add_argument("--arms", default="all", help="'all' or comma-separated API arms")
    send.add_argument("--items", default=None, help="comma-separated item ids (default: all)")
    send.add_argument("--arm-items", action="append", default=[],
                      help="restrict one arm to its own items, arm=b2b_01,b2b_06 (repeatable)")
    send.add_argument("--run-date", default=None, help="YYYY-MM-DD for the leak date slot")
    # The UI account signs in from Pittsburgh; every confirmatory wave uses it.
    # (The pilot's API calls used Boston, a recorded pilot deviation.)
    send.add_argument("--user-location", default=DEFAULT_USER_LOCATION,
                      help='"City,Region,US" (default: %(default)s)')
    send.add_argument("--web-search-version", default="20250305", choices=["20250305", "20260209"])
    send.add_argument("--leak-variant", default="trimmed", choices=["trimmed", "raw"])

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("realtime", parents=[common, send]).set_defaults(fn=cmd_realtime)
    sub.add_parser("submit", parents=[common, send]).set_defaults(fn=cmd_submit)
    sub.add_parser("status", parents=[common]).set_defaults(fn=cmd_status)
    sub.add_parser("collect", parents=[common]).set_defaults(fn=cmd_collect)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
