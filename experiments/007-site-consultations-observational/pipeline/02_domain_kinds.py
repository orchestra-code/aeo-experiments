"""Bulk-classify study domains into kinds via the OpenAI Responses API.

Classifies (a) every site:-consulted domain and (b) every tracked property's
domain (for the panel-mix/skew analysis) into a fixed taxonomy. Only bare
domain strings are sent — no counts, no customer identifiers, no query text.

Results cache to data/interim/domain_kinds.json (idempotent; re-runs classify
only uncached domains). Model: gpt-5.6-terra (the key's verified model).

Usage: uv run python experiments/007-site-consultations-observational/pipeline/02_domain_kinds.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

EXP = Path(__file__).resolve().parents[1]
REPO = EXP.parents[1]
CACHE = EXP / "data" / "interim" / "domain_kinds.json"

MODEL = "gpt-5.6-terra"
BATCH = 80

KINDS = [
    "law_firm",
    "government_or_courts",
    "bar_or_professional_association",
    "healthcare_provider",
    "financial_or_insurance",
    "ai_or_software_vendor",
    "agency_or_consultancy",
    "directory_or_ratings",
    "news_or_media",
    "academic_or_reference",
    "nonprofit_or_foundation",
    "ecommerce_or_retail",
    "other_business",
    "unknown",
]

PROMPT = """Classify each website domain into exactly one of these kinds:
{kinds}

Rules: judge from the domain itself and what you know of the site. A company
selling software/AI products is ai_or_software_vendor; a marketing/design/SEO
firm is agency_or_consultancy; a bank/insurer/broker is financial_or_insurance;
hospitals/clinics/health systems are healthcare_provider; .gov, courts and
legislatures are government_or_courts; bar associations and professional
bodies are bar_or_professional_association; review platforms, rankings and
listing sites are directory_or_ratings. Use unknown only when you genuinely
cannot tell.

Return ONLY a JSON object mapping every input domain to its kind, no prose.

Domains:
{domains}"""


def load_key() -> str:
    for env in [REPO / ".env.local", REPO.parent / "spyglasses" / ".env.local"]:
        for line in env.read_text().splitlines():
            if line.strip().startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    raise SystemExit("No OPENAI_API_KEY found")


def classify_batch(key: str, domains: list[str]) -> dict[str, str]:
    body = {
        "model": MODEL,
        "input": PROMPT.format(kinds=", ".join(KINDS), domains="\n".join(domains)),
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read().decode())
    text = "".join(
        part.get("text", "")
        for item in payload.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    start, end = text.find("{"), text.rfind("}")
    mapping = json.loads(text[start : end + 1])
    return {
        d: (k if k in KINDS else "unknown")
        for d, k in mapping.items()
        if isinstance(k, str)
    }


def main() -> None:
    features = pd.read_csv(EXP / "data" / "interim" / "features.csv",
                           keep_default_na=False, na_values=[""])
    consulted = set(features.loc[features["scoped"], "scoped_domain"].dropna())
    context = pd.read_csv(EXP / "data" / "raw" / "context.csv", dtype=str,
                          keep_default_na=False)
    prop_domains = {
        d.lower().removeprefix("www.")
        for d in context["property_domain"] if d and "." in d
    }
    targets = sorted((consulted | prop_domains) - {""})
    targets = [d for d in targets if not d.startswith("*")]

    cache: dict[str, str] = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [d for d in targets if d not in cache]
    print(f"{len(targets):,} domains ({len(consulted):,} consulted, "
          f"{len(prop_domains):,} property); {len(todo):,} uncached")

    key = load_key()
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        for attempt in (1, 2):
            try:
                cache.update(classify_batch(key, batch))
                break
            except Exception as e:  # noqa: BLE001 — one retry, then surface
                if attempt == 2:
                    raise
                print(f"  batch {i // BATCH}: retry after {e}", file=sys.stderr)
                time.sleep(5)
        CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
        print(f"  {min(i + BATCH, len(todo)):,}/{len(todo):,}")

    got = [d for d in targets if d in cache]
    print(f"classified {len(got):,}/{len(targets):,}")
    print(pd.Series([cache[d] for d in got]).value_counts().to_string())


if __name__ == "__main__":
    main()
