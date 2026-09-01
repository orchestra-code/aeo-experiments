"""Pilot probe: does the direct OpenAI Responses API expose the search phase?

The DataForSEO ChatGPT scraper stopped returning fan_out_queries /
search_results (observed 2026-09-01; exp-005 payloads included). Spyglasses
production harvests grounding from `output[].web_search_call.action.query` on
the direct API — this probe checks that path exposes the queries (including
`site:` ones) for this study's prompt shapes, using the same model production
pins (gpt-5.6-terra).

Usage:
  uv run python experiments/008-brand-domain-knowledge/harness/probe_openai_direct.py \
      --env-file ../spyglasses/.env.local
"""

import argparse
import json
import urllib.request
from pathlib import Path

MODEL = "gpt-5.6-terra"  # spyglasses llm-platforms.ts pin

PROMPTS = {
    "motion_p1": "What is Motion, the AI calendar and scheduling app? What does it offer and how is it priced?",
    "notion_p1": "What is Notion, the workspace and notes software? What does it offer and how is it priced?",
    "catprobe_hp": "What are the best noise cancelling headphones for travel and music in 2026?",
}


def load_key(env_file: str) -> str:
    for line in Path(env_file).read_text().splitlines():
        if line.strip().startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"No OPENAI_API_KEY in {env_file}")


def run(key: str, item_id: str, prompt: str, out_dir: Path) -> None:
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(
            {"model": MODEL, "tools": [{"type": "web_search"}], "input": prompt}
        ).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise SystemExit(f"{item_id}: HTTP {e.code} — {body}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{item_id}.json").write_text(json.dumps(payload, indent=1))

    searches = [
        item.get("action", {})
        for item in payload.get("output", [])
        if item.get("type") == "web_search_call"
    ]
    print(f"\n{item_id}  model={payload.get('model')}  n_web_search_call={len(searches)}")
    for action in searches:
        query = action.get("query")
        sources = action.get("sources") or []
        print(f"  query: {query!r}  ({len(sources)} sources)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", required=True)
    a = ap.parse_args()
    key = load_key(a.env_file)
    out_dir = Path(__file__).resolve().parents[1] / "data" / "raw" / "openai_probe"
    for item_id, prompt in PROMPTS.items():
        run(key, item_id, prompt, out_dir)


if __name__ == "__main__":
    main()
