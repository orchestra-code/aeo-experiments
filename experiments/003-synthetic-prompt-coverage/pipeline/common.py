"""Shared paths, constants, and loaders for the experiment-003 pipeline.

Design: four prompt panels for ONE intent (headphones-as-travel-gift), run
side by side on ChatGPT via DataForSEO's LLM scraper, one run per prompt per
day for 5 days:

- ``hum``    143 human-written prompts (SparkToro survey, re-used from 002,
             re-run contemporaneously — never compared against 002's July
             responses, which came from a different model era)
- ``spy_a``  37 prompts from the production Spyglasses generator anchored on
             bose.com (incumbent brand)
- ``spy_b``  37 prompts from the same generator anchored on soundcore.com
             (mid-tier brand)
- ``neu``    40 prompts from a neutral scenario-only generator (same LLM as
             the Spyglasses generator, no brand context)
- ``coffee`` 40 of 002's coffee-agency prompts, wave 1 only — the
             cross-intent floor for the positive-control gate

See spec.md; harness/ holds the generators and their frozen outputs.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
INTERIM = EXP / "data" / "interim"
PUBLIC = EXP / "data" / "public"
FIGURES = EXP / "figures"
RESULTS = EXP / "results"

GENERATOR_DIR = RAW / "generator"
PROMPTS_CSV = RAW / "prompts.csv"
LEDGER = RAW / "ledger.jsonl"
RESPONSES_DIR = RAW / "responses"
RESPONSES_CSV = INTERIM / "responses.csv"

#: 002's raw prompts file — source of the hum and coffee panels.
EXP002_PROMPTS_CSV = EXP.parent / "002-prompt-consistency" / "data" / "raw" / "prompts.csv"

#: item_id prefix -> arm.
ARM_BY_PREFIX = {"h": "hum", "a": "spy_a", "b": "spy_b", "n": "neu", "c": "coffee"}
PRIMARY_ARM = "hum"
SYNTH_ARMS = ("spy_a", "spy_b", "neu")
CONTRAST_ARM = "coffee"

#: Anchor brands (canonical lexicon names) for the anchor-bias hypothesis.
ANCHORS = {"spy_a": "bose", "spy_b": "anker"}

#: All headphone-category arms share the survey's primary intent so the frozen
#: 002 lexicon applies; the coffee floor keeps its own intent/lexicon.
INTENT_BY_ARM = {
    "hum": "headphones", "spy_a": "headphones", "spy_b": "headphones",
    "neu": "headphones", "coffee": "coffee",
}

WAVES = 5           # one run per prompt per day, waves 1..5
CONTRAST_WAVES = 1  # coffee runs on day 1 only
N_COFFEE = 40

SESOI = 0.10        # absolute Jaccard difference — spec §5
SESOI_SHARE = 0.05  # absolute per-brand mention-share difference — spec §5
SHARE_FLOOR = 0.05  # brands enter H2 only if the human panel mentions them
                    # in >= 5% of responses (avoids zero-inflated tails)
ALPHA = 0.10
N_BOOT = 2000
N_PERM = 5000
SEED = 20260729

TAG_PREFIX = "aeo-exp003"

#: Query params that vary without changing the destination content.
TRACKING_PARAMS = re.compile(
    r"^(utm_\w+|gclid|fbclid|msclkid|ref|ref_src|src|si|feature)$", re.I
)

#: ccTLD second-level registries where the registered domain needs 3 labels.
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}


def arm_of(item_id: str) -> str:
    return ARM_BY_PREFIX[item_id[0]]


def normalize_url(url: str) -> str:
    """Lowercase host, drop fragments and tracking params, strip trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)]
    )
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def registered_domain(url_or_host: str) -> str:
    """Registered domain via a small heuristic (bbc.co.uk, sony.com, ...)."""
    host = url_or_host
    if "//" in host:
        host = urlsplit(host).netloc
    host = host.lower().removeprefix("www.").split(":")[0]
    labels = [p for p in host.split(".") if p]
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


# ------------------------------------------------- responses frame I/O

SEP = "|"


def join_list(values) -> str:
    return SEP.join(values)


def split_list(cell) -> list[str]:
    if pd.isna(cell) or cell == "":
        return []
    return str(cell).split(SEP)


def load_responses(path: Path = RESPONSES_CSV) -> pd.DataFrame:
    """interim/responses.csv with list columns deserialized."""
    df = pd.read_csv(path)
    for col in ("brands", "domains", "urls"):
        df[col + "_list"] = df[col].map(split_list)
    df["brand_set"] = df["brands_list"].map(set)
    df["domain_set"] = df["domains_list"].map(set)
    df["url_set"] = df["urls_list"].map(set)
    df["fanout_token_set"] = df["fanout_tokens"].map(
        lambda c: set() if pd.isna(c) or c == "" else set(str(c).split())
    )
    return df
