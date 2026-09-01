"""Direct OpenAI Responses API collector for experiment 008.

Replaces the DataForSEO scraper (which lost search-phase visibility on
2026-08-25 — spec §8b). Runs each prompt against the model production pins
(gpt-5.6-terra) with the web_search tool and saves the FULL response JSON,
including every `web_search_call` item (`action.type` search/open_page,
`action.query` with site: operators intact).

Ledger-driven and idempotent like scripts/llm_scraper.py: the (intent,
item_id, wave) triple is submitted at most once; raw prompt text never
enters the ledger (keyword_sha256 only). Replicates are distinct item_ids
(…_r0/_r1/_r2), so no special handling.

Usage:
  uv run python experiments/008-brand-domain-knowledge/harness/collect_openai.py \
      --prompts <csv> --intent pilot --wave 0 \
      --ledger <ledger.jsonl> --out-dir <responses/> --env-file .env.local
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from aeo_research.dataforseo import Ledger  # noqa: E402 — generic JSONL ledger

MODEL = "gpt-5.6-terra"  # spyglasses llm-platforms.ts pin
CONCURRENCY = 4
RETRIES = 3
BACKOFF_S = 8.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_key(env_file: str | None) -> str:
    candidates = [Path(env_file)] if env_file else []
    candidates += [REPO / ".env.local", REPO.parent / "spyglasses" / ".env.local"]
    for env in candidates:
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            if line.strip().startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    raise SystemExit("No OPENAI_API_KEY found")


def run_prompt(key: str, text: str) -> dict:
    body = {
        "model": MODEL,
        "tools": [{"type": "web_search"}],
        "input": text,
        # Ask for retrieved sources on search actions; harmless if ignored.
        "include": ["web_search_call.action.sources"],
    }
    last: Exception | None = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code == 400 and "include" in detail:
                # Older include vocabulary — retry once without it.
                body.pop("include", None)
                last = e
                continue
            if e.code < 500 and e.code != 429:
                raise RuntimeError(f"HTTP {e.code}: {detail}") from e
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        time.sleep(BACKOFF_S * (attempt + 1))
    raise RuntimeError(f"gave up after {RETRIES} attempts: {last}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--intent", required=True)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-total-calls", type=int, default=3600,
                    help="hard cap on lifetime ledger size (per-study budget)")
    a = ap.parse_args()

    ledger = Ledger(a.ledger)
    prompts = pd.read_csv(a.prompts)
    rows = prompts[prompts["intent"] == a.intent]
    if rows.empty:
        raise SystemExit(f"no prompts with intent={a.intent!r}")
    if a.limit:
        rows = rows.head(a.limit)

    done = ledger.submitted_keys()
    todo = [r for r in rows.itertuples()
            if (a.intent, r.item_id, a.wave) not in done]
    total_after = len(ledger.frame()) + len(todo)
    if total_after > a.max_total_calls:
        raise SystemExit(f"call cap: ledger would grow to {total_after} "
                         f"(cap {a.max_total_calls})")
    print(f"wave {a.wave} intent={a.intent}: {len(todo)} to run, "
          f"{len(rows) - len(todo)} already done")
    if not todo:
        return

    key = load_key(a.env_file)
    wave_dir = Path(a.out_dir).resolve() / f"w{a.wave}"
    wave_dir.mkdir(parents=True, exist_ok=True)

    def work(row) -> None:
        base = {
            "task_id": f"{a.intent}-{row.item_id}-w{a.wave}",
            "tag": f"aeo-exp008-w{a.wave}",
            "wave": a.wave,
            "item_id": row.item_id,
            "intent": a.intent,
            "platform": "openai_direct",
            "keyword_sha256": hashlib.sha256(row.text.encode()).hexdigest(),
            "submitted_at": now_iso(),
        }
        try:
            payload = run_prompt(key, row.text)
        except Exception as e:  # noqa: BLE001 — recorded, not fatal to the wave
            ledger.append(base | {"status": "failed", "error": str(e)[:300]})
            print(f"  FAILED {row.item_id}: {e}")
            return
        path = wave_dir / f"{row.item_id}.json"
        path.write_text(json.dumps(payload, indent=1))
        usage = payload.get("usage") or {}
        searches = sum(1 for o in payload.get("output", [])
                       if o.get("type") == "web_search_call")
        ledger.append(base | {
            "status": "collected",
            "collected_at": now_iso(),
            "model": payload.get("model"),
            "result_path": str(path),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "n_web_search_call": searches,
        })
        print(f"  collected {row.item_id} w{a.wave} "
              f"({searches} searches, {usage.get('total_tokens', '?')} tok)")

    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        list(pool.map(work, todo))

    df = ledger.frame()
    tok_in = pd.to_numeric(df.get("input_tokens"), errors="coerce").sum()
    tok_out = pd.to_numeric(df.get("output_tokens"), errors="coerce").sum()
    print(f"ledger: {len(df)} calls, {tok_in:,.0f} input + {tok_out:,.0f} "
          f"output tokens lifetime")


if __name__ == "__main__":
    main()
