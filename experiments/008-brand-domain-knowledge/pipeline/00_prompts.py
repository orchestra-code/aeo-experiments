"""Generate data/raw/prompts.csv from the frozen panel — allocation C.

One row per (brand × template × replicate). Replicates share identical text;
they exist so the ledger's (intent, item_id, wave) idempotence gives each its
own slot. Intents:
  core  r0 — every wave (1–10)
  rep1  r1 — wave 1 only, afternoon slot
  rep2  r2 — wave 1 only, evening slot

Deterministic: a full cross product, no sampling.

Usage: uv run python experiments/008-brand-domain-knowledge/pipeline/00_prompts.py
"""

import csv
import importlib.util
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("brands", EXP / "pipeline" / "brands.py")
brands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brands)

REPLICATE_INTENTS = {0: "core", 1: "rep1", 2: "rep2"}


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


rows = []
for b in brands.DRAFT_PANEL:
    for tkey, template in brands.DRAFT_TEMPLATES.items():
        text = template.format(brand=b.canonical, category=b.category)
        for r, intent in REPLICATE_INTENTS.items():
            rows.append((f"{slug(b.canonical)}_{tkey}_r{r}", intent, text))

out = EXP / "data" / "raw" / "prompts.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["item_id", "intent", "text"])
    w.writerows(rows)

n_core = sum(1 for r in rows if r[1] == "core")
print(f"{out}: {len(rows)} rows ({n_core} core; "
      f"total calls over 10 waves = {n_core * 10 + (len(rows) - n_core)})")
