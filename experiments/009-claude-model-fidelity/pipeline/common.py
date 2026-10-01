"""Shared paths, constants, arm roles, URL handling and loaders for experiment 009.

Design (spec §0, Arms table): 40 synthetic B2B software prompts (20 categories
x 2 intents) x 3 waves, through two claude.ai arms collected by hand
(``ui_default`` = Opus 5.5 at Medium, the reference; ``ui_think`` = High) and
seven Anthropic API arms. One row per answer (prompt x arm x wave) comes out
of stage 01 as ``data/interim/features.jsonl``.

Synthetic dry-run frames (spec §8 step 3) live under
``data/interim/synthetic/<world>/`` and ``results/synthetic/<world>/`` so they
can never overwrite the real ones.

This module is self-contained (no sibling imports) so the harness can load it
by path: ``harness/pilot_report.py`` takes its URL normalization from here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

# ----------------------------------------------------------------- paths

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
INTERIM = EXP / "data" / "interim"
RESULTS = EXP / "results"
FIGURES = RESULTS / "figures"

PROMPTS_CSV = RAW / "prompts.csv"
LEDGER = RAW / "ledger.jsonl"
RESPONSES_DIR = RAW / "responses"
UI_SHEETS = RAW / "ui_sheets"
CANDIDATES = RAW / "brand_candidates.jsonl"

#: Source-class map (spec §3 derived variables). 02b writes the draft; a
#: person fills ``reviewer_class`` and saves it as v1, whose hash is recorded
#: in DOMAIN_MAP_SHA256 at freeze.
DOMAIN_MAP_DRAFT = RAW / "domain_map_draft.csv"
DOMAIN_MAP = RAW / "domain_map_v1.csv"
DOMAIN_MAP_SHA256: str | None = None

#: Audit D (spec §2): the spot-check sheet a person fills, and the scored
#: aggregate 03_model checks before it will touch real data.
AUDIT_D_SHEET = RAW / "audit_d_sheet.csv"
AUDIT_D_SCORE = RESULTS / "audit_d_score.json"
AUDIT_REPORT = RESULTS / "audit_report.md"

SYNTHETIC_WORLDS = ("planted", "broken_join")


#: Tests point the synthetic worlds at a temporary directory with this
#: variable; it never affects the real frames.
SYNTHETIC_ROOT_ENV = "EXP009_SYNTHETIC_ROOT"


def _synthetic_base(kind: str) -> Path:
    root = os.environ.get(SYNTHETIC_ROOT_ENV)
    if root:
        return Path(root) / kind
    return (INTERIM if kind == "interim" else RESULTS) / "synthetic"


def interim_dir(synthetic: str | None = None) -> Path:
    return INTERIM if not synthetic else _synthetic_base("interim") / synthetic


def results_dir(synthetic: str | None = None) -> Path:
    return RESULTS if not synthetic else _synthetic_base("results") / synthetic


def figures_dir(synthetic: str | None = None) -> Path:
    return FIGURES if not synthetic else results_dir(synthetic) / "figures"


def features_path(synthetic: str | None = None) -> Path:
    return interim_dir(synthetic) / "features.jsonl"


# ------------------------------------------------------------- constants

SEED = 20260926          # spec header: freeze date as YYYYMMDD
N_BOOT = 2000            # spec §5
ALPHA = 0.10             # 90% percentile CI, TOST on the absolute scale
SESOI = 0.10             # per-answer Jaccard gaps (spec §5)
SESOI_SHARE = 0.05       # panel-share reference line; never a verdict
SHARE_THRESHOLD = 1 / 3  # pooled-share basket (spec §4 H1s)
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
UI_ARMS = ("ui_default", "ui_think")
API_ARMS = (
    "opus55_plain",
    "opus55_leak",
    "sonnet5_plain",
    "sonnet5_leak_think",
    "sonnet5_leak_low",
    "sonnet5_prod",
    "haiku45_leak",
)
ALL_ARMS = UI_ARMS + API_ARMS
#: Holm family (spec §4): H1b for the three cheap arms.
PRIMARY_ARMS = ("sonnet5_plain", "sonnet5_leak_think", "haiku45_leak")
#: H1b, other secondary tests (no multiplicity correction).
SECONDARY_H1B_ARMS = ("sonnet5_leak_low", "sonnet5_prod")
CHEAP_ARMS = PRIMARY_ARMS + SECONDARY_H1B_ARMS
#: H1-ref (ceiling) and H3.
REF_ARMS = ("opus55_plain", "opus55_leak")
#: H1-ref fallback reference when both Opus arms fail H1b.
FALLBACK_REFERENCE = "opus55_plain"

#: UI chats run with the wrong model or reasoning setting (Audit A), as
#: (arm, item_id, wave). The collector recorded "Opus 5.5 with Medium
#: reasoning (default)" at the start of every wave and no wrong-setting chat
#: in the w1-w3 notes (checked 2026-10-01), so none are excluded. Add a row
#: here, with a Deviations entry, if one is found.
UI_WRONG_SETTING: tuple[tuple[str, str, int], ...] = ()

SOURCE_CLASSES = ("vendor", "review marketplace", "community", "publisher", "analyst", "other")


def cross(a: str, b: str) -> str:
    """Condition label for same-prompt, same-wave pairs of two arms."""
    x, y = sorted((a, b))
    return f"cross:{x}|{y}"


def within(arm: str) -> str:
    """Condition label for same-arm, same-prompt, different-wave pairs."""
    return f"within:{arm}"


# --------------------------------------------------------- URL handling
# Same rules as the 002/003/005 pipelines' common.py (normalize_url,
# registered_domain). Moved here from harness/pilot_report.py at freeze.

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


def domains(urls: list[str]) -> set[str]:
    return {registered_domain(normalize_url(u)) for u in urls if u}


def ordered_domains(urls: list[str]) -> list[str]:
    """Registered domains in first-seen order (the set is ``domains``)."""
    seen, out = set(), []
    for u in urls:
        if not u:
            continue
        d = registered_domain(normalize_url(u))
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


# --------------------------------------------------------------- frames


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


LIST_COLUMNS = ("brands", "brands_haiku", "cited_domains", "evaluated_domains",
                "grounding_tokens", "cited_classes")


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
            df[col] = df[col].map(lambda v: v if isinstance(v, list) else (None if v is None else []))
    return df.sort_values(["arm", "wave", "item_id"]).reset_index(drop=True)


def item_number(item_id: str) -> int:
    """``b2b_07`` -> 7 (H_pla splits prompts by parity)."""
    return int(item_id.rsplit("_", 1)[1])


# ---------------------------------------------------------------- pairs


def build_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Same-prompt answer pairs for the spec §4 conditions.

    - ``within:<arm>``: same prompt, same arm, different waves (3 per prompt).
    - ``cross:<a>|<b>``: same prompt, same wave, two arms (labels sorted;
      3 per prompt per arm pair).

    ``df`` must have a unique RangeIndex. Returns ``i, j`` (positional indices
    into ``df``), ``condition`` and ``cluster_i == cluster_j`` (the prompt),
    plus ``category`` for the category-level bootstrap (R6). Unlike
    ``aeo_research.overlap.arm_condition_pairs``, cross pairs never span two
    prompts: every contrast here is same-prompt.
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
