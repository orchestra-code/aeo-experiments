"""Generate the pilot (wave 0) prompts CSV — spec §8.

Deterministic: everything derives from the DRAFT panel and templates. Output
is gitignored (data/raw/). Three intents so submission can route platforms:

  pilot         chatgpt — 10 brands × p1/p2 emission calibration
                + cache_r0..r2 (one identical prompt, batch-submitted)
  pilot_gemini  gemini  — 5 p1 prompts (distinct item_ids, same text)
  pilot_spaced  chatgpt — cache_r3..r5 (same identical prompt, submitted
                hours later for the spaced half of the cache probe)

Usage: uv run python experiments/008-brand-domain-knowledge/harness/make_pilot_prompts.py
"""

import csv
import importlib.util
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("brands", EXP / "pipeline" / "brands.py")
brands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brands)

PANEL = {b.canonical: b for b in brands.DRAFT_PANEL}

# Tier spread: 3 A, 3 B, 2 C, 2 D.
CALIBRATION_BRANDS = [
    "Sony", "Asana", "Figma",
    "Linear", "Motion", "Otter",
    "Notion", "X",
    "Bonsai", "Nutshell",
]
GEMINI_BRANDS = ["Sony", "Linear", "Notion", "X", "Bonsai"]
CACHE_BRAND = "Figma"  # its p1 text is the identical-prompt probe


def prompt(brand_name: str, template_key: str) -> str:
    entry = PANEL[brand_name]
    return brands.DRAFT_TEMPLATES[template_key].format(
        brand=entry.canonical, category=entry.category
    )


def slug(brand_name: str) -> str:
    return brand_name.lower().replace(" ", "-")


rows: list[tuple[str, str, str]] = []
for name in CALIBRATION_BRANDS:
    for tkey in ("p1", "p2"):
        rows.append((f"{slug(name)}_{tkey}", "pilot", prompt(name, tkey)))
for r in range(3):
    rows.append((f"cache_r{r}", "pilot", prompt(CACHE_BRAND, "p1")))
for name in GEMINI_BRANDS:
    rows.append((f"{slug(name)}_p1_gm", "pilot_gemini", prompt(name, "p1")))
for r in range(3, 6):
    rows.append((f"cache_r{r}", "pilot_spaced", prompt(CACHE_BRAND, "p1")))

out = EXP / "data" / "raw" / "prompts_pilot.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["item_id", "intent", "text"])
    w.writerows(rows)

print(f"{out}: {len(rows)} prompts "
      f"(pilot {sum(1 for r in rows if r[1] == 'pilot')}, "
      f"gemini {sum(1 for r in rows if r[1] == 'pilot_gemini')}, "
      f"spaced {sum(1 for r in rows if r[1] == 'pilot_spaced')})")
