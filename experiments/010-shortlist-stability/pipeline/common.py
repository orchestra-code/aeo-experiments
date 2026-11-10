"""Shared code for experiment 010's pre-registered pipeline (pipeline/20_ to 24_).

Implements spec.md (FROZEN at 6342963) §2 to §7 for both stages. Stage 1 (run
to run) uses new-collection waves 1 to 7; Stage 2 (over time) uses waves 1 to
11 and adds H5 (drift), its lag bins, the Audit A rule for those bins, the
Stage 2 Audit E sample and the Stage 2 best-for files. ``25_release.py``
releases the datasets of either stage (Stage 2: the update of the Stage 1
release with waves 8 to 11).

Modes (every stage takes exactly one):

- confirmatory (default): the new collection, waves 1 to 7 at Stage 1 and 1
  to 11 at Stage 2 (``data/raw/tasks_b2b_main.jsonl`` +
  ``judged_b2b_main.jsonl``, rebuilt with lexicon v3), and the holdouts
  (``tasks_holdout`` + ``judged_holdout``). Gated: lexicon v3 and the B2B
  best-for taxonomy must be frozen (their sha256 recorded below) before
  anything reads a judged file, and Audit D must have passed before any
  metric is computed. Stage 2 also needs every wave 8 to 11 task and the
  Stage 2 re-judge sample judged OK, and the Stage 2 best-for phrases
  classified twice.
- ``--split explore``: the exploration split (three old datasets only), for
  checking this code against ``results/exploration.md``. Never confirmatory.
- ``--synthetic <world>``: fake tasks and judge output with planted
  structure, written by ``20_answers.py`` under
  ``data/interim/synthetic/<world>/raw/`` and pushed through the same code as
  real data. Stage 1 worlds: ``planted``, ``broken_join``. Stage 2 worlds:
  ``planted_stable`` (no drift), ``planted_drift`` (a planted drop in far
  pairs on one platform), ``broken_join``.

Inference (spec §5): pooled Dice retention, prompt-level cluster bootstrap
(prompts drawn with replacement; a pair of answers inside one cluster carries
the cluster's drawn count, a pair across two clusters the product of their
counts), 2,000 draws, seed 20261003, 90% percentile intervals, contrasts draw
by draw. Pair sums are aggregated per cluster (a vector for same-cluster
pairs, a matrix for cross-cluster pairs) before resampling, which gives the
same draws as weighting every pair and keeps memory flat.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------- paths

EXP = Path(__file__).resolve().parents[1]
EXPERIMENTS = EXP.parent
RAW = EXP / "data" / "raw"
INTERIM = EXP / "data" / "interim"
RESULTS = EXP / "results"
HARNESS = EXP / "harness"
JUDGE_PIN = HARNESS / "judge_pin.json"
PROMPTS_B2B = "prompts_b2b.csv"  # relative to the mode's raw dir

SRC_002 = EXPERIMENTS / "002-prompt-consistency"
SRC_003 = EXPERIMENTS / "003-synthetic-prompt-coverage"
SRC_005 = EXPERIMENTS / "005-subintent-matched-panels"
SRC_009 = EXPERIMENTS / "009-claude-model-fidelity"

# ----------------------------------------------------- frozen instruments

#: Lexicon v3 (spec §5 lexicon protocol): 009's lexicon v2.1 plus the curated
#: candidates from new waves 1 and 2, same columns as v2.1 (canonical,
#: aliases, category, decision, match, ...). Its sha256 is recorded here at
#: STOP 2, after Jim's review and before Audit D. While it is None, nothing
#: reads a confirmatory judged file.
#: The paths and pins live in harness/instrument.py (shared with build_tasks
#: and audit_d), with the new collection's extraction (deviation 6).
_spec = importlib.util.spec_from_file_location("x010_instrument", HARNESS / "instrument.py")
INSTRUMENT = importlib.util.module_from_spec(_spec)
sys.modules["x010_instrument"] = INSTRUMENT
_spec.loader.exec_module(INSTRUMENT)
LEXICON_V3 = INSTRUMENT.LEXICON_V3
LEXICON_V3_SHA256: str | None = INSTRUMENT.LEXICON_V3_SHA256

#: The 20 B2B "best for" taxonomies (spec §5 taxonomy protocol), built with
#: ``harness/bestfor_segments.mts taxonomy --split taxonomy_b2b``. Frozen at
#: STOP 2 with lexicon v3.
TAXONOMY_B2B = INSTRUMENT.TAXONOMY_B2B
TAXONOMY_B2B_SHA256: str | None = INSTRUMENT.TAXONOMY_B2B_SHA256

#: Headphone and agency taxonomies are the exploration ones (spec §5), frozen
#: with the exploration results (results/exploration_bestfor.md).
TAXONOMY_EXPLORE = RAW / "bestfor_explore" / "taxonomy.json"
TAXONOMY_EXPLORE_SHA256 = "505c5c2f0ae9b7dddfc8f2d00c8aaf8e6038c3296886d9a18e077a7015f275ff"
EXPLORE_TAXONOMY_CATEGORIES = ("headphones", "coffee")

# ------------------------------------------------------------- constants

SEED = 20261003          # spec header: freeze date
N_BOOT = 2000            # spec §5
ALPHA = 0.10             # two-sided level of every reported interval (90%)
FAMILY_ALPHA = 0.05      # Holm, one-sided, within each stage's primary family
MARGIN = 0.10            # SESOI for H1, H2, H7 (one-sided margin tests)
NONSUP_MARGIN = 0.10     # H3 non-superiority bound
EQ_BAND = 0.05           # H6 (and Stage 2 H5), TOST band
PLA_BAND = 0.10          # Stage 1 H_pla, TOST band
H4_LEVEL = 0.90          # H4 level test
H_POS_MIN = 0.10         # H_pos: within minus cross R retention
CAUTION_MIN = 30         # cautioned-status retention reported at >= 30 appearances
HELD_SHARE = 0.80        # "shortlisted in at least 80% of a prompt's runs"

AUDIT_A_MIN = 38         # of 40 tasks per platform and wave, non-empty
AUDIT_A_H5_MIN = 36      # Stage 2: below this a wave leaves H5's lag bins
AUDIT_D_PRECISION = 0.95
AUDIT_D_RECALL = 0.90
AUDIT_E_MIN = 0.90       # judge test-retest category agreement
AUDIT_E_SHARE = 0.10     # seeded share of each stage's confirmatory answers
AUDIT_G_MIN = 0.90       # segment classifier test-retest
PROMPTS_PER_WAVE = 40

#: Firewall rule 1: Stage 1 uses waves 1 to 7 of the new collection only.
STAGE_WAVES = {1: tuple(range(1, 8)), 2: tuple(range(1, 12))}
#: The waves Stage 2 adds (its Audit E sample is drawn from these only).
STAGE2_NEW_WAVES = tuple(range(8, 12))
#: Schedule day of each wave (run_wave.py, collection_schedule.json): days 0
#: to 6, then 13, 20, 27, 34. Used only to show which pairs the true run
#: dates moved across a bin edge; lags themselves come from run dates (§3).
WAVE_OFFSETS = (0, 1, 2, 3, 4, 5, 6, 13, 20, 27, 34)
#: Stage 2 lag bins (spec §4 H5, §7 R7), inclusive day ranges (None = open).
H5_NEAR_DAYS = (1, 2)
H5_FAR_MIN_DAYS = 27
H5_CONSUMER_NEAR_DAYS = (0, 2)
H5_CONSUMER_FAR_MIN_DAYS = 15
R7_NEAR_DAYS = (0, 6)
R7_FAR_DAYS = (27, 34)
H5_NEAR = H5_NEAR_DAYS
H5_FAR = (H5_FAR_MIN_DAYS, None)
H5_CONSUMER_NEAR = H5_CONSUMER_NEAR_DAYS
H5_CONSUMER_FAR = (H5_CONSUMER_FAR_MIN_DAYS, None)
#: Bins of the descriptive retention-by-days-apart curve (Stage 2).
CURVE_BINS = ((0, 0), (1, 2), (3, 6), (7, 13), (14, 20), (21, 26), (27, 34), (35, 99))
#: Datasets H5 tests (spec §4 Stage 2 primary family).
H5_DATASETS = ("chatgpt_b2b", "gemini_b2b", "claude_api_b2b")
H5_CONSUMER = "chatgpt_consumer"

STAGE_WORLDS = {1: ("planted", "broken_join"),
                2: ("planted_stable", "planted_drift", "broken_join")}
SYNTHETIC_WORLDS = ("planted", "broken_join", "planted_stable", "planted_drift")

#: Stage 2 Audit E sample of waves 8 to 11 (spec §2 Audit E).
REJUDGE_S2_SPLIT = "b2b_main_rejudge_s2"

# --------------------------------------------------------------- statuses

CATS = ("top_choice", "one_of_many", "generic_mention", "cautioned_against")
REC = ("top_choice", "one_of_many")
MERGE_RANK = {"cautioned_against": 4, "top_choice": 3, "one_of_many": 2, "generic_mention": 1}

STATUS_LABELS = {
    "M": "Mentioned (any way)",
    "R": "Recommended (top choice or one of many): the shortlist",
    "T": "Top choice",
    "C": "Cautioned against",
    "G": "Generic mention",
    "P1": "First-mentioned brand (rank 1)",
    "Pk": "Exact position (brand at rank k)",
    "Rpos": "Position-only shortlist (first |R| brands)",
    "WP": "\"Where AI picks you\" phrase key (brand in R, normalizePhrase)",
    "WS": "Best-for use case (brand in R, segment)",
    "WSb": "Best-for use case, classifier pass b",
    "T>R": "Top choice stays at least recommended (directional)",
    "P1>R": "Rank-1 brand stays at least recommended (directional)",
    "R>M": "Recommended brand stays at least mentioned (directional)",
}
#: Pair keys every pair set carries: set statuses (pooled Dice) and
#: directional retentions (numerator |A_a & B_b| + |A_b & B_a|, denominator
#: |A_a| + |A_b|).
SET_KEYS = ("M", "R", "T", "C", "G", "P1", "Pk", "Rpos", "WP", "WS", "WSb",
            "M_all", "R_all", "T_all", "C_all", "P1_all", "Pk_all")
DIRECTIONAL = {"T>R": ("T", "R"), "P1>R": ("P1", "R"), "R>M": ("R", "M"),
               "T_all>R_all": ("T_all", "R_all")}
PAIR_KEYS = SET_KEYS + tuple(DIRECTIONAL)
#: Statuses with pair-mean Jaccard alongside (spec §5, continuity).
JACCARD_KEYS = ("M", "R", "T", "P1", "Pk", "WS")

#: Status keys a test suite reads; R1 swaps in the all-brands view.
PRIMARY_KEYS = {"R": "R", "Pk": "Pk", "T": "T", "P1": "P1", "M": "M", "WS": "WS",
                "WP": "WP", "T>R": "T>R"}
ALL_BRAND_KEYS = {"R": "R_all", "Pk": "Pk_all", "T": "T_all", "P1": "P1_all", "M": "M_all",
                  "WS": None, "WP": None, "T>R": "T_all>R_all"}

# --------------------------------------------------------------- datasets


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    label: str            # platform label for tables and figures
    color_key: str        # aeo_research.plotting.PLATFORM_COLORS key
    role: str             # primary | generalization
    source: str           # new | holdout
    arm: str              # the arm the dataset's tests use
    partner: str | None = None  # cross-category partner dataset (consumer <-> agency)
    underpowered: bool = False


DATASETS = (
    DatasetSpec("chatgpt_b2b", "ChatGPT", "openai", "primary", "new", "chatgpt"),
    DatasetSpec("gemini_b2b", "Gemini", "gemini", "primary", "new", "gemini"),
    DatasetSpec("claude_api_b2b", "Claude API", "claude", "primary", "new", "claude"),
    DatasetSpec("claude_b2b", "claude.ai", "claude", "primary", "holdout", "ui_default"),
    DatasetSpec("chatgpt_consumer", "ChatGPT, consumer", "openai", "generalization", "holdout",
                "chatgpt", partner="chatgpt_agency"),
    DatasetSpec("chatgpt_agency", "ChatGPT, agencies", "openai", "generalization", "holdout",
                "chatgpt", partner="chatgpt_consumer", underpowered=True),
)
SPEC = {d.name: d for d in DATASETS}
PRIMARY = tuple(d.name for d in DATASETS if d.role == "primary")
NEW_DATASETS = tuple(d.name for d in DATASETS if d.source == "new")
B2B_DATASETS = PRIMARY
CLAUDE_ARMS = ("ui_default", "ui_think", "opus55_plain")
R6_ARMS = ("ui_default", "ui_think")

# ------------------------------------------------------------------ modes


@dataclass(frozen=True)
class Mode:
    kind: str                 # confirmatory | explore | synthetic
    stage: int = 1
    world: str | None = None

    @property
    def confirmatory(self) -> bool:
        return self.kind == "confirmatory"

    @property
    def raw(self) -> Path:
        if self.kind == "synthetic":
            return INTERIM / "synthetic" / str(self.world) / "raw"
        return RAW

    @property
    def interim(self) -> Path:
        if self.kind == "synthetic":
            return INTERIM / "synthetic" / str(self.world)
        if self.kind == "explore":
            return INTERIM / "stage1_explore"
        return INTERIM

    @property
    def results(self) -> Path:
        if self.kind == "synthetic":
            return RESULTS / "synthetic" / str(self.world)
        if self.kind == "explore":
            return RESULTS / "stage1_explore"
        return RESULTS

    @property
    def figures(self) -> Path:
        return self.results / "figures"

    @property
    def bestfor(self) -> Path:
        if self.kind == "explore":
            return RAW / "bestfor_explore"
        return self.raw / f"bestfor_stage{self.stage}"

    @property
    def audit_d(self) -> Path | None:
        if self.kind == "explore":
            return None
        return self.results / "audit_d_score.json"

    def interim_file(self, name: str) -> Path:
        return self.interim / f"stage{self.stage}_{name}"

    @property
    def answers_path(self) -> Path:
        return self.interim_file("answers.jsonl")

    @property
    def rejudge_path(self) -> Path:
        return self.interim_file("answers_rejudge.jsonl")

    @property
    def rejudge_splits(self) -> tuple[str, ...]:
        """New-collection Audit E samples the stage uses (Stage 2 reuses Stage 1's)."""
        return ("b2b_main_rejudge",) + ((REJUDGE_S2_SPLIT,) if self.stage == 2 else ())

    @property
    def meta_path(self) -> Path:
        return self.interim_file("meta.json")

    @property
    def tag(self) -> str:
        if self.kind == "synthetic":
            return f" (SYNTHETIC/{self.world})"
        if self.kind == "explore":
            return " (EXPLORATION SPLIT: code check, not confirmatory)"
        return ""

    def datasets(self) -> tuple[str, ...]:
        if self.kind == "explore":
            return ("claude_b2b", "chatgpt_consumer", "chatgpt_agency")
        return tuple(d.name for d in DATASETS)


def add_mode_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True,
                    help="analysis stage (spec 'Two stages'): 1 run to run, 2 over time")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None,
                   help="run on a synthetic dry-run world (Stage 1: planted, broken_join; "
                        "Stage 2: planted_stable, planted_drift, broken_join)")
    g.add_argument("--split", choices=("explore",), default=None,
                   help="run on the exploration split (code check against exploration.md)")


def mode_from_args(a: argparse.Namespace) -> Mode:
    if a.synthetic:
        if a.synthetic not in STAGE_WORLDS[a.stage]:
            raise SystemExit(f"--synthetic {a.synthetic} is not a Stage {a.stage} world "
                             f"({', '.join(STAGE_WORLDS[a.stage])})")
        return Mode("synthetic", a.stage, a.synthetic)
    if a.split == "explore":
        if a.stage == 2:
            raise SystemExit("the exploration split has no Stage 2 (no new-collection waves)")
        return Mode("explore", a.stage)
    return Mode("confirmatory", a.stage)


# --------------------------------------------------------------------- io


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_csv(path: Path) -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def load_module(path: Path, name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def brands009():
    """009's self-contained lexicon module (load_lexicon, lexicon_extract, frozen v2.1)."""
    return load_module(SRC_009 / "pipeline/brands.py", "x009_brands")


def item_number(item_id: str) -> int | None:
    m = re.search(r"(\d+)$", item_id)
    return int(m.group(1)) if m else None


def rank_key(unit: str) -> str:
    """build_tasks.py's seeded order (the same SEED string)."""
    return hashlib.sha256(f"{SEED}:{unit}".encode()).hexdigest()


def placebo_halves(answers: list[dict]) -> dict[str, str]:
    """H_pla split (spec deviation 4): item_id -> "A" or "B".

    Prompts are split at random within each intent stratum (the B2B panel's
    "shortlist" and "evaluate" prompts; one stratum for the consumer and
    agency panels), in the seeded order sha256("<SEED>:placebo:<item_id>"):
    the first floor(n/2) of each stratum go to A. The frozen spec's odd/even
    split coincided with the intent split in the B2B panel, so it tested
    intent rather than chance.
    """
    strata: dict[object, set[str]] = {}
    for a in answers:
        strata.setdefault(a.get("intent"), set()).add(a["item_id"])
    out = {}
    for items in strata.values():
        order = sorted(items, key=lambda i: rank_key(f"placebo:{i}"))
        half = len(order) // 2
        out.update({i: ("A" if k < half else "B") for k, i in enumerate(order)})
    return out


def rejudge_sample(tasks: list[dict], share: float = AUDIT_E_SHARE) -> list[dict]:
    """Audit E: seeded share of the tasks, ordered as build_tasks.py --rejudge orders them."""
    n = int(round(share * len(tasks)))
    return sorted(tasks, key=lambda t: rank_key("rejudge:" + t["task_id"]))[:n]


# ------------------------------------------------------------- mappers
# A mapper takes (task, judge name) and returns lexicon canonicals the name
# matches, used when the judge did not tie a name to a tracked brand (as in
# 10_explore.py). Only a single unambiguous hit among the answer's lexicon
# brands is accepted.

Mapper = Callable[[dict, str], list[str]]


def holdout_mapper() -> Mapper:
    """The source studies' frozen lexicons: 005 (headphones, agencies), 009 v2.1 (B2B)."""
    b5 = load_module(SRC_005 / "pipeline/brands.py", "x005_brands")
    b9 = brands009()
    patterns, _, _ = b9.frozen_lexicon()

    def mapper(task: dict, name: str) -> list[str]:
        if task["dataset"] == "claude_b2b":
            return b9.lexicon_extract(name, patterns.get(task["category"], []))
        return b5.extract_brands(name, task["category"])

    return mapper


def lexicon_file_mapper(path: Path) -> tuple[Mapper, dict]:
    """Mapper over a lexicon CSV in 009's format (lexicon v3, or the synthetic one)."""
    b9 = brands009()
    patterns = b9.load_lexicon(path)

    def mapper(task: dict, name: str) -> list[str]:
        return b9.lexicon_extract(name, patterns.get(task["category"], []))

    return mapper, patterns


# --------------------------------------------------------------- answers

#: Audit A refusal heuristic (009's 01_features.py): an apology-shaped refusal
#: in the first 600 characters of the answer, and (deviation 7) no lexicon brand.
REFUSAL = re.compile(
    r"\b(?:I\s+(?:can(?:'|’)?t|cannot|am\s+unable\s+to|won(?:'|’)?t)|I(?:'|’)m\s+(?:not\s+able|unable)\s+to)"
    r"\s+(?:help|assist|provide|recommend|do\s+that|comply)",
    re.I,
)


_TASK_ID_FIELD = re.compile(r'^\{\s*"task_id"\s*:\s*"((?:[^"\\]|\\.)*)"')


def load_judged(path: Path, keep: set[str]) -> dict[str, dict]:
    """task_id -> judge record (an OK record wins over a failed retry), for kept ids only.

    A line whose leading ``task_id`` is not kept is skipped before it is
    parsed, so rows outside a stage's firewall are never decoded.
    """
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            m = _TASK_ID_FIELD.match(line)
            if m and json.loads(f'"{m.group(1)}"') not in keep:
                continue
            r = json.loads(line)
            tid = r.get("task_id")
            if tid not in keep:
                continue
            if r.get("ok") or tid not in out:
                out[tid] = r
    return out


def _norm_cat(c) -> str:
    return str(c or "").strip().lower().replace(" ", "_")


def build_rows(tasks: list[dict], judged: dict[str, dict], mapper: Mapper,
               intents: dict[str, str], models: dict[str, str | None],
               pass_name: str = "first") -> list[dict]:
    """One row per task (answer), the brand logic of 10_explore.build_answers.

    Lexicon brands (``order``) come from the task (its ``brands``: the frozen
    lexicon's first-mention order). A judge brand counts toward a lexicon
    brand through its ``canonical`` (the judge's tracked key) or, failing
    that, a single unambiguous lexicon match of its name. Several judge
    entries on one brand merge by cautioned > top > one of many > generic.
    Every judge name also feeds the all-brands view (R1), keyed by the
    canonical or a normalized spelling, in the judge's order. No answer or
    question text is kept.
    """
    rows = []
    for t in tasks:
        tid = t["task_id"]
        answer = t.get("answer") or ""
        empty = not answer.strip()
        r = judged.get(tid)
        ok = bool(r and r.get("ok"))
        order = list(t["brands"])
        present = set(order)
        cat: dict[str, str] = {}
        best_for: dict[str, list[str]] = {}
        caveat_types: dict[str, list[str]] = {}
        all_cat: dict[str, str] = {}
        untracked = fallback = n_brands = n_verified = 0
        for b in (r.get("brands") or []) if ok else []:
            n_brands += 1
            n_verified += bool(b.get("evidenceVerified"))
            canon = b.get("canonical")
            if not canon:
                hits = [h for h in mapper(t, b.get("name", "")) if h in present]
                if len(set(hits)) == 1:
                    canon = hits[0]
                    fallback += 1
                else:
                    untracked += 1
                    key = "x:" + re.sub(r"[^a-z0-9]+", "", str(b.get("name", "")).lower())
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
            caveat_types.setdefault(canon, []).extend(
                str(c.get("reasonType") or "unspecified") for c in (b.get("caveats") or [])
                if isinstance(c, dict))
        raw_brands = ((r.get("raw") or {}).get("brands") or []) if ok else []
        raw_top: list[str] = []
        n_raw_top = 0
        for b in raw_brands:
            if _norm_cat(b.get("category")) == "top_choice":
                n_raw_top += 1
                hits = [h for h in mapper(t, str(b.get("name", ""))) if h in present]
                if hits and hits[0] not in raw_top:
                    raw_top.append(hits[0])
        cats = {b: cat.get(b, "unclassified") for b in order}
        for b in order:
            all_cat.setdefault(b, "unclassified")
        rows.append({
            "task_id": tid, "pass": pass_name, "dataset": t["dataset"],
            "source_exp": str(t.get("source_exp")), "arm": t["arm"],
            "platform": t.get("platform"), "item_id": t["item_id"],
            "item_number": item_number(t["item_id"]), "category": t["category"],
            "intent": intents.get(t["item_id"]) if t["dataset"] in B2B_DATASETS else None,
            "wave": int(t["wave"]), "run_date": t.get("run_date"),
            "model": t.get("model") or models.get(tid),
            # Deviation 7: a refusal-shaped opening counts only when the answer
            # names no lexicon brand (clarifying openers that go on to answer stay).
            "empty": empty,
            "refusal": (not empty) and not order and bool(REFUSAL.search(answer[:600])),
            "refusal_phrase": (not empty) and bool(REFUSAL.search(answer[:600])),
            "judge_ok": ok,
            "judge_sha256": (r or {}).get("judge_sha256"), "judge_model": (r or {}).get("model"),
            "judge_version": (r or {}).get("version"), "dropped": (r or {}).get("dropped") or {},
            "order": order, "cats": cats,
            "best_for": {b: best_for.get(b, []) for b in order},
            "caveat_types": {b: caveat_types.get(b, []) for b in order},
            "all_order": list(all_cat), "all_cats": all_cat,
            "raw_top": raw_top, "n_raw_top_items": n_raw_top,
            "untracked_names": untracked, "fallback_mapped": fallback,
            "n_judge_brands": n_brands, "n_evidence_verified": n_verified,
        })
    return rows


def usable(a: dict) -> bool:
    """Audit A: refusals, empty answers and judge failures are flagged and excluded."""
    return a["judge_ok"] and not a["empty"] and not a["refusal"]


# ---------------------------------------------------------------- best for


@dataclass
class BestFor:
    norm: dict[str, str]
    seg_a: dict[str, dict[str, str]]
    seg_b: dict[str, dict[str, str]]
    taxonomy: dict
    phrases: dict


def load_bestfor(path: Path) -> BestFor | None:
    files = ("norm.json", "segments_a.json", "segments_b.json", "taxonomy.json", "phrases.json")
    if not all((path / f).exists() for f in files):
        return None
    return BestFor(*(json.loads((path / f).read_text()) for f in files))


#: Stage 2 best-for files (bestfor_stage2/). ``phrases.json`` holds only the
#: phrases Stage 1 did not classify (the input of bestfor_segments.mts
#: normalize and classify); ``phrases_used.json`` every distinct phrase Stage 2
#: uses; ``reuse.json`` the sha256 of the Stage 1 files whose classifications
#: are reused.
BESTFOR_S2_FILES = ("phrases.json", "phrases_used.json", "taxonomy.json", "reuse.json",
                    "norm.json", "segments_a.json", "segments_b.json")
BESTFOR_S1_FILES = ("norm.json", "segments_a.json", "segments_b.json", "taxonomy.json")


def stage1_bestfor_dir(mode: Mode) -> Path:
    return mode.raw / "bestfor_stage1"


def bestfor_file_shas(path: Path, files: Iterable[str] = BESTFOR_S1_FILES) -> dict[str, str]:
    return {f: sha256_file(path / f) for f in files if (path / f).exists()}


def load_stage_bestfor(mode: Mode) -> BestFor | None:
    """The stage's best-for maps. Stage 1 (and explore): the stage directory as
    is. Stage 2: Stage 1's classifications (reused, spec §5) merged with the
    Stage 2 classifications of the phrases Stage 1 did not see; ``phrases`` =
    every distinct phrase Stage 2 uses (what Audit G reports on)."""
    if mode.stage == 1 or mode.kind == "explore":
        return load_bestfor(mode.bestfor)
    s1 = load_bestfor(stage1_bestfor_dir(mode))
    d2 = mode.bestfor
    if s1 is None or not all((d2 / f).exists() for f in BESTFOR_S2_FILES):
        return None
    new = {f: json.loads((d2 / f).read_text()) for f in BESTFOR_S2_FILES}
    cats = set(s1.seg_a) | set(new["segments_a.json"])
    seg_a = {c: s1.seg_a.get(c, {}) | new["segments_a.json"].get(c, {}) for c in cats}
    seg_b = {c: s1.seg_b.get(c, {}) | new["segments_b.json"].get(c, {}) for c in cats}
    return BestFor(s1.norm | new["norm.json"], seg_a, seg_b, new["taxonomy.json"],
                   new["phrases_used.json"])


def bestfor_problems(mode: Mode) -> list[str]:
    """Why the stage's best-for files are not ready (empty list = ready)."""
    if mode.stage == 1 or mode.kind == "explore":
        bf = load_bestfor(mode.bestfor)
        if bf is None:
            return [f"best-for files missing under {mode.bestfor} (20_answers.py "
                    "--gather-bestfor, then bestfor_segments.mts normalize and classify "
                    "--pass a / --pass b with --split stage1)"]
        if mode.confirmatory and not instrument_problems() and bf.taxonomy != merged_stage_taxonomy():
            return ["bestfor_stage1/taxonomy.json is not the frozen B2B + exploration "
                    "taxonomy; re-run 20_answers.py --gather-bestfor"]
        return []
    d1, d2 = stage1_bestfor_dir(mode), mode.bestfor
    out = []
    if load_bestfor(d1) is None:
        out.append(f"the Stage 1 best-for files under {d1} are missing (Stage 2 reuses them)")
    if not all((d2 / f).exists() for f in ("phrases.json", "phrases_used.json", "taxonomy.json",
                                           "reuse.json")):
        out.append(f"Stage 2 best-for phrases are not gathered under {d2} (20_answers.py "
                   "--stage 2 --gather-bestfor)")
        return out
    missing = [f for f in ("norm.json", "segments_a.json", "segments_b.json")
               if not (d2 / f).exists()]
    if missing:
        out.append(f"Stage 2 best-for phrases are not classified yet ({', '.join(missing)} "
                   f"missing under {d2.name}/: bestfor_segments.mts normalize, classify --pass a, "
                   "classify --pass b, all with --split stage2)")
        return out
    todo = json.loads((d2 / "phrases.json").read_text())
    files = {f: json.loads((d2 / f).read_text()) for f in ("segments_a.json", "segments_b.json")}
    norm = json.loads((d2 / "norm.json").read_text())
    gaps = sum(1 for c, lst in todo.items() for e in lst
               if e["phrase"] not in norm or any(e["phrase"] not in files[f].get(c, {})
                                                  for f in files))
    if gaps:
        out.append(f"{gaps} new Stage 2 best-for phrases lack a normalized key or a classifier "
                   "pass; re-run normalize and classify --pass a and b with --split stage2")
    reuse = json.loads((d2 / "reuse.json").read_text())
    if reuse.get("stage1_sha256") != bestfor_file_shas(d1):
        out.append("the Stage 1 best-for files changed after the Stage 2 phrases were gathered; "
                   "re-run 20_answers.py --stage 2 --gather-bestfor")
    tax2 = json.loads((d2 / "taxonomy.json").read_text())
    tax1 = json.loads((d1 / "taxonomy.json").read_text()) if (d1 / "taxonomy.json").exists() else None
    if tax2 != tax1:
        out.append("bestfor_stage2/taxonomy.json differs from bestfor_stage1/taxonomy.json")
    if mode.confirmatory and not instrument_problems() and tax2 != merged_stage_taxonomy():
        out.append("bestfor_stage2/taxonomy.json is not the frozen B2B + exploration taxonomy")
    return out


def merged_stage_taxonomy(raw: Path | None = None) -> dict:
    """The Stage taxonomy file: the 20 frozen B2B taxonomies plus the frozen
    exploration taxonomies for headphones and agencies (spec §5)."""
    b2b = json.loads(TAXONOMY_B2B.read_text())
    explore = json.loads(TAXONOMY_EXPLORE.read_text())
    out = dict(b2b)
    for c in EXPLORE_TAXONOMY_CATEGORIES:
        out[c] = explore[c]
    return out


def _segment_ok(g: str | None) -> bool:
    return bool(g) and g not in ("other", "unassigned")


def derive(a: dict, bf: BestFor | None) -> dict:
    """Attach the spec §3 derived sets to an answer row (``a['S']``)."""
    order, cats = a["order"], a["cats"]
    rec = [b for b in order if cats[b] in REC]
    s: dict[str, set] = {
        "M": set(order),
        "R": set(rec),
        "T": {b for b in order if cats[b] == "top_choice"},
        "C": {b for b in order if cats[b] == "cautioned_against"},
        "G": {b for b in order if cats[b] == "generic_mention"},
        "P1": set(order[:1]),
        "Pk": {(b, i) for i, b in enumerate(order)},
        "Rpos": set(order[:len(rec)]),
    }
    wp, ws, wsb = set(), set(), set()
    if bf is not None:
        sa = bf.seg_a.get(a["category"], {})
        sb = bf.seg_b.get(a["category"], {})
        for b in rec:
            for p in a["best_for"].get(b, []):
                k = bf.norm.get(p)
                if k:
                    wp.add((b, k))
                if _segment_ok(sa.get(p)):
                    ws.add((b, sa[p]))
                if _segment_ok(sb.get(p)):
                    wsb.add((b, sb[p]))
    s["WP"], s["WS"], s["WSb"] = wp, ws, wsb
    ao, ac = a["all_order"], a["all_cats"]
    s["M_all"] = set(ao)
    s["R_all"] = {b for b in ao if ac[b] in REC}
    s["T_all"] = {b for b in ao if ac[b] == "top_choice"}
    s["C_all"] = {b for b in ao if ac[b] == "cautioned_against"}
    s["P1_all"] = set(ao[:1])
    s["Pk_all"] = {(b, i) for i, b in enumerate(ao)}
    a["S"] = s
    return a


def load_answers(mode: Mode, *, rejudge: bool = False, include_unusable: bool = False,
                 bf: BestFor | None = None) -> list[dict]:
    path = mode.rejudge_path if rejudge else mode.answers_path
    if not path.exists():
        if rejudge:
            return []
        raise SystemExit(f"no answer frame at {path}; run 20_answers.py first")
    rows = read_jsonl(path)
    if not include_unusable:
        rows = [a for a in rows if usable(a)]
    return [derive(a, bf) for a in rows]


# ------------------------------------------------------------------ pairs

Pair = tuple[dict, dict]


def run_key(a: dict) -> tuple[str, int]:
    """A run is (study, wave): within pairs need two different runs."""
    return (a["source_exp"], a["wave"])


def within_pairs(ans: list[dict], *, pool_arms: bool = False) -> list[Pair]:
    """Same prompt, same platform or arm, different waves (spec §3).

    ``pool_arms`` (R6) treats the given arms as one platform.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for a in ans:
        key = (a["dataset"], a["item_id"]) if pool_arms else (a["dataset"], a["arm"], a["item_id"])
        groups[key].append(a)
    out = []
    for g in groups.values():
        g = sorted(g, key=lambda a: (run_key(a), a["arm"]))
        out += [(x, y) for x, y in itertools.combinations(g, 2) if run_key(x) != run_key(y)]
    return out


def between_pairs(ans: list[dict]) -> list[Pair]:
    """Different prompts, same category, same platform, same wave (spec §3)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for a in ans:
        groups[(a["dataset"], a["arm"], *run_key(a), a["category"])].append(a)
    out = []
    for g in groups.values():
        out += [(x, y) for x, y in itertools.combinations(g, 2) if x["item_id"] != y["item_id"]]
    return out


def cross_pairs(ans: list[dict], partner: list[dict] | None = None) -> list[Pair]:
    """Different categories, same platform, same wave (spec §3, H_pos).

    With a ``partner`` dataset (chatgpt_consumer <-> chatgpt_agency), the
    pairs are one answer from each dataset in the same study wave.
    """
    out = []
    if partner is None:
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for a in ans:
            groups[(a["dataset"], a["arm"], *run_key(a))].append(a)
        for g in groups.values():
            out += [(x, y) for x, y in itertools.combinations(g, 2)
                    if x["category"] != y["category"]]
        return out
    by_run: dict[tuple, list[dict]] = defaultdict(list)
    for b in partner:
        by_run[(b["arm"], *run_key(b))].append(b)
    for a in ans:
        out += [(a, b) for b in by_run.get((a["arm"], *run_key(a)), [])
                if a["category"] != b["category"]]
    return out


def same_wave_pairs(a_ans: list[dict], b_ans: list[dict]) -> list[Pair]:
    """Same prompt, same wave, two platforms (cross-platform agreement)."""
    idx = {(b["item_id"], b["wave"]): b for b in b_ans}
    return [(a, idx[(a["item_id"], a["wave"])]) for a in a_ans
            if (a["item_id"], a["wave"]) in idx]


def cross_arm_pairs(ans: list[dict], arm_a: str, arm_b: str) -> list[Pair]:
    """Same prompt, two arms, any wave (10_explore's arm comparison)."""
    by_item: dict[str, list[dict]] = defaultdict(list)
    for a in ans:
        by_item[a["item_id"]].append(a)
    out = []
    for g in by_item.values():
        out += [(x, y) for x in g for y in g if x["arm"] == arm_a and y["arm"] == arm_b]
    return out


# ------------------------------------------------------------- bootstrap


@dataclass
class PairSet:
    n_pairs: int
    same: dict[str, np.ndarray]   # key -> (2, n): [num, den] for pairs inside one cluster
    diff: dict[str, np.ndarray]   # key -> (2, n, n): pairs across two clusters
    has_diff: bool
    ci: np.ndarray
    cj: np.ndarray
    jac: dict[str, np.ndarray]


def pair_values(x: dict, y: dict) -> dict[str, tuple[float, float]]:
    sx, sy = x["S"], y["S"]
    out = {}
    for k in SET_KEYS:
        a, b = sx[k], sy[k]
        out[k] = (2 * len(a & b), len(a) + len(b))
    for k, (src, dst) in DIRECTIONAL.items():
        out[k] = (len(sx[src] & sy[dst]) + len(sy[src] & sx[dst]), len(sx[src]) + len(sy[src]))
    return out


def jaccard(a: set, b: set) -> float:
    u = a | b
    return len(a & b) / len(u) if u else float("nan")


def build_pairset(pairs: list[Pair], idx: dict[str, int], unit_of: Callable[[dict], str]
                  ) -> PairSet:
    n = len(idx)
    m = len(pairs)
    ci = np.fromiter((idx[unit_of(x)] for x, _ in pairs), dtype=int, count=m)
    cj = np.fromiter((idx[unit_of(y)] for _, y in pairs), dtype=int, count=m)
    vals = np.zeros((len(PAIR_KEYS), 2, m))
    jac = {k: np.empty(m) for k in JACCARD_KEYS}
    for p, (x, y) in enumerate(pairs):
        v = pair_values(x, y)
        for q, k in enumerate(PAIR_KEYS):
            vals[q, 0, p], vals[q, 1, p] = v[k]
        for k in JACCARD_KEYS:
            jac[k][p] = jaccard(x["S"][k], y["S"][k])
    same_m = ci == cj
    same, diff = {}, {}
    for q, k in enumerate(PAIR_KEYS):
        s = np.zeros((2, n))
        np.add.at(s[0], ci[same_m], vals[q, 0, same_m])
        np.add.at(s[1], ci[same_m], vals[q, 1, same_m])
        d = np.zeros((2, n, n))
        np.add.at(d[0], (ci[~same_m], cj[~same_m]), vals[q, 0, ~same_m])
        np.add.at(d[1], (ci[~same_m], cj[~same_m]), vals[q, 1, ~same_m])
        same[k], diff[k] = s, d
    return PairSet(m, same, diff, bool((~same_m).any()), ci, cj, jac)


def boot_weights(strata: list[int], n_boot: int, seed: int = SEED) -> np.ndarray:
    """Cluster counts per draw: each stratum's clusters drawn with replacement."""
    rng = np.random.default_rng(seed)
    parts = [rng.multinomial(k, np.full(k, 1 / k), size=n_boot) for k in strata if k]
    return np.concatenate(parts, axis=1).astype(float)


@dataclass
class Est:
    """Point estimate plus bootstrap draws (NaN kept, so contrasts align draw by draw)."""
    point: float
    raw: np.ndarray

    @property
    def draws(self) -> np.ndarray:
        return self.raw[~np.isnan(self.raw)]

    def ci(self, alpha: float = ALPHA) -> tuple[float, float]:
        d = self.draws
        if d.size == 0 or not np.isfinite(self.point):
            return float("nan"), float("nan")
        lo, hi = np.quantile(d, [alpha / 2, 1 - alpha / 2])
        return float(lo), float(hi)

    def __sub__(self, other: Est) -> Est:
        return Est(self.point - other.point, self.raw - other.raw)


class Panel:
    """One resampling frame: clusters (prompts, or categories for R5), their
    bootstrap counts, and named pair sets built over them."""

    def __init__(self, strata: list[list[str]], *, unit_of: Callable[[dict], str] | None = None,
                 n_boot: int = N_BOOT, seed: int = SEED):
        self.units = [u for s in strata for u in s]
        self.idx = {u: i for i, u in enumerate(self.units)}
        self.unit_of = unit_of or (lambda a: a["item_id"])
        self.W = boot_weights([len(s) for s in strata], n_boot, seed)
        self.ones = np.ones((1, len(self.units)))
        self.sets: dict[str, PairSet] = {}
        self.pairs: dict[str, list[Pair]] = {}

    def add(self, name: str, pairs: list[Pair]) -> PairSet:
        self.pairs[name] = pairs
        self.sets[name] = build_pairset(pairs, self.idx, self.unit_of)
        return self.sets[name]

    @staticmethod
    def _ratio(ps: PairSet, key: str, W: np.ndarray) -> np.ndarray:
        s, d = ps.same[key], ps.diff[key]
        num = W @ s[0]
        den = W @ s[1]
        if ps.has_diff:
            num = num + np.einsum("bi,ij,bj->b", W, d[0], W)
            den = den + np.einsum("bi,ij,bj->b", W, d[1], W)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)

    def est(self, name: str, key: str) -> Est:
        ps = self.sets[name]
        return Est(float(self._ratio(ps, key, self.ones)[0]), self._ratio(ps, key, self.W))

    def appearances(self, name: str, key: str) -> int:
        """Denominator of the pooled ratio, unweighted (brand appearances in pairs)."""
        ps = self.sets[name]
        return int(ps.same[key][1].sum() + ps.diff[key][1].sum())


def unit_strata(ans: list[dict], partner: list[dict] | None = None,
                unit_of: Callable[[dict], str] | None = None) -> list[list[str]]:
    unit_of = unit_of or (lambda a: a["item_id"])
    strata = [sorted({unit_of(a) for a in ans})]
    if partner:
        strata.append(sorted({unit_of(a) for a in partner} - set(strata[0])))
    return strata


# ------------------------------------------------------------- decisions

MARGIN_LABELS = {
    "SUPPORTED": "Supported: more stable by more than 0.10",
    "SMALLER": "More stable, possibly by less than 0.10",
    "NOT_SHOWN": "Not shown",
    "NA": "Not estimable (no appearances)",
}
EQ_LABELS = {
    "NULL": "Practically equivalent (null)",
    "NEGLIGIBLE": "Detectable but negligible",
    "REAL": "Real change: report it",
    "INCONCLUSIVE": "Inconclusive: do not claim a null",
    "NA": "Not estimable (no appearances)",
}
BOUND_LABELS = {"SUPPORTED": "Supported", "NOT_SUPPORTED": "Not supported",
                "NA": "Not estimable (no appearances)"}

DECISION_TABLE = """| Test | Result | Conclusion |
|---|---|---|
| Margin (H1, H2, H7) | lower bound above 0.10 | Supported: more stable by more than 0.10 |
| | lower bound in (0, 0.10] | More stable, possibly by less than 0.10 |
| | CI includes 0 | Not shown |
| Equivalence (H5, H6, H_pla) | CI inside the band | Practically equivalent (null) |
| | CI excludes 0, inside band | Detectable but negligible |
| | CI excludes 0, extends beyond band | Real change: report it |
| | CI includes 0, extends beyond band | **Inconclusive: do not claim a null** |
| Non-superiority (H3) | upper bound below +0.10 | Supported |
| Level (H4) | lower bound at least 0.90 | Supported |"""


def _nan(*xs: float) -> bool:
    return any(not np.isfinite(x) for x in xs)


def margin_verdict(lo: float, hi: float, margin: float = MARGIN) -> str:
    """Spec §5 margin rule. A CI entirely below 0 is also 'Not shown'."""
    if _nan(lo, hi):
        return "NA"
    if lo > margin:
        return "SUPPORTED"
    if lo > 0:
        return "SMALLER"
    return "NOT_SHOWN"


def eq_verdict(lo: float, hi: float, band: float) -> str:
    if _nan(lo, hi):
        return "NA"
    inside = lo > -band and hi < band
    nonzero = lo > 0 or hi < 0
    if inside:
        return "NEGLIGIBLE" if nonzero else "NULL"
    return "REAL" if nonzero else "INCONCLUSIVE"


def nonsup_verdict(lo: float, hi: float, margin: float = NONSUP_MARGIN) -> str:
    if _nan(lo, hi):
        return "NA"
    return "SUPPORTED" if hi < margin else "NOT_SUPPORTED"


def level_verdict(lo: float, hi: float, level: float = H4_LEVEL) -> str:
    if _nan(lo, hi):
        return "NA"
    return "SUPPORTED" if lo >= level else "NOT_SUPPORTED"


def p_margin(e: Est, margin: float = MARGIN) -> float:
    """One-sided margin test p: share of draws at or below the margin (spec §5)."""
    d = e.draws
    return float((d <= margin).mean()) if d.size else float("nan")


def p_tost(e: Est, band: float) -> float:
    """TOST p: the larger of the two tail shares at the band edges (spec §5)."""
    d = e.draws
    return float(max((d <= -band).mean(), (d >= band).mean())) if d.size else float("nan")


def p_nonsup(e: Est, margin: float = NONSUP_MARGIN) -> float:
    d = e.draws
    return float((d >= margin).mean()) if d.size else float("nan")


def p_level(e: Est, level: float = H4_LEVEL) -> float:
    d = e.draws
    return float((d < level).mean()) if d.size else float("nan")


# ------------------------------------------------------------- formatting


def fmt(x, nd: int = 2) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"{x:.{nd}f}"


def fmt_ci(est: float, lo: float, hi: float, nd: int = 2) -> str:
    return f"{fmt(est, nd)} [{fmt(lo, nd)}, {fmt(hi, nd)}]"


def pct(x: float) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"


# ------------------------------------------------------------ test suite

#: (test id, kind, a key, b key or None, threshold, short label)
SUITE = (
    ("H1", "margin", "R", "Pk", MARGIN, "shortlist minus exact position"),
    ("H2", "margin", "R", "T", MARGIN, "shortlist minus top choice"),
    ("H3", "nonsup", "T", "P1", NONSUP_MARGIN, "top choice minus rank 1"),
    ("H4", "level", "T>R", None, H4_LEVEL, "top choice stays recommended"),
    ("H6", "equiv", "R", "M", EQ_BAND, "shortlist minus mentioned"),
    ("H7", "margin", "R", "WS", MARGIN, "shortlist minus best-for use case"),
)


def test_row(test: str, kind: str, e: Est, threshold: float, *, alpha: float = ALPHA) -> dict:
    lo, hi = e.ci(alpha)
    if kind == "margin":
        v, labels, p = margin_verdict(lo, hi, threshold), MARGIN_LABELS, p_margin(e, threshold)
    elif kind == "equiv":
        v, labels, p = eq_verdict(lo, hi, threshold), EQ_LABELS, p_tost(e, threshold)
    elif kind == "nonsup":
        v, labels, p = nonsup_verdict(lo, hi, threshold), BOUND_LABELS, p_nonsup(e, threshold)
    else:
        v, labels, p = level_verdict(lo, hi, threshold), BOUND_LABELS, p_level(e, threshold)
    return {"test": test, "kind": kind, "estimate": e.point, "lo": lo, "hi": hi,
            "ci_level": 1 - alpha, "p": p, "threshold": threshold, "verdict": v,
            "label": labels[v], "n_draws": int(e.draws.size)}


def run_suite(panel: Panel, dataset: str, *, keys: dict | None = None, name: str = "within",
              tests: Iterable[str] | None = None) -> tuple[list[dict], dict[str, Est]]:
    """The Stage 1 tests on one panel's within pairs (unadjusted 90% CIs)."""
    keys = keys or PRIMARY_KEYS
    wanted = set(tests) if tests else {t[0] for t in SUITE}
    rows, ests = [], {}
    for test, kind, a, b, thr, label in SUITE:
        if test not in wanted or keys.get(a) is None or (b and keys.get(b) is None):
            continue
        e = panel.est(name, keys[a])
        if b:
            e = e - panel.est(name, keys[b])
        row = test_row(test, kind, e, thr) | {"dataset": dataset, "label_short": label,
                                              "n_pairs": panel.sets[name].n_pairs}
        rows.append(row)
        ests[test] = e
    return rows, ests


def suite_line(row: dict) -> str:
    return (f"{row['test']} {row['label_short']}: {fmt_ci(row['estimate'], row['lo'], row['hi'])}"
            f" -> {row['label']}")


# --------------------------------------------------------------- panels


def primary_answers(ans: list[dict], dataset: str) -> list[dict]:
    spec = SPEC[dataset]
    return [a for a in ans if a["dataset"] == dataset and a["arm"] == spec.arm]


def dataset_panel(ans: list[dict], dataset: str, *, n_boot: int = N_BOOT,
                  by_category: bool = False, with_baselines: bool = True,
                  sub: list[dict] | None = None) -> Panel:
    """The standard panel for a dataset: within, between and cross pair sets.

    ``sub`` replaces the dataset's primary answers (robustness subsets).
    ``by_category`` resamples categories instead of prompts (R5).
    """
    spec = SPEC[dataset]
    own = sub if sub is not None else primary_answers(ans, dataset)
    partner = primary_answers(ans, spec.partner) if spec.partner else None
    unit_of = (lambda a: a["category"]) if by_category else None
    panel = Panel(unit_strata(own, partner, unit_of), unit_of=unit_of, n_boot=n_boot)
    panel.add("within", within_pairs(own))
    if with_baselines:
        panel.add("between", between_pairs(own))
        panel.add("cross", cross_pairs(own, partner))
    return panel


def model_modal(ans: list[dict]) -> str | None:
    c = Counter(a["model"] for a in ans if a.get("model"))
    return c.most_common(1)[0][0] if c else None


# ------------------------------------------------------------------ gates


def instrument_problems() -> list[str]:
    """Reasons confirmatory instruments are not usable (empty list = go).

    Checks only constants and the instrument files, never a judged file.
    """
    problems = []
    if LEXICON_V3_SHA256 is None:
        problems.append("lexicon v3 is not frozen: harness/instrument.py LEXICON_V3_SHA256 is None (spec §5 "
                        "lexicon protocol; record the sha256 of data/raw/lexicon_v3/"
                        "lexicon_v3.csv at STOP 2)")
    elif not LEXICON_V3.exists():
        problems.append(f"{LEXICON_V3} is missing")
    elif sha256_file(LEXICON_V3) != LEXICON_V3_SHA256:
        problems.append("lexicon_v3.csv does not match LEXICON_V3_SHA256")
    if TAXONOMY_B2B_SHA256 is None:
        problems.append("the B2B best-for taxonomy is not frozen: harness/instrument.py TAXONOMY_B2B_SHA256 is "
                        "None (spec §5 taxonomy protocol; record the sha256 of data/raw/"
                        "bestfor_taxonomy_b2b/taxonomy.json at STOP 2)")
    elif not TAXONOMY_B2B.exists():
        problems.append(f"{TAXONOMY_B2B} is missing")
    elif sha256_file(TAXONOMY_B2B) != TAXONOMY_B2B_SHA256:
        problems.append("bestfor_taxonomy_b2b/taxonomy.json does not match TAXONOMY_B2B_SHA256")
    if not TAXONOMY_EXPLORE.exists() or sha256_file(TAXONOMY_EXPLORE) != TAXONOMY_EXPLORE_SHA256:
        problems.append("bestfor_explore/taxonomy.json is missing or changed since exploration")
    return problems


def refuse(problems: list[str], who: str, code: int = 3) -> None:
    print(f"{who} refuses to run on the confirmatory data yet:", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    sys.exit(code)


def analysis_gate(mode: Mode, n_boot: int) -> list[str]:
    """Reasons a stage that computes metrics may not run yet (spec §5, §8)."""
    problems: list[str] = []
    if n_boot != N_BOOT and mode.kind != "synthetic":
        problems.append(f"--n-boot {n_boot} != the pre-registered {N_BOOT}")
    if not mode.meta_path.exists():
        problems.append(f"no {mode.meta_path.name}; run 20_answers.py first")
        return problems
    meta = json.loads(mode.meta_path.read_text())
    if meta.get("mode") != mode.kind or meta.get("stage") != mode.stage:
        problems.append(f"{mode.answers_path.name} was built in another mode or stage")
    if not mode.confirmatory:
        if mode.kind == "synthetic" and mode.stage == 2:
            # the Stage 2 dry run exercises the same input gates as real data
            problems += bestfor_problems(mode)
            if not meta.get("stage2_inputs_complete"):
                problems.append("the synthetic Stage 2 frame lacks its Stage 2 inputs")
        return problems
    problems += instrument_problems()
    if meta.get("lexicon_v3_sha256") != LEXICON_V3_SHA256:
        problems.append("the answer frame was built with another lexicon v3; rebuild it")
    if meta.get("taxonomy_b2b_sha256") != TAXONOMY_B2B_SHA256:
        problems.append("the answer frame was built with another B2B taxonomy; rebuild it")
    if meta.get("max_new_wave", 99) > max(STAGE_WAVES[mode.stage]):
        problems.append("the answer frame holds new-collection waves beyond the stage firewall")
    problems += audit_d_problems(mode)
    problems += bestfor_problems(mode)
    for split in (*mode.rejudge_splits, "holdout_rejudge"):
        if not (mode.raw / f"judged_{split}.jsonl").exists():
            problems.append(f"Audit E re-judge output judged_{split}.jsonl is missing")
    if mode.stage == 2 and not meta.get("stage2_inputs_complete"):
        problems.append("the Stage 2 answer frame was built before every wave 8 to 11 task and "
                        "the Stage 2 re-judge sample were judged OK; rebuild it")
    return problems


def stage2_input_problems(raw: Path, tasks: list[dict]) -> list[str]:
    """Stage 2 inputs (spec §8 step 7): the Stage 2 Audit E sample judged OK,
    then every wave 8 to 11 task judged OK. Checks the cheap files first, so
    the main judged file is opened only once the re-judge sample is complete.
    ``tasks`` are the new-collection tasks of waves 1 to 11."""
    s2 = [t for t in tasks if int(t["wave"]) in STAGE2_NEW_WAVES]
    want = 3 * PROMPTS_PER_WAVE * len(STAGE2_NEW_WAVES)
    if len(s2) != want:
        return [f"tasks_b2b_main.jsonl holds {len(s2)} wave 8 to 11 tasks, expected {want}"]
    rj_tasks = raw / f"tasks_{REJUDGE_S2_SPLIT}.jsonl"
    if not rj_tasks.exists():
        return [f"the Stage 2 Audit E sample {rj_tasks.name} is missing (20_answers.py --stage 2 "
                "--write-rejudge-sample)"]
    expect = rejudge_sample(s2)
    got = read_jsonl(rj_tasks)
    if [t["task_id"] for t in got] != [t["task_id"] for t in expect]:
        return [f"{rj_tasks.name} is not the seeded 10% sample of waves 8 to 11"]
    rj_judged = raw / f"judged_{REJUDGE_S2_SPLIT}.jsonl"
    rj = load_judged(rj_judged, {t["task_id"] for t in got})
    bad = [t["task_id"] for t in got if not (rj.get(t["task_id"]) or {}).get("ok")]
    if bad:
        return [f"{len(bad)} of {len(got)} Stage 2 re-judge tasks are not judged OK in "
                f"{rj_judged.name} (judge_runner.mts --split {REJUDGE_S2_SPLIT})"]
    main = load_judged(raw / "judged_b2b_main.jsonl", {t["task_id"] for t in s2})
    bad = [t["task_id"] for t in s2 if not (main.get(t["task_id"]) or {}).get("ok")]
    if bad:
        return [f"{len(bad)} of {len(s2)} wave 8 to 11 tasks are not judged OK in "
                "judged_b2b_main.jsonl (judge_runner.mts --split b2b_main)"]
    return []


# ------------------------------------------------------------- Stage 2 lags


def lag_days(x: dict, y: dict) -> int:
    """Days between the two answers' run dates (spec §3; true dates, deviation 2)."""
    return abs((date.fromisoformat(x["run_date"]) - date.fromisoformat(y["run_date"])).days)


def nominal_lag(x: dict, y: dict) -> int:
    """Days between the two answers' scheduled wave days (new collection only)."""
    return abs(WAVE_OFFSETS[x["wave"] - 1] - WAVE_OFFSETS[y["wave"] - 1])


def in_days(lag: int, bounds: tuple[int, int | None]) -> bool:
    lo, hi = bounds
    return lag >= lo and (hi is None or lag <= hi)


def days_label(bounds: tuple[int, int | None]) -> str:
    lo, hi = bounds
    if hi is None:
        return f"{lo}+ days"
    return f"{lo} day{'s' if lo != 1 else ''}" if lo == hi else f"{lo} to {hi} days"


def h5_wave_counts(rows: list[dict]) -> dict[tuple[str, int], int]:
    """(new dataset, wave) -> answers collected non-empty and not refused (Audit A)."""
    out: Counter = Counter()
    for r in rows:
        if r["dataset"] in NEW_DATASETS:
            out[(r["dataset"], r["wave"])] += int(not r["empty"] and not r["refusal"])
    return dict(out)


def h5_excluded(rows: list[dict]) -> set[tuple[str, int]]:
    """Audit A (spec §2): a wave below 36 of 40 on a platform leaves H5's lag bins
    for that platform (it stays everywhere else). ``rows`` = the whole frame,
    flagged answers included."""
    return {k for k, n in h5_wave_counts(rows).items() if n < AUDIT_A_H5_MIN}


def bin_pairs(pairs: list[Pair], bounds: tuple[int, int | None],
              excluded: set[tuple[str, int]] = frozenset()) -> list[Pair]:
    return [(x, y) for x, y in pairs
            if (x["dataset"], x["wave"]) not in excluded and (y["dataset"], y["wave"]) not in excluded
            and in_days(lag_days(x, y), bounds)]


def h5_bins_for(dataset: str) -> tuple[tuple[int, int | None], tuple[int, int | None]]:
    return (H5_CONSUMER_NEAR, H5_CONSUMER_FAR) if dataset == H5_CONSUMER else (H5_NEAR, H5_FAR)


def h5_panel(own: list[dict], dataset: str, *, excluded: set[tuple[str, int]],
             bins: tuple | None = None, n_boot: int = N_BOOT, by_category: bool = False,
             halves: dict[str, str] | None = None) -> Panel:
    """A panel with the ``near`` and ``far`` within-prompt pair sets of H5.

    ``halves`` (Stage 2 H_pla) adds ``near_A``/``far_A``/``near_B``/``far_B``.
    """
    near_b, far_b = bins or h5_bins_for(dataset)
    unit_of = (lambda a: a["category"]) if by_category else None
    panel = Panel(unit_strata(own, None, unit_of), unit_of=unit_of, n_boot=n_boot)
    pairs = within_pairs(own)
    near, far = bin_pairs(pairs, near_b, excluded), bin_pairs(pairs, far_b, excluded)
    panel.add("near", near)
    panel.add("far", far)
    if halves is not None:
        for h in ("A", "B"):
            panel.add(f"near_{h}", [p for p in near if halves[p[0]["item_id"]] == h])
            panel.add(f"far_{h}", [p for p in far if halves[p[0]["item_id"]] == h])
    return panel


def h5_est(panel: Panel, key: str, suffix: str = "") -> Est:
    """H5 contrast: retention over far pairs minus retention over near pairs."""
    return panel.est(f"far{suffix}", key) - panel.est(f"near{suffix}", key)


def h5_row(panel: Panel, dataset: str, key: str, *, test: str = "H5",
           band: float = EQ_BAND) -> tuple[dict, Est]:
    """H5 for one status (unadjusted 90% CI), with the two bin levels and pair counts."""
    e = h5_est(panel, key)
    row = test_row(test, "equiv", e, band)
    n_items = len({x["item_id"] for x, _ in panel.pairs["near"] + panel.pairs["far"]}) or 1
    near, far = panel.est("near", key), panel.est("far", key)
    row |= {"dataset": dataset, "key": key, "near": [near.point, *near.ci()],
            "far": [far.point, *far.ci()], "near_pairs": panel.sets["near"].n_pairs,
            "far_pairs": panel.sets["far"].n_pairs,
            "near_per_prompt": panel.sets["near"].n_pairs / n_items,
            "far_per_prompt": panel.sets["far"].n_pairs / n_items,
            "near_appearances": panel.appearances("near", key),
            "far_appearances": panel.appearances("far", key)}
    return row, e


def lag_regression(own: list[dict], key: str, *, excluded: set[tuple[str, int]],
                   n_boot: int = N_BOOT) -> tuple[Est, int]:
    """R7: weighted least-squares slope of pair retention on lag (days), every
    within-prompt pair. Pair retention = 2|A & B| / (|A| + |B|), weighted by
    |A| + |B| (so the fit is the pooled-Dice analogue); the slope's interval
    is the prompt-level cluster bootstrap. Returns the slope per day."""
    strata = unit_strata(own)
    idx = {u: i for i, u in enumerate(strata[0])}
    n = len(idx)
    sums = np.zeros((5, n))  # w, w*x, w*y, w*x^2, w*x*y with w = den, w*y = num
    pairs = [p for p in within_pairs(own)
             if (p[0]["dataset"], p[0]["wave"]) not in excluded
             and (p[1]["dataset"], p[1]["wave"]) not in excluded]
    for x, y in pairs:
        num, den = pair_values(x, y)[key]
        if not den:
            continue
        lag = lag_days(x, y)
        i = idx[x["item_id"]]
        sums[:, i] += (den, den * lag, num, den * lag * lag, num * lag)
    W = boot_weights([n], n_boot)

    def slope(Wm: np.ndarray) -> np.ndarray:
        s = Wm @ sums.T
        sw, sx, sy, sxx, sxy = s.T
        d = sw * sxx - sx * sx
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(d > 0, (sw * sxy - sx * sy) / np.where(d > 0, d, 1), np.nan)

    return Est(float(slope(np.ones((1, n)))[0]), slope(W)), len(pairs)


def audit_d_problems(mode: Mode) -> list[str]:
    if mode.audit_d is None:
        return []
    if not mode.audit_d.exists():
        return [f"Audit D is not scored ({mode.audit_d} missing; harness script)"]
    score = json.loads(mode.audit_d.read_text())
    out = []
    if not score.get("passes"):
        out.append("Audit D did not pass (precision >= 0.95 and recall >= 0.90)")
    if not score.get("signed_by"):
        out.append("Audit D is not signed (signed_by)")
    if mode.confirmatory and score.get("lexicon_sha256") != LEXICON_V3_SHA256:
        out.append("Audit D was scored against another lexicon file than the frozen lexicon v3")
    return out


def bestfor_coverage(ans: list[dict], bf: BestFor) -> tuple[int, int]:
    """(recommended phrases classified, recommended phrases) over the answers."""
    have = tot = 0
    for a in ans:
        seg = bf.seg_a.get(a["category"], {})
        for b in a["order"]:
            if a["cats"][b] in REC:
                for p in a["best_for"].get(b, []):
                    tot += 1
                    have += p in seg
    return have, tot


# ---------------------------------------------------------------- audit E


def audit_e(first: list[dict], second: list[dict]) -> dict:
    """Judge test-retest on identical answer text (spec §2 Audit E, as 10_explore).

    Category agreement and Cohen's kappa over lexicon brand mentions (labels
    include ``unclassified``), plus how often a first-pass top choice is a top
    choice again.
    """
    by_id = {a["task_id"]: a for a in first}
    pairs = [(by_id[b["task_id"]], b) for b in second if b["task_id"] in by_id]
    labels = [*CATS, "unclassified"]
    conf: Counter = Counter()
    for x, y in pairs:
        for b in x["order"]:
            conf[(x["cats"][b], y["cats"].get(b, "unclassified"))] += 1
    n = sum(conf.values())
    agree = sum(c for (u, v), c in conf.items() if u == v)
    po = agree / n if n else float("nan")
    px = Counter()
    py = Counter()
    for (u, v), c in conf.items():
        px[u] += c
        py[v] += c
    pe = sum(px[c] * py[c] for c in labels) / n ** 2 if n else float("nan")
    kappa = (po - pe) / (1 - pe) if n and pe < 1 else float("nan")
    top_n = sum(c for (u, _), c in conf.items() if u == "top_choice")
    top_kept = conf[("top_choice", "top_choice")]
    return {"answers": len(pairs), "mentions": n, "agreement": po, "kappa": kappa,
            "top_choices": top_n, "top_kept": top_kept / top_n if top_n else float("nan"),
            "changes": {f"{u} -> {v}": c for (u, v), c in sorted(conf.items(), key=lambda kv: -kv[1])
                        if u != v},
            "pairs": pairs}
