"""Stage 01 — normalized responses -> data/interim/features.jsonl (spec §3).

One row per answer (prompt x arm x wave), waves 1-3 only (the pilot's
``pilot_responses`` are not part of the confirmatory analysis):

- ``brands``: canonical brands in first-mention order, frozen lexicon v2
  (``brands.lexicon_extract`` over ``normalized.answer_text``, which for a
  claude.ai chat that asked clarifying questions is the first reply only,
  deviation 1). The lexicon's sha256 is checked before anything runs.
- ``brands_haiku``: the cached Haiku candidates mapped through lexicon v2
  (``brands.haiku_via_lexicon``) for robustness R4; null where the cache has
  no record for this exact answer (it covers wave 1 only until
  ``harness/lexicon_candidates.py --wave N`` runs for waves 2 and 3).
- ``cited_domains`` / ``evaluated_domains``: registered domains of the
  normalized cited / evaluated URLs, first-seen order.
- ``grounding_tokens``: stopword-filtered tokens of the search queries
  (``aeo_research.overlap.token_set``). The query text itself is never kept.
- counts (``n_searches``, ``n_cited``, ``n_evaluated``, ``n_brands``,
  ``chars``), ``run_date``, ``model``, ``cost_usd`` (ledger, batch-priced,
  API arms only) and ``cache_write_1h`` (the call paid a 1-hour cache write,
  spec §6 cache note), the claude.ai ``clarifying_questions`` flag, the
  collector-notes flag (R7) and the wrong-setting flag (Audit A).
- ``cited_classes``: source class per cited domain from the frozen domain map
  (``data/raw/domain_map_v1.csv``) when it exists, else null.

The interim frame holds brand names and domains, so it stays under the
gitignored ``data/interim/``. It holds no answer text and no query text.

``--synthetic {planted,broken_join}`` builds the spec §8 step 3 dry-run
worlds from fake answers, a fake lexicon and fake ledger costs, pushed
through the SAME ``feature_row`` as real data, under
``data/interim/synthetic/<world>/``:

- ``planted``: every arm draws brands and cited domains per prompt from one
  shared per-prompt profile (so its gap to the UI is 0 by construction),
  except ``haiku45_leak``, which draws from a reshuffled profile within the
  same category (a large real gap), and ``sonnet5_leak_low``, which mixes the
  two and skips the search on some answers.
- ``broken_join``: the planted world with every API answer filed under a
  random other prompt (the join bug H_pos exists to catch), so 03_model must
  stop on H_pos.

Usage:
  uv run python experiments/009-claude-model-fidelity/pipeline/01_features.py
  uv run python .../01_features.py --synthetic planted
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from brands import LEXICON, frozen_lexicon, haiku_via_lexicon, lexicon_extract
from common import (
    ALL_ARMS,
    API_ARMS,
    CANDIDATES,
    DOMAIN_MAP,
    DOMAIN_MAP_SHA256,
    LEDGER,
    PROMPTS_CSV,
    RESPONSES_DIR,
    SEED,
    SYNTHETIC_WORLDS,
    UI_ARMS,
    UI_SHEETS,
    UI_WRONG_SETTING,
    WAVES,
    features_path,
    interim_dir,
    ordered_domains,
    sha256_file,
    write_features,
)

from aeo_research.overlap import token_set

ET = ZoneInfo("America/New_York")

#: Refusal heuristic for Audit A: an apology-shaped refusal near the start of
#: the answer, or the API's ``refusal`` stop reason.
REFUSAL = re.compile(
    r"\b(?:I\s+(?:can(?:'|’)?t|cannot|am\s+unable\s+to|won(?:'|’)?t)|I(?:'|’)m\s+(?:not\s+able|unable)\s+to)"
    r"\s+(?:help|assist|provide|recommend|do\s+that|comply)",
    re.I,
)


# ------------------------------------------------------------- loaders


def load_prompts(path: Path = PROMPTS_CSV) -> dict[str, dict]:
    with path.open(newline="") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def load_ledger(path: Path = LEDGER) -> dict[tuple[str, str, int], dict]:
    """Last collected ledger record per (arm, item_id, wave)."""
    out: dict[tuple[str, str, int], dict] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") == "collected":
            out[(r["arm"], r["item_id"], int(r["wave"]))] = r
    return out


def load_notes(sheets_dir: Path = UI_SHEETS) -> dict[tuple[str, str, int], bool]:
    """(arm, item_id, wave) -> the collector wrote a note on that sheet row (R7)."""
    out: dict[tuple[str, str, int], bool] = {}
    for wave in WAVES:
        path = sheets_dir / f"w{wave}.csv"
        if not path.exists():
            continue
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                out[(r["arm"], r["item_id"], wave)] = bool((r.get("notes") or "").strip())
    return out


def load_candidates(path: Path = CANDIDATES) -> dict[str, list[str]]:
    """Haiku candidate cache keyed ``arm|item_id|wave|answer_sha256``."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["key"]] = rec.get("brands") or []
    return out


def load_domain_map(path: Path = DOMAIN_MAP) -> tuple[dict[str, str] | None, str]:
    """registered domain -> source class, from the frozen map if present."""
    if not path.exists():
        return None, f"no {path.name}; source class left null"
    sha = sha256_file(path)
    if DOMAIN_MAP_SHA256 and sha != DOMAIN_MAP_SHA256:
        raise SystemExit(f"{path.name} sha256 {sha} does not match the frozen "
                         f"{DOMAIN_MAP_SHA256}; refusing to run")
    status = "frozen" if DOMAIN_MAP_SHA256 else "NOT YET FROZEN (sha256 not recorded in common.py)"
    out = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            cls = (r.get("reviewer_class") or "").strip() or (r.get("suggested_class") or "").strip()
            out[r["registered_domain"]] = cls or "other"
    return out, f"{path.name} sha256 {sha[:12]}..., {status}"


# ------------------------------------------------------------- features


def run_date_of(resp: dict, ledger_rec: dict | None) -> str:
    if ledger_rec and ledger_rec.get("run_date"):
        return str(ledger_rec["run_date"])
    if resp.get("run_date"):
        return str(resp["run_date"])
    created = (resp.get("normalized") or {}).get("created_at")
    if created:
        try:
            return datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(ET).date().isoformat()
        except ValueError:
            return str(created)[:10]
    return ""


def feature_row(
    resp: dict,
    prompt: dict,
    patterns: dict,
    alias_map: dict,
    candidates: dict[str, list[str]],
    ledger: dict,
    notes: dict,
    domain_map: dict[str, str] | None,
    *,
    synthetic: int = 0,
) -> dict:
    """The spec §3 row for one normalized response (real or synthetic)."""
    n = resp["normalized"]
    arm, item, wave = resp["arm"], resp["item_id"], int(resp["wave"])
    category = prompt["category"]
    text = n.get("answer_text") or ""
    sha = hashlib.sha256(text.encode()).hexdigest()
    cited_urls = n.get("cited_urls") or []
    eval_urls = n.get("evaluated_urls") or []
    queries = n.get("search_queries") or []
    brands = lexicon_extract(text, patterns.get(category, []))

    key = f"{arm}|{item}|{wave}|{sha}"
    haiku = None
    if key in candidates:
        haiku = haiku_via_lexicon(candidates[key], category, alias_map)

    led = ledger.get((arm, item, wave))
    cited = ordered_domains(cited_urls)
    warnings = n.get("warnings") or []
    stop = n.get("stop_reason")
    return {
        "item_id": item,
        "category": category,
        "intent": prompt["intent"],
        "arm": arm,
        "surface": "ui" if arm in UI_ARMS else "api",
        "wave": wave,
        "run_date": run_date_of(resp, led),
        "model": n.get("model") or ("claude.ai" if arm in UI_ARMS else None),
        "answer_sha256": sha,
        "chars": len(text),
        "empty_answer": not text.strip(),
        "refusal": bool(stop == "refusal" or REFUSAL.search(text[:600])),
        "stop_reason": stop,
        "n_turns": n.get("n_turns"),
        "paused": bool(led.get("paused") or led.get("paused_in_batch")) if led else False,
        "brands": brands,
        "n_brands": len(brands),
        "brands_haiku": haiku,
        "cited_domains": cited,
        "n_cited": len(cited_urls),
        "cited_urls_source": n.get("cited_urls_source") or "citations",
        "n_cited_domains": len(cited),
        "evaluated_domains": ordered_domains(eval_urls),
        "n_evaluated": len(eval_urls),
        "grounding_tokens": sorted(token_set(queries)),
        "n_queries": len(queries),
        "n_searches": int(n.get("n_searches") or 0),
        "n_fetches": int(n.get("n_fetches") or 0),
        "n_warnings": len(warnings),
        "other_tools": any(w.startswith("other tools used") for w in warnings),
        "clarifying_questions": bool(n.get("clarifying_questions")),
        "collector_notes": bool(notes.get((arm, item, wave), False)),
        "ui_wrong_setting": (arm, item, wave) in set(UI_WRONG_SETTING),
        "cost_usd": float(led["cost_usd"]) if led and led.get("cost_usd") is not None else None,
        "cache_write_1h": (
            bool((led.get("cost_breakdown") or {}).get("cache_write_1h", 0) > 0) if led else None
        ),
        "cited_classes": [domain_map.get(d, "other") for d in cited] if domain_map is not None
        else None,
        "synthetic": synthetic,
    }


def build_real() -> tuple[pd.DataFrame, list[str]]:
    patterns, alias_map, sha = frozen_lexicon()
    prompts = load_prompts()
    ledger = load_ledger()
    notes = load_notes()
    candidates = load_candidates()
    domain_map, map_note = load_domain_map()
    rows = []
    for wave in WAVES:
        for path in sorted((RESPONSES_DIR / f"w{wave}").glob("*/*.json")):
            resp = json.loads(path.read_text())
            resp.setdefault("arm", path.parent.name)
            resp.setdefault("item_id", path.stem)
            resp["wave"] = wave
            rows.append(feature_row(resp, prompts[resp["item_id"]], patterns, alias_map,
                                    candidates, ledger, notes, domain_map))
    notes_out = [f"lexicon {LEXICON.name} sha256 {sha} (verified)", f"domain map: {map_note}"]
    return pd.DataFrame(rows), notes_out


# ------------------------------------------------------------- synthetic

N_CATEGORIES = 20
BRANDS_PER_CATEGORY = 14
DOMAINS_PER_CATEGORY = 16
SHARED_PUBLISHERS = 12


def synth_world_inputs(tmp: Path) -> tuple[dict, Path]:
    """Fake prompts (20 categories x 2 intents) and a fake lexicon file.

    Brand names are invented tokens (``Zq0307`` = category 3, brand 7), so
    the dry run needs no real data and leaks none. Each category also has one
    drop row (a "buyer's other system") and one case-sensitive alias.
    """
    prompts = {}
    for i in range(1, 2 * N_CATEGORIES + 1):
        c = (i - 1) // 2 + 1
        prompts[f"b2b_{i:02d}"] = {
            "item_id": f"b2b_{i:02d}", "category": f"category {c:02d}",
            "intent": "shortlist" if i % 2 else "evaluate", "text": f"synthetic prompt {i}",
        }
    lex = tmp / "lexicon_synthetic.csv"
    with lex.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical", "aliases", "category", "decision", "reason", "match",
                    "n_answers", "change"])
        for c in range(1, N_CATEGORIES + 1):
            cat = f"category {c:02d}"
            for k in range(1, BRANDS_PER_CATEGORY + 1):
                name = f"Zq{c:02d}{k:02d}"
                aliases = f"{name}|{name} Cloud" if k == 1 else name
                w.writerow([name.lower(), aliases, cat, "keep", "in category",
                            "cs" if k == 2 else "ci", 0, "new"])
            w.writerow([f"ledgerx{c:02d}", f"LedgerX{c:02d}", cat, "drop",
                        "out of category", "ci", 0, "new"])
    return prompts, lex


def synth_profiles(rng: np.random.Generator) -> dict:
    """Per prompt: inclusion probabilities over the category's brands and domains.

    The divergent profile reassigns the same probabilities to a reshuffled
    brand (and domain) order within the category, so the divergent arm names
    as many brands but largely different ones.
    """
    levels = np.array([0.95, 0.92, 0.9, 0.85, 0.8, 0.6, 0.35, 0.15, 0.08, 0.05, 0.03, 0.02,
                       0.02, 0.01])
    dom_levels = np.array([0.9, 0.85, 0.8, 0.7, 0.55, 0.4, 0.25, 0.15, 0.1, 0.05, 0.05, 0.03,
                           0.02, 0.02, 0.01, 0.01])
    out = {}
    for i in range(1, 2 * N_CATEGORIES + 1):
        brand_p = rng.permutation(levels)
        dom_p = rng.permutation(dom_levels)
        out[f"b2b_{i:02d}"] = {
            "brands": brand_p,
            "brands_div": rng.permutation(brand_p),
            "domains": dom_p,
            "domains_div": rng.permutation(dom_p),
        }
    return out


#: Arm behavior in the planted world: which profile, and no-search rate.
SYNTH_ARMS = {
    "ui_default": ("same", 0.0),
    "ui_think": ("same", 0.0),
    "opus55_plain": ("same", 0.0),
    "opus55_leak": ("same", 0.0),
    "sonnet5_plain": ("same", 0.0),
    "sonnet5_leak_think": ("same", 0.0),
    "sonnet5_leak_low": ("mix", 0.15),
    "sonnet5_prod": ("same", 0.0),
    "haiku45_leak": ("divergent", 0.0),
}
SYNTH_COST = {"opus55_plain": 0.07, "opus55_leak": 0.13, "sonnet5_plain": 0.065,
              "sonnet5_leak_think": 0.078, "sonnet5_leak_low": 0.047, "sonnet5_prod": 0.08,
              "haiku45_leak": 0.046}


def synth_answer(item: str, category_no: int, brand_idx: list[int], arm: str,
                 rng: np.random.Generator) -> str:
    lines = [f"Here is a shortlist for prompt {item}."]
    for k in brand_idx:
        name = f"Zq{category_no:02d}{k + 1:02d}"
        if k == 0 and rng.random() < 0.5:
            name += " Cloud"
        lines.append(f"- **{name}**: a fit for teams like yours ([site](https://{name.lower()}.com/x)).")
    lines.append(f"It also syncs with LedgerX{category_no:02d}, your accounting system.")
    if arm == "sonnet5_prod":
        # A sources block naming a brand that is not otherwise in the answer:
        # strip_sources must remove it before extraction (deviation 3).
        lines += ["", "**Sources referenced:**", f"- Zq{category_no:02d}14 blog", "- a review site"]
    return "\n".join(lines)


def build_synthetic(world: str) -> tuple[pd.DataFrame, list[str]]:
    rng = np.random.default_rng(SEED)
    out_dir = interim_dir(world)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts, lex_path = synth_world_inputs(out_dir)
    patterns, alias_map, _ = frozen_lexicon(lex_path, expected=None)
    profiles = synth_profiles(rng)
    publishers = [f"https://pub{j:02d}.org/review" for j in range(1, SHARED_PUBLISHERS + 1)]

    responses, ledger, notes, candidates = [], {}, {}, {}
    for wave in WAVES:
        for arm, (profile, no_search) in SYNTH_ARMS.items():
            for item, prompt in prompts.items():
                c = int(prompt["category"].split()[-1])
                prof = profiles[item]
                use_div = profile == "divergent" or (profile == "mix" and rng.random() < 0.5)
                bp = prof["brands_div"] if use_div else prof["brands"]
                dp = prof["domains_div"] if use_div else prof["domains"]
                picked = [k for k in range(BRANDS_PER_CATEGORY) if rng.random() < bp[k]]
                order = list(rng.permutation(picked))
                searched = rng.random() >= no_search
                cited = [f"https://www.d{c:02d}x{k + 1:02d}.com/page?utm_source=x"
                         for k in range(DOMAINS_PER_CATEGORY) if rng.random() < dp[k]]
                if searched:
                    cited += [p for p in publishers if rng.random() < 0.08]
                else:
                    cited = []
                evaluated = cited + [p for p in publishers if rng.random() < 0.3] if searched else []
                text = synth_answer(item, c, order, arm, rng)
                norm = {
                    "answer_text": text, "cited_urls": cited, "evaluated_urls": evaluated,
                    "search_queries": [f"best {prompt['category']} tools", "pricing comparison"]
                    if searched else [],
                    "n_searches": int(rng.integers(1, 4)) if searched else 0,
                    "stop_reason": "end_turn" if arm not in UI_ARMS else None,
                    "model": None if arm in UI_ARMS else f"synthetic-{arm}",
                    "warnings": [],
                }
                if arm in UI_ARMS and item == "b2b_28":
                    norm["clarifying_questions"] = True
                responses.append({"arm": arm, "item_id": item, "wave": wave, "normalized": norm})
                if arm in UI_ARMS:
                    notes[(arm, item, wave)] = item in ("b2b_28", "b2b_36")
                else:
                    first = rng.random() < 0.1
                    ledger[(arm, item, wave)] = {
                        "run_date": f"2026-09-{26 + wave:02d}",
                        "cost_usd": SYNTH_COST[arm] * float(rng.uniform(0.8, 1.2))
                        + (0.04 if first else 0.0),
                        "cost_breakdown": {"cache_write_1h": 0.04 if first else 0.0},
                    }
                sha = hashlib.sha256(text.encode()).hexdigest()
                if wave in (1, 2):  # partial R4 coverage, as in the real cache
                    names = [f"Zq{c:02d}{k + 1:02d}" for k in order]
                    candidates[f"{arm}|{item}|{wave}|{sha}"] = names

    if world == "broken_join":
        # File every API answer under a random other prompt, consistently per
        # (arm, wave): the join bug H_pos is there to catch.
        items = list(prompts)
        for wave in WAVES:
            for arm in API_ARMS:
                perm = dict(zip(items, rng.permutation(items)))
                for r in responses:
                    if r["arm"] == arm and r["wave"] == wave:
                        r["item_id"] = str(perm[r["item_id"]])

    rows = [feature_row(r, prompts[r["item_id"]], patterns, alias_map, candidates, ledger,
                        notes, None, synthetic=1) for r in responses]
    return pd.DataFrame(rows), [f"SYNTHETIC world '{world}' (fake lexicon, no real data)"]


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    a = ap.parse_args()

    df, notes = build_synthetic(a.synthetic) if a.synthetic else build_real()
    if df.empty:
        raise SystemExit("no responses found")
    path = features_path(a.synthetic)
    write_features(df, path)

    tag = f"SYNTHETIC/{a.synthetic} " if a.synthetic else ""
    print(f"wrote {len(df)} {tag}answers -> {path}")
    for line in notes:
        print(f"  {line}")
    counts = df.groupby(["arm", "wave"]).size().unstack(fill_value=0)
    print(counts.reindex([x for x in ALL_ARMS if x in counts.index]).to_string())
    missing_r4 = Counter(int(w) for w, h in zip(df["wave"], df["brands_haiku"]) if h is None)
    print(f"answers without Haiku candidates (R4) by wave: {dict(sorted(missing_r4.items()))}")


if __name__ == "__main__":
    main()
