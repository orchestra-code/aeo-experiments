"""Experiment 010, initial evaluation (EXPLORATORY; sketch.md, exploration split).

Reads the judge output for the exploration split and reports, per dataset:

- instrument checks (G1): judge success, evidence verification, unclassified
  lexicon brands, how often a judge name had to be mapped back to a lexicon
  brand, raw top choices removed by the two-top-choice cap;
- answer shape (G2, G3): category mix over lexicon brand mentions, answers
  with a top choice, answers where the recommended set differs from the
  mentioned set;
- retention (G4): for each status, the share of brand appearances with that
  status in one run that keep it in another run of the same prompt (pooled
  Dice), within prompt and between prompts of the same category on the same
  day, with prompt-level cluster bootstrap 90% intervals;
- brand-level consistency, retention by days between runs (consumer
  ChatGPT), and claude.ai vs Opus API agreement (Claude B2B).

Brand identity is the source study's frozen lexicon (sketch.md, Instrument).
Writes results/exploration.md (aggregates only, no brand names) and
data/interim/answers.jsonl (per-answer statuses, gitignored).

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/10_explore.py
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parents[1]
EXPERIMENTS = EXP.parent
RAW = EXP / "data" / "raw"
INTERIM = EXP / "data" / "interim"
RESULTS = EXP / "results"

SEED = 20261003
N_BOOT = 2000
ALPHA = 0.10
SESOI = 0.10

#: gpt-5.6-luna list price, USD per million tokens (third-party price tracker,
#: 2026-10-03; not reconciled with OpenAI billing).
LUNA_IN, LUNA_OUT = 0.20, 1.20

CATS = ("top_choice", "one_of_many", "generic_mention", "cautioned_against")
MERGE_RANK = {"cautioned_against": 4, "top_choice": 3, "one_of_many": 2, "generic_mention": 1}
STATUSES = ("M", "R", "T", "BF", "C", "P1", "Pk", "Rpos")
#: Robustness: every brand the judge names (lexicon brands plus untracked names,
#: keyed by a normalized spelling), ordered by the judge's first appearance.
STATUSES_ALL = ("M_all", "R_all", "T_all", "P1_all", "Pk_all")
STATUS_LABELS = {
    "M": "Mentioned (any way)",
    "R": "Recommended (top choice or one of many)",
    "T": "Top choice",
    "BF": "Best-for pick (one of many with a best-for phrase)",
    "C": "Cautioned against",
    "P1": "First-mentioned brand (rank 1)",
    "Pk": "Exact position (brand at rank k)",
    "Rpos": "Position-only shortlist (first |R| brands)",
}
DATASETS = ("chatgpt_consumer", "chatgpt_agency", "claude_b2b")
CLAUDE_PRIMARY_ARM = "ui_default"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ load


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def lexicon_mappers():
    """Map a free-text judge name to lexicon canonicals, per dataset."""
    b5 = _load(EXPERIMENTS / "005-subintent-matched-panels/pipeline/brands.py", "x005_brands")
    sys.path.insert(0, str(EXPERIMENTS / "009-claude-model-fidelity/pipeline"))
    b9 = _load(EXPERIMENTS / "009-claude-model-fidelity/pipeline/brands.py", "x009_brands")
    patterns, _, _ = b9.frozen_lexicon()

    def mapper(task: dict, name: str) -> list[str]:
        if task["dataset"] == "claude_b2b":
            return b9.lexicon_extract(name, patterns.get(task["category"], []))
        return b5.extract_brands(name, task["category"])

    return mapper


def build_answers(split: str = "explore") -> tuple[list[dict], dict]:
    tasks = {t["task_id"]: t for t in read_jsonl(RAW / f"tasks_{split}.jsonl")}
    judged: dict[str, dict] = {}
    for r in read_jsonl(RAW / f"judged_{split}.jsonl"):
        if r.get("ok") or r["task_id"] not in judged:
            judged[r["task_id"]] = r
    mapper = lexicon_mappers()
    diag = Counter()
    usage = Counter()
    answers = []
    for tid, t in tasks.items():
        r = judged.get(tid)
        diag["tasks"] += 1
        if not r or not r.get("ok"):
            diag["judge_failed"] += 1
            continue
        for k in ("inputTokens", "outputTokens", "cachedInputTokens"):
            usage[k] += (r.get("usage") or {}).get(k) or 0
        order = t["brands"]
        present = set(order)
        cat: dict[str, str] = {}
        best_for: dict[str, list[str]] = {}
        verified: dict[str, bool] = {}
        untracked = 0
        all_cat: dict[str, str] = {}
        for b in r["brands"]:
            canon = b.get("canonical")
            diag["judge_brands"] += 1
            diag["evidence_verified"] += bool(b.get("evidenceVerified"))
            if not canon:
                hits = [h for h in mapper(t, b["name"]) if h in present]
                if len(set(hits)) == 1:
                    canon = hits[0]
                    diag["fallback_mapped"] += 1
                else:
                    untracked += 1
                    key = "x:" + re.sub(r"[^a-z0-9]+", "", b["name"].lower())
                    prev = all_cat.get(key)
                    if prev is None or MERGE_RANK[b["category"]] > MERGE_RANK[prev]:
                        all_cat[key] = b["category"]
                    continue
            prev = all_cat.get(canon)
            if prev is None or MERGE_RANK[b["category"]] > MERGE_RANK[prev]:
                all_cat[canon] = b["category"]
            prev = cat.get(canon)
            if prev is None or MERGE_RANK[b["category"]] > MERGE_RANK[prev]:
                cat[canon] = b["category"]
            best_for.setdefault(canon, []).extend(b.get("bestFor") or [])
            verified[canon] = verified.get(canon, False) or bool(b.get("evidenceVerified"))
        # Raw top choices (before the cap), mapped the same way.
        raw_top = set()
        for b in (r.get("raw") or {}).get("brands") or []:
            if str(b.get("category", "")).strip().lower().replace(" ", "_") == "top_choice":
                hits = [h for h in mapper(t, str(b.get("name", ""))) if h in present]
                raw_top.update(hits[:1])
        n_raw_top_items = sum(
            1 for b in (r.get("raw") or {}).get("brands") or []
            if str(b.get("category", "")).strip().lower().replace(" ", "_") == "top_choice")
        cats = {b: cat.get(b, "unclassified") for b in order}
        R = [b for b in order if cats[b] in ("top_choice", "one_of_many")]
        for b in order:
            all_cat.setdefault(b, "unclassified")
        all_order = list(all_cat)
        a = {
            "task_id": tid, "dataset": t["dataset"], "source_exp": t["source_exp"],
            "arm": t["arm"], "item_id": t["item_id"], "category": t["category"],
            "wave": t["wave"], "run_date": t["run_date"],
            "order": order, "cats": cats,
            "best_for": {b: best_for.get(b, []) for b in order},
            "M": set(order),
            "R": set(R),
            "T": {b for b in order if cats[b] == "top_choice"},
            "BF": {b for b in order if cats[b] == "one_of_many" and best_for.get(b)},
            "C": {b for b in order if cats[b] == "cautioned_against"},
            "G": {b for b in order if cats[b] == "generic_mention"},
            "P1": set(order[:1]),
            "Pk": {(b, i) for i, b in enumerate(order)},
            "Rpos": set(order[:len(R)]),
            "M_all": set(all_order),
            "R_all": {b for b in all_order if all_cat[b] in ("top_choice", "one_of_many")},
            "T_all": {b for b in all_order if all_cat[b] == "top_choice"},
            "P1_all": set(all_order[:1]),
            "Pk_all": {(b, i) for i, b in enumerate(all_order)},
            "raw_top": raw_top, "n_raw_top_items": n_raw_top_items,
            "untracked_names": untracked,
            "verified_lex": sum(verified.get(b, False) for b in order if b in cat),
        }
        answers.append(a)
    diag["usage"] = dict(usage)
    return answers, diag


# ------------------------------------------------------------------ pairs


def panel_key(a: dict, pooled_claude: bool = False):
    if a["dataset"] == "claude_b2b" and not pooled_claude:
        return (a["item_id"], a["arm"])
    return (a["item_id"],)


def within_pairs(ans: list[dict], pooled_claude: bool = False):
    groups = defaultdict(list)
    for a in ans:
        groups[panel_key(a, pooled_claude)].append(a)
    for g in groups.values():
        yield from itertools.combinations(g, 2)


def between_pairs(ans: list[dict]):
    groups = defaultdict(list)
    for a in ans:
        groups[(a["source_exp"], a["arm"], a["wave"], a["category"])].append(a)
    for g in groups.values():
        for x, y in itertools.combinations(g, 2):
            if x["item_id"] != y["item_id"]:
                yield x, y


def pair_table(pairs, items: list[str]):
    idx = {it: i for i, it in enumerate(items)}
    rows = {s: [] for s in STATUSES + STATUSES_ALL}
    extra = defaultdict(list)
    ca, cb, lag = [], [], []
    for x, y in pairs:
        ca.append(idx[x["item_id"]])
        cb.append(idx[y["item_id"]])
        lag.append(abs((date.fromisoformat(x["run_date"]) - date.fromisoformat(y["run_date"])).days))
        for s in STATUSES + STATUSES_ALL:
            sa, sb = x[s], y[s]
            rows[s].append((2 * len(sa & sb), len(sa) + len(sb), len(sa | sb)))
        # directional, both ways: top pick stays at least recommended
        extra["T_to_R"].append((len(x["T"] & y["R"]) + len(y["T"] & x["R"]),
                                len(x["T"]) + len(y["T"])))
        extra["P1_to_M"].append((len(x["P1"] & y["M"]) + len(y["P1"] & x["M"]),
                                 len(x["P1"]) + len(y["P1"])))
        extra["P1_to_R"].append((len(x["P1"] & y["R"]) + len(y["P1"] & x["R"]),
                                 len(x["P1"]) + len(y["P1"])))
        extra["R_to_M"].append((len(x["R"] & y["M"]) + len(y["R"] & x["M"]),
                                len(x["R"]) + len(y["R"])))
        # best-for phrase overlap for brands that are best-for picks in both runs
        for b in x["BF"] & y["BF"]:
            extra["bf_phrase_j"].append(phrase_jaccard(x["best_for"][b], y["best_for"][b]))
    arr = {s: np.array(v, dtype=float).reshape(-1, 3) for s, v in rows.items()}
    ext = {k: np.array(v, dtype=float) for k, v in extra.items()}
    return arr, ext, np.array(ca, dtype=int), np.array(cb, dtype=int), np.array(lag)


_STOP = set("a an the for and or of to with who in on at by your you is are best".split())


def phrase_tokens(phrases: list[str]) -> set[str]:
    toks = set()
    for p in phrases:
        toks.update(w for w in re.findall(r"[a-z0-9]+", p.lower()) if w not in _STOP)
    return toks


def phrase_jaccard(a: list[str], b: list[str]) -> float:
    ta, tb = phrase_tokens(a), phrase_tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else np.nan


# ------------------------------------------------------------------ stats


def boot_weights(n_items: int, rng: np.random.Generator) -> np.ndarray:
    return rng.multinomial(n_items, np.full(n_items, 1 / n_items), size=N_BOOT).astype(float)


def pooled(num: np.ndarray, den: np.ndarray, w: np.ndarray | None = None) -> float:
    if w is None:
        d = den.sum()
        return num.sum() / d if d else np.nan
    d = (w * den).sum()
    return (w * num).sum() / d if d else np.nan


def boot_stat(num, den, ca, cb, within: bool, W: np.ndarray):
    """Pooled ratio under each bootstrap weight row (item multiplicities)."""
    pw = W[:, ca] if within else W[:, ca] * W[:, cb]
    d = pw @ den
    with np.errstate(invalid="ignore", divide="ignore"):
        return (pw @ num) / d


def ci(samples: np.ndarray) -> tuple[float, float]:
    s = samples[~np.isnan(samples)]
    if len(s) == 0:
        return (np.nan, np.nan)
    return (float(np.quantile(s, ALPHA / 2)), float(np.quantile(s, 1 - ALPHA / 2)))


def fmt(x: float, nd: int = 2) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def fmt_ci(est: float, lo: float, hi: float) -> str:
    return f"{fmt(est)} [{fmt(lo)}, {fmt(hi)}]"


def pct(x: float) -> str:
    return "n/a" if np.isnan(x) else f"{100 * x:.0f}%"


# ------------------------------------------------------------------ report


def dataset_report(name: str, ans: list[dict], rng: np.random.Generator, gates: dict) -> list[str]:
    out = []
    items = sorted({a["item_id"] for a in ans})
    W = boot_weights(len(items), rng)
    n_runs = Counter(panel_key(a) for a in ans)
    out.append(f"## {name}\n")
    out.append(f"{len(ans)} answers evaluated (in this study), {len(items)} prompts, "
               f"runs per prompt panel: {sorted(set(n_runs.values()))}.\n")

    # Answer shape
    mentions = Counter()
    for a in ans:
        mentions.update(a["cats"].values())
    n_mentions = sum(mentions.values())
    with_t = np.mean([bool(a["T"]) for a in ans])
    with_raw_t = np.mean([a["n_raw_top_items"] > 0 for a in ans])
    capped = np.mean([a["n_raw_top_items"] > 2 for a in ans])
    r_ne_m = np.mean([a["R"] != a["M"] for a in ans])
    with_c = np.mean([bool(a["C"]) for a in ans])
    gen_or_c = (mentions["generic_mention"] + mentions["cautioned_against"]) / max(n_mentions, 1)
    unclassified = mentions["unclassified"] / max(n_mentions, 1)
    out.append("### Answer shape\n")
    out.append("| Measure | Value |\n|---|---|")
    out.append(f"| Lexicon brands per answer (mean) | {np.mean([len(a['M']) for a in ans]):.1f} |")
    out.append(f"| Recommended per answer (mean) | {np.mean([len(a['R']) for a in ans]):.1f} |")
    out.append(f"| Answers with a top choice (after the two-pick cap) | {pct(with_t)} |")
    out.append(f"| Answers with a top choice in the raw judge output | {pct(with_raw_t)} |")
    out.append(f"| Answers whose raw top choices were demoted (more than two) | {pct(capped)} |")
    out.append(f"| Answers where recommended set differs from mentioned set | {pct(r_ne_m)} |")
    out.append(f"| Answers that caution against at least one lexicon brand | {pct(with_c)} |")
    out.append(f"| Judge names outside the lexicon (per answer, mean) | "
               f"{np.mean([a['untracked_names'] for a in ans]):.1f} |")
    out.append("")
    out.append("Category mix over lexicon brand mentions "
               f"({n_mentions} mentions):\n")
    out.append("| Category | Share |\n|---|---|")
    for c in (*CATS, "unclassified"):
        out.append(f"| {c} | {pct(mentions[c] / max(n_mentions, 1))} |")
    out.append("")
    gates.setdefault("G1_unclassified", {})[name] = unclassified
    gates.setdefault("G2", {})[name] = (gen_or_c, r_ne_m)
    gates.setdefault("G3", {})[name] = with_t

    # Retention, within vs between
    primary = ans if name != "claude_b2b" else [a for a in ans if a["arm"] == CLAUDE_PRIMARY_ARM]
    if name == "claude_b2b":
        out.append(f"Retention below uses the `{CLAUDE_PRIMARY_ARM}` arm (claude.ai, default "
                   "setting): 3 runs per prompt. Other arms follow.\n")
    wi, wext, wa, wb, wlag = pair_table(list(within_pairs(primary)), items)
    bt, _, ba, bb, _ = pair_table(list(between_pairs(primary)), items)
    out.append("### Retention: does a brand keep its status in another run?\n")
    out.append(f"Within-prompt pairs: {len(wa)}. Between-prompt pairs (same category, "
               f"same day): {len(ba)}. Intervals: 90%, prompt-level cluster bootstrap.\n")
    out.append("| Status | Appearances | Within prompt | Between prompts | Within minus between | "
               "Pair Jaccard (within) |")
    out.append("|---|---|---|---|---|---|")
    boots = {}
    for s in STATUSES:
        num, den, uni = wi[s][:, 0], wi[s][:, 1], wi[s][:, 2]
        est = pooled(num, den)
        bw = boot_stat(num, den, wa, wb, True, W)
        boots[s] = bw
        if len(ba):
            bnum, bden = bt[s][:, 0], bt[s][:, 1]
            best = pooled(bnum, bden)
            bb_ = boot_stat(bnum, bden, ba, bb, False, W)
            diff = bw - bb_
            between_s = fmt_ci(best, *ci(bb_))
            diff_s = fmt_ci(est - best, *ci(diff))
        else:
            between_s = diff_s = "n/a"
        jac = np.nanmean(np.where(uni > 0, (num / 2) / np.where(uni > 0, uni, 1), np.nan)) \
            if (uni > 0).any() else np.nan
        appearances = sum(len(a[s]) for a in primary)
        out.append(f"| {STATUS_LABELS[s]} | {appearances} | {fmt_ci(est, *ci(bw))} | "
                   f"{between_s} | {diff_s} | {fmt(jac)} |")
        if s == "R" and len(ba):
            gates.setdefault("G4_pos", {})[name] = (est - best, *ci(diff))
    out.append("")

    # Key contrasts
    out.append("**Contrasts (within prompt):**\n")
    for a_, b_, label in (("R", "Pk", "Recommended minus exact position"),
                          ("R", "M", "Recommended minus mentioned"),
                          ("R", "Rpos", "Recommended minus position-only shortlist"),
                          ("T", "P1", "Top choice minus rank 1")):
        est = pooled(wi[a_][:, 0], wi[a_][:, 1]) - pooled(wi[b_][:, 0], wi[b_][:, 1])
        lo, hi = ci(boots[a_] - boots[b_])
        out.append(f"- {label}: {fmt_ci(est, lo, hi)}")
        if (a_, b_) == ("R", "Pk"):
            gates.setdefault("G4_gap", {})[name] = (est, lo, hi)
    t2r = wext.get("T_to_R", np.empty((0, 2)))
    if len(t2r) and t2r[:, 1].sum():
        out.append(f"- A top choice in one run is at least recommended in the other: "
                   f"{pct(pooled(t2r[:, 0], t2r[:, 1]))} of {int(t2r[:, 1].sum())} top-choice "
                   "appearances")
    p2r = wext.get("P1_to_R", np.empty((0, 2)))
    if len(p2r) and p2r[:, 1].sum():
        out.append(f"- For comparison, the rank-1 brand in one run is at least recommended in the "
                   f"other: {pct(pooled(p2r[:, 0], p2r[:, 1]))}")
    r2m = wext.get("R_to_M", np.empty((0, 2)))
    if len(r2m):
        out.append(f"- A recommended brand is at least mentioned in the other run: "
                   f"{pct(pooled(r2m[:, 0], r2m[:, 1]))}")
    bfj = wext.get("bf_phrase_j", np.array([]))
    bfj = bfj[~np.isnan(bfj)] if len(bfj) else bfj
    if len(bfj):
        out.append(f"- Best-for wording, same brand a best-for pick in both runs: mean token "
                   f"overlap {np.mean(bfj):.2f}, at least half the words shared in "
                   f"{pct(np.mean(bfj >= 0.5))} of {len(bfj)} brand pairs (crude; exploratory)")
    out.append("")

    out.append("**Robustness, every brand the judge names** (lexicon brands plus untracked "
               "names; order = the judge's order of first appearance):\n")
    out.append("| Status | Within prompt | Between prompts |\n|---|---|---|")
    for s in STATUSES_ALL:
        bw = boot_stat(wi[s][:, 0], wi[s][:, 1], wa, wb, True, W)
        between = pooled(bt[s][:, 0], bt[s][:, 1]) if len(ba) else np.nan
        out.append(f"| {STATUS_LABELS[s[:-4]]} | {fmt_ci(pooled(wi[s][:, 0], wi[s][:, 1]), *ci(bw))}"
                   f" | {fmt(between)} |")
    est = pooled(wi["R_all"][:, 0], wi["R_all"][:, 1]) - pooled(wi["Pk_all"][:, 0], wi["Pk_all"][:, 1])
    gap = (boot_stat(wi["R_all"][:, 0], wi["R_all"][:, 1], wa, wb, True, W)
           - boot_stat(wi["Pk_all"][:, 0], wi["Pk_all"][:, 1], wa, wb, True, W))
    out.append(f"\nRecommended minus exact position, all brands: {fmt_ci(est, *ci(gap))}\n")

    # Brand-level consistency
    out.append("### Brand-level consistency within a prompt\n")
    out.append("Among brands that hold a status in at least one run of a prompt: how often "
               "they hold it across that prompt's runs.\n")
    out.append("| Status | Brand-prompt pairs | Held in every run | Held in at least 80% of runs "
               "| Held in only one run |")
    out.append("|---|---|---|---|---|")
    groups = defaultdict(list)
    for a in primary:
        groups[panel_key(a)].append(a)
    for s in ("M", "R", "T", "P1"):
        rates = []
        singles = 0
        for runs in groups.values():
            n = len(runs)
            cnt = Counter(b for a in runs for b in a[s])
            for _, c in cnt.items():
                rates.append(c / n)
                singles += c == 1
        rates = np.array(rates)
        if len(rates):
            out.append(f"| {STATUS_LABELS[s]} | {len(rates)} | {pct(np.mean(rates == 1))} | "
                       f"{pct(np.mean(rates >= 0.8))} | {pct(singles / len(rates))} |")
    out.append("")

    # Over time (consumer ChatGPT spans three weeks)
    if name == "chatgpt_consumer":
        out.append("### Retention by days between runs\n")
        bins = [(0, 2), (3, 7), (8, 14), (15, 21)]
        out.append("| Days apart | Pairs | " + " | ".join(STATUS_LABELS[s] for s in
                                                       ("R", "T", "P1", "Pk", "M")) + " |")
        out.append("|---|---|" + "---|" * 5)
        for lo_, hi_ in bins:
            m = (wlag >= lo_) & (wlag <= hi_)
            cells = []
            for s in ("R", "T", "P1", "Pk", "M"):
                cells.append(fmt(pooled(wi[s][m, 0], wi[s][m, 1])))
            out.append(f"| {lo_} to {hi_} | {int(m.sum())} | " + " | ".join(cells) + " |")
        out.append("")

    # Claude arms
    if name == "claude_b2b":
        out.append("### Other Claude arms and cross-arm agreement\n")
        out.append("| Comparison | Pairs | Recommended | Top choice | Rank 1 | Exact position |")
        out.append("|---|---|---|---|---|---|")
        combos = [("ui_think within", lambda x, y: x["arm"] == y["arm"] == "ui_think"),
                  ("opus55_plain within", lambda x, y: x["arm"] == y["arm"] == "opus55_plain"),
                  ("ui_default vs ui_think", lambda x, y: {x["arm"], y["arm"]} ==
                   {"ui_default", "ui_think"}),
                  ("ui_default vs opus55_plain", lambda x, y: {x["arm"], y["arm"]} ==
                   {"ui_default", "opus55_plain"})]
        allpairs = list(within_pairs(ans, pooled_claude=True))
        for label, keep in combos:
            sel = [(x, y) for x, y in allpairs if keep(x, y)]
            t, _, _, _, _ = pair_table(sel, items)
            cells = [fmt(pooled(t[s][:, 0], t[s][:, 1])) for s in ("R", "T", "P1", "Pk")]
            out.append(f"| {label} | {len(sel)} | " + " | ".join(cells) + " |")
        out.append("")
    return out


def judge_retest(answers: list[dict]) -> list[str]:
    """Second judge pass on identical answers: the instrument's own noise."""
    if not (RAW / "judged_explore_rejudge.jsonl").exists():
        return []
    second, _ = build_answers("explore_rejudge")
    first = {a["task_id"]: a for a in answers}
    pairs = [(first[b["task_id"]], b) for b in second if b["task_id"] in first]
    out = ["## Judge test-retest (same answer text, judged twice)\n",
           f"{len(pairs)} answers re-judged (seeded sample of the exploration split). "
           "Any disagreement here is instrument noise, not AI variation, so it caps the "
           "retention the study can observe.\n"]
    labels = [*CATS, "unclassified"]
    agree, n = 0, 0
    conf = Counter()
    for x, y in pairs:
        for b in x["order"]:
            conf[(x["cats"][b], y["cats"][b])] += 1
            agree += x["cats"][b] == y["cats"][b]
            n += 1
    po = agree / max(n, 1)
    px = Counter(k[0] for k in conf.elements())
    py = Counter(k[1] for k in conf.elements())
    pe = sum(px[c] * py[c] for c in labels) / max(n, 1) ** 2
    kappa = (po - pe) / (1 - pe) if pe < 1 else np.nan
    out.append(f"Category agreement over {n} lexicon brand mentions: {pct(po)} "
               f"(Cohen's kappa {fmt(kappa)}).\n")
    out.append("| Status | Retention between the two passes, by dataset |\n|---|---|")
    for s_ in ("R", "T", "BF", "C"):
        cells = []
        for ds in DATASETS:
            sub = [(x, y) for x, y in pairs if x["dataset"] == ds]
            num = sum(2 * len(x[s_] & y[s_]) for x, y in sub)
            den = sum(len(x[s_]) + len(y[s_]) for x, y in sub)
            cells.append(f"{ds} {fmt(num / den) if den else 'n/a'} (n={len(sub)})")
        out.append(f"| {STATUS_LABELS[s_]} | {'; '.join(cells)} |")
    out.append("")
    out.append("Category changes between passes (first pass -> second pass):\n")
    for (a_, b_), c in sorted(conf.items(), key=lambda kv: -kv[1]):
        if a_ != b_:
            out.append(f"- {a_} -> {b_}: {c}")
    out.append("")
    return out


def main() -> None:
    answers, diag = build_answers()
    rng = np.random.default_rng(SEED)
    gates: dict = {}
    lines = ["# Experiment 010: initial evaluation (exploratory)\n",
             "Exploration split only (sketch.md). Nothing here is confirmatory. "
             "Generated by `pipeline/10_explore.py`.\n"]

    n_ok = diag["tasks"] - diag["judge_failed"]
    ev = diag["evidence_verified"] / max(diag["judge_brands"], 1)
    u = diag["usage"]
    lines.append("## Instrument\n")
    lines.append("| Check | Value |\n|---|---|")
    lines.append(f"| Answers judged OK | {n_ok} of {diag['tasks']} ({pct(n_ok / diag['tasks'])}) |")
    lines.append(f"| Evidence quotes verified (all judge brands) | {pct(ev)} of {diag['judge_brands']} |")
    lines.append(f"| Judge names mapped back to a lexicon brand by the lexicon matcher | "
                 f"{diag['fallback_mapped']} |")
    lines.append(f"| Tokens: input / cached input / output | {u.get('inputTokens', 0):,} / "
                 f"{u.get('cachedInputTokens', 0):,} / {u.get('outputTokens', 0):,} |")
    cost = u.get("inputTokens", 0) * LUNA_IN / 1e6 + u.get("outputTokens", 0) * LUNA_OUT / 1e6
    lines.append(f"| Estimated judge cost (list price, cached input billed in full) | "
                 f"${cost:.2f}, ${cost / max(n_ok, 1):.4f} per answer |")
    lines.append("")
    gates["G1"] = (n_ok / diag["tasks"], ev)

    INTERIM.mkdir(parents=True, exist_ok=True)
    with (INTERIM / "answers.jsonl").open("w") as f:
        for a in answers:
            f.write(json.dumps({k: (sorted(map(str, v)) if isinstance(v, set) else v)
                                for k, v in a.items()}) + "\n")

    for ds in DATASETS:
        sub = [a for a in answers if a["dataset"] == ds]
        if sub:
            lines += dataset_report(ds, sub, rng, gates)

    lines += judge_retest(answers)

    # Gates
    lines.append("## Go/no-go criteria (sketch.md)\n")
    ok_rate, ev = gates["G1"]
    worst_unc = max(gates["G1_unclassified"].values())
    g1 = ok_rate >= 0.98 and ev >= 0.90 and worst_unc <= 0.05
    lines.append(f"- **G1 instrument:** judged {pct(ok_rate)} (need 98%), evidence verified "
                 f"{pct(ev)} (need 90%), worst unclassified {pct(worst_unc)} (max 5%): "
                 f"**{'PASS' if g1 else 'FAIL'}**")
    g2 = any(g >= 0.10 or r >= 0.25 for g, r in gates["G2"].values())
    lines.append("- **G2 shortlist is not the mention list:** " + "; ".join(
        f"{k} generic+cautioned {pct(g)}, R differs from M {pct(r)}"
        for k, (g, r) in gates["G2"].items()) + f": **{'PASS' if g2 else 'FAIL'}**")
    g3 = any(v >= 0.25 for v in gates["G3"].values())
    lines.append("- **G3 top choices exist:** " + "; ".join(
        f"{k} {pct(v)}" for k, v in gates["G3"].items()) + f": **{'PASS' if g3 else 'FAIL'}**")
    g4_gap = {k: v for k, v in gates.get("G4_gap", {}).items()}
    g4_pos = gates.get("G4_pos", {})
    g4 = any(est >= SESOI and lo > 0 and g4_pos.get(k, (0,))[0] >= SESOI
             for k, (est, lo, hi) in g4_gap.items())
    lines.append("- **G4 story (R minus Pk at least 0.10, interval above 0, and R within minus "
                 "between at least 0.10):** " + "; ".join(
                     f"{k} gap {fmt_ci(*v)}, within minus between "
                     f"{fmt(g4_pos.get(k, (np.nan,))[0])}" for k, v in g4_gap.items())
                 + f": **{'PASS' if g4 else 'FAIL'}**")
    lines.append("")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "exploration.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
