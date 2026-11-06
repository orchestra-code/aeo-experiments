"""Score experiment 004's feasibility run against sketch.md (G1 to G4), per platform.

Aggregates only: the report names no brand, quotes no answer and prints no prompt
text (public repo). Answers flagged for G2 are listed by (arm, item, round) on
stdout only, for a person to read; ``CLEARED_BY_READING`` records the ones read
and cleared.

Instruments and measures (sketch, Measures):

- Brands: 010's ``extract_new`` (009's ``lexicon_extract`` after citation links
  are removed) with lexicon v3, hash-checked, on every arm, UI and API alike.
- Coverage (G3): 009's Haiku pass (same prompt and schema, cached in
  ``data/raw/brand_candidates.jsonl``) and the lexicon-matcher rule: a Haiku name
  is covered when a lexicon alias of the prompt's category matches inside it.
- Brand gap: mean(within:ui) minus mean(cross:arm|ui). within:ui = the 3 pairs of
  UI rounds per prompt; cross = the arm's answer against each of the 3 UI rounds.
  90% prompt-level cluster bootstrap, seed 20261105, 2000 reps.
- Domains: registered domains of cited and evaluated URLs. Gemini API chunk URIs
  are redirect links; their domain comes from the chunk's ``web.domain`` when
  present, else ``web.title`` when it is a hostname (``harness/answers.py``).

Usage (repo root):
    uv run python experiments/004-api-vs-ui/pipeline/pilot_report.py
    uv run python experiments/004-api-vs-ui/pipeline/pilot_report.py --prefix smoke_ --no-haiku
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from aeo_research.overlap import cluster_boot, jaccard

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP / "harness"))
import answers  # noqa: E402
import exp004  # noqa: E402
import leaks  # noqa: E402

G1_API_MIN, G1_UI_MIN = 9, 28
G1_CG_MODEL_MIN, G1_GM_MODEL_MIN = 28, 27
CG_UI_MODEL, GM_UI_MODEL = "gpt-6", "3.5 Flash-Lite"
G2_ANSWER_MIN = 0.90
G2_SEARCH_MIN = 0.70
G3_COVERAGE_MIN = 0.90
G3_DOMAINS_MIN = 0.80
G4_GAP_MAX = 0.20
PLAIN_PREFERENCE = 0.03
QUESTION_ONLY_MAX_CHARS = 1200
#: (arm, item_id, round) read by a person and cleared as buyer-facing answers.
CLEARED_BY_READING: frozenset[tuple[str, str, int]] = frozenset()
#: Full study (sketch, "What a full study would look like").
FULL_PROMPTS, FULL_WAVES, FULL_API_ARMS = 40, 3, 2

PLATFORM_NAME = {"chatgpt": "ChatGPT", "gemini": "Gemini"}
PLATFORM_ARMS = {
    "chatgpt": ("cg_ui", "cg_api_plain", "cg_api_low", "cg_api_leak"),
    "gemini": ("gm_ui", "gm_api_plain", "gm_api_leak"),
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


b9 = _load("exp009_brands", exp004.EXP009 / "pipeline" / "brands.py")
instrument = _load("exp010_instrument", exp004.EXP010 / "harness" / "instrument.py")


# ---------------------------------------------------------------- loading


def _latest(records: list[dict], key) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(key(r), {}).update(r)
    return out


def load_ui(prefix: str, categories: dict[str, str]) -> tuple[list[dict], dict]:
    """Final UI answer per (arm, item, round), plus per-platform task tallies."""
    rows, tallies = [], {}
    for platform in ("chatgpt", "gemini"):
        path = exp004.ui_ledger(prefix, platform)
        recs = exp004.JsonlLedger(path).records()
        tasks = _latest(recs, lambda r: r["task_id"])
        tally = Counter(t["status"] for t in tasks.values())
        tally["submissions"] = sum(r.get("status") == "submitted" for r in recs)
        tally["cost"] = sum(float(t.get("cost") or 0) for t in tasks.values())
        tallies[exp004.UI_ARM[platform]] = tally
        final: dict[tuple, dict] = {}
        for t in sorted(tasks.values(), key=lambda t: t.get("collected_at") or ""):
            if t["status"] == "collected":
                final[(t["item_id"], int(t["wave"]))] = t
        for (item, rnd), t in sorted(final.items()):
            raw = json.loads(Path(t["result_path"]).read_text())
            rows.append({"arm": exp004.UI_ARM[platform], "platform": platform, "item_id": item,
                         "round": rnd, "category": categories[item],
                         **answers.from_dataforseo(raw)})
    return rows, tallies


def load_api(prefix: str, categories: dict[str, str]) -> tuple[list[dict], dict]:
    rows, tallies = [], {}
    for instrument_name in ("openai", "gemini"):
        recs = exp004.JsonlLedger(exp004.api_ledger(prefix, instrument_name)).records()
        for r in recs:
            t = tallies.setdefault(r["arm"], Counter())
            t[r["status"]] += 1
            t["cost"] += float(r.get("cost_usd") or 0)
        final = {}
        for r in recs:
            if r["status"] == "collected":
                final[(r["arm"], r["item_id"], int(r["round"]))] = r
        for (arm, item, rnd), r in sorted(final.items()):
            raw = json.loads(Path(r["response_path"]).read_text())
            # Re-normalized from the raw response, so a parser fix reaches stored answers.
            norm = answers.NORMALIZERS[exp004.ARMS[arm].instrument](raw["raw"])
            rows.append({"arm": arm, "platform": exp004.ARMS[arm].platform, "item_id": item,
                         "round": rnd, "category": categories[item], **norm,
                         "cost_usd": r.get("cost_usd"), "model_problems": r.get("problems") or []})
    return rows, tallies


def load_frame(prefix: str) -> tuple[pd.DataFrame, dict]:
    prompts = exp004.load_prompts()
    categories = {k: v["category"] for k, v in prompts.items()}
    ui_rows, ui_t = load_ui(prefix, categories)
    api_rows, api_t = load_api(prefix, categories)
    frame = pd.DataFrame(ui_rows + api_rows)
    patterns = b9.load_lexicon(exp004.verify_lexicon())
    frame["brands"] = [instrument.extract_new(b9, r.answer_text, patterns.get(r.category, []))
                       for r in frame.itertuples()]
    frame["domains"] = [list(dict.fromkeys([*c, *e])) for c, e in
                        zip(frame["cited_domains"], frame["evaluated_domains"], strict=True)]
    frame["leak_syntax"] = frame["answer_text"].map(lambda t: len(leaks.TOOL_SYNTAX.findall(t)))
    frame["searched"] = [searched(r) for r in frame.to_dict("records")]
    return frame, {**ui_t, **api_t}


def searched(r: dict) -> bool:
    """API: at least one search ran. UI: fan-out queries or sources were reported."""
    if r["arm"].endswith("_ui"):
        return bool(r.get("search_queries")) or bool(r.get("cited_urls"))
    return (r.get("n_web_search_calls") or 0) > 0 or (r.get("n_searches") or 0) > 0


# ---------------------------------------------------------------- Haiku pass


def _cache_key(category: str, text: str) -> str:
    return exp004.sha256_text(f"{category}\n{text}")


def haiku_names(frame: pd.DataFrame, run: bool = True) -> dict[str, list[str]]:
    """009's Haiku brand extractor per answer, cached; costs recorded in the cache."""
    cache_path = exp004.RAW / "brand_candidates.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                cache[rec["key"]] = rec["names"]
    todo = {}
    for r in frame.itertuples():
        k = _cache_key(r.category, r.answer_text)
        if k not in cache and r.answer_text.strip():
            todo[k] = (r.answer_text, r.category)
    if not todo or not run:
        return cache
    exp004.env_value("ANTHROPIC_API_KEY")  # stop unless the main checkout's key exists
    harness = str(exp004.EXP009 / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    ext = _load("exp009_harness_report", exp004.EXP009 / "harness" / "pilot_report.py")
    from anthropic_client import make_client

    client = make_client(str(exp004.ENV_FILE))
    lock = threading.Lock()

    def work(item):
        key, (text, category) = item
        names, usage = ext.extract_brands(client, text, category)
        cost = ext.cost_from_usage(ext.EXTRACT_MODEL, usage)["total"]
        rec = {"key": key, "names": names, "model": ext.EXTRACT_MODEL, "usage": usage,
               "cost_usd": cost, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with lock, cache_path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return key, names

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        for key, names in pool.map(work, todo.items()):
            cache[key] = names
    print(f"Haiku pass: {len(todo)} answers extracted")
    return cache


def coverage(frame: pd.DataFrame, cache: dict) -> dict[str, dict]:
    patterns = b9.load_lexicon(exp004.LEXICON_V3)
    out: dict[str, list[int]] = {}
    for r in frame.itertuples():
        names = cache.get(_cache_key(r.category, r.answer_text))
        tally = out.setdefault(r.arm, [0, 0, 0])
        if names is None:
            tally[2] += 1
            continue
        for name in names:
            clean = name.strip()
            if not clean:
                continue
            tally[0] += 1
            tally[1] += any(p.search(clean) for p, _c, _k in patterns.get(r.category, []))
    return {arm: {"names": n, "covered": c / n if n else float("nan"), "uncached": u}
            for arm, (n, c, u) in out.items()}


# ---------------------------------------------------------------- gap


def gap_pairs(frame: pd.DataFrame, arm: str, ui_arm: str) -> pd.DataFrame:
    out = []
    # An app error message is a missing answer, not an empty brand set (sketch, G1).
    usable = frame[~frame.answer_text.map(answers.is_error_answer)]
    ui = usable[usable.arm == ui_arm]
    mine = usable[usable.arm == arm]
    for item, group in ui.groupby("item_id"):
        recs = list(group.sort_values("round").to_dict("records"))
        for i, left in enumerate(recs):
            for right in recs[i + 1:]:
                out.append(("within", item, jaccard(set(left["brands"]), set(right["brands"]))))
        for ans in mine[mine.item_id == item].to_dict("records"):
            for right in recs:
                out.append(("cross", item, jaccard(set(ans["brands"]), set(right["brands"]))))
    data = pd.DataFrame(out, columns=["condition", "cluster_i", "value"])
    data["cluster_j"] = data["cluster_i"]
    return data


def brand_gap(frame: pd.DataFrame, arm: str, ui_arm: str):
    data = gap_pairs(frame, arm, ui_arm)
    usable = data.dropna(subset=["value"])
    if not {"within", "cross"} <= set(usable.condition):
        return None, data  # e.g. both brand sets empty everywhere (Jaccard undefined)
    return cluster_boot(data, contrast=("within", "cross"), n_boot=exp004.N_BOOT, seed=exp004.SEED,
                        alpha=0.10), data


# ---------------------------------------------------------------- report


def question_only(r: dict) -> bool:
    """Short, no lexicon brand, and asks the user something: a question back."""
    text = r["answer_text"].strip()
    return not r["brands"] and len(text) <= QUESTION_ONLY_MAX_CHARS and "?" in text


def select_arm(screen: dict[str, float]) -> str | None:
    """Sketch, Reading the outcome: the smallest gap among arms that passed G4; a plain
    arm is preferred when within 0.03 of the smallest, since it needs no leaked prompt."""
    if not screen:
        return None
    best = min(screen, key=lambda a: (screen[a], a))
    plain = next((a for a in sorted(screen) if a.endswith("_plain")), None)
    return plain if plain and screen[plain] <= screen[best] + PLAIN_PREFERENCE + 1e-12 else best


def fmt(x, nd=3, signed=False) -> str:
    if x is None or x != x:
        return "n/a"
    return f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"


def pct(x) -> str:
    return "n/a" if x is None or x != x else f"{x:.0%}"


def build_report(frame: pd.DataFrame, tallies: dict, cache: dict, expected_items: int,
                 rounds: int) -> tuple[str, list[str]]:
    cov = coverage(frame, cache)
    flagged_out: list[str] = []
    lines = [
        "# Experiment 004: feasibility report",
        "",
        "Scored against `sketch.md` (G1 to G4, per platform). Pilot data, never part of a "
        "confirmatory analysis. Aggregates only: no brand, answer or prompt text. "
        f"Prompts: {expected_items}; UI rounds: {rounds}; API arms: one answer per prompt. "
        f"Costs are estimates at list prices checked {exp004.PRICES_CHECKED} "
        "(`harness/exp004.py`).",
        "",
    ]
    verdicts: dict[str, dict] = {}
    for platform, arms in PLATFORM_ARMS.items():
        ui_arm = arms[0]
        api_arms = arms[1:]
        lines += [f"## {PLATFORM_NAME[platform]}", ""]

        # ---- G1
        lines += ["### G1, clean instrument", "",
                  "| Arm | Answers | Need | Model ids reported | Model check | First-try failures "
                  "or app error messages | G1 |", "|---|---|---|---|---|---|---|"]
        g1 = {}
        for arm in arms:
            group = frame[frame.arm == arm]
            n_ok = int((~group.answer_text.map(answers.is_error_answer)).sum())
            is_ui = arm == ui_arm
            need = G1_UI_MIN if is_ui else G1_API_MIN
            models = Counter(group.model.fillna("(none)"))
            model_str = ", ".join(f"`{m}` {n}" for m, n in models.most_common())
            if is_ui:
                want = CG_UI_MODEL if platform == "chatgpt" else GM_UI_MODEL
                need_model = G1_CG_MODEL_MIN if platform == "chatgpt" else G1_GM_MODEL_MIN
                n_model = int((group.model == want).sum())
                model_ok = n_model >= need_model
                model_note = f"{n_model} report `{want}`, need {need_model}"
                t = tallies.get(arm, Counter())
                retries = f"{t['failed'] + t['error_answer']} of {t['submissions']} submissions"
            else:
                want = exp004.OPENAI_MODEL if platform == "chatgpt" else exp004.GEMINI_MODEL
                n_model = int(group.model.fillna("").str.startswith(want).sum())
                model_ok = n_model == len(group) and len(group) > 0
                model_note = f"{n_model} of {len(group)} report `{want}`"
                t = tallies.get(arm, Counter())
                retries = f"{t['failed']} failed attempts"
            ok = n_ok >= need and model_ok
            g1[arm] = ok
            lines.append(f"| `{arm}` | {n_ok} | {need} | {model_str} | {model_note} | {retries} | "
                         f"{'PASS' if ok else 'FAIL'} |")

        # ---- behavior
        lines += ["", "### Behavior per answer", "",
                  "| Arm | n | Searched | Search calls | Queries (fan-out) | Cited URLs | "
                  "Evaluated URLs | Cited domains | Chars | Brands | No search |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm in arms:
            g = frame[frame.arm == arm]
            if g.empty:
                lines.append(f"| `{arm}` | 0 | | | | | | | | | |")
                continue
            calls = (g["n_web_search_calls"].fillna(0).mean() if "n_web_search_calls" in g
                     and arm.startswith("cg_api") else float("nan"))
            queries = g.search_queries.map(len).mean()
            q_str = "not reported" if arm == "gm_ui" and queries == 0 else fmt(queries, 1)
            lines.append(
                f"| `{arm}` | {len(g)} | {pct(g.searched.mean())} | {fmt(calls, 1)} | {q_str} | "
                f"{fmt(g.cited_urls.map(len).mean(), 1)} | {fmt(g.evaluated_urls.map(len).mean(), 1)} | "
                f"{fmt(g.cited_domains.map(len).mean(), 1)} | {g.answer_text.str.len().mean():.0f} | "
                f"{fmt(g.brands.map(len).mean(), 1)} | {pct(1 - g.searched.mean())} |")
        if platform == "gemini":
            api = frame[frame.arm.isin(api_arms)]
            src = Counter(api.get("domain_source", pd.Series(dtype=str)).fillna("none"))
            no_dom = int(api.get("n_chunks_no_domain", pd.Series(dtype=float)).fillna(0).sum())
            n_chunks = int(api.get("n_chunks", pd.Series(dtype=float)).fillna(0).sum())
            lines += ["", f"Gemini API grounding chunk URIs are redirect links. Domains come from "
                      f"the chunk field named here, per answer: {dict(src)}; {no_dom} of {n_chunks} "
                      "chunks had no usable domain. No redirect was resolved. The Gemini UI scrape "
                      "reports no fan-out queries, so its search depth is not observable; "
                      "\"searched\" there means sources were reported."]
        else:
            lines += ["", "OpenAI: search calls are `web_search_call` items; queries are the queries "
                      "inside search actions. ChatGPT UI: queries are DataForSEO `fan_out_queries`."]

        # ---- G2 / G3
        lines += ["", "### G2 and G3, per arm", "",
                  "| Arm | Buyer-facing answers | Flagged | Searched (API) | Leak-syntax answers | "
                  "Haiku names | Covered by lexicon v3 | Domains parse when searched | G2 | G3 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        passed = []
        for arm in arms:
            g = frame[frame.arm == arm]
            recs = g.to_dict("records")
            flagged = [(r["arm"], r["item_id"], r["round"]) for r in recs
                       if not r["brands"] or question_only(r)
                       or answers.is_error_answer(r["answer_text"])]
            flagged_out += [f"{a} {i} r{n}" for a, i, n in flagged]
            bad = [f for f in flagged if f not in CLEARED_BY_READING]
            answer_rate = 1 - len(bad) / len(recs) if recs else float("nan")
            search_rate = g.searched.mean() if len(g) else float("nan")
            leak_hits = int((g.leak_syntax > 0).sum())
            s = g[g.searched]
            dom_rate = (s.domains.map(len) > 0).mean() if len(s) else float("nan")
            c = cov.get(arm, {"names": 0, "covered": float("nan"), "uncached": len(g)})
            is_api = arm != ui_arm
            g2 = (answer_rate >= G2_ANSWER_MIN
                  and (not is_api or search_rate >= G2_SEARCH_MIN)
                  and (not exp004.ARMS[arm].leak or leak_hits == 0))
            g3 = (c["covered"] == c["covered"] and c["covered"] >= G3_COVERAGE_MIN
                  and c["uncached"] == 0 and dom_rate == dom_rate and dom_rate >= G3_DOMAINS_MIN)
            if is_api and g1[arm] and g2 and g3:
                passed.append(arm)
            lines.append(
                f"| `{arm}` | {pct(answer_rate)} | {len(flagged)} | "
                f"{pct(search_rate) if is_api else 'n/a'} | {leak_hits} | {c['names']} | "
                f"{pct(c['covered']) if c['uncached'] == 0 else 'not run'} | {pct(dom_rate)} | "
                f"{'PASS' if g2 else 'FAIL'} | {'PASS' if g3 else 'FAIL'} |")
        lines += ["", "Flagged = no lexicon brand, a short answer with a question and no brand, or "
                  "the app's error message; listed by id on stdout for a person to read. Cleared by "
                  f"reading: {len([c for c in CLEARED_BY_READING if c[0] in arms])}. Leak syntax: "
                  "tool records, reference ids, web app components or tool JSON "
                  "(`harness/leaks.py`, `TOOL_SYNTAX`); gated on leak arms only. Covered: a Haiku "
                  "name counts when a lexicon alias of the prompt's category matches inside it."]

        # ---- G4
        lines += ["", "### G4, brand gap against the UI", "",
                  "Gap = UI against itself across the 3 rounds, minus the arm against the UI. "
                  "Positive means further from the UI than the UI is from itself. 90% interval, "
                  "prompt-level bootstrap. A screen, not a test.", "",
                  "| Arm | Brand gap [90% CI] | Mean overlap with UI | Prompts | Passed G1 to G3 |",
                  "|---|---|---|---|---|"]
        gaps = {}
        floor = None
        for arm in api_arms:
            res, data = brand_gap(frame, arm, ui_arm)
            if floor is None and (data.condition == "within").any():
                floor = data[data.condition == "within"].value.mean()
            level = data[data.condition == "cross"].value.mean() if len(data) else float("nan")
            n_prompts = data[data.condition == "cross"].cluster_i.nunique() if len(data) else 0
            gaps[arm] = res.estimate if res else None
            ci = f"{fmt(res.estimate, signed=True)} [{fmt(res.lo, signed=True)}, " \
                 f"{fmt(res.hi, signed=True)}]" if res else "n/a"
            lines.append(f"| `{arm}` | {ci} | {fmt(level)} | {n_prompts} | "
                         f"{'yes' if arm in passed else 'no'} |")
        lines += ["", f"UI against itself on these prompts: {fmt(floor)}. For scale, 009's "
                  "confirmatory gap (Opus 5.5 API vs claude.ai) was +0.067.", ""]
        screen = {a: gaps[a] for a in passed if gaps.get(a) is not None and gaps[a] <= G4_GAP_MAX}
        g4 = bool(screen)
        lines.append(f"**G4 {'PASS' if g4 else 'FAIL'}:** arms that passed G1 to G3 with a gap of at "
                     f"most {G4_GAP_MAX}: {sorted(screen) or 'none'}.")
        pick = select_arm(screen)
        if screen:
            best = min(screen, key=screen.get)
            others = sorted((a for a in screen if a != pick), key=screen.get)
            lines.append(f"**Selection rule:** first arm `{pick}` (smallest gap "
                         f"{fmt(screen[best], signed=True)} by `{best}`; a plain arm is preferred "
                         f"within {PLAIN_PREFERENCE}). Other arms that passed G4, by gap: "
                         f"{others or 'none'} (at most one more joins the spec).")
        verdicts[platform] = {"g1": g1, "passed_g1_g3": passed, "gaps": gaps, "g4": g4, "pick": pick}
        lines.append("")

    # ---- cost
    lines += ["## Cost (reported, not gated)", "",
              "| Arm | Answers | Estimated cost | Per answer | Full study, 120 answers |",
              "|---|---|---|---|---|"]
    per_answer = {}
    for arm in exp004.ARMS:
        t = tallies.get(arm, Counter())
        n = int((frame.arm == arm).sum())
        total = float(t.get("cost", 0.0))
        per_answer[arm] = total / n if n else float("nan")
        lines.append(f"| `{arm}` | {n} | ${total:.4f} | ${fmt(per_answer[arm], 4)} | "
                     f"${fmt(per_answer[arm] * FULL_PROMPTS * FULL_WAVES, 2)} |")
    full = FULL_PROMPTS * FULL_WAVES
    proj_hi = 0.0
    for platform, arms in PLATFORM_ARMS.items():
        ui_cost = per_answer[arms[0]] if per_answer[arms[0]] == per_answer[arms[0]] else 0.0
        api_costs = sorted((per_answer[a] for a in arms[1:] if per_answer[a] == per_answer[a]),
                           reverse=True)
        proj_hi += full * (ui_cost + sum(api_costs[:FULL_API_ARMS]))
    lines += ["", f"Projected full study ({FULL_PROMPTS} prompts x {FULL_WAVES} waves, the UI arm "
              f"and {FULL_API_ARMS} API arms per platform), taking the {FULL_API_ARMS} most "
              f"expensive API arms per platform: about ${proj_hi:.2f}, plus the Haiku pass. UI "
              "per-answer cost includes resubmitted tasks. Haiku pass so far: "
              f"${haiku_spend():.4f}.", ""]

    lines += ["## Verdicts", "", "| Platform | G1 | G2 and G3 (arms passing G1 to G3) | G4 | Pick |",
              "|---|---|---|---|---|"]
    for platform, v in verdicts.items():
        g1_all = "PASS" if all(v["g1"].values()) else "FAIL: " + ", ".join(
            f"`{a}`" for a, ok in v["g1"].items() if not ok)
        lines.append(f"| {PLATFORM_NAME[platform]} | {g1_all} | {', '.join(f'`{a}`' for a in v['passed_g1_g3']) or 'none'}"
                     f" | {'PASS' if v['g4'] else 'FAIL'} | {('`' + v['pick'] + '`') if v['pick'] else 'none'} |")
    lines += ["", "STOP: Jim Wrubel's go/no-go before anything else starts (sketch, STOP)."]
    return "\n".join(lines) + "\n", flagged_out


def haiku_spend() -> float:
    path = exp004.RAW / "brand_candidates.jsonl"
    if not path.exists():
        return 0.0
    return sum(float(json.loads(x).get("cost_usd") or 0) for x in path.read_text().splitlines()
               if x.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default="", help='"smoke_" scores the smoke ledgers')
    ap.add_argument("--no-haiku", action="store_true", help="skip uncached Haiku calls")
    a = ap.parse_args()
    frame, tallies = load_frame(a.prefix)
    cache = haiku_names(frame, run=not a.no_haiku)
    items = frame.item_id.nunique()
    rounds = int(frame[frame.arm.str.endswith("_ui")]["round"].nunique())
    text, flagged = build_report(frame, tallies, cache, items, rounds)
    out = (exp004.RESULTS / "pilot_report.md") if not a.prefix else (
        exp004.RAW / f"{a.prefix}pilot_report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    print(f"wrote {out}")
    print("G2 flagged answers for a person to read (arm item round), not in the report:")
    for f in flagged:
        print(f"  {f}")
    print(f"Lexicon v3 sha256 verified: {exp004.LEXICON_V3_SHA256[:12]}")


if __name__ == "__main__":
    main()
