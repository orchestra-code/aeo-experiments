#!/usr/bin/env python3
"""Render a branded 1200×630 pull-quote card (WEBP).

White field, brand-blue frame with a copper pinstripe, the quote centered in
Figtree, gold isotype lower-right. The blog-post counterpart embeds the card
above the quote text and share buttons.

Usage:
    uv run python scripts/make_pull_quote.py DST.webp --quote "The quote text."
    uv run python scripts/make_pull_quote.py DST.webp --quote "..." --attribution "Spyglasses"

Options:
    --quote TEXT        the pull quote (curly quotes added automatically)
    --attribution TEXT  optional "— Name" line under the quote
    --logo PATH         override the stamp (default: brass isotype)
    --quality INT       WEBP quality (default 90)
"""

from __future__ import annotations

import argparse

from aeo_research.og_image import DEFAULT_LOGO
from aeo_research.pull_quote import make_pull_quote


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dst")
    ap.add_argument("--quote", required=True)
    ap.add_argument("--attribution", default=None)
    ap.add_argument("--logo", default=str(DEFAULT_LOGO))
    ap.add_argument("--quality", type=int, default=90)
    a = ap.parse_args()

    out = make_pull_quote(
        a.dst, a.quote, attribution=a.attribution, logo=a.logo, quality=a.quality
    )
    print(f"  {out}  (1200x630 WEBP)")


if __name__ == "__main__":
    main()
