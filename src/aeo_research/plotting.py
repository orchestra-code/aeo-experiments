"""Branded, watermarked matplotlib output for Spyglasses research figures.

Every published figure goes through ``save_figure``, which applies the source
caption and the corner logotype watermark and writes both SVG (crisp in-page)
and PNG (social sharing / OG). The palette below was validated with the
dataviz six-check procedure (lightness band, chroma floor, CVD separation,
contrast vs white) on 2026-07-12; if you change a hex, re-validate.

Categorical color follows the *entity* (platform), never the series rank —
use ``PLATFORM_COLORS``/``PLATFORM_LABELS`` so ChatGPT is always blue no
matter which subset of platforms a chart shows. The all-pairs CVD worst case
(rose vs green, ΔE 10.5) sits in the 8–12 floor band, which is legal only
with secondary encoding: in scatter plots, give each platform a distinct
marker shape (``PLATFORM_MARKERS``).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from statsmodels.stats.proportion import proportion_confint

matplotlib.use("Agg")

# --------------------------------------------------------------------------
# Brand + palette (validated — see module docstring)
# --------------------------------------------------------------------------
BRAND_BLUE = "#5887DA"
INK = "#222222"        # brand black — titles, primary text
INK_MUTED = "#6b7280"  # secondary text, captions, reference lines
GRID = "#d9dde3"

#: Fixed categorical order. Assign in sequence; never cycle past the end —
#: a 6th series folds into "Other" or becomes small multiples.
CATEGORICAL = ["#5887DA", "#C95920", "#12925f", "#4a3aa7", "#cf4f80"]

#: Single-hue blue ramp for magnitude/ordinal encodings, light → dark.
BLUE_RAMP = ["#9db8ea", "#7ba0e1", "#5887DA", "#3a62b8", "#274784"]

#: Color follows the platform entity, in the fixed categorical order.
PLATFORM_COLORS = {
    "openai": CATEGORICAL[0],
    "gemini": CATEGORICAL[1],
    "claude": CATEGORICAL[2],
    "perplexity": CATEGORICAL[3],
    "google_ai_overview": CATEGORICAL[4],
}
PLATFORM_LABELS = {
    "openai": "ChatGPT",
    "gemini": "Gemini",
    "claude": "Claude",
    "perplexity": "Perplexity",
    "google_ai_overview": "AI Overviews",
}
#: Secondary encoding for scatter (CVD floor-band pair rose/green).
PLATFORM_MARKERS = {
    "openai": "o",
    "gemini": "s",
    "claude": "^",
    "perplexity": "D",
    "google_ai_overview": "v",
}

CAPTION = "Source: Spyglasses Research · research.spyglasses.io"

#: 12 × 6.3 in at dpi 100 → exactly 1200×630 px, the OpenGraph image size.
OG_FIGSIZE = (12.0, 6.3)

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_WATERMARK_PNG = _ASSETS / "brand" / "spyglasses_logotype_watermark.png"
_FONT_DIR = _ASSETS / "fonts"

_watermark_cache: np.ndarray | None = None


def theme() -> None:
    """Apply the Spyglasses figure theme. Call once before plotting."""
    import logging

    from matplotlib import font_manager

    family = ["Helvetica Neue", "Arial", "DejaVu Sans"]
    if _FONT_DIR.is_dir():
        for ttf in sorted(_FONT_DIR.glob("Figtree-*.ttf")):
            font_manager.fontManager.addfont(str(ttf))
        family = ["Figtree", *family]
        # Figtree carries every weight we use; matplotlib still logs a
        # spurious "Failed to find font weight medium" while scoring the
        # *fallback* families (Arial has no medium). Drop just that message.
        logging.getLogger("matplotlib.font_manager").addFilter(
            lambda r: "Failed to find font weight" not in r.getMessage()
        )

    plt.rcParams.update(
        {
            "font.family": family,
            "text.color": INK,
            "axes.edgecolor": INK_MUTED,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "axes.titlelocation": "left",
            "axes.titleweight": "medium",
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "axes.prop_cycle": plt.cycler(color=CATEGORICAL),
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "lines.linewidth": 2.0,
            "lines.markersize": 8,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "figure.dpi": 100,
        }
    )


def _watermark_image() -> np.ndarray:
    global _watermark_cache
    if _watermark_cache is None:
        _watermark_cache = plt.imread(_WATERMARK_PNG)  # RGBA float [0,1]
    return _watermark_cache


# Watermark: the logotype sits in a dedicated footer band (see _place_footer),
# never over the plot, so it can't collide with a tall bar or a low line in the
# lower-right corner.
WATERMARK_ALPHA = 0.45
WATERMARK_WIDTH_FRAC = 0.11


def _resized_watermark(fig_w_px: float, width_frac: float) -> np.ndarray:
    from PIL import Image

    img = _watermark_image()
    tw = max(1, int(fig_w_px * width_frac))
    th = max(1, int(tw * img.shape[0] / img.shape[1]))
    pil = Image.fromarray((img * 255).astype(np.uint8), mode="RGBA").resize(
        (tw, th), Image.LANCZOS
    )
    return np.asarray(pil).astype(float) / 255.0


def _place_footer(fig: plt.Figure, *, watermark: bool, caption: bool) -> None:
    """Reserve a clear footer band and put the caption + watermark inside it.

    The band is sized to the watermark and reserved via tight_layout's rect,
    so the axes (and their tick/axis labels) are pushed entirely above it. That
    guarantees the source line and logo never overlap chart content, whatever
    shape the plot takes.
    """
    dpi = fig.dpi
    fig_w_px = fig.get_figwidth() * dpi
    fig_h_px = fig.get_figheight() * dpi
    pad = 0.012 * fig_w_px

    wm = _resized_watermark(fig_w_px, WATERMARK_WIDTH_FRAC) if watermark else None
    band_px = 0.05 * fig_h_px  # floor: enough for the caption line
    if wm is not None:
        band_px = max(band_px, wm.shape[0] + 1.3 * pad)
    band_frac = band_px / fig_h_px if (watermark or caption) else 0.0

    fig.tight_layout(rect=(0, band_frac, 1, 1))

    if caption:
        fig.text(
            pad / fig_w_px,
            (band_px / 2) / fig_h_px,
            CAPTION,
            fontsize=9,
            color=INK_MUTED,
            ha="left",
            va="center",
        )
    if wm is not None:
        wm_h, wm_w = wm.shape[0], wm.shape[1]
        fig.figimage(
            wm,
            xo=int(fig_w_px - wm_w - pad),
            yo=int((band_px - wm_h) / 2),  # centered in the band
            alpha=WATERMARK_ALPHA,
            zorder=10,
            origin="upper",
        )


def save_figure(
    fig: plt.Figure,
    outdir: str | Path,
    name: str,
    *,
    watermark: bool = True,
    caption: bool = True,
    png_dpi: int = 200,
    og: bool = False,
) -> dict[str, Path]:
    """Write ``name.svg`` + ``name.png`` with the watermark and caption baked in.

    Branding is applied inside the save call so it cannot be forgotten.
    With ``og=True`` the figure is resized to OG_FIGSIZE at dpi 100 → the PNG
    is exactly 1200×630 px (the OpenGraph image size).
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if og:
        fig.set_size_inches(*OG_FIGSIZE)
        png_dpi = 100

    # figimage positions in device pixels, so fix the dpi BEFORE placing the
    # watermark and render both formats at that dpi — layout stays identical.
    fig.set_dpi(png_dpi)
    _place_footer(fig, watermark=watermark, caption=caption)

    paths = {
        "svg": outdir / f"{name}.svg",
        "png": outdir / f"{name}.png",
    }
    fig.savefig(paths["svg"], dpi=png_dpi)
    fig.savefig(paths["png"], dpi=png_dpi)
    plt.close(fig)
    return paths


def decile_plot(
    df,
    x: str,
    outcome: str,
    *,
    bins: int = 10,
    xlabel: str,
    ylabel: str,
    title: str,
    alpha: float = 0.10,
    figsize: tuple[float, float] = (9, 5.4),
) -> plt.Figure:
    """Outcome share by quantile bin of ``x``, with Wilson intervals.

    The flat-line-across-deciles chart is the most persuasive form for an
    equivalence (null) result — more persuasive than any coefficient.
    """
    import pandas as pd

    d = df[[x, outcome]].dropna().copy()
    d["bin"] = pd.qcut(d[x], bins, labels=False, duplicates="drop")
    g = d.groupby("bin")[outcome].agg(["mean", "count", "sum"])
    lo, hi = proportion_confint(g["sum"], g["count"], alpha=alpha, method="wilson")

    fig, ax = plt.subplots(figsize=figsize)
    ax.errorbar(
        g.index + 1,
        g["mean"],
        yerr=[g["mean"] - lo, hi - g["mean"]],
        fmt="o-",
        capsize=4,
        lw=2,
        ms=7,
        color=BRAND_BLUE,
    )
    overall = d[outcome].mean()
    ax.axhline(overall, ls="--", c=INK_MUTED, lw=1.5, label=f"overall rate ({overall:.1%})")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_ylim(0, 1)
    ax.set_xticks(range(1, len(g) + 1))
    ax.legend()
    return fig
