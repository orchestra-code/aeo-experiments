"""Stage 01 — ledger + raw Responses JSONs -> interim/{responses,site_observations}.csv.

One row per study call in ``responses.csv`` (call-level outcomes, spec §3)
and one row per ``site:`` query in ``site_observations.csv`` (the unit H2 and
H3 analyse). All scoring goes through ``scoring.py``; this stage only walks
the ledger, resolves item_ids to panel brands, and shapes the frames.

The pilot (intent ``pilot``, wave 0) is excluded from the study frame — it
ran before the freeze on a different item_id scheme and is reported in
Audit A as pilot only.

``--synthetic {lookup,guess}`` plants the two dry-run worlds required by spec
§5 and writes them under ``interim/synthetic/<world>/`` so they can never
overwrite the real frames. Both are built as fake Responses-API payloads and
pushed through the SAME extractor and scorer as real data:

- ``lookup``  a pure stored-association world. Tier A is always right; every
  other brand that HAS a frozen candidate set gets a fixed per-brand error
  probability (one in three is 0, the rest ~0.5-0.7) and when it errs it
  always emits the SAME domain — its old domain where it has one, otherwise
  its first frozen guess — stable across replicates and days, with a sticky
  day-to-day chain so wrong-at-t predicts wrong-at-t+1. The panel's tier-C
  brands carry the migrated-domain story; tiers B and D are included because
  a stored association can be wrong about any brand, and because the frozen
  candidate sets of tier B/D are the only ones with K >= 2 — the region where
  the H2 sensitivity is identifying at all.
- ``guess``   a pure per-run generative world. Every brand with a frozen
  candidate set errs with p≈0.3 per call, independently across replicates and
  days, and the erring domain is drawn fresh and uniformly from that brand's
  FROZEN candidate set (``expected_guess`` + ``old_domains``, minus the true
  domain) — the mechanism the spec describes in §1 ("brandname.com/.io-style
  tokens"), not an invented wider space. Brands the frozen panel gives no
  candidate domains (most of tier D) therefore never err here: the instrument
  cannot express a guess for them, which 03_model reports.

Usage:
  uv run python experiments/008-brand-domain-knowledge/pipeline/01_features.py
  uv run python .../01_features.py --synthetic lookup
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from common import (
    INTENT_BY_REPLICATE,
    LEDGER,
    MAX_WAVE,
    PANEL,
    SEED,
    STUDY_INTENTS,
    SYNTHETIC_WORLDS,
    TEMPLATES,
    interim_dir,
    obs_csv,
    parse_item_id,
    registered_domain,
    responses_csv,
    slug,
)
from annotations import attribution
from scoring import build_scorers, frozen_candidate_set, score_call

from aeo_research.dataforseo import Ledger



def with_attribution(call: dict, observations: list[dict], brand: str) -> None:
    """Attach Jim's signed Audit D attribution (annotations.py) in place.

    Only ``name_bearing_other`` needs one; everything else gets "". This is a
    labelled layer on top of the frozen scoring, never part of it — the
    primary outcome is computed before this function runs and is not touched
    by it.
    """
    for obs in observations:
        obs["attribution"] = (
            attribution(brand, obs["registered_domain"])
            if obs["error_kind"] == "name_bearing_other" else ""
        )
    call["first_site_attribution"] = (
        attribution(brand, call["first_site_domain"])
        if call["first_site_error_kind"] == "name_bearing_other" else ""
    )


def run_date_of(created_at, fallback: str) -> str:
    if pd.notna(created_at):
        try:
            return datetime.fromtimestamp(int(created_at), tz=timezone.utc).date().isoformat()
        except (ValueError, OSError, OverflowError):
            pass
    return str(fallback)[:10]


def ledger_frame() -> pd.DataFrame:
    """Last ledger line per (intent, item_id, wave) — the collector retries."""
    records = Ledger(LEDGER).records()
    frame = pd.DataFrame(records)
    frame["wave"] = pd.to_numeric(frame["wave"], errors="coerce").astype("Int64")
    return frame.drop_duplicates(subset=["intent", "item_id", "wave"], keep="last")


def study_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        frame["intent"].isin(STUDY_INTENTS)
        & frame["wave"].between(1, MAX_WAVE)
        & (frame["status"] == "collected")
    ].copy()


def build_real() -> tuple[pd.DataFrame, pd.DataFrame]:
    scorers = build_scorers(PANEL)
    repo_root = Path(__file__).resolve().parents[3]
    calls, observations = [], []
    for row in study_rows(ledger_frame()).itertuples():
        brand_slug, template, replicate = parse_item_id(row.item_id)
        scorer = scorers[brand_slug]
        path = Path(row.result_path)
        if not path.is_absolute():
            path = repo_root / path
        response = json.loads(path.read_text())
        call, obs = score_call(response, scorer)
        with_attribution(call, obs, scorer.canonical)
        keys = {
            "item_id": row.item_id,
            "brand": scorer.canonical,
            "slug": brand_slug,
            "tier": scorer.tier,
            "template": template,
            "replicate": replicate,
            "intent": row.intent,
            "wave": int(row.wave),
        }
        run_date = run_date_of(call.pop("created_at"), row.collected_at)
        calls.append(keys | {"run_date": run_date, "synthetic": 0} | call)
        observations += [keys | {"run_date": run_date, "synthetic": 0} | o for o in obs]
    return pd.DataFrame(calls), pd.DataFrame(observations)


# ------------------------------------------------------------- synthetic

#: Reference/competitor domains a comparison prompt consults by design —
#: third_party observations, not errors about the asked brand.
THIRD_PARTY = ("g2.com", "capterra.com", "clickup.com", "trustradius.com", "pcmag.com")

STICKINESS = 0.92           # lookup world: P(state carries to the next wave)
ERROR_RATE = 0.30           # guess world: P(a call errs), independent per call
NO_EMISSION_RATE = 0.02     # a handful of comparison calls emit no site: query
THIRD_PARTY_ONLY_RATE = 0.03  # comparison calls that only ever open competitors


def fake_response(hosts: list[str], entry, rng: np.random.Generator, created_at: int) -> dict:
    """A Responses-API-shaped payload carrying exactly these site: hosts.

    Deliberately mixes the two search-action shapes the real API emits: one
    action carrying only ``action.query`` and one carrying ``action.queries``
    plus a repeated ``action.query`` (which must not be double counted).
    """
    queries = [f"site:{host} {entry.category} official pricing" for host in hosts]
    queries.append(f"{entry.canonical} {entry.category} reviews")
    output: list[dict] = [{"type": "reasoning", "summary": []}]
    first, rest = queries[0], queries[1:]
    sources = [{"type": "url", "url": f"https://{h}/about"} for h in hosts[:1]]
    sources += [{"type": "url", "url": f"https://{rng.choice(THIRD_PARTY)}/reviews"}]
    output.append(
        {"type": "web_search_call",
         "action": {"type": "search", "query": first, "sources": sources}}
    )
    if rest:
        output.append(
            {"type": "web_search_call",
             "action": {"type": "search", "query": rest[0], "queries": rest,
                        "sources": [{"type": "url", "url": f"https://{h}/pricing"}
                                    for h in hosts[1:]]}}
        )
    output.append({"type": "web_search_call", "action": {"type": "open_page"}})
    cited = hosts[:1] or [registered_domain(entry.true_domain)]
    output.append(
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": f"{entry.canonical} is a {entry.category}. " * 20,
                    "annotations": [
                        {"type": "url_citation", "url": f"https://{c}/product"} for c in cited
                    ],
                }
            ],
        }
    )
    return {
        "model": "gpt-5.6-terra-synthetic",
        "created_at": created_at,
        "usage": {"input_tokens": int(rng.integers(20000, 32000)),
                  "output_tokens": int(rng.integers(900, 2400))},
        "output": output,
    }


def call_plan() -> list[tuple[str, int, int]]:
    """(intent, wave, replicate) for allocation C: core waves 1-10 + wave-1 R3."""
    plan = [("core", wave, 0) for wave in range(1, MAX_WAVE + 1)]
    plan += [(INTENT_BY_REPLICATE[r], 1, r) for r in (1, 2)]
    return plan


def mechanism_parameters(rng: np.random.Generator) -> tuple[dict, dict, dict]:
    """Per-brand error probability, stored wrong domain, and guess pool.

    Both worlds err only where the FROZEN panel gives the brand a candidate
    wrong domain; tier A (which has none) is always correct, so H_pos holds
    in both worlds by construction.
    """
    error_prob, stored, pools = {}, {}, {}
    for i, entry in enumerate(PANEL):
        key = slug(entry.canonical)
        pool = sorted(frozen_candidate_set(entry))
        pools[key] = pool
        olds = [registered_domain(d) for d in entry.old_domains]
        if entry.tier == "A" or not pool:
            error_prob[key], stored[key] = 0.0, ""
            continue
        error_prob[key] = 0.0 if i % 3 == 0 else float(rng.uniform(0.5, 0.7))
        stored[key] = olds[0] if olds else pool[0]
    return error_prob, stored, pools


def build_synthetic(world: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    scorers = build_scorers(PANEL)
    base_day = datetime(2026, 9, 2, 14, 30, tzinfo=timezone.utc).timestamp()
    error_prob, stored, pools = mechanism_parameters(rng)

    calls, observations = [], []
    for entry in PANEL:
        key = slug(entry.canonical)
        scorer = scorers[key]
        truth = registered_domain(entry.true_domain)
        for template in TEMPLATES:
            # Lookup world: one sticky day-to-day chain per brand x template,
            # shared by the same day's replicates (stable within a day).
            chain: dict[int, bool] = {}
            state = rng.random() < error_prob[key]
            for wave in range(1, MAX_WAVE + 1):
                if wave > 1 and rng.random() >= STICKINESS:
                    state = rng.random() < error_prob[key]
                chain[wave] = state

            for intent, wave, replicate in call_plan():
                if world == "lookup":
                    wrong_domain = stored[key] if chain[wave] else ""
                else:
                    errs = pools[key] and rng.random() < ERROR_RATE
                    wrong_domain = str(rng.choice(pools[key])) if errs else ""

                hosts = [wrong_domain or truth]
                if wrong_domain and rng.random() < 0.5:
                    hosts.append(truth)          # the call also finds the real site
                elif not wrong_domain and rng.random() < 0.4:
                    hosts.append(f"help.{truth}")
                if template == "p2":
                    draw = rng.random()
                    if draw < NO_EMISSION_RATE:
                        hosts = []
                    elif draw < NO_EMISSION_RATE + THIRD_PARTY_ONLY_RATE:
                        # Opens on a competitor and never names the brand's own
                        # site: no brand-attributable commitment at all.
                        hosts = [str(rng.choice(THIRD_PARTY))]
                    else:
                        hosts.append(str(rng.choice(THIRD_PARTY)))

                created_at = int(base_day + (wave - 1) * 86400 + replicate * 14400)
                response = fake_response(hosts, entry, rng, created_at)
                call, obs = score_call(response, scorer)
                with_attribution(call, obs, entry.canonical)
                keys = {
                    "item_id": f"{key}_{template}_r{replicate}",
                    "brand": entry.canonical,
                    "slug": key,
                    "tier": entry.tier,
                    "template": template,
                    "replicate": replicate,
                    "intent": intent,
                    "wave": wave,
                }
                run_date = run_date_of(call.pop("created_at"), "")
                calls.append(keys | {"run_date": run_date, "synthetic": 1} | call)
                observations += [keys | {"run_date": run_date, "synthetic": 1} | o for o in obs]
    return pd.DataFrame(calls), pd.DataFrame(observations)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    a = ap.parse_args()

    calls, observations = (
        build_synthetic(a.synthetic) if a.synthetic else build_real()
    )
    if calls.empty:
        raise SystemExit("no collected study calls in the ledger")

    interim_dir(a.synthetic).mkdir(parents=True, exist_ok=True)
    calls.to_csv(responses_csv(a.synthetic), index=False)
    observations.to_csv(obs_csv(a.synthetic), index=False)

    tag = f"SYNTHETIC/{a.synthetic} " if a.synthetic else ""
    print(f"wrote {len(calls)} {tag}calls -> {responses_csv(a.synthetic)}")
    print(f"wrote {len(observations)} {tag}site: observations -> {obs_csv(a.synthetic)}")
    print(calls.groupby(["intent", "wave"]).size().to_string())
    print("\ncall-level first-site label by tier:")
    print(pd.crosstab(calls["tier"], calls["first_site_label"]).to_string())
    print("\nobservation-level error kinds by tier:")
    if not observations.empty:
        print(pd.crosstab(observations["tier"], observations["error_kind"]).to_string())


if __name__ == "__main__":
    main()
