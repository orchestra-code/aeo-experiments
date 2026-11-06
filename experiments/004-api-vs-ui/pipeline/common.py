"""Shared paths, constants, arm roles and loaders for experiment 004's study pipeline.

Design (spec §1): 009's 40 B2B prompts x 3 waves x 5 arms. Per platform, the UI scrape is
the reference (``cg_ui``, ``gm_ui``) and the API arms are compared with it. Stage 01 writes
one row per answer to ``frame.jsonl``; stages 02 and 03 read only that frame.

Modes (each stage takes at most one):

- real (default): the main-study ledgers and responses in ``exp004.RAW`` (main checkout,
  gitignored), frame in the main checkout's ``data/interim/`` next to it, reports in this
  checkout's ``results/`` (aggregates only).
- ``--synthetic <world>``: a fake world written by ``synthetic.py`` through the real wave
  driver, under ``data/interim/synthetic/<world>/`` of this checkout, reports under
  ``results/synthetic/<world>/`` (both gitignored).
- ``--pilot``: the feasibility run's ledgers, as a sanity check of the gap code only. The
  pilot's three same-day UI rounds stand in for waves, and each API arm's single answer is
  set against every round (``replicated``), which is how ``pilot_report.py`` paired them.
  Its frame and outputs stay in this checkout's ``data/interim/pilot/`` (gitignored).

The bootstrap, Holm step and pair helpers are 011's frozen code (``m011``), loaded by path;
004 passes its own seed and draws to them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

EXP = Path(__file__).resolve().parents[1]
HARNESS = EXP / "harness"
sys.path.insert(0, str(HARNESS))
import exp004  # noqa: E402

RESULTS = EXP / "results"
EXP011_PIPELINE = EXP.parent / "011-claude-code-fidelity" / "pipeline"

SYNTHETIC_WORLDS = ("planted", "planted_flip", "broken_join")
#: Tests point the synthetic worlds at a temporary directory with this variable.
SYNTHETIC_ROOT_ENV = "EXP004_SYNTHETIC_ROOT"

# ------------------------------------------------------------- constants

SEED = exp004.STUDY_SEED  # 20261106, spec header
N_BOOT = 2000             # spec §5
ALPHA = 0.10              # 90% percentile CI unless a test says otherwise
SESOI = 0.10              # absolute Jaccard, spec §5
TOP_K = 10                # R1
RBO_P = 0.9               # spec §3
NO_SEARCH_MAX = 0.30      # Audit A
H_POS_MIN = 0.10          # spec §4
WAVES = exp004.STUDY_WAVES
#: The lexicon the confirmatory model must use. Lexicon v3 until §5's coverage check says
#: otherwise; an extension updates this pin (and the spec) before any confirmatory metric.
STUDY_LEXICON = exp004.LEXICON_V3
STUDY_LEXICON_SHA256 = exp004.LEXICON_V3_SHA256
PILOT_SEED = exp004.SEED  # 20261105, the pilot report's bootstrap seed

# ------------------------------------------------------------------ arms


@dataclass(frozen=True)
class Platform:
    name: str
    label: str
    ref: str
    primary: tuple[str, ...]


PLATFORMS = {
    "chatgpt": Platform("chatgpt", "ChatGPT", "cg_ui", ("cg_api_low", "cg_api_plain")),
    "gemini": Platform("gemini", "Gemini", "gm_ui", ("gm_api_plain",)),
}
ALL_ARMS = exp004.STUDY_ARMS
API_ARMS = exp004.STUDY_API_ARMS
UI_ARMS = tuple(p.ref for p in PLATFORMS.values())
H2_PAIR = ("cg_api_low", "cg_api_plain")
UI_MODEL_EXPECTED = exp004.UI_MODEL_EXPECTED
PILOT_ITEMS = exp004.PILOT_ITEMS

#: Markers inside fake answers and queries; the dry run asserts neither reaches a frame or
#: report, the rule real answers and queries follow. Fake brand names start with "Zq".
SYNTH_ANSWER_MARK = "ANSWERTEXTMARKER"
SYNTH_QUERY_MARK = "QUERYTEXTMARKER"
SYNTH_BRAND_PREFIX = "Zq"


def platform_of(arm: str) -> str:
    return exp004.ARMS[arm].platform


# ------------------------------------------------------------- 011 code


def _load_011():
    """011's ``03_model`` (bootstrap, Holm, pair helpers), with its own ``common`` and
    ``brands``. Those names are swapped out of ``sys.modules`` while it loads, so neither
    module is confused with 004's."""
    shadow = ("common", "brands")
    saved = {n: sys.modules.pop(n) for n in shadow if n in sys.modules}
    sys.path.insert(0, str(EXP011_PIPELINE))
    try:
        spec = importlib.util.spec_from_file_location("exp011_model_for_004",
                                                      EXP011_PIPELINE / "03_model.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        brands011 = sys.modules["brands"]
    finally:
        sys.path.remove(str(EXP011_PIPELINE))
        for n in shadow:
            sys.modules.pop(n, None)
        sys.modules.update(saved)
    return module, brands011


m011, brands011 = _load_011()
if (m011.ALPHA, m011.SESOI, m011.TOP_K, m011.RBO_P, m011.H_POS_MIN) != (ALPHA, SESOI, TOP_K, RBO_P,
                                                                       H_POS_MIN):
    raise SystemExit("011's constants differ from 004's; its helpers cannot be reused as is")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: 009's matcher and 010's new-collection extraction, the pilot's instruments.
b9 = _load("exp009_brands_for_004", exp004.EXP009 / "pipeline" / "brands.py")
instrument010 = _load("exp010_instrument_for_004", exp004.EXP010 / "harness" / "instrument.py")


def extract(text: str, patterns: list) -> list[str]:
    """Lexicon brands in first-mention order: 010's ``extract_new`` (citation links out)."""
    return instrument010.extract_new(b9, text, patterns)


# ----------------------------------------------------------------- paths


def interim_root() -> Path:
    """The real frame lives beside the raw data (main checkout, gitignored)."""
    return exp004.RAW.parent / "interim"


def synthetic_root(kind: str) -> Path:
    root = os.environ.get(SYNTHETIC_ROOT_ENV)
    if root:
        return Path(root) / kind
    return (EXP / "data" / "interim" / "synthetic") if kind == "interim" else RESULTS / "synthetic"


@dataclass(frozen=True)
class Mode:
    """One pipeline run's inputs and outputs."""

    synthetic: str | None = None
    pilot: bool = False

    @property
    def label(self) -> str:
        return f"synthetic/{self.synthetic}" if self.synthetic else ("pilot" if self.pilot else "study")

    @property
    def interim(self) -> Path:
        if self.synthetic:
            return synthetic_root("interim") / self.synthetic
        return EXP / "data" / "interim" / "pilot" if self.pilot else interim_root()

    @property
    def raw(self) -> Path:
        return self.interim / "raw" if self.synthetic else exp004.RAW

    @property
    def results(self) -> Path:
        if self.synthetic:
            return synthetic_root("results") / self.synthetic
        return self.interim / "results" if self.pilot else RESULTS

    @property
    def frame_path(self) -> Path:
        return self.interim / "frame.jsonl"

    @property
    def meta_path(self) -> Path:
        return self.interim / "frame_meta.json"


def add_mode_args(ap) -> None:
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    g.add_argument("--pilot", action="store_true",
                   help="the feasibility run's data, for the gap reproduction check only")


def mode_from(args) -> Mode:
    return Mode(synthetic=args.synthetic, pilot=bool(getattr(args, "pilot", False)))


# ----------------------------------------------------------------- frames

LIST_COLUMNS = ("brands", "brands_markup", "brands_all", "cited_domains", "evaluated_domains")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_frame(df: pd.DataFrame, meta: dict, mode: Mode) -> None:
    mode.interim.mkdir(parents=True, exist_ok=True)
    with mode.frame_path.open("w") as f:
        for rec in df.to_dict("records"):
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    mode.meta_path.write_text(json.dumps(meta, indent=1, default=str) + "\n")


def load_frame(mode: Mode) -> tuple[pd.DataFrame, dict]:
    if not mode.frame_path.exists():
        raise SystemExit(f"no frame at {mode.frame_path}; run 01_frame.py first")
    recs = [json.loads(x) for x in mode.frame_path.read_text().splitlines() if x.strip()]
    df = pd.DataFrame(recs)
    for col in LIST_COLUMNS:
        if col in df.columns:
            df[col] = df[col].map(lambda v: v if isinstance(v, list) else None).astype(object)
    meta = json.loads(mode.meta_path.read_text())
    return df.sort_values(["arm", "wave", "item_id"]).reset_index(drop=True), meta


def item_number(item_id: str) -> int:
    return m011.item_number(item_id)


def md_table(df: pd.DataFrame, digits: int = 3) -> str:
    return m011.md_table(df, digits)


def jsonable(x):
    return m011.jsonable(x)


def num_mean(s: pd.Series) -> float:
    values = pd.to_numeric(s, errors="coerce")
    return float(values.mean()) if values.notna().any() else float("nan")


def arm_order(df: pd.DataFrame, col: str = "arm") -> pd.DataFrame:
    order = {a: i for i, a in enumerate(ALL_ARMS)}
    by = [col] + (["wave"] if "wave" in df.columns else [])
    return df.sort_values(by=by, key=lambda s: s.map(order) if s.name == col else s,
                          kind="stable").reset_index(drop=True)


def fmt(x, nd: int = 3, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"
