"""Deterministic brand extraction for experiment 011 (spec §2 Audit B, §5 lexicon protocol).

Same matcher as 009's ``pipeline/brands.py``, so that 009's lexicon rules still apply. The
lexicon (``data/raw/lexicon_v1.csv``, gitignored: it is built from AI answers) has one row
per (brand, prompt category): ``canonical``, ``aliases`` (``|``-separated), ``category``,
``decision`` (keep|drop), ``match`` (ci|cs). Labelled sources blocks, markdown link targets,
bare URLs and markup are stripped; the category's aliases are matched longest first on word
boundaries; order is first mention. Matched spans are consumed, so a longer alias shadows a
shorter one inside it, and drop rows consume their spans without counting.

Self-contained (no sibling imports) so the harness can load it by path.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"

#: The frozen lexicon. It is created at the lexicon step after wave 1 (spec §5), and its
#: hash goes here and in the spec before any confirmatory metric. Until then every stage
#: that reads real data refuses to run.
LEXICON = RAW / "lexicon_v1.csv"
LEXICON_SHA256: str | None = None

# ------------------------------------------------------------ lexicon matching

_MD_URL = re.compile(r"\((?:https?|www)[^)]*\)|https?://\S+")
_MD_MARKUP = re.compile(r"[*_#>`]")


def load_lexicon(path: Path) -> dict[str, list[tuple[re.Pattern, str, bool]]]:
    """category -> [(pattern, canonical, keep)], longest alias first."""
    by_cat: dict[str, list[tuple[str, str, bool, bool]]] = defaultdict(list)
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            for alias in row["aliases"].split("|"):
                if alias.strip():
                    by_cat[row["category"]].append(
                        (alias.strip(), row["canonical"], row["decision"] == "keep",
                         row["match"] == "cs"))
    out = {}
    for cat, entries in by_cat.items():
        entries = sorted(set(entries), key=lambda e: len(e[0]), reverse=True)
        out[cat] = [
            (re.compile(rf"(?<![\w&]){re.escape(a)}(?![\w&])", 0 if cs else re.I), canon, keep)
            for a, canon, keep, cs in entries
        ]
    return out


#: A "Sources" / "Sources referenced" label (heading, bold or plain) that ends its line or is
#: followed by a colon. Claude Code's search tool asks for such a block at the end of an answer.
_SOURCES_LABEL = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*sources?(?:[ \t]+(?:referenced|consulted|cited|used))?"
    r"[ \t]*(?::\**|\**:|\**[ \t]*$)",
    re.I | re.M,
)
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+•]|\d+[.)])[ \t]")


def strip_sources(text: str) -> str:
    """Drop each sources block: the label line and the list items after it."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if _SOURCES_LABEL.match(lines[i]):
            i += 1
            while i < len(lines) and (not lines[i].strip() or _LIST_ITEM.match(lines[i])):
                i += 1
            out.append("")
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def lexicon_extract(text: str, patterns) -> list[str]:
    text = _MD_MARKUP.sub(" ", _MD_URL.sub(" ", strip_sources(text)))
    taken = np.zeros(len(text) + 1, dtype=bool)
    first: dict[str, int] = {}
    for pattern, canon, keep in patterns:
        for m in pattern.finditer(text):
            if taken[m.start():m.end()].any():
                continue
            taken[m.start():m.end()] = True
            if keep and (canon not in first or m.start() < first[canon]):
                first[canon] = m.start()
    return sorted(first, key=first.get)


def lexicon_alias_map(path: Path) -> dict[tuple[str, str], tuple[str, bool]]:
    amap = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            for alias in row["aliases"].split("|"):
                amap[(row["category"], alias.strip().lower())] = (
                    row["canonical"], row["decision"] == "keep")
    return amap


def unplaced_names(raw_names: list[str], patterns) -> list[str]:
    """Haiku names the lexicon's own matcher cannot place, lowercased and sorted.

    A name counts as placed when an alias matches inside it, as it would in the answer text,
    so a plan tier of a known vendor is placed (pilot_report.coverage_and_residuals).
    """
    left = set()
    for name in raw_names:
        clean = name.strip()
        if clean and not any(p.search(clean) for p, _canon, _keep in patterns):
            left.add(clean.lower())
    return sorted(left)


def with_unplaced(brand_list: list[str], raw_names: list[str], patterns) -> list[str]:
    """R4: the lexicon's brands, then every unplaced name. Nothing censored."""
    return list(dict.fromkeys([*brand_list, *unplaced_names(raw_names, patterns)]))


# ------------------------------------------------------------ frozen lexicon


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lexicon(path: Path = LEXICON, expected: str | None = LEXICON_SHA256) -> str:
    """Refuse to run unless the lexicon file exists, is frozen, and is the frozen one."""
    if expected is None:
        raise SystemExit(
            "the lexicon is not frozen: brands.LEXICON_SHA256 is None. It is set at the lexicon "
            "step after wave 1 (spec §5); no confirmatory stage runs on real data before that."
        )
    if not path.exists():
        raise SystemExit(f"lexicon not found: {path}")
    got = sha256_file(path)
    if got != expected:
        raise SystemExit(
            f"lexicon sha256 mismatch for {path.name}: got {got}, frozen {expected}. "
            "The lexicon is part of the frozen instrument (spec §5); a change must be "
            "logged as a deviation and the hash updated here."
        )
    return got


def frozen_lexicon(path: Path = LEXICON, expected: str | None = LEXICON_SHA256):
    """(patterns by category, sha256) for the frozen lexicon. Refuses anything else."""
    sha = verify_lexicon(path, expected)
    return load_lexicon(path), sha


def synthetic_lexicon(path: Path):
    """(patterns by category, sha256) for a dry run's fake lexicon, with no hash gate."""
    return load_lexicon(path), sha256_file(path)
