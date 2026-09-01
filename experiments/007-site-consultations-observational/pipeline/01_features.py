"""extract.csv + context.csv → interim/features.csv (one row per execution).

Adds read-time classifications (scope_class, named_class, prompt_class),
week buckets, and capture-path flags. Drops query_text on output — the
interim table is the figure/model input and needs no raw text.

Also prints the Audit A/B/E counters the spec asks for:
- properties in extract with no context row
- rows where the persisted siteScopeDomain disagrees with a light text parse
- classification distributions

Usage: uv run python experiments/007-site-consultations-observational/pipeline/01_features.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import load_context, named_class, prompt_class  # noqa: E402
from aeo_research.brand_match import normalize_domain_or_null  # noqa: E402

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
INTERIM = EXP / "data" / "interim"

#: Light port of site-scope.ts's operator regex, for the fallback AUDIT only —
#: the persisted column is the source of truth (stamped at ingest + backfilled).
_SITE_TOKEN = re.compile(r"(^|\s)(-?)site:\s?(\S+)", re.IGNORECASE)


def parse_site_scope(query: str) -> str | None:
    for m in _SITE_TOKEN.finditer(query or ""):
        if m.group(2) == "-":
            continue
        token = m.group(3).split("/")[0].split("?")[0]
        host = normalize_domain_or_null(token)
        if host and "." in host:
            return host
        return None  # first operator wins, parseable or not
    return None


def main() -> None:
    df = pd.read_csv(RAW / "extract.csv", dtype=str, keep_default_na=False)
    df["executed_at"] = pd.to_datetime(df["executed_at"], utc=True, format="ISO8601")
    contexts = load_context(RAW / "context.csv")
    print(f"{len(df):,} execution rows, {len(contexts):,} property contexts")

    missing_ctx = set(df["property_id"]) - set(contexts)
    print(f"Audit A: properties missing context: {len(missing_ctx)}")

    df["scoped_domain"] = df["site_scope_domain"].map(
        lambda d: normalize_domain_or_null(d) if d else None
    )
    df["scoped"] = df["scoped_domain"].notna()

    # Audit B: persisted parse vs light text fallback.
    fallback = df["query_text"].map(parse_site_scope)
    disagree = int((fallback.fillna("∅") != df["scoped_domain"].fillna("∅")).sum())
    print(f"Audit B: persisted-vs-fallback parse disagreements: {disagree:,} "
          f"({disagree / len(df):.2%}) — fallback is the lighter parser; "
          f"the persisted column wins")

    # Per-property classification, grouped so each matcher compiles once.
    scope_class = pd.Series(index=df.index, dtype=object)
    named = pd.Series(index=df.index, dtype=object)
    for pid, idx in df.groupby("property_id").groups.items():
        ctx = contexts.get(pid)
        if ctx is None:
            continue
        sub = df.loc[idx]
        scope_class.loc[idx] = sub["scoped_domain"].map(ctx.scope_class)
        matcher = ctx.named_matcher()
        unscoped = sub.index[~sub["scoped"]]
        named.loc[unscoped] = df.loc[unscoped, "query_text"].map(
            lambda q: named_class(matcher(q))
        )
    df["scope_class"] = scope_class
    df["named_class"] = named

    df["prompt_class"] = df["query_type"].map(lambda t: prompt_class(t or None))
    df["day"] = df["executed_at"].dt.date
    df["week"] = df["executed_at"].dt.to_period("W").dt.start_time.dt.date
    df["capture_path"] = df["run_type"].map(
        {"nightly": "nightly_dfs", "weekly_grounding": "weekly_harvest"}
    ).fillna("report_direct")

    print("\nscoped rows by platform:")
    print(df[df["scoped"]].groupby("platform").size().to_string())
    print("\nscope_class distribution (scoped rows):")
    print(df[df["scoped"]]["scope_class"].value_counts().to_string())
    print("\nnamed_class distribution (non-scoped rows):")
    print(df[~df["scoped"]]["named_class"].value_counts(dropna=False).to_string())

    out_cols = [
        "execution_link_id", "discovery_execution_id", "property_id", "platform",
        "executed_at", "day", "week", "capture_path", "run_type", "query_type",
        "prompt_class", "scoped", "scoped_domain", "scope_class", "named_class",
        "scoped_hc_rank", "scoped_harmonic_centrality", "scoped_organic_etv",
        "scoped_etv_percentile",
    ]
    INTERIM.mkdir(parents=True, exist_ok=True)
    df[out_cols].to_csv(INTERIM / "features.csv", index=False)
    print(f"\nwrote {INTERIM / 'features.csv'} ({len(df):,} rows)")

    # Top third-party scoped domains — input for the F6 category map.
    top = (
        df[df["scope_class"] == "third_party"]
        .groupby("scoped_domain").size().sort_values(ascending=False).head(60)
    )
    top.to_csv(INTERIM / "top_third_party_domains.csv", header=["n"])
    print(f"wrote {INTERIM / 'top_third_party_domains.csv'}")


if __name__ == "__main__":
    main()
