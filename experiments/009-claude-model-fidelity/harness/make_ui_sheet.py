"""Write the randomized claude.ai collection checklist for one wave.

Every (prompt, UI arm) pair appears once, in an order shuffled with a seed
derived from the wave number, so the order is reproducible and differs
between waves. The collector works down the sheet top to bottom (see
``ui_collection_protocol.md``).

Usage (repo root):
    uv run python experiments/009-claude-model-fidelity/harness/make_ui_sheet.py \
        --wave 1 [--arms ui_default,ui_think] [--items b2b_01,b2b_02] [--out w1_pilot.csv]

Output: ``data/raw/ui_sheets/w<wave>.csv`` with columns
order, item_id, arm, chat_name, text, done, notes. The file holds prompt text,
so it stays under data/raw/.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
RAW = EXP / "data" / "raw"
UI_ARMS = ("ui_default", "ui_think")


def chat_name(wave: int, arm: str, item_id: str) -> str:
    return f"w{wave}-{arm}-{item_id}"


def build_sheet(prompts: list[dict], wave: int, arms: list[str]) -> list[dict]:
    pairs = [(p, arm) for p in prompts for arm in arms]
    random.Random(f"aeo-exp009-ui-w{wave}").shuffle(pairs)
    return [
        {
            "order": i,
            "item_id": p["item_id"],
            "arm": arm,
            "chat_name": chat_name(wave, arm, p["item_id"]),
            "text": p["text"],
            "done": "",
            "notes": "",
        }
        for i, (p, arm) in enumerate(pairs, start=1)
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--arms", default=",".join(UI_ARMS))
    ap.add_argument("--items", default=None, help="comma-separated item ids (default: all)")
    ap.add_argument("--prompts", default=str(RAW / "prompts.csv"))
    ap.add_argument("--out-dir", default=str(RAW / "ui_sheets"))
    ap.add_argument("--out", default=None,
                    help="output file name inside --out-dir (default w<wave>.csv)")
    a = ap.parse_args()

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    bad = [x for x in arms if x not in UI_ARMS]
    if bad:
        raise SystemExit(f"unknown UI arms {bad}; expected {UI_ARMS}")
    with open(a.prompts, newline="") as f:
        prompts = list(csv.DictReader(f))
    if a.items:
        keep = {i.strip() for i in a.items.split(",")}
        missing = sorted(keep - {p["item_id"] for p in prompts})
        if missing:
            raise SystemExit(f"unknown item ids {missing}")
        prompts = [p for p in prompts if p["item_id"] in keep]
    rows = build_sheet(prompts, a.wave, arms)

    out = Path(a.out_dir) / (a.out or f"w{a.wave}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["order"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out}: {len(rows)} chats ({len(prompts)} prompts x {len(arms)} arms)\n")
    for r in rows:
        print(f"{r['order']:>3}. {r['chat_name']}\n     {r['text']}")


if __name__ == "__main__":
    main()
