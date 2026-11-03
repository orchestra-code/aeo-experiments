"""Write the randomized claude.ai checklist for one wave of experiment 011.

The chat names start with ``e011-``. The collection account also holds experiment 009's chats,
on the same prompts, and those are named ``w1-ui_default-b2b_07``. The prefix is what keeps
them out of this study's data (``ingest_claude_export.py``).

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/harness/make_ui_sheet.py --wave 1

Output: ``data/raw/ui_sheets/w<wave>.csv``. It holds prompt text and stays under data/raw/.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
PROMPTS = EXP.parent / "009-claude-model-fidelity" / "data" / "raw" / "prompts.csv"
ARM = "ui_default"
SEED = 20261103


def chat_name(wave: int, item_id: str) -> str:
    return f"e011-w{wave}-{ARM}-{item_id}"


def build_sheet(prompts: list[dict], wave: int) -> list[dict]:
    order = sorted(prompts, key=lambda p: p["item_id"])
    random.Random(f"{SEED}:ui:{wave}").shuffle(order)
    return [
        {"order": i, "item_id": p["item_id"], "arm": ARM, "chat_name": chat_name(wave, p["item_id"]),
         "text": p["text"], "done": "", "notes": ""}
        for i, p in enumerate(order, start=1)
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    args = ap.parse_args()
    with PROMPTS.open(newline="") as f:
        prompts = list(csv.DictReader(f))
    rows = build_sheet(prompts, args.wave)
    out = RAW / "ui_sheets" / f"w{args.wave}.csv"
    if out.exists():
        raise SystemExit(f"{out} exists and may hold notes; not overwriting it")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out}: {len(rows)} chats")


if __name__ == "__main__":
    main()
