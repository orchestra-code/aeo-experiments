"""Stage 02b — draft source-class map for cited domains (spec §3 derived variables).

Spec §3 calls for a "source class per cited domain (vendor, review
marketplace, community, publisher, analyst, other) from a frozen domain map
built with the lexicon". This stage drafts that map for a person to review;
it is descriptive input only (the source-class mix in 03_model's descriptive
outcomes) and enters no test.

Lists every registered domain cited by any answer (all arms, waves 1-3) with
counts, and a heuristic ``suggested_class``:

1. the gitignored seed list ``data/raw/domain_class_seed.csv``
   (registered_domain, class) of well-known review marketplaces,
   communities, analysts and reference sites, when present;
2. ``vendor`` when the domain's name label equals a lexicon v2 canonical or
   alias (any category, keep or drop row; case, punctuation and a trailing
   ``.com``-style suffix ignored; a ``get``/``try``/``use`` prefix or an
   ``hq``/``app`` suffix on the label also tried);
3. ``other`` for .gov / .edu / .mil hosts;
4. otherwise ``publisher`` (the default; most need a person's read, since a
   vendor outside the lexicon also publishes buyer guides).

Writes ``data/raw/domain_map_draft.csv`` (gitignored: domains from AI
answers) with empty ``reviewer_class`` and ``reviewer_notes`` columns. The
reviewer fills ``reviewer_class`` (one of the six classes), saves the file as
``data/raw/domain_map_v1.csv`` and records its sha256 in
``common.DOMAIN_MAP_SHA256``; 01_features then attaches the classes. An
existing draft with reviewer input is never overwritten without ``--force``.

Prints aggregates only (class counts).

Usage:
  uv run python experiments/009-claude-model-fidelity/pipeline/02b_domain_map.py [--force]
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from brands import LEXICON, verify_lexicon
from common import (
    DOMAIN_MAP_DRAFT,
    RAW,
    SOURCE_CLASSES,
    UI_ARMS,
    load_features,
)

SEED_LIST = RAW / "domain_class_seed.csv"
_NON_ALNUM = re.compile(r"[^a-z0-9]")
_TLD_SUFFIX = re.compile(r"\.(com|io|ai|co|app|net|org)$", re.I)
_PREFIXES = ("get", "try", "use", "go")
_SUFFIXES = ("hq", "app", "inc")


def key(name: str) -> str:
    return _NON_ALNUM.sub("", _TLD_SUFFIX.sub("", name.strip().lower()))


def lexicon_keys(path: Path = LEXICON) -> dict[str, str]:
    """Normalized alias / canonical -> canonical, over every lexicon row."""
    out: dict[str, str] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            for name in [row["canonical"], *row["aliases"].split("|")]:
                k = key(name)
                if len(k) >= 3:
                    out.setdefault(k, row["canonical"])
    return out


def load_seed(path: Path = SEED_LIST) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {r["registered_domain"].strip().lower(): r["class"].strip() for r in csv.DictReader(f)}


def label_of(domain: str) -> str:
    """The name label of a registered domain (``bbc.co.uk`` -> ``bbc``)."""
    return domain.split(".")[0]


def suggest(domain: str, seed: dict[str, str], lex: dict[str, str]) -> tuple[str, str, str]:
    """(suggested_class, basis, lexicon canonical matched)."""
    if domain in seed:
        return seed[domain], "seed list", ""
    tld = domain.rsplit(".", 1)[-1]
    if tld in ("gov", "edu", "mil") or ".gov." in domain or ".edu." in domain:
        return "other", "government or education host", ""
    label = key(label_of(domain))
    candidates = [label]
    candidates += [label[len(p):] for p in _PREFIXES if label.startswith(p) and len(label) > len(p) + 2]
    candidates += [label[: -len(s)] for s in _SUFFIXES if label.endswith(s) and len(label) > len(s) + 2]
    for c in candidates:
        if c in lex:
            return "vendor", "lexicon name match", lex[c]
    return "publisher", "default (unmatched)", ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="overwrite a draft that has reviewer input")
    a = ap.parse_args()

    verify_lexicon()
    if DOMAIN_MAP_DRAFT.exists() and not a.force:
        with DOMAIN_MAP_DRAFT.open(newline="") as f:
            if any((r.get("reviewer_class") or "").strip() for r in csv.DictReader(f)):
                raise SystemExit(f"{DOMAIN_MAP_DRAFT.name} has reviewer input; use --force")

    df = load_features()
    answers: Counter = Counter()
    ui: Counter = Counter()
    api: Counter = Counter()
    arms: dict[str, set] = defaultdict(set)
    for r in df.itertuples():
        for d in set(r.cited_domains):
            answers[d] += 1
            (ui if r.arm in UI_ARMS else api)[d] += 1
            arms[d].add(r.arm)

    seed, lex = load_seed(), lexicon_keys()
    rows = []
    for d in sorted(answers, key=lambda x: (-answers[x], x)):
        cls, basis, canon = suggest(d, seed, lex)
        rows.append({"registered_domain": d, "n_answers": answers[d], "n_ui_answers": ui[d],
                     "n_api_answers": api[d], "n_arms": len(arms[d]),
                     "suggested_class": cls, "basis": basis, "lexicon_match": canon,
                     "reviewer_class": "", "reviewer_notes": ""})
    with DOMAIN_MAP_DRAFT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by_class = Counter(r["suggested_class"] for r in rows)
    by_basis = Counter(r["basis"] for r in rows)
    weighted = Counter()
    for r in rows:
        weighted[r["suggested_class"]] += r["n_answers"]
    print(f"wrote {DOMAIN_MAP_DRAFT} ({len(rows)} cited registered domains)")
    print(f"seed list: {'present, ' + str(len(seed)) + ' rows' if seed else 'absent'}")
    print("suggested class (domains / answer-citations):")
    for c in SOURCE_CLASSES:
        print(f"  {c:20} {by_class.get(c, 0):>5} / {weighted.get(c, 0):>6}")
    print(f"basis: {dict(by_basis)}")
    print(f"allowed reviewer_class values: {', '.join(SOURCE_CLASSES)}")


if __name__ == "__main__":
    main()
