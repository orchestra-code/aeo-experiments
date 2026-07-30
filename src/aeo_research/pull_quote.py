"""Render a branded 1200×630 pull-quote card for blog posts.

The share-image counterpart to :mod:`aeo_research.og_image`: instead of
branding generated art, this draws the card itself — white field, brand-blue
frame with a copper pinstripe, the quote centered in Figtree, and the gold
isotype in the lower-right corner. Blog posts embed the card above the quote
text and per-network share buttons (the `PullQuote` MDX component in the
spyglasses repo).

Deterministic by design: same quote in, same card out.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from aeo_research.og_image import DEFAULT_LOGO, OG_SIZE, _load_logo_rgba

_ASSETS = Path(__file__).resolve().parents[2]
_FONT_DIR = _ASSETS / "assets" / "fonts"
QUOTE_FONT = _FONT_DIR / "Figtree-SemiBold.ttf"
ATTRIBUTION_FONT = _FONT_DIR / "Figtree-Medium.ttf"

#: Brand palette (matches tooling/tailwind/theme.css in the spyglasses repo).
BLUE = "#5887DA"
COPPER = "#C95920"
INK = "#292b35"
MUTED = "#6b7280"

_FRAME_PX = 14  # solid blue outer frame
_PINSTRIPE_INSET = 30  # copper hairline inset from the canvas edge
_PINSTRIPE_PX = 2
_TEXT_MAX_WIDTH = 960
_QUOTE_SIZES = range(58, 30, -2)  # try large, shrink until it fits


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Greedy word wrap by measured pixel width."""
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_pull_quote(
    dst: str | Path,
    quote: str,
    *,
    attribution: str | None = None,
    logo: str | Path = DEFAULT_LOGO,
    size: tuple[int, int] = OG_SIZE,
    quality: int = 90,
) -> Path:
    """Draw the pull-quote card and write it as WEBP. Returns the dest path."""
    dst = Path(dst)
    w, h = size
    canvas = Image.new("RGBA", size, "#FFFFFF")
    draw = ImageDraw.Draw(canvas)

    # Frame: solid blue border, then a copper pinstripe inset from it.
    for i in range(_FRAME_PX):
        draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=BLUE)
    p = _PINSTRIPE_INSET
    for i in range(_PINSTRIPE_PX):
        draw.rectangle([p + i, p + i, w - 1 - p - i, h - 1 - p - i], outline=COPPER)

    # Typographic quotes around the text (with a copper accent rule above).
    text = quote.strip().strip("\"“”").replace("'", "’")
    body = f"“{text}”"

    chosen_font = None
    chosen_lines: list[str] = []
    for px in _QUOTE_SIZES:
        font = ImageFont.truetype(str(QUOTE_FONT), px)
        lines = _wrap(draw, body, font, _TEXT_MAX_WIDTH)
        line_height = round(px * 1.3)
        if len(lines) * line_height <= h - 260:
            chosen_font, chosen_lines, chosen_line_height = font, lines, line_height
            break
    if chosen_font is None:  # very long quote: take the smallest size
        px = _QUOTE_SIZES[-1]
        chosen_font = ImageFont.truetype(str(QUOTE_FONT), px)
        chosen_lines = _wrap(draw, body, chosen_font, _TEXT_MAX_WIDTH)
        chosen_line_height = round(px * 1.3)

    accent_height = 6  # short copper rule above the quote
    accent_gap = 44

    attr_font = ImageFont.truetype(str(ATTRIBUTION_FONT), 26)
    attr_gap = 34 if attribution else 0
    attr_height = 30 if attribution else 0

    block_height = (
        accent_height + accent_gap + len(chosen_lines) * chosen_line_height + attr_gap + attr_height
    )
    y = (h - block_height) // 2

    draw.rectangle(
        [w / 2 - 40, y, w / 2 + 40, y + accent_height], fill=COPPER
    )
    y += accent_height + accent_gap
    for line in chosen_lines:
        draw.text((w / 2, y), line, font=chosen_font, fill=INK, anchor="ma")
        y += chosen_line_height
    if attribution:
        y += attr_gap - 8
        draw.text((w / 2, y), f"— {attribution}", font=attr_font, fill=MUTED, anchor="ma")

    # Gold isotype, lower-right, inside the pinstripe.
    mark = _load_logo_rgba(Path(logo), round(w * 0.062))
    inset = _PINSTRIPE_INSET + 18
    canvas.alpha_composite(mark, (w - mark.width - inset, h - mark.height - inset))

    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(dst, "WEBP", quality=quality, method=6)
    return dst
