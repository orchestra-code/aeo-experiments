"""OpenAI Responses API collector for experiment 004's ChatGPT API arms (sketch, Arms).

Arms (all ``gpt-6-luna``, ``web_search`` tool with ``user_location`` country US,
``tool_choice`` auto, one user turn = the prompt text byte for byte):

- ``cg_api_plain``: default reasoning (the request sets none), no instructions.
- ``cg_api_low``: the lowest reasoning effort the API accepts with web search
  attached, probed in order ``none``, ``minimal``, ``low``. The probe result is
  recorded in ``data/raw/low_effort_probe.json`` and reused, so every
  ``cg_api_low`` answer uses the same setting.
- ``cg_api_leak``: default reasoning, ``instructions`` = ``adapted_chatgpt.txt``.

Requests ask for ``web_search_call.action.sources`` so consulted URLs come back.
``store`` is false. Plain HTTPS (urllib), like the repo's DataForSEO client. The
full raw response goes to ``data/raw/<prefix>responses/r<round>/<arm>/<item>.json``
with the normalized answer, and one JSONL ledger record per attempt to
``<prefix>ledger_api_openai.jsonl``: arm, item, round, request hash, response
model, usage, web search calls, status, timestamps, estimated cost. The ledger
holds no prompt text. Reruns skip collected answers; failures are retried.

Usage (repo root):
    uv run python experiments/004-api-vs-ui/harness/collect_openai.py probe-effort
    uv run python experiments/004-api-vs-ui/harness/collect_openai.py run --round 1 \
        --arms cg_api_plain --items b2b_01 --prefix smoke_
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answers  # noqa: E402
import exp004  # noqa: E402
import leaks  # noqa: E402

URL = "https://api.openai.com/v1/responses"
TOOL = {"type": "web_search", "user_location": {"type": "approximate", "country": "US"}}
INCLUDE = ["web_search_call.action.sources"]
PROBE_PATH = exp004.RAW / "low_effort_probe.json"
PROBE_INPUT = "Reply with the single word OK."


def _headers() -> dict:
    return {"Authorization": f"Bearer {exp004.env_value('OPENAI_API_KEY')}"}


def send(body: dict) -> exp004.HttpResult:
    return exp004.post_json(URL, body, _headers())


def base_body(text: str) -> dict:
    return {"model": exp004.OPENAI_MODEL, "input": text, "tools": [TOOL], "tool_choice": "auto",
            "include": INCLUDE, "store": False}


def probe_effort(force: bool = False) -> str:
    """The lowest effort accepted with web search attached (cached in RAW)."""
    if PROBE_PATH.exists() and not force:
        return json.loads(PROBE_PATH.read_text())["accepted"]
    tried = []
    accepted = None
    for effort in exp004.LOW_EFFORT_CANDIDATES:
        body = base_body(PROBE_INPUT) | {"reasoning": {"effort": effort}}
        res = exp004.post_json(URL, body, _headers(), retries=2)
        echoed = ((res.body or {}).get("reasoning") or {}).get("effort") if res.status == 200 else None
        tried.append({"effort": effort, "http_status": res.status, "echoed_effort": echoed,
                      "error": None if res.status == 200 else (res.error or "")[:400],
                      "usage": (res.body or {}).get("usage") if res.status == 200 else None})
        if res.status == 200 and echoed == effort:
            accepted = effort
            break
    if accepted is None:
        raise SystemExit(f"no low effort accepted: {tried}")
    cost = sum(exp004.openai_cost(t["usage"], 0)["total"] for t in tried if t["usage"])
    PROBE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROBE_PATH.write_text(json.dumps({"model": exp004.OPENAI_MODEL, "tool": TOOL, "tried": tried,
                                      "accepted": accepted, "cost_usd": cost,
                                      "at": exp004.now_iso()}, indent=1) + "\n")
    print(f"low-effort probe: accepted {accepted!r} after {[t['effort'] for t in tried]}")
    return accepted


def build(arm: str, text: str) -> tuple[dict, dict]:
    spec = exp004.ARMS[arm]
    body = base_body(text)
    meta = {"effort_requested": None, "instructions_sha256": None}
    if spec.low_effort:
        effort = probe_effort()
        body["reasoning"] = {"effort": effort}
        meta["effort_requested"] = effort
    if spec.leak:
        instructions = leaks.load_adapted("chatgpt")
        body["instructions"] = instructions
        meta["instructions_sha256"] = exp004.sha256_text(instructions)
    return body, meta


def cost(raw: dict, norm: dict) -> dict:
    # Billed per web_search call. Every web_search_call item is counted (search,
    # open_page, find_in_page), an upper bound on the billed calls.
    return exp004.openai_cost(raw.get("usage"), norm.get("n_web_search_calls") or 0)


def run(arms: list[str], items: list[str], rnd: int, prefix: str = "", log=print) -> dict:
    bad = [a for a in arms if a not in exp004.OPENAI_ARMS]
    if bad:
        raise SystemExit(f"not OpenAI arms: {bad}")
    if any(exp004.ARMS[a].low_effort for a in arms):
        probe_effort()
    return exp004.run_api_jobs(instrument="openai", arms=arms, items=items, rnd=rnd,
                               prefix=prefix, build=build, send=send,
                               normalize=answers.from_openai, cost=cost,
                               check_model=exp004.OPENAI_MODEL, log=log)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe-effort")
    p.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--round", type=int, required=True)
    r.add_argument("--arms", default=",".join(exp004.OPENAI_ARMS))
    r.add_argument("--items", default=",".join(exp004.PILOT_ITEMS))
    r.add_argument("--prefix", default="", help='"smoke_" for the smoke ledger')
    a = ap.parse_args()
    if a.cmd == "probe-effort":
        print(probe_effort(force=a.force))
    else:
        run(a.arms.split(","), a.items.split(","), a.round, a.prefix)


if __name__ == "__main__":
    main()
