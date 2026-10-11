"""Stage 20: one row per answer -> data/interim/stage<N>_answers.jsonl (spec §3).

Builds the answer frame every later stage reads. One row per judged answer:
dataset, platform and arm, item_id, category, intent (009's "shortlist" or
"evaluate"; B2B only), wave, run date, reported model, the lexicon brands in
first-mention order with the judge's status for each (``unclassified`` when
the judge did not classify a lexicon brand), best-for phrases per brand,
caveat reason types per brand, the raw top choices before the two-pick cap,
and the all-brands view for R1 (every name the judge lists). Refusals, empty
answers and judge failures are kept and flagged (Audit A); the analysis
stages drop them. No answer or question text is written.

Inputs per mode (see common.Mode):

- confirmatory: ``tasks_b2b_main.jsonl`` + ``judged_b2b_main.jsonl`` (rebuilt
  with lexicon v3 as trackedPresent; brands = the task's ``brands``), waves
  1 to 7 only at Stage 1 (firewall rule 1: later waves are dropped before
  any judged row is read, and the count is logged), plus ``tasks_holdout`` +
  ``judged_holdout`` (the source studies' frozen lexicons), plus the Audit E
  second passes ``judged_b2b_main_rejudge`` and ``judged_holdout_rejudge``
  -> ``stage1_answers_rejudge.jsonl``.
  Refuses (exit 3) before reading any judged file while LEXICON_V3_SHA256 or
  TAXONOMY_B2B_SHA256 is None, or when the task file was not built with the
  frozen lexicon v3.
- ``--split explore``: tasks_explore + judged_explore (three old datasets).
- ``--synthetic {planted,broken_join}``: writes a fake world (tasks, judge
  output, lexicon, best-for files, Audit D score) under
  ``data/interim/synthetic/<world>/raw/`` and builds it with the same code.

Instrument helpers (each writes one file under data/raw, refuses to
overwrite a different existing file, and computes no metric):

- ``--gather-taxonomy-phrases``: the phrase pool the 20 B2B taxonomies are
  built from (spec §5): best-for phrases on brands the judge recommends, all
  judge brands (no lexicon needed), in the Claude answers of the exploration
  and holdout splits and new waves 1 and 2 (``--w12-split``) ->
  ``bestfor_taxonomy_b2b/phrases.json``. Then ``bestfor_segments.mts taxonomy
  --split taxonomy_b2b`` and the freeze.
- ``--write-rejudge-sample``: the seeded 10% Audit E sample of the Stage 1
  new-collection tasks -> ``tasks_b2b_main_rejudge.jsonl`` (then
  ``judge_runner.mts --split b2b_main_rejudge``).
- ``--gather-bestfor``: after the answer frame is built, the Stage 1 phrases
  (recommended lexicon brands, both judge passes) and the merged frozen
  taxonomy -> ``bestfor_stage1/{phrases,taxonomy}.json``. Then
  ``bestfor_segments.mts normalize``, ``classify --pass a``, ``classify --pass
  b``, all with ``--split stage1``.

Usage:
  uv run python experiments/010-shortlist-stability/pipeline/20_answers.py --stage 1
  uv run python .../20_answers.py --stage 1 --split explore
  uv run python .../20_answers.py --stage 1 --synthetic planted
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from common import (
    INSTRUMENT,
    AUDIT_E_SHARE,
    CLAUDE_ARMS,
    JUDGE_PIN,
    LEXICON_V3,
    LEXICON_V3_SHA256,
    NEW_DATASETS,
    PROMPTS_B2B,
    RAW,
    REC,
    SEED,
    SRC_002,
    SRC_003,
    SRC_005,
    SRC_009,
    STAGE_WAVES,
    TAXONOMY_B2B_SHA256,
    Mode,
    add_mode_args,
    brands009,
    build_rows,
    holdout_mapper,
    instrument_problems,
    lexicon_file_mapper,
    load_judged,
    merged_stage_taxonomy,
    mode_from_args,
    read_csv,
    read_jsonl,
    refuse,
    rejudge_sample,
    sha256_file,
    usable,
    write_jsonl,
)

WHO = "20_answers.py"


def log(msg: str) -> None:
    print(msg, flush=True)


# ------------------------------------------------------------- loaders


def load_intents(raw: Path) -> dict[str, str]:
    path = raw / PROMPTS_B2B
    return {p["item_id"]: p["prompt_intent"] for p in read_csv(path)} if path.exists() else {}


def load_stage_tasks(path: Path, stage: int) -> tuple[list[dict], int]:
    """New-collection tasks inside the stage's waves; later waves dropped and counted."""
    waves = set(STAGE_WAVES[stage])
    tasks = read_jsonl(path)
    kept = [t for t in tasks if int(t["wave"]) in waves]
    filtered = len(tasks) - len(kept)
    if any(int(t["wave"]) not in waves for t in kept):  # defensive: never reached
        refuse(["a task outside the stage waves survived the firewall filter"], WHO)
    log(f"firewall (stage {stage}, waves {min(waves)} to {max(waves)}): kept {len(kept)} "
        f"new-collection tasks from {path.name}, dropped {filtered} from later waves before "
        "reading any judge output")
    return kept, filtered


def check_lexicon_build(tasks: list[dict], patterns: dict, label: str) -> dict:
    """Every task's lexicon brands must be what the frozen lexicon finds in its answer."""
    b9 = brands009()
    bad = [t["task_id"] for t in tasks
           if INSTRUMENT.extract_new(b9, t.get("answer") or "", patterns.get(t["category"], []))
           != list(t["brands"])
           or [x["canonical"] for x in t.get("tracked", [])] != list(t["brands"])]
    if bad:
        refuse([f"{len(bad)} of {len(tasks)} tasks in {label} were not built with this lexicon "
                "(their brands differ from what it extracts from the answer); rebuild them "
                "with build_tasks.py --collection main pointed at lexicon v3, then re-judge"],
               WHO)
    return {"tasks_checked": len(tasks), "mismatches": 0}


def check_judged_canonicals(tasks: list[dict], judged: dict[str, dict], label: str) -> None:
    """A judge canonical outside the task's brands means the judge saw another task build."""
    brands = {t["task_id"]: set(t["brands"]) for t in tasks}
    stale = [tid for tid, r in judged.items() if r.get("ok") and any(
        b.get("canonical") and b["canonical"] not in brands.get(tid, set())
        for b in r.get("brands") or [])]
    if stale:
        refuse([f"{len(stale)} judged rows in {label} name tracked brands their task does not "
                "carry: the judge output predates the current task build; re-judge"], WHO)


def source_models(tasks: list[dict]) -> dict[str, str | None]:
    """Reported model per holdout or exploration task, from the source studies."""
    out: dict[str, str | None] = {}
    need = {t["task_id"] for t in tasks}
    chat: dict[tuple, str] = {}
    for src, exp in ((SRC_002, "002"), (SRC_003, "003"), (SRC_005, "005")):
        path = src / "data/interim/responses.csv"
        if not path.exists():
            continue
        for r in read_csv(path):
            arm = r.get("arm") or ("hum" if r["intent"] == "headphones" else "coffee")
            chat[(exp, arm, r["item_id"], int(r["wave"]))] = r.get("model") or None
    claude: dict[tuple, str] = {}
    feats = SRC_009 / "data/interim/features.jsonl"
    if feats.exists():
        for r in read_jsonl(feats):
            if r["arm"] in CLAUDE_ARMS:
                claude[(r["arm"], r["item_id"], int(r["wave"]))] = r.get("model")
    for t in tasks:
        if t["task_id"] not in need:
            continue
        if t["dataset"] == "claude_b2b":
            out[t["task_id"]] = claude.get((t["arm"], t["item_id"], int(t["wave"])))
        else:
            exp, arm = t["task_id"].split("|")[1:3]
            out[t["task_id"]] = chat.get((exp, arm, t["item_id"], int(t["wave"])))
    return out


def judge_pin_sha() -> str | None:
    return json.loads(JUDGE_PIN.read_text()).get("sha256") if JUDGE_PIN.exists() else None


# --------------------------------------------------------------- builds


def build(mode: Mode) -> None:
    raw = mode.raw
    if mode.confirmatory:
        # Constants and instrument files only: nothing below runs, and no
        # judged file is opened, until lexicon v3 and the taxonomy are frozen.
        problems = instrument_problems()
        if problems:
            refuse(problems, WHO)
    intents = load_intents(raw)
    meta: dict = {"mode": mode.kind, "stage": mode.stage, "world": mode.world,
                  "judge_pin_sha256": judge_pin_sha()}
    rows: list[dict] = []
    rejudge: list[dict] = []

    if mode.kind == "explore":
        tasks = read_jsonl(raw / "tasks_explore.jsonl")
        mapper = holdout_mapper()
        models = source_models(tasks)
        judged = load_judged(raw / "judged_explore.jsonl", {t["task_id"] for t in tasks})
        rows = build_rows(tasks, judged, mapper, intents, models)
        rj_path = raw / "tasks_explore_rejudge.jsonl"
        if rj_path.exists():
            rt = read_jsonl(rj_path)
            rejudge = build_rows(rt, load_judged(raw / "judged_explore_rejudge.jsonl",
                                                 {t["task_id"] for t in rt}),
                                 mapper, intents, models, pass_name="rejudge")
        meta |= {"max_new_wave": 0, "filtered_waves": 0}
    else:
        if mode.confirmatory:
            lex_path, lex_sha = LEXICON_V3, LEXICON_V3_SHA256
            tax_sha = TAXONOMY_B2B_SHA256
            hold_mapper = holdout_mapper()
        else:
            lex_path = raw / "lexicon_v3" / "lexicon_v3.csv"
            lex_sha = sha256_file(lex_path)
            tax_sha = sha256_file(raw / "bestfor_taxonomy_b2b" / "taxonomy.json")
            hold_mapper = None
        new_mapper, patterns = lexicon_file_mapper(lex_path)
        hold_mapper = hold_mapper or new_mapper

        new_tasks, filtered = load_stage_tasks(raw / "tasks_b2b_main.jsonl", mode.stage)
        meta["lexicon_v3_check"] = check_lexicon_build(new_tasks, patterns, "tasks_b2b_main")
        judged = load_judged(raw / "judged_b2b_main.jsonl", {t["task_id"] for t in new_tasks})
        check_judged_canonicals(new_tasks, judged, "judged_b2b_main")
        rows += build_rows(new_tasks, judged, new_mapper, intents, {})

        hold = read_jsonl(raw / "tasks_holdout.jsonl")
        models = source_models(hold) if mode.confirmatory else {}
        hjudged = load_judged(raw / "judged_holdout.jsonl", {t["task_id"] for t in hold})
        rows += build_rows(hold, hjudged, hold_mapper, intents, models)

        rj_new = raw / "tasks_b2b_main_rejudge.jsonl"
        if rj_new.exists():
            rt, _ = load_stage_tasks(rj_new, mode.stage)
            rjud = load_judged(raw / "judged_b2b_main_rejudge.jsonl", {t["task_id"] for t in rt})
            check_judged_canonicals(rt, rjud, "judged_b2b_main_rejudge")
            rejudge += build_rows(rt, rjud, new_mapper, intents, {}, pass_name="rejudge")
        else:
            log("no tasks_b2b_main_rejudge.jsonl yet (Audit E sample of the new collection; "
                "20_answers.py --write-rejudge-sample)")
        rj_hold = raw / "tasks_holdout_rejudge.jsonl"
        if rj_hold.exists():
            rt = read_jsonl(rj_hold)
            rjud = load_judged(raw / "judged_holdout_rejudge.jsonl", {t["task_id"] for t in rt})
            rejudge += build_rows(rt, rjud, hold_mapper, intents, models, pass_name="rejudge")

        max_new = max((r["wave"] for r in rows if r["dataset"] in NEW_DATASETS), default=0)
        if max_new > max(STAGE_WAVES[mode.stage]):
            refuse([f"a new-collection answer from wave {max_new} reached the Stage "
                    f"{mode.stage} frame"], WHO)
        meta |= {"lexicon_v3_sha256": lex_sha, "taxonomy_b2b_sha256": tax_sha,
                 "filtered_waves": filtered, "max_new_wave": max_new}

    pin = meta["judge_pin_sha256"]
    meta["judge_rows_off_pin"] = sum(1 for r in rows + rejudge
                                     if r["judge_ok"] and pin and r["judge_sha256"] != pin)
    meta["rows"] = dict(Counter(r["dataset"] for r in rows))
    meta["rejudge_rows"] = dict(Counter(r["dataset"] for r in rejudge))
    meta["unusable"] = dict(Counter(r["dataset"] for r in rows if not usable(r)))
    write_jsonl(mode.answers_path, rows)
    write_jsonl(mode.rejudge_path, rejudge)
    mode.meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    log(f"wrote {len(rows)} answers to {mode.answers_path} and {len(rejudge)} second-pass "
        f"answers to {mode.rejudge_path.name}: {meta['rows']}")
    if meta["unusable"]:
        log(f"flagged (refusal, empty or judge failure; excluded downstream): {meta['unusable']}")


# ------------------------------------------------------- instrument helpers


def write_new_file(path: Path, text: str) -> None:
    if path.exists():
        if path.read_text() == text:
            log(f"{path} already up to date")
            return
        refuse([f"{path} exists and differs; move it aside deliberately if it must change "
                "(a frozen instrument input)"], WHO, code=5)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    log(f"wrote {path}")


def gather_taxonomy_phrases(w12_split: str) -> None:
    """Spec §5 taxonomy protocol: pooled best-for phrases, Claude explore + holdout + waves 1-2."""
    counts: dict[str, Counter] = defaultdict(Counter)
    sources = [("explore", lambda t: t["dataset"] == "claude_b2b"),
               ("holdout", lambda t: t["dataset"] == "claude_b2b"),
               (w12_split, lambda t: t["dataset"] in NEW_DATASETS and int(t["wave"]) in (1, 2))]
    for split, keep in sources:
        tasks = {t["task_id"]: t for t in read_jsonl(RAW / f"tasks_{split}.jsonl") if keep(t)}
        judged = load_judged(RAW / f"judged_{split}.jsonl", set(tasks))
        for tid, r in judged.items():
            if not r.get("ok"):
                continue
            for b in r.get("brands") or []:
                if b.get("category") in REC:
                    counts[tasks[tid]["category"]].update(b.get("bestFor") or [])
        log(f"{split}: {len(judged)} judged answers")
    out = {c: [{"phrase": p, "count": n} for p, n in cnt.most_common()]
           for c, cnt in sorted(counts.items())}
    write_new_file(RAW / "bestfor_taxonomy_b2b" / "phrases.json", json.dumps(out, indent=1))
    log(f"{sum(len(v) for v in out.values())} distinct phrases in {len(out)} categories")


def write_rejudge_sample(mode: Mode) -> None:
    if not mode.confirmatory:
        refuse(["--write-rejudge-sample is for the confirmatory collection only"], WHO)
    problems = instrument_problems()
    if problems:
        refuse(problems, WHO)
    _, patterns = lexicon_file_mapper(LEXICON_V3)
    tasks, _ = load_stage_tasks(RAW / "tasks_b2b_main.jsonl", mode.stage)
    check_lexicon_build(tasks, patterns, "tasks_b2b_main")
    sample = rejudge_sample(tasks, AUDIT_E_SHARE)
    text = "".join(json.dumps(t) + "\n" for t in sample)
    write_new_file(RAW / "tasks_b2b_main_rejudge.jsonl", text)
    log(f"{len(sample)} of {len(tasks)} Stage {mode.stage} tasks; judge them with "
        "judge_runner.mts --split b2b_main_rejudge")


def gather_bestfor(mode: Mode) -> None:
    if mode.kind == "explore":
        refuse(["the exploration split already has bestfor_explore/"], WHO)
    if mode.confirmatory:
        problems = instrument_problems()
        if problems:
            refuse(problems, WHO)
    if not mode.answers_path.exists():
        refuse([f"build the answer frame first ({mode.answers_path.name} missing)"], WHO)
    counts: dict[str, Counter] = defaultdict(Counter)
    for path in (mode.answers_path, mode.rejudge_path):
        for a in read_jsonl(path) if path.exists() else []:
            if not usable(a):
                continue
            for b in a["order"]:
                if a["cats"][b] in REC:
                    counts[a["category"]].update(a["best_for"].get(b, []))
    phrases = {c: [{"phrase": p, "count": n} for p, n in cnt.most_common()]
               for c, cnt in sorted(counts.items())}
    taxonomy = (merged_stage_taxonomy() if mode.confirmatory
                else json.loads((mode.bestfor / "taxonomy.json").read_text()))
    missing = sorted(set(phrases) - set(taxonomy))
    if missing:
        refuse([f"{len(missing)} categories have phrases but no frozen taxonomy"], WHO)
    write_new_file(mode.bestfor / "phrases.json", json.dumps(phrases, indent=1))
    write_new_file(mode.bestfor / "taxonomy.json", json.dumps(taxonomy, indent=1))
    log(f"next: bestfor_segments.mts normalize, classify --pass a, classify --pass b, all with "
        f"--split stage{mode.stage}")


# ------------------------------------------------------- synthetic worlds
# Fake answers with planted structure, written in the real file formats so
# the build above (and everything after it) runs unchanged. Brand names are
# coded (V0307, Hp04, Ag017); categories are "Category 01" to "Category 20".

SCHEDULE_START = date(2026, 10, 3)
WAVE_OFFSETS = (0, 1, 2, 3, 4, 5, 6, 13, 20, 27, 34)  # run_wave.py, collection_schedule.json
SEGMENTS = ("seg_1", "seg_2", "seg_3", "seg_4", "general")
REASONS = ("price", "fit", "complexity", "support")

#: Planted generators. p_core: inclusion probability of each core brand (in
#: rank order); top_probs: chance the top choice is core[0], core[1]; the
#: rest of the time there is none. top_first: chance the top choice is named
#: first. sigma: order noise (higher = less stable positions).
B2B_GEN = dict(p_core=(0.99, 0.98, 0.92, 0.9, 0.88, 0.86), n_periph=5, p_periph=0.2, sigma=1.0,
               top_probs=(0.6, 0.3), top_first=1.0, p_gen=0.85, p_cau=0.35, seg_keep=0.55)
#: Gemini: a top pick that never changes while the order is shuffled, so the
#: shortlist does NOT beat the top pick (H2 not supported) and the top pick
#: IS steadier than rank 1 (H3 not supported).
GEMINI_GEN = B2B_GEN | dict(top_probs=(0.97, 0.0), top_first=0.0, sigma=3.0)
CONSUMER_GEN = dict(p_core=(0.99, 0.96, 0.92, 0.88), n_periph=3, p_periph=0.25, sigma=0.9,
                    top_probs=(0.75, 0.2), top_first=1.0, p_gen=0.3, p_cau=0.0, seg_keep=0.55)
#: Agencies: a fixed list in a fixed order, so exact position is nearly as
#: stable as the shortlist (H1 not supported).
AGENCY_GEN = dict(p_core=(0.97, 0.96, 0.95), n_periph=0, p_periph=0.0, sigma=0.0,
                  top_probs=(0.3, 0.0), top_first=1.0, p_gen=0.0, p_cau=0.0, seg_keep=0.55)

PLANTED_EXPECT = {
    # dataset: {test: expected verdict(s)} asserted by 22_model.py --expect planted
    "chatgpt_b2b": {"H1": ("SUPPORTED",), "H2": ("SUPPORTED",), "H3": ("SUPPORTED",),
                    "H4": ("SUPPORTED",), "H6": ("NULL", "NEGLIGIBLE"), "H7": ("SUPPORTED",)},
    "gemini_b2b": {"H1": ("SUPPORTED",), "H2": ("NOT_SHOWN",), "H3": ("NOT_SUPPORTED",),
                   "H4": ("SUPPORTED",), "H6": ("NULL", "NEGLIGIBLE"), "H7": ("SUPPORTED",)},
    "claude_api_b2b": {"H1": ("SUPPORTED",), "H2": ("SUPPORTED",), "H3": ("SUPPORTED",),
                       "H4": ("SUPPORTED",), "H6": ("NULL", "NEGLIGIBLE"),
                       "H7": ("SUPPORTED",)},
    "claude_b2b": {"H1": ("SUPPORTED",), "H2": ("SUPPORTED",), "H4": ("SUPPORTED",),
                   "H6": ("NULL", "NEGLIGIBLE"), "H7": ("SUPPORTED",)},
    "chatgpt_consumer": {"H1": ("SUPPORTED",), "H2": ("SUPPORTED",), "H4": ("SUPPORTED",)},
    "chatgpt_agency": {"H1": ("SMALLER", "NOT_SHOWN")},
}


class World:
    def __init__(self, world: str):
        self.world = world
        self.rng = np.random.default_rng(SEED)
        self.cats = [f"Category {k:02d}" for k in range(1, 21)]
        self.pool = {c: [f"V{k + 1:02d}{j:02d}" for j in range(1, 25)]
                     for k, c in enumerate(self.cats)}
        self.pool["headphones"] = [f"Hp{j:02d}" for j in range(1, 15)]
        self.pool["coffee"] = [f"Ag{j:03d}" for j in range(1, 121)]
        self.profiles: dict[tuple, dict] = {}

    # -- instruments

    def prompts(self) -> list[dict]:
        out = []
        for n in range(1, 41):
            out.append({"item_id": f"b2b_{n:02d}", "intent": "b2b", "text": f"Synthetic {n}",
                        "category": self.cats[(n - 1) // 2],
                        "prompt_intent": "shortlist" if n % 2 else "evaluate"})
        return out

    def lexicon_rows(self) -> list[dict]:
        """Every B2B brand under every B2B category, so a misfiled answer still
        yields its brands (the broken join is then a pure join error)."""
        b2b = [b for c in self.cats for b in self.pool[c]]
        rows = []
        for c in self.cats:
            rows += [{"canonical": b, "aliases": b, "category": c, "decision": "keep",
                      "reason": "", "match": "cs", "n_answers": 0, "change": ""} for b in b2b]
        for c in ("headphones", "coffee"):
            rows += [{"canonical": b, "aliases": b, "category": c, "decision": "keep",
                      "reason": "", "match": "cs", "n_answers": 0, "change": ""}
                     for b in self.pool[c]]
        return rows

    def phrase(self, cat: str, seg: str, p: int) -> str:
        return f"{cat.lower()} {seg} use {p}"

    def bestfor_files(self, flip: float = 0.04) -> dict[str, dict]:
        rng = np.random.default_rng(SEED + 7)
        cats = [*self.cats, "headphones", "coffee"]
        taxonomy = {c: [{"id": s, "label": f"Segment {s}", "definition": "synthetic"}
                        for s in SEGMENTS] for c in cats}
        phrases, norm, sa, sb = {}, {}, {}, {}
        for c in cats:
            phrases[c] = []
            sa[c], sb[c] = {}, {}
            for s in SEGMENTS:
                for p in range(3):
                    ph = self.phrase(c, s, p)
                    phrases[c].append({"phrase": ph, "count": 1})
                    norm[ph] = ph if p == 0 else f"{c.lower()} {s} shared"
                    sa[c][ph] = s
                    sb[c][ph] = (str(rng.choice([x for x in SEGMENTS if x != s]))
                                 if rng.random() < flip else s)
        return {"taxonomy.json": taxonomy, "phrases.json": phrases, "norm.json": norm,
                "segments_a.json": sa, "segments_b.json": sb}

    # -- answers

    def profile(self, group: str, item: str, cat: str, gen: dict) -> dict:
        key = (group, item)
        if key not in self.profiles:
            pool = list(self.rng.permutation(self.pool[cat]))
            n_core = len(gen["p_core"])
            core = pool[:n_core]
            periph = pool[n_core:n_core + gen["n_periph"]]
            rest = pool[n_core + gen["n_periph"]:]
            self.profiles[key] = {
                "core": core, "periph": periph,
                "generic": rest[0] if rest else None, "caution": rest[1] if len(rest) > 1 else None,
                "seg": {b: str(self.rng.choice(SEGMENTS)) for b in pool},
                "untracked": [f"Unlisted {item} {k}" for k in range(4)],
            }
        return self.profiles[key]

    def answer(self, prof: dict, gen: dict, cat: str) -> tuple[list[str], dict, list[str]]:
        rng = self.rng
        rec = [b for b, p in zip(prof["core"], gen["p_core"]) if rng.random() < p]
        rec += [b for b in prof["periph"] if rng.random() < gen["p_periph"]]
        gen_b = [prof["generic"]] if prof["generic"] and rng.random() < gen["p_gen"] else []
        cau = [prof["caution"]] if prof["caution"] and rng.random() < gen["p_cau"] else []
        base = {b: i for i, b in enumerate(prof["core"] + prof["periph"])}
        base |= {prof["generic"]: 3.5, prof["caution"]: 5.5}
        present = rec + gen_b + cau
        key = {b: base[b] + (rng.normal(0, gen["sigma"]) if gen["sigma"] else 0.0)
               for b in present}
        order = sorted(present, key=key.get)
        u = rng.random()
        p0, p1 = gen["top_probs"]
        cand = prof["core"][0] if u < p0 else (prof["core"][1] if u < p0 + p1 else None)
        top = cand if cand in rec else None
        if top and rng.random() < gen["top_first"]:
            order.remove(top)
            order.insert(0, top)
        cats = {b: "one_of_many" for b in rec}
        cats |= {b: "generic_mention" for b in gen_b} | {b: "cautioned_against" for b in cau}
        if top:
            cats[top] = "top_choice"
        untracked = [n for n in prof["untracked"] if rng.random() < 0.5]
        return order, cats, untracked

    def best_for(self, prof: dict, b: str, cat: str, gen: dict) -> list[str]:
        seg = prof["seg"][b]
        if self.rng.random() >= gen["seg_keep"]:
            seg = str(self.rng.choice([s for s in SEGMENTS if s != seg]))
        return [self.phrase(cat, seg, int(self.rng.integers(0, 3)))]

    def judged(self, tid: str, prof: dict, gen: dict, cat: str, order: list[str],
               cats: dict[str, str], untracked: list[str], pin: str | None) -> dict:
        brands, raw = [], []
        for b in order + untracked:
            c = cats.get(b, "one_of_many")
            bf = self.best_for(prof, b, cat, gen) if c in REC and b in cats else []
            cav = ([{"reasonType": str(self.rng.choice(REASONS)), "reason": "",
                     "reasonNorm": "", "audience": "", "audienceNorm": ""}]
                   if c == "cautioned_against" or (c == "one_of_many" and self.rng.random() < 0.1)
                   else [])
            brands.append({"brandKey": b.lower(), "name": b, "trackedKey": b.lower() if b in cats
                           else None, "category": c, "bestFor": bf, "caveats": cav,
                           "evidence": "", "evidenceVerified": True,
                           "canonical": b if b in cats else None})
            raw.append({"name": b, "category": c, "bestFor": bf, "caveats": cav, "evidence": ""})
        over = 0
        if any(c == "top_choice" for c in cats.values()) and self.rng.random() < 0.03:
            for e in raw:
                if e["category"] == "one_of_many" and over < 2:
                    e["category"] = "top_choice"
                    over += 1
        return {"task_id": tid, "model": "gpt-5.6-luna", "version": 2, "judge_sha256": pin,
                "ok": True, "raw": {"brands": raw}, "brands": brands,
                "dropped": {"emptyName": 0, "invalidCategory": 0, "notInAnswer": 0,
                            "overCap": over, "invalidCaveats": 0},
                "usage": {"inputTokens": 0, "outputTokens": 0, "cachedInputTokens": 0}, "ms": 0}

    @staticmethod
    def text(order: list[str], untracked: list[str]) -> str:
        return "Synthetic answer.\n" + "\n".join(f"- {b} is an option." for b in order + untracked)

    def task(self, tid: str, dataset: str, exp: str, arm: str, item: str, cat: str, wave: int,
             run_date: str, model: str, platform: str, order: list[str], answer: str) -> dict:
        return {"task_id": tid, "dataset": dataset, "source_exp": exp, "arm": arm,
                "item_id": item, "category": cat, "split": "synthetic", "wave": wave,
                "run_date": run_date, "model": model, "platform": platform,
                "question": "", "answer": answer, "brands": order,
                "tracked": [{"canonical": b, "aliases": [b]} for b in order]}

    def emit(self, out: list, judged: list, *, tid, dataset, exp, arm, item, cat, wave,
             run_date, model, platform, group, gen, pin, special=None) -> None:
        prof = self.profile(group, item, cat, gen)
        order, cats, untracked = self.answer(prof, gen, cat)
        if special == "refusal":
            order, cats, untracked = [], {}, []
            answer = "I can't help with that request."
        elif special == "empty":
            order, cats, untracked, answer = [], {}, [], ""
        else:
            answer = self.text(order, untracked)
        out.append(self.task(tid, dataset, exp, arm, item, cat, wave, run_date, model, platform,
                             order, answer))
        judged.append(self.judged(tid, prof, gen, cat, order, cats, untracked, pin))

    def build(self, raw: Path) -> None:
        pin = judge_pin_sha()
        prompts = self.prompts()
        cat_of = {p["item_id"]: p["category"] for p in prompts}
        new_tasks, new_judged = [], []
        plats = (("chatgpt_b2b", "chatgpt", "openai", B2B_GEN),
                 ("gemini_b2b", "gemini", "gemini", GEMINI_GEN),
                 ("claude_api_b2b", "claude", "claude", B2B_GEN))
        for ds, plat, platform, gen in plats:
            for wave, off in enumerate(WAVE_OFFSETS, start=1):
                day = SCHEDULE_START + timedelta(days=off + (plat != "claude"))
                model = {"chatgpt": "gpt-5-6" if wave <= 5 else "gpt-6",
                         "gemini": "3.5 Flash-Lite", "claude": "claude-opus-5-5"}[plat]
                for p in prompts:
                    item = p["item_id"]
                    special = None
                    if (ds, wave, item) == ("chatgpt_b2b", 3, "b2b_05"):
                        special = "refusal"
                    if (ds, wave, item) == ("gemini_b2b", 2, "b2b_06"):
                        special = "empty"
                    self.emit(new_tasks, new_judged, tid=f"{ds}|010|{plat}|{item}|w{wave}",
                              dataset=ds, exp="010", arm=plat, item=item, cat=cat_of[item],
                              wave=wave, run_date=day.isoformat(), model=model,
                              platform=platform, group=ds, gen=gen, pin=pin, special=special)
        hold_tasks, hold_judged = [], []
        studies = (("002", 7, date(2026, 7, 17)), ("003", 5, date(2026, 7, 24)),
                   ("005", 5, date(2026, 8, 1)))
        for exp, n_waves, start in studies:
            for wave in range(1, n_waves + 1):
                day = (start + timedelta(days=3 * (wave - 1))).isoformat()
                for n in range(1, 96):
                    item = f"h{n:03d}"
                    self.emit(hold_tasks, hold_judged,
                              tid=f"chatgpt_consumer|{exp}|hum|{item}|w{wave}",
                              dataset="chatgpt_consumer", exp=exp, arm="chatgpt", item=item,
                              cat="headphones", wave=wave, run_date=day, model="gpt-5-5",
                              platform="openai", group="consumer", gen=CONSUMER_GEN, pin=pin)
                if wave == 1:
                    for n in range(1, 28):
                        item = f"c{n:03d}"
                        self.emit(hold_tasks, hold_judged,
                                  tid=f"chatgpt_agency|{exp}|coffee|{item}|w{wave}",
                                  dataset="chatgpt_agency", exp=exp, arm="chatgpt", item=item,
                                  cat="coffee", wave=wave, run_date=day, model="gpt-5-5",
                                  platform="openai", group="agency", gen=AGENCY_GEN, pin=pin)
        for wave in (1, 2, 3):
            day = (date(2026, 9, 27) + timedelta(days=2 * (wave - 1))).isoformat()
            for arm in CLAUDE_ARMS:
                for p in prompts[:26]:
                    item = p["item_id"]
                    self.emit(hold_tasks, hold_judged, tid=f"claude_b2b|009|{arm}|{item}|w{wave}",
                              dataset="claude_b2b", exp="009", arm=arm, item=item,
                              cat=cat_of[item], wave=wave, run_date=day,
                              model="claude.ai" if arm.startswith("ui_") else "claude-opus-5-5",
                              platform="claude", group="claude_ui" if arm.startswith("ui_")
                              else "claude_opus", gen=B2B_GEN, pin=pin)
        raw.mkdir(parents=True, exist_ok=True)
        lex = raw / "lexicon_v3" / "lexicon_v3.csv"
        lex.parent.mkdir(parents=True, exist_ok=True)
        rows = self.lexicon_rows()
        with lex.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        if self.world == "broken_join":
            new_tasks, rename = self.misfile(new_tasks, prompts, lex)
            new_judged = [r | {"task_id": rename[r["task_id"]]} for r in new_judged]

        # second judge pass (Audit E): a seeded sample, a few categories changed
        stage1 = [t for t in new_tasks if t["wave"] in STAGE_WAVES[1]]
        rj_new = rejudge_sample(stage1)
        rj_hold = rejudge_sample(hold_tasks)
        jmap = {r["task_id"]: r for r in new_judged + hold_judged}
        flips = {"one_of_many": "generic_mention", "top_choice": "one_of_many",
                 "generic_mention": "one_of_many", "cautioned_against": "one_of_many"}

        def second(tid: str) -> dict:
            r = json.loads(json.dumps(jmap[tid]))
            for b in r["brands"]:
                if self.rng.random() < 0.03:
                    b["category"] = flips[b["category"]]
            return r

        write_jsonl(raw / "tasks_b2b_main.jsonl", new_tasks)
        write_jsonl(raw / "judged_b2b_main.jsonl", new_judged)
        write_jsonl(raw / "tasks_holdout.jsonl", hold_tasks)
        write_jsonl(raw / "judged_holdout.jsonl", hold_judged)
        write_jsonl(raw / "tasks_b2b_main_rejudge.jsonl", rj_new)
        write_jsonl(raw / "judged_b2b_main_rejudge.jsonl", [second(t["task_id"]) for t in rj_new])
        write_jsonl(raw / "tasks_holdout_rejudge.jsonl", rj_hold)
        write_jsonl(raw / "judged_holdout_rejudge.jsonl", [second(t["task_id"]) for t in rj_hold])
        with (raw / PROMPTS_B2B).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(prompts[0]))
            w.writeheader()
            w.writerows(prompts)
        files = self.bestfor_files()
        tax = raw / "bestfor_taxonomy_b2b" / "taxonomy.json"
        tax.parent.mkdir(parents=True, exist_ok=True)
        tax.write_text(json.dumps({c: files["taxonomy.json"][c] for c in self.cats}, indent=1))
        bf = raw / "bestfor_stage1"
        bf.mkdir(parents=True, exist_ok=True)
        for name, obj in files.items():
            (bf / name).write_text(json.dumps(obj, indent=1))
        res = Mode("synthetic", 1, self.world).results
        res.mkdir(parents=True, exist_ok=True)
        (res / "audit_d_score.json").write_text(json.dumps(
            {"precision": 0.97, "recall": 0.93, "passes": True, "n_answers": 30,
             "signed_by": "synthetic dry run"}, indent=1) + "\n")
        (raw / "planted_expect.json").write_text(json.dumps(PLANTED_EXPECT, indent=1) + "\n")
        log(f"synthetic world {self.world}: {len(new_tasks)} new-collection tasks (waves 1 to "
            f"11), {len(hold_tasks)} holdout tasks, {len(rj_new) + len(rj_hold)} re-judged")

    def misfile(self, tasks: list[dict], prompts: list[dict], lex: Path
                ) -> tuple[list[dict], dict[str, str]]:
        """The broken join: every new answer filed under a random prompt of its
        wave, its lexicon brands re-extracted for that prompt's category (as the
        task builder would), and its judge output moved along with it."""
        cat_of = {p["item_id"]: p["category"] for p in prompts}
        _, patterns = lexicon_file_mapper(lex)
        b9 = brands009()
        by = defaultdict(list)
        for t in tasks:
            by[(t["dataset"], t["wave"])].append(t)
        out, rename = [], {}
        for group in by.values():
            perm = list(self.rng.permutation([t["item_id"] for t in group]))
            for t, new_item in zip(group, perm):
                t = dict(t)
                old = t["task_id"]
                t["item_id"], t["category"] = new_item, cat_of[new_item]
                t["task_id"] = f"{t['dataset']}|010|{t['arm']}|{new_item}|w{t['wave']}"
                t["brands"] = INSTRUMENT.extract_new(b9, t["answer"], patterns.get(t["category"], []))
                t["tracked"] = [{"canonical": b, "aliases": [b]} for b in t["brands"]]
                rename[old] = t["task_id"]
                out.append(t)
        return out, rename


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_mode_args(ap)
    ap.add_argument("--gather-taxonomy-phrases", action="store_true")
    ap.add_argument("--w12-split", default="b2b_main_w12",
                    help="task/judged split holding new waves 1 and 2 for the taxonomy pool")
    ap.add_argument("--write-rejudge-sample", action="store_true")
    ap.add_argument("--gather-bestfor", action="store_true")
    a = ap.parse_args()
    mode = mode_from_args(a)

    if a.gather_taxonomy_phrases:
        if mode.kind != "confirmatory":
            refuse(["--gather-taxonomy-phrases reads the real splits only"], WHO)
        gather_taxonomy_phrases(a.w12_split)
        return
    if a.write_rejudge_sample:
        write_rejudge_sample(mode)
        return
    if a.gather_bestfor:
        gather_bestfor(mode)
        return
    if mode.kind == "synthetic":
        World(mode.world).build(mode.raw)
    build(mode)


if __name__ == "__main__":
    main()
