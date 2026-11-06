"""Stage 01: one row per answer (spec §3) -> data/interim/frame.jsonl + frame_meta.json.

Reads the main-study ledgers and raw responses (``harness/run_wave.py``), never the
pilot's, re-normalizes every response with ``harness/answers.py`` and extracts brands:

- ``brands``: 010's ``extract_new`` (009's ``lexicon_extract`` after citation links are
  removed) with the prompt category's lexicon aliases, in first-mention order. For
  ``gm_ui`` the Gemini app's follow-up and chip markup is stripped first (Audit B).
- ``brands_markup``: the same with the markup kept (R6). Equal to ``brands`` off ``gm_ui``.
- ``brands_all``: ``brands`` plus every Haiku name the lexicon cannot place (R4), or null
  when the Haiku cache has no entry for the answer. ``--haiku`` runs 009's Haiku pass on
  answers not yet cached (paid; it writes ``brand_candidates_main.jsonl``, which the
  study's cost guard counts). The Haiku pass reads the same text the lexicon reads.

The lexicon is pinned by sha256: lexicon v3 (``exp004.LEXICON_V3_SHA256``) unless
``--lexicon PATH --lexicon-sha256 SHA`` names an extended one. The frame holds no answer
text and no search query text, only derived fields; it is gitignored all the same, since
it names brands and domains.

An answer counts once per (arm, prompt, wave): the UI task that was collected last, or
the API attempt that was collected. The app's error message is not an answer. Every
ledger tally Audit A needs (submissions, failed tasks, error answers, failed attempts,
missing answers) goes to ``frame_meta.json``.

Usage (repo root):
    uv run python experiments/004-api-vs-ui/pipeline/01_frame.py
    uv run python .../01_frame.py --synthetic planted
    uv run python .../01_frame.py --pilot      # the gap reproduction check (03_model.py --pilot)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import common
import pandas as pd
from common import ALL_ARMS, API_ARMS, PILOT_ITEMS, UI_MODEL_EXPECTED, WAVES, Mode

sys.path.insert(0, str(common.HARNESS))
import answers  # noqa: E402
import exp004  # noqa: E402

report = common._load("exp004_pilot_report_for_frame", common.EXP / "pipeline" / "pilot_report.py")


def latest_by(records: list[dict], key) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(key(r), {}).update(r)
    return out


def utc_to_et_date(stamp: str | None) -> str | None:
    if not stamp:
        return None
    from zoneinfo import ZoneInfo

    return datetime.fromisoformat(stamp).astimezone(ZoneInfo("America/New_York")).date().isoformat()


# ---------------------------------------------------------------- loading


def load_ui(store: exp004.Store, waves) -> tuple[list[dict], list[dict]]:
    """Final UI answer per (arm, item, wave), and per (arm, item, wave) ledger tallies."""
    rows, tallies = [], []
    for platform in ("chatgpt", "gemini"):
        arm = exp004.UI_ARM[platform]
        recs = [r for r in exp004.read_jsonl(store.ui_ledger(platform)) if int(r["wave"]) in waves]
        tasks = latest_by(recs, lambda r: r["task_id"])
        subs = Counter((r["item_id"], int(r["wave"])) for r in recs if r.get("status") == "submitted")
        by_key: dict[tuple, list[dict]] = {}
        for t in tasks.values():
            by_key.setdefault((t["item_id"], int(t["wave"])), []).append(t)
        for (item, wave), ts in sorted(by_key.items()):
            cost = sum(float(t.get("cost") or 0) for t in ts)
            tally = {"arm": arm, "item_id": item, "wave": wave, "submissions": subs[(item, wave)],
                     "failed": sum(t["status"] == "failed" for t in ts),
                     "error_answers": sum(t["status"] == "error_answer" for t in ts),
                     "pending": sum(t["status"] == "submitted" for t in ts), "cost_usd": cost}
            done = sorted((t for t in ts if t["status"] == "collected"),
                          key=lambda t: t.get("collected_at") or "")
            final = None
            for t in reversed(done):
                raw = json.loads(Path(t["result_path"]).read_text())
                norm = answers.from_dataforseo(raw)
                if answers.is_error_answer(norm["answer_text"]):
                    tally["error_answers"] += 1  # collected before the error rule matched it
                    continue
                final = (t, norm)
                break
            tally["answered"] = final is not None
            tallies.append(tally)
            if final is None:
                continue
            t, norm = final
            rows.append({"arm": arm, "item_id": item, "wave": wave, "norm": norm,
                         "run_date": utc_to_et_date(t.get("submitted_at")),
                         "submissions": tally["submissions"], "error_answers": tally["error_answers"],
                         "failed_tasks": tally["failed"], "attempts": tally["submissions"],
                         "resubmitted": tally["submissions"] > 1, "cost_usd": cost,
                         "replicated": False})
    return rows, tallies


def load_api(store: exp004.Store, waves, *, pilot: bool) -> tuple[list[dict], list[dict]]:
    """The collected API answer per (arm, item, wave), and ledger tallies.

    Pilot: one answer per arm in one round, set against every UI round (``replicated``)."""
    rows, tallies = [], []
    for instrument in ("openai", "gemini"):
        recs = [r for r in exp004.read_jsonl(store.api_ledger(instrument)) if r["arm"] in API_ARMS]
        wave_of = (lambda r: int(r["round"])) if pilot else (lambda r: int(r["wave"]))
        recs = [r for r in recs if pilot or wave_of(r) in waves]
        by_key: dict[tuple, list[dict]] = {}
        for r in recs:
            by_key.setdefault((r["arm"], r["item_id"], wave_of(r)), []).append(r)
        for (arm, item, wave), rs in sorted(by_key.items()):
            ok = [r for r in rs if r["status"] == "collected"]
            tally = {"arm": arm, "item_id": item, "wave": wave, "attempts": len(rs),
                     "failed": sum(r["status"] == "failed" for r in rs),
                     "empty_answers": sum(r["status"] == "empty_answer" for r in rs),
                     "model_mismatch": sum(r["status"] == "model_mismatch" for r in rs),
                     "answered": bool(ok), "cost_usd": sum(float(r.get("cost_usd") or 0) for r in rs)}
            if not pilot:
                tallies.append(tally)
            if not ok:
                continue
            r = ok[-1]
            stored = json.loads(Path(r["response_path"]).read_text())
            # Re-normalized from the raw response, so a parser fix reaches stored answers.
            norm = answers.NORMALIZERS[exp004.ARMS[arm].instrument](stored["raw"])
            base = {"arm": arm, "item_id": item, "norm": norm, "run_date": r.get("run_date"),
                    "submissions": None, "error_answers": None, "failed_tasks": None,
                    "attempts": len(rs), "resubmitted": False, "cost_usd": tally["cost_usd"],
                    "model_problems": r.get("problems") or []}
            if pilot:
                for w in waves:
                    rows.append(base | {"wave": w, "replicated": True, "source_round": wave})
                    tallies.append(tally | {"wave": w})
            else:
                rows.append(base | {"wave": wave, "replicated": False})
    return rows, tallies


# ---------------------------------------------------------------- features


def lexicon_for(mode: Mode, args) -> tuple[Path, str]:
    if mode.synthetic:
        path = mode.raw / "lexicon.csv"
        return path, common.sha256_file(path)
    if args.lexicon:
        if not args.lexicon_sha256:
            raise SystemExit("--lexicon needs --lexicon-sha256 (the extended lexicon's pin)")
        path, sha = Path(args.lexicon), args.lexicon_sha256
    else:
        path, sha = common.STUDY_LEXICON, common.STUDY_LEXICON_SHA256
    got = common.sha256_file(path)
    if got != sha:
        raise SystemExit(f"lexicon sha256 mismatch for {path.name}: got {got}, pinned {sha}")
    return path, sha


def build(mode: Mode, args) -> tuple[pd.DataFrame, dict]:
    exp004.RAW = mode.raw  # every Store path resolves against the mode's raw directory
    prompts = exp004.load_prompts(mode.raw / "prompts.csv") if mode.synthetic else exp004.load_prompts()
    categories = {k: v["category"] for k, v in prompts.items()}
    store = exp004.Store("") if mode.pilot else exp004.STUDY
    waves = exp004.UI_ROUNDS if mode.pilot else WAVES
    ui_rows, ui_tallies = load_ui(store, waves)
    api_rows, api_tallies = load_api(store, waves, pilot=mode.pilot)
    lex_path, lex_sha = lexicon_for(mode, args)
    patterns = common.b9.load_lexicon(lex_path)
    raw_rows = ui_rows + api_rows
    if not raw_rows:
        raise SystemExit(f"no answers found under {mode.raw}")

    texts = [answers.brand_text(r["arm"], r["norm"]["answer_text"]) for r in raw_rows]
    cache_path = (mode.raw / "brand_candidates_main.jsonl") if not mode.pilot else (
        mode.raw / "brand_candidates.jsonl")
    hk = pd.DataFrame({"category": [categories[r["item_id"]] for r in raw_rows], "answer_text": texts})
    haiku = report.haiku_names(hk, run=bool(args.haiku), cache_path=cache_path)

    rows = []
    for r, text in zip(raw_rows, texts, strict=True):
        n = r.pop("norm")
        cat = categories[r["item_id"]]
        pats = patterns.get(cat, [])
        raw_text = n["answer_text"]
        brands = common.extract(text, pats)
        names = haiku.get(report._cache_key(cat, text))
        unplaced = common.brands011.unplaced_names(names, pats) if names is not None else None
        is_api = r["arm"] in API_ARMS
        model = n.get("model")
        if is_api:
            pin = exp004.OPENAI_MODEL if exp004.ARMS[r["arm"]].instrument == "openai" else exp004.GEMINI_MODEL
            model_ok = model is not None and str(model).startswith(pin)
        else:
            model_ok = model == UI_MODEL_EXPECTED[r["arm"]]
        rec = {
            **{k: v for k, v in r.items() if k != "model_problems"},
            "platform": common.platform_of(r["arm"]), "category": cat, "intent": "b2b",
            "model": model, "model_ok": bool(model_ok),
            "brands": brands, "n_brands": len(brands),
            "brands_markup": common.extract(raw_text, pats) if r["arm"] == "gm_ui" else brands,
            "brands_all": (common.brands011.with_unplaced(brands, names, pats)
                           if names is not None else None),
            "n_haiku_names": len([x for x in names if x.strip()]) if names is not None else None,
            "n_unplaced": len(unplaced) if unplaced is not None else None,
            "cited_domains": n["cited_domains"], "evaluated_domains": n["evaluated_domains"],
            "n_cited": len(n["cited_urls"]), "n_evaluated": len(n["evaluated_urls"]),
            "n_cited_domains": len(n["cited_domains"]),
            "n_search_calls": n.get("n_web_search_calls") if exp004.ARMS[r["arm"]].instrument == "openai" else None,
            "n_queries": None if r["arm"] == "gm_ui" else len(n["search_queries"]),
            "searched": report.searched({"arm": r["arm"], **n}),
            "chars": len(raw_text), "empty": not raw_text.strip(),
            "question_only": report.question_only({"answer_text": raw_text, "brands": brands}),
            "markup_tags": len(answers.app_markup_tags(raw_text)),
            "markup_left": len(answers.app_markup_tags(text)),
            "reasoning_effort": n.get("reasoning_effort"),
            "domain_source": n.get("domain_source"),
            "pilot_prompt": r["item_id"] in PILOT_ITEMS,
            "answer_sha256": exp004.sha256_text(raw_text),
            "synthetic": int(bool(mode.synthetic)),
        }
        rows.append(rec)
    df = common.arm_order(pd.DataFrame(rows))
    tallies = ui_tallies + api_tallies
    expected = sorted(PILOT_ITEMS) if mode.pilot else sorted(prompts)
    present = {(t["arm"], t["item_id"], t["wave"]) for t in tallies if t["answered"]}
    missing = [{"arm": a, "wave": w, "item_id": i} for a in ALL_ARMS for w in waves for i in expected
               if (a, i, w) not in present]
    meta = {
        "mode": mode.label, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lexicon": lex_path.name, "lexicon_sha256": lex_sha, "waves": list(waves),
        "prompts": len(expected), "answers": len(df), "missing": missing, "tallies": tallies,
        "haiku_cache": cache_path.name, "haiku_covered": int(df["brands_all"].notna().sum()),
        "seed": common.SEED,
    }
    return df, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_mode_args(ap)
    ap.add_argument("--lexicon", default=None, help="an extended lexicon (needs --lexicon-sha256)")
    ap.add_argument("--lexicon-sha256", default=None)
    ap.add_argument("--haiku", action="store_true",
                    help="run 009's Haiku pass on uncached answers (paid; main study only)")
    a = ap.parse_args()
    mode = common.mode_from(a)
    if a.haiku and (mode.synthetic or mode.pilot):
        raise SystemExit("--haiku is for the main study only")
    df, meta = build(mode, a)
    common.write_frame(df, meta, mode)
    by = df.groupby(["arm", "wave"]).size().unstack(fill_value=0)
    print(f"01_frame ({mode.label}): {len(df)} answers, lexicon {meta['lexicon']} "
          f"{meta['lexicon_sha256'][:12]}, Haiku names for {meta['haiku_covered']} answers, "
          f"{len(meta['missing'])} missing")
    print(by.to_string())
    print(f"wrote {mode.frame_path}")


if __name__ == "__main__":
    main()
