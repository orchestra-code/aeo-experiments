"""Shared paths, constants, and loaders for the experiment-002 pipeline.

Design: 143 human-written headphone-gift prompts (SparkToro's survey), each
run once per day for 7 days on ChatGPT via DataForSEO's LLM scraper, plus one
wave of the survey's coffee-shop-agency prompts as the cross-intent contrast.
See spec.md.
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

SURVEY_TSV = RAW / "survey.tsv"
PROMPTS_CSV = RAW / "prompts.csv"
LEDGER = RAW / "ledger.jsonl"
RESPONSES_DIR = RAW / "responses"
RESPONSES_CSV = INTERIM / "responses.csv"

PRIMARY_INTENT = "headphones"
CONTRAST_INTENT = "coffee"
N_PROMPTS_EXPECTED = 144  # the survey export holds 144 fully-populated rows
                          # (SparkToro's article says 142; we use all valid rows)
WAVES = 7          # headphone waves (1..7, one per day)
CONTRAST_WAVES = 1  # coffee runs on day 1 only

SESOI = 0.10   # absolute Jaccard difference — see spec §5
ALPHA = 0.10   # 90% CIs, matching the house TOST convention
N_BOOT = 2000
N_PERM = 5000
SEED = 20260716

TAG_PREFIX = "aeo-exp002"

#: Query params that vary without changing the destination content.
TRACKING_PARAMS = re.compile(
    r"^(utm_\w+|gclid|fbclid|msclkid|ref|ref_src|src|si|feature)$", re.I
)

#: ccTLD second-level registries where the registered domain needs 3 labels.
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}


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
