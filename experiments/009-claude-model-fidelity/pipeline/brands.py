"""Deterministic brand extraction for experiment 009 (spec §2 Audit B, §5 lexicon protocol).

Moved here from ``harness/pilot_report.py`` at freeze (spec §8 step 2); the
function bodies are unchanged, and ``pilot_report`` re-exports them so the
pilot report and ``harness/lexicon_candidates.py`` keep their behavior byte
for byte.

The lexicon (``data/raw/lexicon_v2.csv``, gitignored: it is built from AI
answers) has one row per (brand, prompt category): ``canonical``, ``aliases``
(``|``-separated), ``category``, ``decision`` (keep|drop), ``match`` (ci|cs).
Extraction follows experiment 003's ``brands.extract_brands``: labelled
sources blocks, markdown link targets, bare URLs and markup are stripped; the
category's aliases are matched longest first on word boundaries; order is
first mention. Matched spans are consumed (so a longer alias shadows a
shorter one inside it), and drop rows consume their spans without counting.
Only the rows for the answer's own prompt category are used.

This module is self-contained (no sibling imports) so the harness can load it
by path without colliding with other experiments' ``brands`` modules.
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

#: The frozen lexicon (spec §5, lexicon protocol; v2 replaced v1 before any
#: confirmatory metric, see the spec's Deviations). Every pipeline stage that
#: extracts brands verifies this hash and refuses to run on a mismatch.
#:
#: A canonical is not unique per category: v2 folds some rows into one brand
#: (for example a case-sensitive alias row and a case-insensitive row with the
#: same canonical). Extraction keys matches by canonical, so either row's
#: alias counts as that one brand; nothing here keys rows by
#: (category, canonical).
LEXICON = RAW / "lexicon_v2.csv"
LEXICON_SHA256 = "a2745081980cb819b7de7e0dc698d0fecb001fc7a677259e68d57bf5c744e1eb"


def ordered_unique(items):
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


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


#: A "Sources" / "Sources referenced" label (heading, bold or plain) that ends
#: its line or is followed by a colon. The production discovery prompt asks
#: for the sources consulted, so sonnet5_prod answers end with one (deviation 3).
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


def haiku_via_lexicon(raw_names: list[str], category: str, alias_map) -> list[str]:
    """Haiku candidates mapped through lexicon v0 (merges and drops applied)."""
    out = []
    for name in raw_names:
        hit = alias_map.get((category, name.strip().lower()))
        if hit and hit[1]:
            out.append(hit[0])
    return ordered_unique(out)


def lexicon_alias_map(path: Path) -> dict[tuple[str, str], tuple[str, bool]]:
    amap = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            for alias in row["aliases"].split("|"):
                amap[(row["category"], alias.strip().lower())] = (
                    row["canonical"], row["decision"] == "keep")
    return amap


# ------------------------------------------------------------ frozen lexicon


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lexicon(path: Path = LEXICON, expected: str = LEXICON_SHA256) -> str:
    """Refuse to run unless the lexicon file is the frozen one."""
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
    """(patterns by category, alias map, sha256) for the frozen lexicon.

    ``expected=None`` skips the hash check; only the synthetic dry run, which
    writes its own fake lexicon, passes it.
    """
    sha = verify_lexicon(path, expected) if expected else sha256_file(path)
    return load_lexicon(path), lexicon_alias_map(path), sha


def lexicon_categories(path: Path) -> dict[str, list[dict]]:
    """Raw lexicon rows per category (02b_domain_map's vendor heuristic)."""
    out: dict[str, list[dict]] = defaultdict(list)
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            out[row["category"]].append(row)
    return out
