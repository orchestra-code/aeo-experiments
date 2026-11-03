"""Score the feasibility run against the criteria in ``sketch.md`` (G1 to G5).

Aggregates only: the report names no brands and quotes no answer. Writes
``results/pilot_report.md`` and prints it. The Haiku brand pass (G3) is cached
in the gitignored ``data/raw/brand_candidates.jsonl``, so a rerun costs nothing.

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/pipeline/pilot_report.py
"""

from __future__ import annotations

import concurrent.futures as cf
import csv
import hashlib
import importlib.util
import json
import re
import statistics as st
import sys
from pathlib import Path

import pandas as pd

from aeo_research.overlap import cluster_boot, jaccard, rbo

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
RAW = EXP / "data" / "raw"
EXP009 = EXP.parent / "009-claude-model-fidelity"
sys.path.insert(0, str(EXP009 / "harness"))
ENV_FILE = str(ROOT / ".env.local")

LEXICON = EXP.parent / "010-shortlist-stability" / "data" / "raw" / "lexicon_v3" / "lexicon_v3.csv"
LEXICON_SHA256 = "6084f47ca1831474de9cb64d79425d522b75ac409d2b5080b24653ec9905cf5d"
CC_ARMS = ("cc_stock_full", "cc_stock_search", "cc_none_full", "cc_none_search")
ANCHOR = "opus55_plain"
#: One scheduled task, one fresh subagent per prompt, told to use web search. Directional only.
SCHEDULED = "sched_kit"
UI_WAVES = (1, 2, 3)
WAVE = 0
SEED = 20261103
N_BOOT = 2000
G1_MIN_RUNS = 38
G2_ANSWER_MIN = 0.90
G2_SEARCH_MIN = 0.70
G3_COVERAGE_MIN = 0.90
G3_LINKS_MIN = 0.80
G4_ANCHOR_MAX = 0.15
G5_GAP_MAX = 0.20
OFFER_RE = re.compile(
    r"(?i)\b(?:i can|i could|want me to|would you like me to|shall i|let me)\b[^.?!\n]{0,60}"
    r"\b(?:file|script|code|repo|repository|commit|directory)\b"
)
BUILD_RE = re.compile(r"(?i)\b(?:i (?:wrote|created|saved|edited)|your (?:codebase|repository))\b")
#: Flags read by a person and cleared: both offer to "draft a demo script" for a
#: vendor call, which is advice to a buyer, not coding behavior.
CLEARED_BY_READING = {("cc_none_full", "b2b_09"), ("cc_none_search", "b2b_09")}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


brands = _load("exp009_brands", EXP009 / "pipeline" / "brands.py")
common = _load("exp009_common", EXP009 / "pipeline" / "common.py")


def load_answers() -> tuple[pd.DataFrame, dict[str, str]]:
    with (EXP009 / "data" / "raw" / "prompts.csv").open(newline="") as handle:
        categories = {row["item_id"]: row["category"] for row in csv.DictReader(handle)}
    rows = []

    def add(path: Path, arm: str, item: str, wave: int) -> None:
        record = json.loads(path.read_text())
        rows.append({"arm": arm, "item_id": item, "wave": wave, **record["normalized"]})

    arm_items = sorted((RAW / "responses" / f"w{WAVE}" / CC_ARMS[0]).glob("*.json"))
    items = [p.stem for p in arm_items]
    for arm in (*CC_ARMS, ANCHOR, SCHEDULED):
        for item in items:
            path = RAW / "responses" / f"w{WAVE}" / arm / f"{item}.json"
            if path.exists():
                add(path, arm, item, WAVE)
    for wave in UI_WAVES:
        for item in items:
            add(EXP009 / "data" / "raw" / "responses" / f"w{wave}" / "ui_default" / f"{item}.json",
                "ui_default", item, wave)
    frame = pd.DataFrame(rows)
    frame["category"] = frame["item_id"].map(categories)
    return frame, categories


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    patterns, _aliases, _sha = brands.frozen_lexicon(LEXICON, LEXICON_SHA256)
    frame["brands"] = [
        brands.lexicon_extract(row.answer_text, patterns.get(row.category, []))
        for row in frame.itertuples()
    ]
    frame["cited_domains"] = [common.domains(u) for u in frame["cited_urls"]]
    frame["evaluated_domains"] = [common.domains(u) for u in frame["evaluated_urls"]]
    return frame


def _value(metric: str, a: pd.Series, b: pd.Series) -> float:
    if metric == "brand":
        return jaccard(set(a["brands"]), set(b["brands"]))
    if metric == "brand_all":
        return jaccard(set(a["brands_all"]), set(b["brands_all"]))
    if metric == "order":
        return rbo(a["brands"], b["brands"], p=0.9)
    return jaccard(a[metric], b[metric])


def pairs(frame: pd.DataFrame, arm: str, metric: str) -> pd.DataFrame:
    """within:ui (3 per prompt) and cross:arm|ui (3 per prompt), see the sketch."""
    out = []
    ui = frame[frame.arm == "ui_default"]
    answers = frame[frame.arm == arm]
    for item, group in ui.groupby("item_id"):
        records = list(group.to_dict("records"))
        for i, left in enumerate(records):
            for right in records[i + 1:]:
                out.append(("within", item, _value(metric, left, right)))
        for answer in answers[answers.item_id == item].to_dict("records"):
            for right in records:
                out.append(("cross", item, _value(metric, answer, right)))
    data = pd.DataFrame(out, columns=["condition", "cluster_i", "value"])
    data["cluster_j"] = data["cluster_i"]
    return data


def gap(frame: pd.DataFrame, arm: str, metric: str = "brand"):
    return cluster_boot(pairs(frame, arm, metric), contrast=("within", "cross"), n_boot=N_BOOT,
                        seed=SEED)


def same_day_overlap(frame: pd.DataFrame, arm: str, other: str = ANCHOR) -> float:
    left = frame[frame.arm == arm].set_index("item_id")
    right = frame[frame.arm == other].set_index("item_id")
    shared = left.index.intersection(right.index)
    return st.mean(jaccard(set(left.at[i, "brands"]), set(right.at[i, "brands"])) for i in shared)


def _key(category: str, text: str) -> str:
    return hashlib.sha256(f"{category}\n{text}".encode()).hexdigest()


def haiku_names(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Haiku brand names per answer: 009's cache for claude.ai, ours for the rest."""
    import pilot_report as harness_report  # 009's Haiku extractor, same prompt and schema
    from anthropic_client import make_client

    cache_path = RAW / "brand_candidates.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            row = json.loads(line)
            cache[row["key"]] = row["names"]

    stored = {}
    for line in (EXP009 / "data" / "raw" / "brand_candidates.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["arm"] == "ui_default":
            stored[(row["item_id"], row["wave"])] = row["brands"]
    for row in frame[frame.arm == "ui_default"].itertuples():
        cache[_key(row.category, row.answer_text)] = stored.get((row.item_id, row.wave), [])

    subset = frame[frame.arm.isin((*CC_ARMS, ANCHOR, SCHEDULED))]
    todo = [
        (_key(r.category, r.answer_text), r.answer_text, r.category)
        for r in subset.itertuples()
        if _key(r.category, r.answer_text) not in cache and r.answer_text
    ]
    if todo:
        client = make_client(ENV_FILE)

        def call(job):
            key, text, category = job
            names, _usage = harness_report.extract_brands(client, text, category)
            return key, names

        with cf.ThreadPoolExecutor(max_workers=8) as pool, cache_path.open("a") as out:
            for key, names in pool.map(call, todo):
                cache[key] = names
                out.write(json.dumps({"key": key, "names": names}) + "\n")
    return cache


def coverage_and_residuals(frame: pd.DataFrame) -> tuple[dict[str, dict], pd.DataFrame]:
    """Coverage of Haiku names, two ways, and each answer's names the lexicon cannot place.

    strict: the name is exactly an alias (the first scoring, which failed G3).
    resolved: the lexicon's own matcher finds an alias inside the name, as it would in
    the answer text, so a plan tier of a known vendor counts. See the sketch's
    deviation 1. The residual names feed the sensitivity gap, which needs neither rule.
    """
    cache = haiku_names(frame)
    patterns, alias_map, _sha = brands.frozen_lexicon(LEXICON, LEXICON_SHA256)
    tally: dict[str, list[int]] = {}
    residuals = []
    for row in frame.itertuples():
        counts = tally.setdefault(row.arm, [0, 0, 0])
        left = set()
        for name in cache.get(_key(row.category, row.answer_text), []):
            clean = name.strip()
            counts[0] += 1
            counts[1] += (row.category, clean.lower()) in alias_map
            if any(p.search(clean) for p, _c, _k in patterns.get(row.category, [])):
                counts[2] += 1
            else:
                left.add(clean.lower())
        residuals.append(left)
    frame = frame.assign(residual=residuals)
    frame["brands_all"] = [
        list(dict.fromkeys([*b, *sorted(r)])) for b, r in zip(frame["brands"], frame["residual"], strict=True)
    ]
    coverage = {
        arm: {"names": n, "strict": s / n if n else float("nan"), "resolved": r / n if n else float("nan")}
        for arm, (n, s, r) in tally.items()
    }
    return coverage, frame


def ledger_rows() -> pd.DataFrame:
    rows = [json.loads(x) for x in (RAW / "ledger_cc.jsonl").read_text().splitlines() if x]
    data = pd.DataFrame(rows)
    return data[data.wave == WAVE].sort_values("started")


def usage_table(ledger: pd.DataFrame) -> list[str]:
    out = []
    for arm in CC_ARMS:
        runs = ledger[(ledger.arm == arm) & (ledger.status == "ok")]
        marks = [r for r in runs["rate_limits"] if r]
        if not marks:
            continue
        five = marks[-1]["last"]["five_hour"] - marks[0]["first"]["five_hour"]
        seven = marks[-1]["last"]["seven_day"] - marks[0]["first"]["seven_day"]
        out.append(
            f"| `{arm}` | {len(runs)} | {five:+.2f} | {seven:+.2f} | "
            f"${runs['total_cost_usd'].mean():.2f} | {runs['duration_ms'].mean() / 1000:.0f} s |"
        )
    return out


def main() -> None:
    frame, _ = load_answers()
    frame = add_features(frame)
    ledger = ledger_rows()
    coverage, frame = coverage_and_residuals(frame)

    ok = int((ledger.drop_duplicates(["arm", "item_id"], keep="last").status == "ok").sum())
    lines = [
        "# Experiment 011: feasibility report",
        "",
        "Scored against `sketch.md`. Pilot data, never part of a confirmatory analysis. "
        "Aggregates only. The claude.ai reference is 009's stored `ui_default` waves 1 to 3.",
        "",
        "## G1, clean instrument",
        f"{ok} of {len(CC_ARMS) * frame.item_id.nunique()} runs finished and passed the `init` "
        f"audit; need at least {G1_MIN_RUNS}. **{'PASS' if ok >= G1_MIN_RUNS else 'FAIL'}**",
        "",
    ]
    failed = ledger[ledger.status != "ok"]
    if len(failed):
        lines += [f"- failed attempt: {r.arm} {r.item_id}: {r.problems}" for r in failed.itertuples()]
        lines.append("")

    lines += [
        "## Behavior per answer",
        "| Arm | n | Searches | Fetches | Backend searches | Evaluated URLs | Links in answer "
        "| Chars | Brands | No search |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ("ui_default", ANCHOR, *CC_ARMS):
        group = frame[frame.arm == arm]
        if group.empty:
            continue
        backend = group["n_backend_searches"].mean() if "n_backend_searches" in group else None
        fetches = group["n_fetches"].fillna(0).mean() if "n_fetches" in group else 0.0
        lines.append(
            f"| `{arm}` | {len(group)} | {group.n_searches.mean():.1f} | {fetches:.1f} | "
            f"{backend if backend == backend and backend is not None else float('nan'):.1f} | "
            f"{group.evaluated_urls.map(len).mean():.1f} | {group.cited_urls.map(len).mean():.1f} | "
            f"{group.answer_text.str.len().mean():.0f} | {group.brands.map(len).mean():.1f} | "
            f"{(group.n_searches == 0).mean():.0%} |"
        )

    lines += ["", "## G2 and G3, per arm",
              "| Arm | Answers, not questions or coding offers | Searched | Coverage, exact alias "
              "| Coverage, resolved | Links when searched | G2 | G3 |",
              "|---|---|---|---|---|---|---|---|"]
    passed_g123 = []
    flagged = []
    for arm in CC_ARMS:
        group = frame[frame.arm == arm]
        bad = group[
            (group.brands.map(len) == 0)
            | group.answer_text.str.contains(OFFER_RE)
            | group.answer_text.str.contains(BUILD_RE)
        ]
        flagged += [(arm, i) for i in bad.item_id]
        bad = bad[[(arm, i) not in CLEARED_BY_READING for i in bad.item_id]]
        answer_rate = 1 - len(bad) / len(group)
        searched = group[group.n_searches > 0]
        search_rate = len(searched) / len(group)
        links = (searched.cited_urls.map(len) > 0).mean() if len(searched) else 0.0
        g2 = answer_rate >= G2_ANSWER_MIN and search_rate >= G2_SEARCH_MIN
        g3 = coverage[arm]["resolved"] >= G3_COVERAGE_MIN and links >= G3_LINKS_MIN
        if g2 and g3 and ok >= G1_MIN_RUNS:
            passed_g123.append(arm)
        lines.append(
            f"| `{arm}` | {answer_rate:.0%} | {search_rate:.0%} | {coverage[arm]['strict']:.1%} | "
            f"{coverage[arm]['resolved']:.1%} | {links:.0%} | {'PASS' if g2 else 'FAIL'} | "
            f"{'PASS' if g3 else 'FAIL'} |"
        )
    lines += ["",
              f"Answers flagged by the pattern check: {flagged or 'none'}. Read by a person; cleared: "
              f"{sorted(CLEARED_BY_READING) or 'none'} (an offer to draft a demo script for a vendor "
              "call, not coding behavior).", "",
              "G3 uses resolved coverage (sketch, deviation 1). As first scored, on exact aliases, "
              "every arm failed. The sensitivity gap below does not depend on either rule.", "",
              "Coverage on the same lexicon, for comparison: "
              + "; ".join(f"`{a}` exact {coverage[a]['strict']:.1%}, resolved {coverage[a]['resolved']:.1%}"
                          for a in ("ui_default", ANCHOR) if a in coverage) + ".", ""]

    lines += ["## G4 and G5, brand gap against claude.ai",
              "Gap = claude.ai against itself across waves, minus the arm against claude.ai. "
              "Positive means further from claude.ai than claude.ai is from itself. 10 prompts, "
              "90% interval, prompt-level bootstrap. A screen, not a test.", "",
              "| Arm | Brand gap | Mean overlap with claude.ai | Same-day overlap with the API anchor |",
              "|---|---|---|---|"]
    results = {}
    if (frame.arm == ANCHOR).any():
        result = gap(frame, ANCHOR)
        results[ANCHOR] = result
        level = pairs(frame, ANCHOR, "brand").query("condition == 'cross'").value.mean()
        lines.append(f"| `{ANCHOR}` | {result.estimate:+.3f} [{result.lo:+.3f}, {result.hi:+.3f}] "
                     f"| {level:.3f} | n/a |")
    else:
        lines.append(f"| `{ANCHOR}` | batch not collected | | |")
    for arm in CC_ARMS:
        result = gap(frame, arm)
        results[arm] = result
        level = pairs(frame, arm, "brand").query("condition == 'cross'").value.mean()
        same_day = f"{same_day_overlap(frame, arm):.3f}" if ANCHOR in results else "n/a"
        lines.append(f"| `{arm}` | {result.estimate:+.3f} [{result.lo:+.3f}, {result.hi:+.3f}] | "
                     f"{level:.3f} | {same_day} |")
    floor = pairs(frame, CC_ARMS[0], "brand").query("condition == 'within'").value.mean()
    lines += ["", f"claude.ai against itself on these 10 prompts: {floor:.3f}.", ""]

    if ANCHOR in results:
        anchor_gap = results[ANCHOR].estimate
        g4 = anchor_gap <= G4_ANCHOR_MAX
        lines.append(f"**G4 {'PASS' if g4 else 'FAIL'}:** anchor gap {anchor_gap:+.3f}, limit "
                     f"{G4_ANCHOR_MAX}. For scale, 009's confirmatory gap was +0.067.")
    else:
        lines.append("**G4 not scored:** the anchor batch has not landed.")
    screen = [a for a in passed_g123 if results[a].estimate <= G5_GAP_MAX]
    if passed_g123:
        lines.append(f"**G5 {'PASS' if screen else 'FAIL'}:** arms that passed G1 to G3 with a gap of "
                     f"at most {G5_GAP_MAX}: {screen or 'none'}.")
    else:
        lines.append("**G5 not scored:** no arm passed G1 to G3.")

    lines += ["", "## Sensitivity: nothing censored",
              "The same gap, with every Haiku name the lexicon cannot place added to the answer's "
              "brand set, on both sides, claude.ai included. These names are not curated: some are "
              "not brands, and spelling variants count as different names, so the level is lower. "
              "It shows how much the lexicon's blind spots move the gap.", "",
              "| Arm | Gap, lexicon | Gap, nothing censored | Unplaced names per answer |",
              "|---|---|---|---|"]
    for arm in ((ANCHOR,) if ANCHOR in results else ()) + CC_ARMS:
        result = gap(frame, arm, "brand_all")
        group = frame[frame.arm == arm]
        lines.append(f"| `{arm}` | {results[arm].estimate:+.3f} | {result.estimate:+.3f} "
                     f"[{result.lo:+.3f}, {result.hi:+.3f}] | {group.residual.map(len).mean():.1f} |")
    lines.append(f"| `ui_default` | | | {frame[frame.arm == 'ui_default'].residual.map(len).mean():.1f} |")

    if (frame.arm == SCHEDULED).any():
        result = gap(frame, SCHEDULED)
        censored = gap(frame, SCHEDULED, "brand_all")
        group = frame[frame.arm == SCHEDULED]
        level = pairs(frame, SCHEDULED, "brand").query("condition == 'cross'").value.mean()
        local_pairs = [same_day_overlap(frame, a, b) for i, a in enumerate(CC_ARMS) for b in CC_ARMS[i + 1:]]
        lines += ["", "## Scheduled task (directional only)",
                  "One scheduled task in Claude Code's cloud, a fresh subagent per prompt, each told to "
                  "use web search. The arm was designed after the feasibility criteria and is not "
                  "covered by them. The wording around the prompt differs from the local arms, and the "
                  "effort level could not be set or confirmed. 10 prompts, one run.", "",
                  f"- Brand gap to claude.ai: {result.estimate:+.3f} [{result.lo:+.3f}, {result.hi:+.3f}]; "
                  f"nothing censored {censored.estimate:+.3f} [{censored.lo:+.3f}, {censored.hi:+.3f}].",
                  f"- Mean brand overlap with claude.ai: {level:.3f}.",
                  f"- Overlap with local `cc_stock_full`, same prompt: "
                  f"{same_day_overlap(frame, SCHEDULED, 'cc_stock_full'):.3f}; with `cc_none_search`: "
                  f"{same_day_overlap(frame, SCHEDULED, 'cc_none_search'):.3f}; with the API anchor: "
                  f"{same_day_overlap(frame, SCHEDULED):.3f}.",
                  f"- For scale, the local arms overlap each other at {min(local_pairs):.3f} to "
                  f"{max(local_pairs):.3f}.",
                  f"- Per answer: {group.answer_text.str.len().mean():.0f} characters, "
                  f"{group.brands.map(len).mean():.1f} brands, {group.cited_urls.map(len).mean():.1f} links. "
                  f"Coverage: exact {coverage[SCHEDULED]['strict']:.1%}, resolved "
                  f"{coverage[SCHEDULED]['resolved']:.1%}.",
                  "- With one prompt pasted in unchanged and no subagent, the only such run did no web "
                  "search and answered from memory (n = 1, not scored)."]

    lines += ["", "## Other measures (descriptive; links are not 009's citation objects)",
              "| Arm | Cited-domain gap | Evaluated-domain gap | Brand-order gap |", "|---|---|---|---|"]
    for arm in ((ANCHOR,) if ANCHOR in results else ()) + CC_ARMS:
        cells = [gap(frame, arm, m) for m in ("cited_domains", "evaluated_domains", "order")]
        lines.append(f"| `{arm}` | " + " | ".join(
            f"{c.estimate:+.3f} [{c.lo:+.3f}, {c.hi:+.3f}]" for c in cells) + " |")

    lines += ["", "## Usage on this account (reported, not gated)",
              "Change in window utilization across each arm's 10 answers. The value rounds to 1% and "
              "other work on the account moves it. Cost is Claude Code's client-side estimate, used "
              "only to compare arms.", "",
              "| Arm | Runs | Five-hour change | Seven-day change | Estimated cost per answer | "
              "Time per answer |", "|---|---|---|---|---|---|"]
    lines += usage_table(ledger)
    ordered = ledger.sort_values("started")
    marks = [r for r in ordered["rate_limits"] if r]
    first, last = marks[0]["first"], marks[-1]["last"]
    lines += ["", f"Across all {len(ordered)} answers: five-hour {first['five_hour']:.0%} to "
              f"{last['five_hour']:.0%}, seven-day {first['seven_day']:.0%} to {last['seven_day']:.0%}. "
              "Other work on the account ran at the same time and the values round to 1%, so read "
              "these as rough. One plan, and its tier is not recorded in the stream."]

    text = "\n".join(lines) + "\n"
    (EXP / "results" / "pilot_report.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
