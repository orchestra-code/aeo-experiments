#!/usr/bin/env python3
"""Step 2 — the spec §2 audits. Prints and writes results/audit.txt.

Do not proceed to 03_model.py until the output here matches the spec's
expectations (or the spec is amended pre-freeze with the discrepancy noted).
"""

from __future__ import annotations

import io
import sys

import pandas as pd
from common import CITATIONS_CSV, PRIMARY_PLATFORMS, RESULTS, VIDEOS_CSV


def main() -> None:
    rows = pd.read_csv(CITATIONS_CSV)
    units = pd.read_csv(VIDEOS_CSV)
    out = io.StringIO()

    def p(*args):
        print(*args)
        print(*args, file=out)

    p("=" * 72)
    p("AUDIT — experiment 001 (spec §2)")
    p("=" * 72)

    primary = units[units["platform"].isin(PRIMARY_PLATFORMS)]
    cited = int(primary["cited"].sum())
    n = len(primary)
    p(f"\nPrimary frame (openai/gemini/claude, unit = execution x video)")
    p(f"  units                  : {n:,}")
    p(f"  cited inline           : {cited:,} ({cited / n:.1%})")
    p(f"  evaluated, not cited   : {n - cited:,} ({1 - cited / n:.1%})")
    p(f"  EFFECTIVE SAMPLE (rarer class): {min(cited, n - cited):,}")
    p(f"  -> supports ~{min(cited, n - cited) // 15} parameters at 15 events each")

    p("\nAudit A — negative-class contamination (failed fetches)")
    neg = primary[primary["cited"] == 0]
    bad = int((neg["fetch_ok"] == 0).sum())
    p(f"  not-cited units with fetch_ok=0 : {bad:,} ({bad / max(len(neg), 1):.1%} of negatives)")
    nosim = int(primary["similarity"].isna().sum())
    p(f"  units with null similarity      : {nosim:,} (excluded from the model — report in article)")

    p("\nAudit B — outcome semantics: see spec §2 (citation-type.ts quoted).")
    by_pt = rows.pivot_table(
        index="platform", columns="citation_type", values="citation_id", aggfunc="count"
    ).fillna(0).astype(int)
    p(by_pt.to_string())
    aio_pplx = rows[rows["platform"].isin(["google_ai_overview", "perplexity"])]
    leaked = int((aio_pplx["citation_type"] == "EVALUATED_SOURCE").sum())
    p(f"  AIO/Perplexity EVALUATED_SOURCE rows (must be 0): {leaked}")

    p("\nAudit C — independence")
    p(f"  distinct videos in primary frame : {primary['video_id'].nunique():,}")
    repeats = n - primary["video_id"].nunique()
    p(f"  repeat appearances               : {repeats:,} ({repeats / n:.1%})")
    per_exec = primary.groupby("execution_id").size()
    p(f"  executions                       : {len(per_exec):,}")
    p(f"  single-YouTube-video executions  : {(per_exec == 1).sum():,} ({(per_exec == 1).mean():.1%})")
    disc = primary.groupby("execution_id")["cited"].agg(["sum", "size"])
    disc = disc[(disc["sum"] > 0) & (disc["sum"] < disc["size"])]
    p(f"  discordant executions            : {len(disc):,}")

    p("\nAudit D — hostname-fallback misclassification exposure")
    for plat in PRIMARY_PLATFORMS:
        sub = primary[primary["platform"] == plat]
        multi = sub[sub["n_youtube_in_execution"] > 1]
        p(
            f"  {plat:8s}: {len(multi):,}/{len(sub):,} units in multi-YouTube executions "
            f"({len(multi) / max(len(sub), 1):.1%})"
            + ("  <- markdown-derived, exposed" if plat != "claude" else "  <- clean (citations[] sets)")
        )

    p("\nMissingness (primary frame)")
    for col in ["audience_size", "video_view_count", "reactions_count", "duration_seconds",
                "video_category", "video_has_captions", "published_at"]:
        p(f"  {col:20s}: {primary[col].isna().mean():6.1%} null")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "audit.txt").write_text(out.getvalue())
    print(f"\n  -> {RESULTS / 'audit.txt'}")

    if leaked:
        print("\n!! Audit B failed: AIO/Perplexity produced EVALUATED_SOURCE rows.")
        sys.exit(1)


if __name__ == "__main__":
    main()
