"""Stage 01 — ledger + raw response JSONs -> interim/responses.csv.

One row per collected task: extracted brands (ordered), cited URLs/domains
(from ``sources[]`` only — ``search_results[]`` are SERP extras, not
citations; spec §2 Audit B), grounding-query token set, answer text (interim
only, never published), word count, model version.

``--synthetic`` generates a fake-but-structured dataset through the SAME
extraction code path so stages 02-05 can be dry-run end to end before any
API spend. The synthetic frame is marked ``synthetic=1``; stage 05 refuses it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from brands import LEXICONS, extract_brands
from common import (
    INTERIM,
    LEDGER,
    PROMPTS_CSV,
    RESPONSES_CSV,
    SEED,
    WAVES,
    join_list,
    normalize_url,
    registered_domain,
)

from aeo_research.dataforseo import Ledger
from aeo_research.overlap import token_set


def entity_titles(result: dict) -> list[str]:
    """DataForSEO's own brand/product annotations (coverage is inconsistent —
    null on some responses — so this is an Audit-D cross-check, never the
    primary extractor)."""
    seen: dict[str, None] = {}
    pools = [result.get("brand_entities") or []]
    pools += [i.get("brand_entities") or [] for i in result.get("items") or []]
    for ent in (e for pool in pools for e in pool):
        title = (ent.get("title") or "").strip()
        if title:
            seen.setdefault(title, None)
    return list(seen)


def features_from_result(result: dict, intent: str) -> dict:
    markdown = result.get("markdown") or ""
    fanouts = result.get("fan_out_queries") or []
    sources = result.get("sources") or []
    entities = entity_titles(result)

    urls = []
    seen = set()
    for s in sources:
        url = (s.get("url") or "").strip()
        if not url:
            continue
        norm = normalize_url(url)
        if norm not in seen:
            seen.add(norm)
            urls.append(norm)

    brands = extract_brands(markdown, intent)
    return {
        "model": result.get("model"),
        "brands": join_list(brands),
        "n_brands": len(brands),
        "top_brand": brands[0] if brands else "",
        "urls": join_list(urls),
        "domains": join_list(sorted({registered_domain(u) for u in urls})),
        "n_sources": len(urls),
        "fanout_tokens": " ".join(sorted(token_set(fanouts))),
        "n_fanout": len(fanouts),
        "entity_titles": join_list(entities),
        "n_entities": len(entities),
        "had_web_search": int(bool(fanouts or sources)),
        "reply_word_count": len(markdown.split()),
        "answer_text": markdown,
    }


def build_real() -> pd.DataFrame:
    ledger = Ledger(LEDGER)
    frame = ledger.frame()
    collected = frame[frame["status"] == "collected"]
    repo_root = Path(__file__).resolve().parents[3]
    rows = []
    for r in collected.itertuples():
        path = Path(r.result_path)
        if not path.is_absolute():
            path = repo_root / path
        result = json.loads(path.read_text())
        rows.append(
            {
                "task_id": r.task_id,
                "item_id": r.item_id,
                "intent": r.intent,
                "wave": int(r.wave),
                "run_date": str(r.collected_at)[:10],
                "synthetic": 0,
            }
            | features_from_result(result, r.intent)
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------- synthetic

REVIEW_DOMAINS = [
    "rtings.com", "soundguys.com", "nytimes.com", "cnet.com", "whathifi.com",
    "techradar.com", "wired.com", "pcmag.com", "tomsguide.com", "reddit.com",
]
AGENCY_DOMAINS = [
    "clutch.co", "designrush.com", "behance.net", "dribbble.com", "99designs.com",
    "upwork.com", "themanifest.com", "sortlist.com",
]


def synth_markdown(brands: list[str], rng: np.random.Generator) -> str:
    lines = ["Here are strong options I found:"]
    for b in brands:
        lines.append(f"- **{b.title()}** — a well-reviewed pick ({rng.integers(100, 400)} reviews)")
    lines.append("Any of these would make a great gift.")
    return "\n".join(lines)


def build_synthetic() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    prompts = pd.read_csv(PROMPTS_CSV)
    rows = []
    pool = {intent: list(LEXICONS[intent]) for intent in LEXICONS}
    # Global popularity: prompts share top brands (the SparkToro effect).
    weights = {
        intent: np.linspace(2.0, 0.2, len(pool[intent])) for intent in pool
    }
    for r in prompts.itertuples():
        w = weights[r.intent] / weights[r.intent].sum()
        profile = list(
            rng.choice(pool[r.intent], size=min(6, len(pool[r.intent])), replace=False, p=w)
        )
        n_waves = WAVES if r.intent == "headphones" else 1
        for wave in range(1, n_waves + 1):
            keep = [b for b in profile if rng.random() > 0.15]
            domains = list(
                rng.choice(
                    REVIEW_DOMAINS if r.intent == "headphones" else AGENCY_DOMAINS,
                    size=5, replace=False,
                )
            )
            result = {
                "markdown": synth_markdown(keep, rng),
                "fan_out_queries": [
                    f"best {r.intent} 2026", f"{keep[0]} review" if keep else "top picks",
                ],
                "sources": [{"url": f"https://{d}/reviews/best-picks"} for d in domains],
                "model": "gpt-5-synthetic",
            }
            rows.append(
                {
                    "task_id": f"syn-{r.item_id}-w{wave}",
                    "item_id": r.item_id,
                    "intent": r.intent,
                    "wave": wave,
                    "run_date": f"2026-07-{15 + wave:02d}",
                    "synthetic": 1,
                }
                | features_from_result(result, r.intent)
            )
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()

    df = build_synthetic() if a.synthetic else build_real()
    if df.empty:
        raise SystemExit("no collected responses in the ledger")
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESPONSES_CSV, index=False)
    tag = "SYNTHETIC " if a.synthetic else ""
    print(f"wrote {len(df)} {tag}responses -> {RESPONSES_CSV}")
    print(df.groupby(["intent", "wave"]).size().to_string())


if __name__ == "__main__":
    main()
