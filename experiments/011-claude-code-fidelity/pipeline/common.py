"""Shared paths, constants, arm roles, URL handling and loaders for experiment 011.

Design (spec §0, Arms table): 009's 40 synthetic B2B software prompts x 3 waves through
``ui_default`` (claude.ai by hand, the reference), ``cc_stock_full`` and ``cc_none_search``
(local Claude Code), ``sched_kit`` (scheduled task) and ``opus55_plain`` (API). One row per
answer comes out of stage 01 as ``data/interim/features.jsonl``.

Only waves 1 to 3 are read. Wave 0 (pilot) and wave 91 (usage check) never enter this
pipeline.

Synthetic dry-run frames (spec §8 step 3) live under ``data/interim/synthetic/<world>/`` and
``results/synthetic/<world>/``, so they can never overwrite the real ones.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
import pandas as pd

# ----------------------------------------------------------------- paths

EXP = Path(__file__).resolve().parents[1]
EXP009 = EXP.parent / "009-claude-model-fidelity"
RAW = EXP / "data" / "raw"
INTERIM = EXP / "data" / "interim"
RESULTS = EXP / "results"
PROMPTS_CSV = EXP009 / "data" / "raw" / "prompts.csv"

SYNTHETIC_WORLDS = ("planted", "planted_equiv", "broken_join")

#: Tests point the synthetic worlds at a temporary directory with this variable; it never
#: affects the real frames.
SYNTHETIC_ROOT_ENV = "EXP011_SYNTHETIC_ROOT"


def _synthetic_base(kind: str) -> Path:
    root = os.environ.get(SYNTHETIC_ROOT_ENV)
    if root:
        return Path(root) / kind
    return (INTERIM if kind == "interim" else RESULTS) / "synthetic"


def interim_dir(synthetic: str | None = None) -> Path:
    return INTERIM if not synthetic else _synthetic_base("interim") / synthetic


def results_dir(synthetic: str | None = None) -> Path:
    return RESULTS if not synthetic else _synthetic_base("results") / synthetic


def features_path(synthetic: str | None = None) -> Path:
    return interim_dir(synthetic) / "features.jsonl"


@dataclass(frozen=True)
class Sources:
    """Where one world's inputs live. Real and synthetic runs read the same layout."""

    raw: Path
    prompts: Path

    @property
    def responses(self) -> Path:
        return self.raw / "responses"

    @property
    def ledger_cc(self) -> Path:
        return self.raw / "ledger_cc.jsonl"

    @property
    def ledger_anchor(self) -> Path:
        return self.raw / "ledger_anchor.jsonl"

    @property
    def ui_sheets(self) -> Path:
        return self.raw / "ui_sheets"

    @property
    def candidates(self) -> Path:
        return self.raw / "brand_candidates.jsonl"

    @property
    def audit_d_sheet(self) -> Path:
        return self.raw / "audit_d_sheet.csv"

    @property
    def audit_d_answers(self) -> Path:
        return self.raw / "audit_d_answers.md"

    @property
    def audit_d_key(self) -> Path:
        return self.raw / "audit_d_key.csv"


def sources(synthetic: str | None = None) -> Sources:
    if not synthetic:
        return Sources(RAW, PROMPTS_CSV)
    raw = interim_dir(synthetic) / "raw"
    return Sources(raw, raw / "prompts.csv")


# ------------------------------------------------------------- constants

SEED = 20261103          # spec header: freeze date as YYYYMMDD
N_BOOT = 2000            # spec §5
ALPHA = 0.10             # 90% percentile CI, TOST on the absolute scale
SESOI = 0.10             # absolute Jaccard, spec §5
TOP_K = 10               # R1
RBO_P = 0.9              # spec §3 derived variables
NO_SEARCH_MAX = 0.30     # Audit A: above this, an arm's domain claims are INCONCLUSIVE
H_POS_MIN = 0.10         # H_pos: same-prompt minus cross-category brand Jaccard
AUDIT_D_N = 30
AUDIT_D_PRECISION = 0.95
AUDIT_D_RECALL = 0.90
WAVES = (1, 2, 3)

# ------------------------------------------------------------------ arms

REFERENCE = "ui_default"
PRIMARY_ARMS = ("cc_stock_full", "sched_kit")  # Holm family, spec §4
SECONDARY_ARMS = ("cc_none_search", "opus55_plain")
COMPARE_ARMS = PRIMARY_ARMS + SECONDARY_ARMS
ALL_ARMS = (REFERENCE,) + COMPARE_ARMS
ANCHOR = "opus55_plain"
SCHEDULED = "sched_kit"
LOCAL_ARMS = ("cc_stock_full", "cc_none_search")
CLAUDE_CODE_ARMS = ("cc_stock_full", "sched_kit", "cc_none_search")  # H2
H3_PAIR = ("sched_kit", "cc_stock_full")
#: Arms whose evaluated URLs are observed. A subagent's searches are not in the pulled
#: transcript (spec §2 Audit B), so an empty list on ``sched_kit`` means unknown, not none.
EVALUATED_ARMS = (REFERENCE, "cc_stock_full", "cc_none_search", "opus55_plain")
#: Plan behind each arm's ledger usage readings (spec §1: one account of each kind).
USAGE_PLAN = {"cc_stock_full": "Max", "cc_none_search": "Max"}

SURFACE = {"ui_default": "claude.ai", "cc_stock_full": "local", "cc_none_search": "local",
           "sched_kit": "scheduled", "opus55_plain": "api"}

#: Markers inside fake answers and fake queries. The dry run asserts that neither reaches
#: the interim frame or any report, which is the rule real answers and queries must follow.
SYNTH_ANSWER_MARK = "ANSWERTEXTMARKER"
SYNTH_QUERY_MARK = "QUERYTEXTMARKER"


def cross(a: str, b: str) -> str:
    """Condition label for same-prompt, same-wave pairs of two arms."""
    x, y = sorted((a, b))
    return f"cross:{x}|{y}"


def within(arm: str) -> str:
    """Condition label for same-arm, same-prompt, different-wave pairs."""
    return f"within:{arm}"


# --------------------------------------------------------- URL handling
# Same rules as 009's common.py (normalize_url, registered_domain), spec §3.

TRACKING_PARAMS = re.compile(r"^(utm_\w+|gclid|fbclid|msclkid|ref|ref_src|src|si|feature)$", re.I)
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    netloc = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), query, ""))


def registered_domain(url_or_host: str) -> str:
    host = url_or_host
    if "//" in host:
        host = urlsplit(host).netloc
    host = host.lower().removeprefix("www.").split(":")[0]
    labels = [p for p in host.split(".") if p]
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def ordered_domains(urls: list[str]) -> list[str]:
    """Registered domains in first-seen order."""
    seen, out = set(), []
    for u in urls:
        if not u:
            continue
        d = registered_domain(normalize_url(u))
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


# --------------------------------------------------------------- ledgers


def read_ledger(path: Path) -> list[dict]:
    """A ledger's records for the study waves, in file order. Other waves are never read."""
    if not path.exists():
        return []
    records = (json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return [r for r in records if int(r.get("wave", -1)) in WAVES]


def ledger_records(src: Sources) -> list[dict]:
    return read_ledger(src.ledger_cc) + read_ledger(src.ledger_anchor)


def last_by_answer(records: list[dict]) -> dict[tuple[str, str, int], dict]:
    """Last record per (arm, item_id, wave). A rerun's record replaces the earlier ones."""
    return {(r["arm"], r["item_id"], int(r["wave"])): r for r in records}


# --------------------------------------------------------------- frames


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


LIST_COLUMNS = ("brands", "brands_all", "cited_domains", "evaluated_domains")


def write_features(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for rec in df.to_dict("records"):
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def load_features(path: Path | None = None, synthetic: str | None = None) -> pd.DataFrame:
    """interim/features.jsonl, one row per answer, list columns as lists."""
    path = path or features_path(synthetic)
    if not path.exists():
        raise SystemExit(f"no feature frame at {path}; run 01_features.py first")
    recs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    df = pd.DataFrame(recs)
    for col in LIST_COLUMNS:
        if col in df.columns:
            df[col] = df[col].map(lambda v: v if isinstance(v, list) else None).astype(object)
    return df.sort_values(["arm", "wave", "item_id"]).reset_index(drop=True)


def item_number(item_id: str) -> int:
    """``b2b_07`` -> 7 (H_pla splits prompts by parity)."""
    return int(item_id.rsplit("_", 1)[1])


def md_table(df: pd.DataFrame, digits: int = 3) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        cells = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                cells.append("n/a" if np.isnan(v) else f"{v:.{digits}f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def arm_order(df: pd.DataFrame, col: str = "arm") -> pd.DataFrame:
    """Rows in the spec's arm order, then by wave when there is one."""
    order = {a: i for i, a in enumerate(ALL_ARMS)}
    by = [col] + (["wave"] if "wave" in df.columns else [])
    return df.sort_values(by=by, key=lambda s: s.map(order) if s.name == col else s,
                          kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------- pairs


def build_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Same-prompt answer pairs for the spec §4 conditions.

    - ``within:<arm>``: same prompt, same arm, different waves (3 per prompt).
    - ``cross:<a>|<b>``: same prompt, same wave, two arms (labels sorted; 3 per prompt).

    ``df`` must have a unique RangeIndex. Returns ``i, j`` (positional indices into ``df``),
    ``condition`` and ``cluster_i == cluster_j`` (the prompt), plus ``category`` for the
    category-level bootstrap (R5). Cross pairs never span two prompts.
    """
    out = []
    arms = df["arm"].to_numpy()
    waves = df["wave"].to_numpy()
    for item, idx in df.groupby("item_id", sort=True).indices.items():
        idx = sorted(idx)
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if arms[i] == arms[j]:
                    if waves[i] != waves[j]:
                        out.append((i, j, within(arms[i]), item))
                elif waves[i] == waves[j]:
                    out.append((i, j, cross(arms[i], arms[j]), item))
    pairs = pd.DataFrame(out, columns=["i", "j", "condition", "cluster_i"])
    pairs["cluster_j"] = pairs["cluster_i"]
    pairs["category"] = df["category"].to_numpy()[pairs["i"].to_numpy()] if len(pairs) else []
    return pairs
