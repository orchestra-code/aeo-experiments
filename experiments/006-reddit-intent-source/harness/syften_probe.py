"""006 feasibility probe — count-only, per the frozen protocol in feasibility.md.

Runs the three specificity tiers against Syften's archive, then measures the
qualifying rate on a sample from the narrowest viable tier. Publishes
nothing: post text lands in the gitignored data/raw/, and only counts and
aggregates reach results/.

Quota is metered (1,000 fetched items/month). Counts cost 1 item each
because `total` comes back without fetching matches; only the qualifying-rate
sample spends meaningfully.

Usage:
    uv run python experiments/006-reddit-intent-source/harness/syften_probe.py
    uv run python .../syften_probe.py --counts-only     # skip the 100-item sample
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
RAW = EXP / "data" / "raw"
RESULTS = EXP / "results"

ENDPOINT = "https://syften.com/api/0.1/archive/search"
AFTER = "2026-01-01T00:00:00Z"
SAMPLE_N = 100

#: Tier queries, rewritten 2026-08-06 after the syntax probe (logged as a
#: deviation in feasibility.md). The archive uses Community Monitoring
#: syntax: space is an implicit AND and parentheses are treated as LITERAL
#: characters rather than grouping, so the original parenthesised queries
#: silently under-matched (Tier C returned 991 with parens vs 10,000+
#: without). Every query below is a pure conjunction. Inclusion criteria are
#: unchanged — only the retrieval syntax moved.
TIERS = {
    # Tier A — intent-matched, comparable to the 002/003/005 human panel.
    # Three separate frames because OR precedence without parentheses is
    # unreliable; they overlap and are reported separately, not summed.
    "A1_travel": "headphones travel recommendation site:reddit.com",
    "A2_gift": "headphones gift recommendation site:reddit.com",
    "A3_flight": "headphones flight recommendation site:reddit.com",
    "A4_travel_earbuds": "earbuds travel recommendation site:reddit.com",
    # Tier B — category advice, any frame.
    "B_category_advice": "headphones recommendation site:reddit.com",
    # Tier C — upper bound on available material.
    "C_category_any": "headphones site:reddit.com",
}

#: Order tried when picking a tier to sample: narrowest (most comparable) first.
TIER_PREFERENCE = ["A1_travel", "A2_gift", "A3_flight", "A4_travel_earbuds",
                   "B_category_advice", "C_category_any"]

#: Seconds between requests. The archive rate-limits aggressively (observed:
#: "try again in 2m13s" after a dozen rapid calls), and a 429 mid-probe
#: would otherwise look like a zero result.
PACE_SECONDS = 30

#: Inclusion criteria 4 and 5, frozen. Tuning these to hit the threshold is
#: the failure mode this file exists to prevent.
ADVICE = re.compile(
    r"\b(looking for|recommend|recommendation|suggestions?|which should i|"
    r"help me choose|any advice|what should i (get|buy)|worth (it|buying))\b",
    re.I,
)
REC_INTENT = re.compile(
    r"\b(best|recommend|recommendation|suggest|advice|which|what)\b.{0,80}"
    r"\b(headphone|headphones|earbud|earbuds|pair|set)\b"
    r"|\b(headphone|headphones|earbud|earbuds)\b.{0,80}"
    r"\b(recommend|suggestion|advice|which one|worth)\b",
    re.I | re.S,
)
MIN_CHARS, MAX_CHARS = 40, 1200
DEAD = {"[deleted]", "[removed]", ""}


def load_key() -> str:
    key = os.environ.get("SYFTEN_API_KEY")
    if key:
        return key
    env = ROOT / ".env.local"
    if env.is_file():
        for line in env.read_text().splitlines():
            if line.startswith("SYFTEN_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("SYFTEN_API_KEY not found in env or .env.local")


_RETRY_AFTER = re.compile(r"try again in\s*(?:(\d+)m)?\s*(?:(\d+)s)?", re.I)


def search(key: str, query: str, limit: int) -> dict:
    """POST one archive query. A 429 is waited out rather than swallowed —
    a rate-limited response must never be mistaken for a zero result."""
    body = json.dumps({"query": query, "after": AFTER, "limit": limit}).encode()
    for attempt in range(5):
        req = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read()[:300].decode(errors="replace")
            if e.code == 429 and attempt < 4:
                m = _RETRY_AFTER.search(raw)
                wait = (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 60
                print(f"    rate limited, waiting {wait + 5}s")
                time.sleep(wait + 5)
                continue
            if e.code in (500, 502, 503) and attempt < 4:
                time.sleep(15 * (attempt + 1))
                continue
            raise SystemExit(f"Syften HTTP {e.code}: {raw}")
        except urllib.error.URLError as e:
            if attempt < 4:
                time.sleep(15 * (attempt + 1))
                continue
            raise SystemExit(f"Syften unreachable: {e}")

        # A body-level error object also arrives with HTTP 200 sometimes.
        if isinstance(payload, dict) and payload.get("code") == 429 and attempt < 4:
            m = _RETRY_AFTER.search(str(payload.get("error", "")))
            wait = (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 60
            print(f"    rate limited, waiting {wait + 5}s")
            time.sleep(wait + 5)
            continue
        if isinstance(payload, dict) and "total" not in payload:
            raise SystemExit(f"unexpected Syften response: {str(payload)[:300]}")
        return payload
    raise SystemExit("gave up after repeated rate limiting")


def qualifies(inner: dict) -> tuple[bool, str]:
    """Frozen criteria 1-7. Returns (ok, first failing criterion)."""
    if inner.get("type") != "post":
        return False, "not_a_post"
    if (inner.get("lang") or "").lower() != "en":
        return False, "not_english"
    text = (inner.get("text") or "").strip()
    if text in DEAD:
        return False, "deleted_or_empty"
    if not (MIN_CHARS <= len(text) <= MAX_CHARS):
        return False, "length_out_of_band"
    if "?" not in text and not ADVICE.search(text):
        return False, "no_question_marker"
    if not REC_INTENT.search(text):
        return False, "no_recommendation_intent"
    if (inner.get("analysis") or {}).get("nsfw"):
        return False, "nsfw"
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts-only", action="store_true")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    key = load_key()
    out = ["# 006 feasibility probe — counts", "",
           "Count-only, per the frozen protocol in `feasibility.md`.",
           "No post text appears here; raw payloads stay in gitignored data/raw/.", ""]

    # --- step 1: tier counts (1 item each) --------------------------------
    counts, quota = {}, None
    out.append("## Tier counts\n")
    out.append("| Tier | Matching items | Query |")
    out.append("|---|---|---|")
    for i, (name, q) in enumerate(TIERS.items()):
        if i:
            time.sleep(PACE_SECONDS)
        r = search(key, q, 1)
        counts[name] = r.get("total", 0)
        quota = r.get("quota", quota)
        rel = r.get("total_relation", "")
        print(f"{name}: total={counts[name]} {rel}")
        out.append(f"| {name} | {counts[name]:,}{'+' if rel == 'gte' else ''} | `{q}` |")
    out.append("")
    out.append("Counts overlap between tiers and are not summed. `+` marks a "
               "lower bound the API reports rather than an exact total.\n")

    if args.counts_only:
        (RESULTS / "feasibility-counts.md").write_text("\n".join(out) + "\n")
        print(f"\nquota: {quota}")
        return

    # --- step 2: qualifying rate on the narrowest viable tier -------------
    tier = next((t for t in TIER_PREFERENCE if counts.get(t, 0) >= 200), None)
    if tier is None:
        out.append("## Qualifying rate\n\nNo tier reached 200 matches; "
                   "sample skipped. Estimated qualifying posts: **< 20**. "
                   "Decision: **stop** per the frozen kill criterion.\n")
        (RESULTS / "feasibility-counts.md").write_text("\n".join(out) + "\n")
        print("no tier >= 200 — stopping per protocol")
        return

    print(f"\nsampling {SAMPLE_N} from {tier} ...")
    time.sleep(PACE_SECONDS)
    r = search(key, TIERS[tier], SAMPLE_N)
    quota = r.get("quota", quota)
    items = r.get("items", [])
    (RAW / f"sample_{tier}.json").write_text(json.dumps(items, indent=2))

    reasons: dict[str, int] = {}
    seen: set[str] = set()
    ok_items = []
    for it in items:
        inner = it.get("item", it)
        good, why = qualifies(inner)
        if good:
            h = hashlib.sha256(
                re.sub(r"\s+", " ", (inner.get("text") or "").lower()).encode()
            ).hexdigest()
            if h in seen:
                good, why = False, "duplicate_text"
            else:
                seen.add(h)
        if good:
            ok_items.append(inner)
        else:
            reasons[why] = reasons.get(why, 0) + 1

    rate = len(ok_items) / len(items) if items else 0.0
    est = counts[tier] * rate
    decision = ("VIABLE — proceed to a pre-registered design" if est >= 50 else
                "REDUCED PANEL ONLY — report lower power and decide" if est >= 20 else
                "STOP — no follow-up study designed or announced")

    out.append(f"## Qualifying rate ({tier})\n")
    out.append(f"- Sampled: **{len(items)}** posts")
    out.append(f"- Qualifying: **{len(ok_items)}** ({rate:.1%})")
    out.append(f"- Tier total: **{counts[tier]:,}**")
    out.append(f"- **Estimated qualifying posts: {est:,.0f}**")
    out.append(f"- **Decision: {decision}**\n")
    out.append("### Why posts were excluded\n")
    out.append("| Reason | Count |")
    out.append("|---|---|")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        out.append(f"| {why} | {n} |")
    out.append("")

    subs: dict[str, int] = {}
    for inner in ok_items:
        s = inner.get("backend_sub") or "?"
        subs[s] = subs.get(s, 0) + 1
    out.append("### Subreddit spread of qualifying posts\n")
    out.append("Frame check: material concentrated in a handful of enthusiast")
    out.append("subreddits is a narrower population than one spread widely.\n")
    out.append("| Subreddit | Qualifying posts |")
    out.append("|---|---|")
    for s, n in sorted(subs.items(), key=lambda kv: -kv[1])[:20]:
        out.append(f"| {s} | {n} |")
    out.append(f"\nDistinct subreddits among qualifying posts: **{len(subs)}**\n")
    out.append(f"## Quota\n\n`{quota}`\n")

    (RESULTS / "feasibility-counts.md").write_text("\n".join(out) + "\n")
    print(f"qualifying {len(ok_items)}/{len(items)} = {rate:.1%} -> est {est:.0f}")
    print(f"DECISION: {decision}")
    print(f"quota: {quota}")


if __name__ == "__main__":
    main()
