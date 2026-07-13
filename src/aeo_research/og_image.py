"""Turn a raw generated image into a branded 1200×630 OpenGraph card.

The Spyglasses convention (see the example blog cards): an abstract image in
the brand palette, no words, with the gold isotype composited in the lower-
right corner. This module does the deterministic part — cover-crop to exactly
1200×630 and stamp the isotype — so the only manual step left is generating
the source art.

Used for both research-article hero/OG images and the companion blog cards.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

_ASSETS = Path(__file__).resolve().parents[2]
#: Default stamp: the gold/brass isotype the brand cards use.
DEFAULT_LOGO = _ASSETS / "site" / "public" / "brand" / "spyglasses_isotype.svg"

OG_SIZE = (1200, 630)


def _load_logo_rgba(logo: Path, width_px: int) -> Image.Image:
    """Rasterize an SVG (via cairosvg) or open a raster, as RGBA at width_px."""
    logo = Path(logo)
    if logo.suffix.lower() == ".svg":
        import cairosvg

        png_bytes = cairosvg.svg2png(url=str(logo), output_width=width_px)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    img = Image.open(logo).convert("RGBA")
    h = round(width_px * img.height / img.width)
    return img.resize((width_px, h), Image.LANCZOS)


def cover_crop(img: Image.Image, size: tuple[int, int] = OG_SIZE) -> Image.Image:
    """Scale to fully cover `size`, then center-crop to it (no distortion)."""
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (resized.width - tw) // 2
    top = (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def make_og_image(
    src: str | Path,
    dst: str | Path,
    *,
    logo: str | Path = DEFAULT_LOGO,
    size: tuple[int, int] = OG_SIZE,
    logo_width_frac: float = 0.062,
    pad_frac: float = 0.018,
    quality: int = 90,
) -> Path:
    """Cover-crop `src` to `size`, stamp the isotype lower-right, write WEBP.

    logo_width_frac and pad_frac are fractions of the canvas width, matching
    the existing brand cards (~74 px logo, ~22 px inset on a 1200 px card).
    """
    dst = Path(dst)
    base = Image.open(src).convert("RGB")
    canvas = cover_crop(base, size).convert("RGBA")

    logo_px = round(size[0] * logo_width_frac)
    mark = _load_logo_rgba(Path(logo), logo_px)
    pad = round(size[0] * pad_frac)
    pos = (size[0] - mark.width - pad, size[1] - mark.height - pad)
    canvas.alpha_composite(mark, pos)

    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(dst, "WEBP", quality=quality, method=6)
    return dst
