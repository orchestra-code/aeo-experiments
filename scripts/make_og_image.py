#!/usr/bin/env python3
"""Brand a raw image into a 1200×630 Spyglasses OpenGraph card.

Cover-crops the source to 1200×630 and stamps the gold isotype lower-right,
matching the brand blog cards. Output is WEBP.

Usage:
    uv run python scripts/make_og_image.py SRC DST.webp
    uv run python scripts/make_og_image.py raw.png site/public/figures/<slug>/hero-og.webp

Options:
    --logo PATH        override the stamp (default: brass isotype)
    --logo-frac FLOAT  logo width as a fraction of 1200 (default 0.062)
    --quality INT      WEBP quality (default 90)
"""

from __future__ import annotations

import argparse

from aeo_research.og_image import DEFAULT_LOGO, make_og_image


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--logo", default=str(DEFAULT_LOGO))
    ap.add_argument("--logo-frac", type=float, default=0.062)
    ap.add_argument("--quality", type=int, default=90)
    a = ap.parse_args()

    out = make_og_image(
        a.src, a.dst, logo=a.logo, logo_width_frac=a.logo_frac, quality=a.quality
    )
    print(f"  {out}  (1200x630 WEBP)")


if __name__ == "__main__":
    main()
