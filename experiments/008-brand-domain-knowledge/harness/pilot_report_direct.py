"""Summarize the direct-API pilot: emission rates + first domain scoring.

Reads ledger_direct.jsonl + responses_direct/, and for every brand item
scores each site: query's domain against the panel map: true / stale
(old_domains) / guess (expected_guess) / other. Prints per-template emission
rates and per-call token usage (the §7 re-costing input).

Usage: uv run python experiments/008-brand-domain-knowledge/harness/pilot_report_direct.py
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pandas as pd

EXP = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("brands", EXP / "pipeline" / "brands.py")
brands = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brands)
PANEL = {b.canonical.lower().replace(" ", "-"): b for b in brands.DRAFT_PANEL}

SITE_RE = re.compile(r"(?:^|\s)-?site:\s?([^\s/]+)", re.IGNORECASE)


def norm(d: str) -> str:
    return d.lower().removeprefix("www.")


def score(slug: str, domain: str) -> str:
    b = PANEL.get(slug)
    if b is None:
        return "?"
    d = norm(domain)
    def hits(target: str) -> bool:
        return d == target or d.endswith("." + target)
    if hits(b.true_domain):
        return "TRUE"
    if any(hits(o) for o in b.old_domains):
        return "STALE"
    if any(hits(g) for g in b.expected_guess):
        return "GUESS"
    return "other"


def main() -> None:
    ledger = [json.loads(l) for l in
              (EXP / "data/raw/ledger_direct.jsonl").read_text().splitlines()]
    latest: dict[str, dict] = {}
    for r in ledger:
        latest[r["task_id"]] = {**latest.get(r["task_id"], {}), **r}

    rows = []
    for r in latest.values():
        if r.get("status") != "collected":
            print(f"FAILED: {r.get('item_id')}: {r.get('error')}")
            continue
        payload = json.loads(Path(r["result_path"]).read_text())
        searches = [o.get("action") or {} for o in payload.get("output", [])
                    if o.get("type") == "web_search_call"]
        queries = [a.get("query") for a in searches if a.get("query")]
        site_domains = [m.group(1) for q in queries for m in [SITE_RE.search(q)] if m]
        slug = r["item_id"].rsplit("_", 1)[0]
        if slug.startswith("cache"):
            slug = "figma"
        verdicts = [score(slug, d) for d in site_domains]
        rows.append({
            "item_id": r["item_id"],
            "template": (r["item_id"].rsplit("_", 1)[-1]
                         if r["item_id"].rsplit("_", 1)[-1] in ("p1", "p2")
                         else "p1"),
            "n_search_calls": len(searches),
            "n_queries": len(queries),
            "n_site": len(site_domains),
            "site_verdicts": ",".join(verdicts) or "-",
            "site_domains": ";".join(norm(d) for d in site_domains) or "-",
            "in_tok": r.get("input_tokens"),
            "out_tok": r.get("output_tokens"),
        })

    df = pd.DataFrame(rows).sort_values("item_id")
    print(df.to_string(index=False))
    print("\n--- emission by template ---")
    for template, g in df.groupby("template"):
        print(f"{template}: n={len(g)}  any-query {sum(g.n_queries > 0)}/{len(g)}  "
              f"site: {sum(g.n_site > 0)}/{len(g)}")
    all_verdicts = [v for vs in df["site_verdicts"] for v in vs.split(",") if v and v != "-"]
    print("\nsite:-domain verdicts:", pd.Series(all_verdicts).value_counts().to_dict()
          if all_verdicts else "none")
    print(f"\ntokens/call: input median {df['in_tok'].median():,.0f} "
          f"(p90 {df['in_tok'].quantile(0.9):,.0f}), "
          f"output median {df['out_tok'].median():,.0f}")


if __name__ == "__main__":
    main()
