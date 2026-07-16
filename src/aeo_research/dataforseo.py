"""Minimal DataForSEO AI-Optimization LLM-scraper client (async task API).

Submits prompts to DataForSEO's LLM scraper (ChatGPT et al.) via ``task_post``
and collects results via ``task_get/advanced/{id}``, tracking every task in an
append-only JSONL ledger so submission and collection are idempotent and
crash-safe.

HARD RULE — never call ``tasks_ready``. That endpoint is account-wide and the
Spyglasses production poller consumes it every 5 minutes; a research run that
touched it could race the production collector (and vice versa). Polling
``task_get`` by our own stored task ids is race-free in both directions, and
results stay retrievable for ~30 days.

Auth: ``DATAFORSEO_API_KEY`` is the base64 of ``login:password`` and is sent
verbatim as ``Authorization: Basic <key>``. Read it from the environment or a
dotenv via :func:`load_api_key` — never write it to committed files.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

BASE_URL = "https://api.dataforseo.com/v3/ai_optimization"

#: Endpoint path segment per platform (extend when a study needs another LLM).
PLATFORM_PATHS = {
    "chatgpt": "chat_gpt/llm_scraper",
    "gemini": "gemini/llm_scraper",
}

#: task_get status codes that mean "still processing" rather than failure.
PENDING_STATUS_CODES = {40601, 40602}  # Task handed / Task in Queue

#: Per-task acceptance code from task_post.
ACCEPTED_STATUS_CODE = 20100

_MAX_TASKS_PER_POST = 100
_RETRIES = 3
_BACKOFF_S = 2.0


class DataForSeoError(RuntimeError):
    """The API refused a request or returned a terminal task error."""


def load_api_key(env_file: str | Path | None = None) -> str:
    """DATAFORSEO_API_KEY from the environment, else from a dotenv file."""
    key = os.environ.get("DATAFORSEO_API_KEY")
    if key:
        return key
    if env_file:
        for line in Path(env_file).read_text().splitlines():
            if line.strip().startswith("DATAFORSEO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(
        "No DATAFORSEO_API_KEY. Set it in the environment or pass --env-file "
        "pointing at a dotenv that defines it (e.g. spyglasses/.env.local)."
    )


def _request(
    api_key: str,
    method: str,
    url: str,
    body: object | None = None,
    *,
    opener=None,
) -> dict:
    """One JSON request with Basic auth and retry-with-backoff on 5xx/network."""
    data = json.dumps(body).encode() if body is not None else None
    open_fn = opener or urllib.request.urlopen
    last_err: Exception | None = None
    for attempt in range(_RETRIES):
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Basic {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with open_fn(req) as resp:
                payload = json.loads(resp.read().decode())
            if payload.get("status_code") != 20000:
                raise DataForSeoError(
                    f"{url}: {payload.get('status_code')} {payload.get('status_message')}"
                )
            return payload
        except DataForSeoError:
            raise
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code < 500:
                raise DataForSeoError(f"{url}: HTTP {e.code} {e.reason}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
        time.sleep(_BACKOFF_S * (attempt + 1))
    raise DataForSeoError(f"{url}: gave up after {_RETRIES} attempts") from last_err


@dataclass
class TaskSpec:
    """One prompt to run. Field defaults match the Spyglasses production payload."""

    keyword: str
    tag: str
    language_code: str = "en"
    location_code: int = 2840  # United States
    force_web_search: bool = True  # required for fan_out_queries + sources
    device: str = "desktop"
    os: str = "windows"
    priority: int = 2  # priority queue (~5 min vs ~45 min)

    def to_payload(self) -> dict:
        return {
            "language_code": self.language_code,
            "location_code": self.location_code,
            "keyword": self.keyword,
            "force_web_search": self.force_web_search,
            "device": self.device,
            "os": self.os,
            "tag": self.tag,
            "priority": self.priority,
        }


@dataclass
class Submitted:
    task_id: str
    keyword: str
    tag: str
    cost: float | None
    status_code: int
    status_message: str = ""

    @property
    def accepted(self) -> bool:
        return self.status_code == ACCEPTED_STATUS_CODE


def post_tasks(
    api_key: str,
    specs: list[TaskSpec],
    *,
    platform: str = "chatgpt",
    opener=None,
) -> list[Submitted]:
    """Submit specs in chunks of <=100. Returns one Submitted per spec, in order.

    Rejected tasks (status != 20100) are returned with ``accepted == False``
    rather than raised, so a single bad prompt doesn't abort a wave.
    """
    url = f"{BASE_URL}/{PLATFORM_PATHS[platform]}/task_post"
    out: list[Submitted] = []
    for i in range(0, len(specs), _MAX_TASKS_PER_POST):
        chunk = specs[i : i + _MAX_TASKS_PER_POST]
        payload = _request(api_key, "POST", url, [s.to_payload() for s in chunk], opener=opener)
        tasks = payload.get("tasks") or []
        if len(tasks) != len(chunk):
            raise DataForSeoError(
                f"task_post returned {len(tasks)} tasks for {len(chunk)} specs"
            )
        for spec, task in zip(chunk, tasks):
            out.append(
                Submitted(
                    task_id=task.get("id", ""),
                    keyword=spec.keyword,
                    tag=spec.tag,
                    cost=task.get("cost"),
                    status_code=task.get("status_code", 0),
                    status_message=task.get("status_message", ""),
                )
            )
    return out


@dataclass
class TaskOutcome:
    """Result of one task_get poll."""

    task_id: str
    state: str  # "done" | "pending" | "failed"
    status_code: int
    status_message: str = ""
    #: tasks[0].result[0] when state == "done" (answer markdown, fan_out_queries,
    #: sources, search_results, model, check_url ...).
    result: dict | None = None
    cost: float | None = None


def get_task(
    api_key: str,
    task_id: str,
    *,
    platform: str = "chatgpt",
    opener=None,
) -> TaskOutcome:
    """Poll one task by id via task_get/advanced (NEVER tasks_ready — see module doc)."""
    url = f"{BASE_URL}/{PLATFORM_PATHS[platform]}/task_get/advanced/{task_id}"
    payload = _request(api_key, "GET", url, opener=opener)
    task = (payload.get("tasks") or [{}])[0]
    code = task.get("status_code", 0)
    message = task.get("status_message", "")
    result = (task.get("result") or [None])[0]
    if code == 20000 and result is not None:
        return TaskOutcome(task_id, "done", code, message, result, task.get("cost"))
    if code in PENDING_STATUS_CODES:
        return TaskOutcome(task_id, "pending", code, message)
    return TaskOutcome(task_id, "failed", code, message)


class Ledger:
    """Append-only JSONL task ledger; the latest record per task_id wins.

    Record fields: task_id, tag, wave, item_id, intent, keyword_sha256,
    status ("submitted" | "collected" | "failed"), submitted_at, collected_at,
    model, cost, result_path, error. Raw prompt text is deliberately NOT
    stored here — the ledger frame is safe to print and share in analysis.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
            f.flush()

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def frame(self) -> pd.DataFrame:
        """Latest record per task_id (file order breaks ties)."""
        records = self.records()
        if not records:
            return pd.DataFrame(
                columns=["task_id", "tag", "wave", "item_id", "intent", "status"]
            )
        df = pd.DataFrame(records)
        return df.groupby("task_id", as_index=False).last()

    def submitted_keys(self) -> set[tuple]:
        """(intent, item_id, wave) triples already submitted or collected."""
        df = self.frame()
        if df.empty:
            return set()
        live = df[df["status"].isin(["submitted", "collected"])]
        return set(zip(live["intent"], live["item_id"], live["wave"]))

    def pending(self) -> pd.DataFrame:
        """Tasks submitted but not yet collected or failed."""
        df = self.frame()
        if df.empty:
            return df
        return df[df["status"] == "submitted"].copy()


@dataclass
class LedgerStats:
    total: int = 0
    by_status: dict = field(default_factory=dict)
    cost: float = 0.0


def ledger_stats(ledger: Ledger) -> LedgerStats:
    df = ledger.frame()
    if df.empty:
        return LedgerStats()
    cost = float(pd.to_numeric(df.get("cost"), errors="coerce").fillna(0).sum())
    return LedgerStats(
        total=len(df),
        by_status=df["status"].value_counts().to_dict(),
        cost=cost,
    )
