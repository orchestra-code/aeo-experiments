"""Summarize pilot wave 0 collections — spec §8 decisions.

Reads the ledger + raw responses and prints, per task: platform, model,
fan-out presence/count, `site:` fan-outs, the domains a `site:` fan-out
targets, search_results/sources counts — plus the cache-probe byte-identity
check (markdown sha256 across cache_r* replicates) and per-template emission
rates.

Usage: uv run python experiments/008-brand-domain-knowledge/harness/pilot_report.py
"""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

EXP = Path(__file__).resolve().parents[1]
LEDGER = EXP / "data" / "raw" / "ledger.jsonl"

SITE_RE = re.compile(r"(?:^|\s)-?site:\s?([^\s/]+)", re.IGNORECASE)

records = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
df = pd.DataFrame(records).groupby("task_id", as_index=False).last()
collected = df[df["status"] == "collected"]

rows = []
for r in collected.itertuples():
    result = json.loads(Path(r.result_path).read_text())
    fanouts = result.get("fan_out_queries") or []
    site_fanouts = [q for q in fanouts if SITE_RE.search(q)]
    md = result.get("markdown") or ""
    rows.append(
        {
            "item_id": r.item_id,
            "intent": r.intent,
            "platform": getattr(r, "platform", None) or "chatgpt",
            "model": result.get("model"),
            "n_fanout": len(fanouts),
            "n_site_fanout": len(site_fanouts),
            "site_domains": ";".join(
                sorted({m.group(1).lower() for q in site_fanouts for m in [SITE_RE.search(q)] if m})
            ),
            "n_search_results": len(result.get("search_results") or []),
            "n_sources": len(result.get("sources") or []),
            "md_sha8": hashlib.sha256(md.encode()).hexdigest()[:8],
            "md_len": len(md),
        }
    )

rep = pd.DataFrame(rows).sort_values(["intent", "item_id"])
print(rep.to_string(index=False))

print("\n--- emission by intent/template (any fan-out | site: fan-out) ---")
rep["template"] = rep["item_id"].str.extract(r"_(p\d)")[0].fillna("cache")
for (intent, template), g in rep.groupby(["intent", "template"]):
    print(
        f"{intent:>13} {template}: n={len(g):>2}  "
        f"fanout {sum(g.n_fanout > 0)}/{len(g)}  "
        f"site: {sum(g.n_site_fanout > 0)}/{len(g)}"
    )

cache = rep[rep["item_id"].str.startswith("cache_")]
if not cache.empty:
    print("\n--- cache probe (byte-identity of markdown) ---")
    print(cache[["item_id", "intent", "md_sha8", "md_len"]].to_string(index=False))
    by_batch = defaultdict(set)
    for r in cache.itertuples():
        by_batch[r.intent].add(r.md_sha8)
    for intent, hashes in sorted(by_batch.items()):
        verdict = "IDENTICAL — caching suspected" if len(hashes) == 1 else "distinct"
        print(f"{intent}: {len(hashes)} unique hashes -> {verdict}")
