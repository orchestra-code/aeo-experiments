"""Experiment 004: shared paths, pins, prices, ledger and cost guard (sketch.md).

Every 004 script imports this module, so the arms, the pilot prompts, the
lexicon pin, the price table and the $10 cap live in one place.

Data location. A worktree holds no gitignored data, so raw data always goes to
the MAIN checkout, resolved at runtime from git's common dir
(``<MAIN>/experiments/004-api-vs-ui/data/raw/``, gitignored). Prompts and
lexicon v3 are read from experiment 010's raw data in the main checkout. No
010 answer is ever read. ``EXP004_RAW`` overrides the raw directory (tests).

Keys come only from ``<MAIN>/.env.local``. Nothing falls back to the process
environment or to another repository, and no key is ever printed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
EXP_NAME = EXP.name  # "004-api-vs-ui"


def main_checkout() -> Path:
    """The main checkout: parent of git's common dir (worktrees share it)."""
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=HERE, capture_output=True, text=True, check=True,
    ).stdout.strip()
    return Path(out).parent


MAIN = main_checkout()
RAW = Path(os.environ.get("EXP004_RAW") or MAIN / "experiments" / EXP_NAME / "data" / "raw")
ENV_FILE = MAIN / ".env.local"
RESULTS = EXP / "results"

EXP010_RAW = MAIN / "experiments" / "010-shortlist-stability" / "data" / "raw"
PROMPTS = EXP010_RAW / "prompts_b2b.csv"
LEXICON_V3 = EXP010_RAW / "lexicon_v3" / "lexicon_v3.csv"
LEXICON_V3_SHA256 = "6084f47ca1831474de9cb64d79425d522b75ac409d2b5080b24653ec9905cf5d"

#: Sibling experiments whose committed code 004 reuses (read from this checkout).
EXP009 = EXP.parent / "009-claude-model-fidelity"
EXP010 = EXP.parent / "010-shortlist-stability"

SEED = 20261105
N_BOOT = 2000
PILOT_ITEMS = tuple(f"b2b_{n:02d}" for n in (1, 6, 9, 14, 17, 22, 25, 30, 33, 38))
UI_ROUNDS = (1, 2, 3)
COST_CAP_USD = 10.0
TAG = "aeo-exp004"

# ------------------------------------------------------------------ arms

OPENAI_MODEL = "gpt-6-luna"
GEMINI_MODEL = "gemini-3.5-flash-lite"
#: Lowest effort first. cg_api_low uses the first one the API accepts (probed).
LOW_EFFORT_CANDIDATES = ("none", "minimal", "low")


@dataclass(frozen=True)
class Arm:
    name: str
    platform: str  # "chatgpt" | "gemini"
    instrument: str  # "dataforseo" | "openai" | "gemini_api"
    leak: bool = False
    low_effort: bool = False


ARMS = {
    a.name: a
    for a in (
        Arm("cg_ui", "chatgpt", "dataforseo"),
        Arm("cg_api_plain", "chatgpt", "openai"),
        Arm("cg_api_low", "chatgpt", "openai", low_effort=True),
        Arm("cg_api_leak", "chatgpt", "openai", leak=True),
        Arm("gm_ui", "gemini", "dataforseo"),
        Arm("gm_api_plain", "gemini", "gemini_api"),
        Arm("gm_api_leak", "gemini", "gemini_api", leak=True),
    )
}
UI_ARM = {"chatgpt": "cg_ui", "gemini": "gm_ui"}
OPENAI_ARMS = tuple(a for a, v in ARMS.items() if v.instrument == "openai")
GEMINI_ARMS = tuple(a for a, v in ARMS.items() if v.instrument == "gemini_api")
API_ARMS = OPENAI_ARMS + GEMINI_ARMS

# ---------------------------------------------------------------- prices
# List prices, checked 2026-11-05. Every cost 004 reports is an estimate from
# token and tool-call counts at these prices (009's rule), never an invoice.
#
# OpenAI, https://developers.openai.com/api/docs/pricing and
# https://developers.openai.com/api/docs/models/gpt-6-luna (Standard tier):
#   gpt-6-luna input $0.10 / 1M, cached input $0.01 / 1M, cache writes $0.125 / 1M,
#   output $0.50 / 1M
#   (reasoning tokens bill as output). Prompts over 272K input tokens cost more;
#   004's never come close. Web search tool: $10.00 per 1,000 calls, plus search
#   content tokens billed at model rates (they arrive inside input_tokens).
# Google, https://aistudio.google.com/docs/pricing (redirect target of
# ai.google.dev/gemini-api/docs/pricing), paid tier, Standard:
#   gemini-3.5-flash-lite input $0.30 / 1M, output incl. thinking $2.50 / 1M.
#   Grounding with Google Search: $14 per 1,000 search requests after 5,000 free
#   per month shared across Gemini 3 and newer models. The free allowance is
#   shared with other work on the key, so 004 prices every search query.
# DataForSEO: the task cost the API reports at submission (ledger ``cost``).
PRICES_CHECKED = "2026-11-05"
PRICE_SOURCES = {
    "openai": "https://developers.openai.com/api/docs/pricing",
    "openai_model": "https://developers.openai.com/api/docs/models/gpt-6-luna",
    "gemini": "https://aistudio.google.com/docs/pricing",
}
PRICES = {
    OPENAI_MODEL: {"input": 0.10, "cached_input": 0.01, "cache_write": 0.125, "output": 0.50,
                   "search": 10.00 / 1000},
    GEMINI_MODEL: {"input": 0.30, "cached_input": 0.30, "output": 2.50, "search": 14.00 / 1000},
}
#: Prior USD per answer for the cost guard, generous on purpose. Set from the smoke
#: run (2026-11-05, b2b_01): cg_api_plain $0.045, cg_api_low $0.23 (22 search calls
#: at effort none), cg_api_leak $0.035, gm_api_plain and gm_api_leak $0.031.
PRIOR_USD = {
    "cg_api_plain": 0.10, "cg_api_low": 0.35, "cg_api_leak": 0.10,
    "gm_api_plain": 0.06, "gm_api_leak": 0.06,
    "cg_ui": 0.0024, "gm_ui": 0.0024,
}


def openai_cost(usage: dict | None, n_search_calls: int) -> dict:
    """Estimated USD of one Responses API call (``usage`` as returned).

    ``input_tokens`` includes cached reads and cache writes, which
    ``input_tokens_details`` reports separately (observed 2026-11-05).
    """
    usage = usage or {}
    p = PRICES[OPENAI_MODEL]
    details = usage.get("input_tokens_details") or {}
    inp = int(usage.get("input_tokens") or 0)
    cached = int(details.get("cached_tokens") or 0)
    written = int(details.get("cache_write_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    parts = {
        "input": max(inp - cached - written, 0) * p["input"] / 1e6,
        "cached_input": cached * p["cached_input"] / 1e6,
        "cache_write": written * p["cache_write"] / 1e6,
        "output": out * p["output"] / 1e6,
        "search": n_search_calls * p["search"],
    }
    parts["total"] = sum(parts.values())
    return parts


def gemini_cost(usage: dict | None, n_search_queries: int) -> dict:
    """Estimated USD of one generateContent call (``usageMetadata`` as returned).

    Output = candidates + thoughts. Tool-use prompt tokens (grounding context),
    when reported, bill as input.
    """
    usage = usage or {}
    p = PRICES[GEMINI_MODEL]
    inp = int(usage.get("promptTokenCount") or 0) + int(usage.get("toolUsePromptTokenCount") or 0)
    out = int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)
    parts = {
        "input": inp * p["input"] / 1e6,
        "output": out * p["output"] / 1e6,
        "search": n_search_queries * p["search"],
    }
    parts["total"] = sum(parts.values())
    return parts


# ---------------------------------------------------------------- keys


def env_value(name: str, path: Path = ENV_FILE) -> str:
    """One key from the main checkout's ``.env.local``, or stop. Never printed."""
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise SystemExit(f"no {name} in {path}; 004 keys come only from that file")


# ---------------------------------------------------------------- inputs


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prompts(path: Path = PROMPTS) -> dict[str, dict]:
    """item_id -> row (item_id, intent, text, category, prompt_intent)."""
    with path.open(newline="") as f:
        rows = {r["item_id"]: r for r in csv.DictReader(f)}
    if not rows or any(r["intent"] != "b2b" for r in rows.values()):
        raise SystemExit(f"unexpected prompts file: {path}")
    return rows


def verify_lexicon(path: Path = LEXICON_V3, expected: str = LEXICON_V3_SHA256) -> Path:
    got = sha256_file(path)
    if got != expected:
        raise SystemExit(f"lexicon v3 sha256 mismatch: got {got}, pinned {expected}")
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_date() -> str:
    """The run date, YYYY-MM-DD, US Eastern (where the study is run)."""
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


# ---------------------------------------------------------------- ledgers


class JsonlLedger:
    """Append-only JSONL; one record per attempt. Thread-safe appends."""

    _lock = threading.Lock()

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, record: dict) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(record, sort_keys=True) + "\n")

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def done(self) -> set[tuple[str, str, int]]:
        """(arm, item_id, round) with a collected answer."""
        return {(r["arm"], r["item_id"], int(r["round"])) for r in self.records()
                if r.get("status") == "collected"}

    def spend(self) -> float:
        return sum(float(r.get("cost_usd") or 0) for r in self.records()
                   if r.get("status") == "collected")


def api_ledger(prefix: str, instrument: str) -> Path:
    """``<RAW>/<prefix>ledger_api_<instrument>.jsonl`` (prefix "" or "smoke_")."""
    return RAW / f"{prefix}ledger_api_{instrument}.jsonl"


def ui_ledger(prefix: str, platform: str) -> Path:
    return RAW / f"{prefix}ledger_ui_{platform}.jsonl"


def total_spend() -> float:
    """All 004 spend recorded in RAW: API estimates (pilot and smoke ledgers, the
    low-effort probe), DataForSEO task costs and the Haiku brand pass."""
    total = 0.0
    for path in sorted(RAW.glob("*ledger_api_*.jsonl")):
        total += JsonlLedger(path).spend()
    for path in sorted(RAW.glob("*ledger_ui_*.jsonl")):
        latest: dict[str, dict] = {}
        for r in JsonlLedger(path).records():
            latest.setdefault(r["task_id"], {}).update(r)
        total += sum(float(r.get("cost") or 0) for r in latest.values()
                     if r.get("status") in ("submitted", "collected"))
    probe = RAW / "low_effort_probe.json"
    if probe.exists():
        total += float(json.loads(probe.read_text()).get("cost_usd") or 0)
    cache = RAW / "brand_candidates.jsonl"
    if cache.exists():
        total += sum(float(json.loads(x).get("cost_usd") or 0)
                     for x in cache.read_text().splitlines() if x.strip())
    return total


class CostCapError(SystemExit):
    pass


def guard_cost(planned: dict[str, int], cap: float = COST_CAP_USD, spent: float | None = None) -> float:
    """Refuse to start when spend so far plus the planned run's prior passes the cap.

    ``planned``: arm -> number of answers about to be requested.
    Returns the projected total.
    """
    spent = total_spend() if spent is None else spent
    estimate = sum(PRIOR_USD[arm] * n for arm, n in planned.items())
    total = spent + estimate
    print(f"cost guard: spent ${spent:.4f} + planned ${estimate:.4f} = ${total:.4f} (cap ${cap:.2f})")
    if total > cap:
        raise CostCapError(f"cost cap: ${total:.2f} would pass ${cap:.2f}; refusing to start")
    return total


def response_path(prefix: str, arm: str, item_id: str, rnd: int) -> Path:
    return RAW / f"{prefix}responses" / f"r{rnd}" / arm / f"{item_id}.json"


# ---------------------------------------------------------------- HTTP

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


@dataclass
class HttpResult:
    status: int  # HTTP status, 0 for a network failure
    body: dict | None
    error: str | None
    attempts: int


def post_json(url: str, body: dict, headers: dict, *, retries: int = 4, backoff_s: float = 15.0,
              timeout_s: float = 600.0, opener=None, sleep=None) -> HttpResult:
    """POST JSON with retry and linear backoff on 408/409/429/5xx and network errors.

    Other 4xx come back at once with the error body (never raised), so a caller
    can record a refused request in its ledger. Headers are never logged.
    """
    import time
    import urllib.error
    import urllib.request

    open_fn = opener or urllib.request.urlopen
    sleep = sleep or time.sleep
    data = json.dumps(body).encode()
    last = HttpResult(0, None, "not sent", 0)
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with open_fn(req, timeout=timeout_s) as resp:
                return HttpResult(resp.status, json.loads(resp.read().decode()), None, attempt)
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
            last = HttpResult(e.code, payload, f"HTTP {e.code}: {raw[:500]}", attempt)
            if e.code not in RETRY_STATUS:
                return last
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = HttpResult(0, None, f"{type(e).__name__}: {e}", attempt)
        if attempt < retries:
            sleep(backoff_s * attempt)
    return last


# ---------------------------------------------------------------- API arm runner


def request_sha256(body: dict) -> str:
    return sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False))


def run_api_jobs(*, instrument: str, arms: list[str], items: list[str], rnd: int, prefix: str,
                 build, send, normalize, cost, check_model: str, workers: int = 4,
                 log=print) -> dict:
    """Run every (arm, item) not yet collected for ``rnd``; one ledger record per attempt.

    ``build(arm, text) -> (body, meta)``; ``send(body) -> HttpResult``;
    ``normalize(raw) -> dict``; ``cost(raw, norm) -> dict`` with ``total``.
    The cost guard runs first on the planned answers. Idempotent: a collected
    (arm, item, round) is skipped. Returns counts.
    """
    import concurrent.futures as cf

    prompts = load_prompts()
    ledger = JsonlLedger(api_ledger(prefix, instrument))
    done = ledger.done()
    todo = [(arm, item) for arm in arms for item in items if (arm, item, rnd) not in done]
    if not todo:
        log(f"{instrument} r{rnd}: nothing to do ({len(arms) * len(items)} collected)")
        return {"ok": 0, "failed": 0, "skipped": len(arms) * len(items)}
    planned: dict[str, int] = {}
    for arm, _item in todo:
        planned[arm] = planned.get(arm, 0) + 1
    guard_cost(planned)

    def one(job):
        arm, item = job
        text = prompts[item]["text"]
        body, meta = build(arm, text)
        started = now_iso()
        res = send(body)
        rec = {"arm": arm, "item_id": item, "round": rnd, "instrument": instrument,
               "keyword_sha256": sha256_text(text), "request_sha256": request_sha256(body),
               "model_requested": body.get("model") or check_model, **meta,
               "started": started, "finished": now_iso(), "attempts": res.attempts,
               "http_status": res.status, "run_date": run_date()}
        if res.status != 200 or not res.body:
            ledger.append(rec | {"status": "failed", "error": res.error, "cost_usd": 0.0})
            return arm, item, "failed", res.error
        path = response_path(prefix, arm, item, rnd)
        path.parent.mkdir(parents=True, exist_ok=True)
        norm = normalize(res.body)
        price = cost(res.body, norm)
        path.write_text(json.dumps({"request_meta": meta | {"request_sha256": rec["request_sha256"]},
                                    "raw": res.body, "normalized": norm}, indent=1,
                                   ensure_ascii=False))
        problems = []
        if norm.get("model") is None or not str(norm["model"]).startswith(check_model):
            problems.append(f"model {norm.get('model')!r} != {check_model!r}")
        if not norm["answer_text"].strip():
            problems.append("empty answer")
        ledger.append(rec | {"status": "collected", "response_model": norm.get("model"),
                             "response_status": norm.get("status"),
                             "usage": res.body.get("usage") or res.body.get("usageMetadata"),
                             "n_searches": norm["n_searches"],
                             "n_web_search_calls": norm.get("n_web_search_calls"),
                             "cost_usd": price["total"], "cost_parts": price,
                             "problems": problems, "response_path": str(path)})
        return arm, item, "collected", "; ".join(problems)

    ok = failed = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for arm, item, status, note in pool.map(one, todo):
            ok += status == "collected"
            failed += status == "failed"
            log(f"  {instrument} r{rnd} {arm} {item}: {status}{' ' + note if note else ''}")
    log(f"{instrument} r{rnd}: {ok} collected, {failed} failed")
    return {"ok": ok, "failed": failed, "skipped": len(arms) * len(items) - len(todo)}
