"""Shared toolkit for Spyglasses research studies (research.spyglasses.io)."""

from aeo_research.anonymize import (
    ColumnSpec,
    Datasheet,
    ReleaseError,
    pseudonymize,
    release_dataset,
)
from aeo_research.plotting import (
    BLUE_RAMP,
    BRAND_BLUE,
    CATEGORICAL,
    OG_FIGSIZE,
    PLATFORM_COLORS,
    PLATFORM_LABELS,
    PLATFORM_MARKERS,
    decile_plot,
    save_figure,
    theme,
)
from aeo_research.stats import (
    ClusteredLogitResult,
    TostResult,
    Verdict,
    collinearity_report,
    fit_clustered_logit,
    tost,
    wilson_interval,
)
from aeo_research.og_image import OG_SIZE, cover_crop, make_og_image
from aeo_research.synthetic import synthesize
from aeo_research.youtube import (
    description_features,
    extract_chapter_timestamps,
    parse_timestamp,
    parse_video_id,
    timestamp_matches_chapter,
)

__all__ = [
    "BLUE_RAMP",
    "BRAND_BLUE",
    "CATEGORICAL",
    "OG_FIGSIZE",
    "PLATFORM_COLORS",
    "PLATFORM_LABELS",
    "PLATFORM_MARKERS",
    "OG_SIZE",
    "ClusteredLogitResult",
    "ColumnSpec",
    "Datasheet",
    "ReleaseError",
    "TostResult",
    "Verdict",
    "collinearity_report",
    "cover_crop",
    "decile_plot",
    "description_features",
    "extract_chapter_timestamps",
    "fit_clustered_logit",
    "make_og_image",
    "parse_timestamp",
    "parse_video_id",
    "pseudonymize",
    "release_dataset",
    "save_figure",
    "synthesize",
    "theme",
    "timestamp_matches_chapter",
    "tost",
    "wilson_interval",
]
