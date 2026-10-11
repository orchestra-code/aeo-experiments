"""Experiment 010: the new collection's frozen instruments, in one place.

Imported by harness/build_tasks.py, harness/audit_d.py and pipeline/common.py
so the task build, Audit D and the analysis use the same lexicon file, the
same pins and the same extraction.

Extraction for the new collection = 009's ``lexicon_extract`` over the
answer with citation links removed first (spec deviation 6). ChatGPT and
Gemini, as DataForSEO returns them, cite inline as markdown links whose text
is a domain, ``[www.vendor.com](https://...)``. 009's extractor removes link
targets but keeps link text, so a cited vendor's domain counted as a mention
of the vendor, and sometimes as its first mention. A link whose text is a
domain or URL is now removed whole. Link text that is a name stays. The
holdout datasets keep their source studies' frozen extraction.
"""

from __future__ import annotations

import re
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"

LEXICON_V3 = RAW / "lexicon_v3" / "lexicon_v3.csv"
LEXICON_V3_SHA256: str | None = "6084f47ca1831474de9cb64d79425d522b75ac409d2b5080b24653ec9905cf5d"
TAXONOMY_B2B = RAW / "bestfor_taxonomy_b2b" / "taxonomy.json"
TAXONOMY_B2B_SHA256: str | None = "b7fe060460d49e4ffdb6018d35c7feca74f461d6db06105ced6f3c6c5828e9f7"

#: A markdown link whose visible text is a bare domain or URL.
CITATION_LINK = re.compile(
    r"\[\s*(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:/[^\]\s]*)?\s*\]"
    r"\([^)]*\)")


def strip_citation_links(text: str) -> str:
    return CITATION_LINK.sub(" ", text)


def extract_new(b9, text: str, patterns: list) -> list[str]:
    """Lexicon brands in a new-collection answer, in first-mention order."""
    return b9.lexicon_extract(strip_citation_links(text), patterns)
