"""Shared paths, constants, panel lookups, and loaders for experiment 008.

Design: 48 real brands in four tiers (A guessable / B non-obvious domain /
C recently migrated / D obscure) x 2 prompt templates (p1 brand-identity,
p2 comparison), run against the direct OpenAI Responses API with the
``web_search`` tool across 10 daily waves, plus two spaced same-day
replicates on wave 1 (allocation C, spec §7).

The observable is the ``site:`` operator the model types into its own search
tool: emitting ``site:usemotion.com pricing`` is a commitment to a belief
about which domain belongs to Motion. Every call is scored against the
frozen brand->domain map in ``brands.py`` (see ``scoring.py`` for the label
definitions, which Audit B quotes verbatim).

Two frames come out of stage 01:
- ``interim/responses.csv``        one row per study call (call-level outcomes)
- ``interim/site_observations.csv`` one row per ``site:`` observation

Synthetic dry-run frames (spec §5) live under ``interim/synthetic/`` and
``results/synthetic/`` so they can never overwrite the real ones; stage 05
refuses any frame marked ``synthetic=1``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
from brands import DRAFT_PANEL, DRAFT_TEMPLATES, BrandEntry

# ----------------------------------------------------------------- paths

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
INTERIM = EXP / "data" / "interim"
PUBLIC = EXP / "data" / "public"
FIGURES = EXP / "figures"
RESULTS = EXP / "results"

LEDGER = RAW / "ledger_direct.jsonl"
RESPONSES_DIR = RAW / "responses_direct"
PROMPTS_CSV = RAW / "prompts.csv"

RESPONSES_CSV = INTERIM / "responses.csv"
OBS_CSV = INTERIM / "site_observations.csv"
RESOLUTION_JSON = INTERIM / "resolution.json"
RESOLVED_CSV = INTERIM / "error_kind_resolved.csv"

#: Synthetic worlds get their own interim/results subtrees (spec §5 dry run).
SYNTHETIC_WORLDS = ("lookup", "guess")


def interim_dir(synthetic: str | None = None) -> Path:
    return INTERIM if not synthetic else INTERIM / "synthetic" / synthetic


def results_dir(synthetic: str | None = None) -> Path:
    return RESULTS if not synthetic else RESULTS / "synthetic" / synthetic


def responses_csv(synthetic: str | None = None) -> Path:
    return interim_dir(synthetic) / "responses.csv"


def obs_csv(synthetic: str | None = None) -> Path:
    return interim_dir(synthetic) / "site_observations.csv"


# ------------------------------------------------------------- constants

SEED = 20260901        # spec: seed = freeze date
ALPHA = 0.05           # 95% Wilson / bootstrap intervals (spec §5)
N_PERM = 5000          # spec §5: permutation baseline, 5,000 draws
N_BOOT = 2000          # spec §5: cluster bootstrap, 2,000 draws

SYSTEMIC_DELTA = 0.25   # H2 systemic verdict band (spec §4)
STOCHASTIC_DELTA = 0.05  # H2 stochastic verdict band (spec §4)
H_POS_MIN = 0.90        # H_pos gate: tier A accuracy when a domain is emitted

MAX_WAVE = 10
STUDY_INTENTS = ("core", "rep1", "rep2")
CORE_INTENT = "core"
#: Replicate slot lives in the item_id suffix (…_r0/_r1/_r2, spec §7).
INTENT_BY_REPLICATE = {0: "core", 1: "rep1", 2: "rep2"}

TIERS = ("A", "B", "C", "D")
TIER_LABELS = {
    "A": "A — guessable domain",
    "B": "B — non-obvious domain",
    "C": "C — migrated domain",
    "D": "D — obscure brand",
}
TEMPLATES = ("p1", "p2")
TEMPLATE_LABELS = {"p1": "brand-identity prompt", "p2": "comparison prompt"}

LABELS = ("correct", "stale", "wrong")
ERROR_KINDS = (
    "stale_old_domain",
    "morphological_guess",
    "name_bearing_other",
    "third_party",
    "nonexistent",
)
#: Error kinds whose domains get the analysis-time resolution check.
RESOLVED_ERROR_KINDS = ("stale_old_domain", "morphological_guess", "name_bearing_other")

#: The frozen spec (§2 Audit B) names four kinds; `name_bearing_other` and
#: `third_party` are an analysis-time split of its `other_real` bucket, so the
#: frozen labels stay derivable. 02_audit documents this in Deviations.
SPEC_OTHER_REAL = ("name_bearing_other", "third_party")

#: §8c pilot point estimates for the emission funnel, printed next to H1.
PILOT_EMISSION = {"p1": (13, 13), "p2": (10, 10)}

# --------------------------------------------------------------- panel

PANEL: tuple[BrandEntry, ...] = DRAFT_PANEL
TEMPLATE_TEXT = DRAFT_TEMPLATES


def slug(name: str) -> str:
    """Brand slug as the ledger encodes it (00_prompts.py)."""
    return name.lower().replace(" ", "-")


BY_SLUG: dict[str, BrandEntry] = {slug(b.canonical): b for b in PANEL}
TIER_BY_SLUG: dict[str, str] = {s: b.tier for s, b in BY_SLUG.items()}


def parse_item_id(item_id: str) -> tuple[str, str, int]:
    """``goto_p1_r2`` -> ("goto", "p1", 2). Slugs never contain "_"."""
    brand_slug, template, rep = item_id.rsplit("_", 2)
    return brand_slug, template, int(rep.removeprefix("r"))


# --------------------------------------------------------- host handling

#: ccTLD second-level registries where the registered domain needs 3 labels
#: (copied from 005's common.py so domain handling matches across studies).
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}


def normalize_host(url_or_host: str) -> str:
    """Lowercase host without scheme, path, port, ``www.`` or trailing dot."""
    host = (url_or_host or "").strip()
    if "//" in host:
        host = urlsplit(host).netloc
    host = host.split("/")[0].split("?")[0].split("#")[0]
    host = host.lower().split("@")[-1].split(":")[0]
    host = host.strip(".").removeprefix("www.")
    return host


def registered_domain(url_or_host: str) -> str:
    """Registered domain via 005's heuristic (bbc.co.uk, sony.com, abc.xyz)."""
    host = normalize_host(url_or_host)
    labels = [p for p in host.split(".") if p]
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


# ------------------------------------------------- list columns / frames

SEP = "|"


def join_list(values: Iterable[str]) -> str:
    return SEP.join(values)


def split_list(cell) -> list[str]:
    if cell is None or (isinstance(cell, float) and pd.isna(cell)) or cell == "":
        return []
    return [v for v in str(cell).split(SEP) if v]


def load_responses(path: Path | None = None, synthetic: str | None = None) -> pd.DataFrame:
    """interim/responses.csv with list columns deserialized."""
    df = pd.read_csv(path or responses_csv(synthetic))
    for col in ("site_domains", "consulted_domains", "cited_domains"):
        if col in df.columns:
            df[col + "_list"] = df[col].map(split_list)
    df["first_site_label"] = df["first_site_label"].fillna("")
    for col in ("first_site_error_kind", "first_site_attribution", "first_error_domain"):
        df[col] = df.get(col, pd.Series("", index=df.index)).fillna("")
    return df


def load_observations(path: Path | None = None, synthetic: str | None = None) -> pd.DataFrame:
    """interim/site_observations.csv (one row per ``site:`` observation)."""
    df = pd.read_csv(path or obs_csv(synthetic))
    df["error_kind"] = df["error_kind"].fillna("")
    df["attribution"] = df.get("attribution", pd.Series("", index=df.index)).fillna("")
    return df


def apply_resolution(obs: pd.DataFrame, path: Path | None = None) -> tuple[pd.DataFrame, str]:
    """Merge Audit B's resolution check: unresolvable error domains -> nonexistent.

    02_audit writes ``interim/error_kind_resolved.csv`` keyed by registered
    domain rather than rewriting the interim frames, so the scored frame
    stays reproducible from the raw responses alone.
    """
    path = path or RESOLVED_CSV
    if not path.exists():
        return obs, "no resolution file — error kinds unchanged (run 02_audit.py --resolve)"
    table = pd.read_csv(path)
    dead = set(table.loc[table["resolved_error_kind"] == "nonexistent", "registered_domain"])
    if not dead:
        return obs, f"resolution file present ({len(table)} domains), none unresolvable"
    out = obs.copy()
    hit = out["registered_domain"].isin(dead) & out["error_kind"].isin(RESOLVED_ERROR_KINDS)
    out.loc[hit, "error_kind"] = "nonexistent"
    return out, f"{int(hit.sum())} observations reassigned to nonexistent ({len(dead)} domains)"


# ------------------------------------------------------------ inference

def brand_pairs_frame(
    df: pd.DataFrame, value_col: str, condition_col: str, brand_col: str = "slug"
) -> pd.DataFrame:
    """Shape a row-level frame for ``aeo_research.overlap.cluster_boot``.

    cluster_boot resamples clusters and weights observations by their draw
    count; setting ``cluster_i == cluster_j`` makes each row a within-cluster
    observation, which is exactly a brand-clustered bootstrap of a mean (or a
    difference of two group means). Every pooled rate in stage 03 goes
    through this so its CI clusters on brand (Audit C).
    """
    return pd.DataFrame(
        {
            "value": pd.to_numeric(df[value_col], errors="coerce").astype(float),
            "condition": df[condition_col].astype(str),
            "cluster_i": df[brand_col].astype(str),
            "cluster_j": df[brand_col].astype(str),
        }
    )


def brand_bootstrap(
    clusters: Sequence,
    stat: Callable[[list], float],
    *,
    n_boot: int = N_BOOT,
    alpha: float = ALPHA,
    seed: int = SEED,
) -> tuple[float, float, float]:
    """Cluster bootstrap over brands for statistics cluster_boot can't express.

    ``stat`` receives a list of cluster keys (with multiplicity) and returns a
    scalar; NaN draws are dropped. Returns (observed, lo, hi).
    """
    keys = list(clusters)
    observed = stat(keys)
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot)
    for k in range(n_boot):
        idx = rng.integers(0, len(keys), size=len(keys))
        draws[k] = stat([keys[i] for i in idx])
    draws = draws[~np.isnan(draws)]
    if draws.size == 0:
        return float(observed), float("nan"), float("nan")
    lo, hi = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
    return float(observed), float(lo), float(hi)


def rule_of_three(n: int) -> float:
    """Upper bound on a rate after zero events in n trials (spec §1/§5)."""
    return 3.0 / n if n else float("nan")


def fmt_rate(k: int, n: int, lo: float, hi: float) -> str:
    if not n:
        return "n=0"
    if k == 0:
        return f"0/{n} = 0.000 (rule-of-three upper bound {rule_of_three(n):.3f})"
    return f"{k}/{n} = {k / n:.3f} [{lo:.3f}, {hi:.3f}]"
