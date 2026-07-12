#!/usr/bin/env python3
"""Phrasing lint for research articles and blog drafts.

Advisory grep for the data-policy phrasing rules (docs/data-policy.md §5).
Exit 1 on any hit so it can gate CI. Deliberately dumb: false positives are
cheap, silent violations are not.

Usage: uv run python scripts/lint_article.py <file.mdx> [more files...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DENY = [
    # Database-inventory phrasing — report study samples, not DB totals.
    (r"(?i)\bour database (contains|holds|has)", "describes database contents"),
    (r"(?i)\bin (the|our) spyglasses database\b", "references database inventory"),
    (r"(?i)\bacross (our|the) (entire |whole )?database\b", "references database inventory"),
    (r"(?i)\ball citations (in|across) (our|the)\b", "implies database totals"),
    (r"(?i)\btotal (number of )?citations (in|across)\b", "implies database totals"),
    # Proprietary content markers that should never appear.
    (r"(?i)\bthe customer('s)? prompt\b", "references customer prompt content"),
    (r"(?i)\bfan[- ]?out quer(y|ies) (was|were|reads?|says?)\b", "quotes fan-out queries"),
]

# "N = 5,500" style without study framing nearby (±160 chars).
BARE_N = re.compile(r"[nN]\s*=\s*[\d,]+")
STUDY_FRAMING = re.compile(r"(?i)(in this study|evaluated|this sample|study sample)")


def lint(path: Path) -> list[str]:
    text = path.read_text()
    problems = []
    for pattern, why in DENY:
        for m in re.finditer(pattern, text):
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"{path}:{line}: {why}: {m.group(0)!r}")
    for m in BARE_N.finditer(text):
        window = text[max(0, m.start() - 160) : m.end() + 160]
        if not STUDY_FRAMING.search(window):
            line = text.count("\n", 0, m.start()) + 1
            problems.append(
                f"{path}:{line}: bare sample size {m.group(0)!r} — phrase as "
                "'citations evaluated (in this study)'"
            )
    return problems


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    problems = []
    for arg in sys.argv[1:]:
        problems += lint(Path(arg))
    for p in problems:
        print(p)
    if problems:
        print(f"\n{len(problems)} problem(s). See docs/data-policy.md.")
        return 1
    print("phrasing lint: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
