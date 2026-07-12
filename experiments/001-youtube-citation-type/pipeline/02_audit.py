#!/usr/bin/env python3
"""Step 2 — the spec §2 audits (post-pivot). Writes results/audit.txt.

Do not proceed to 03_model.py until the output matches the spec's
expectations (or the spec is amended pre-freeze with the discrepancy noted).
"""

from __future__ import annotations

import io

import pandas as pd
from common import CITATIONS_CSV, PRIMARY_PLATFORM, RESULTS, VIDEOS_CSV


def main() -> None:
    rows = pd.read_csv(CITATIONS_CSV)
    units = pd.read_csv(VIDEOS_CSV)
    out = io.StringIO()

    def p(*args):
        print(*args)
        print(*args, file=out)

    p("=" * 72)
    p("AUDIT — experiment 001 (spec §2, moment-citation design)")
    p("=" * 72)

    primary = units[(units["platform"] == PRIMARY_PLATFORM) & (units["cited"] == 1)]
    n = len(primary)
    moments = int(primary["moment_cited"].sum())
    p(f"\nPrimary frame (AIO inline, unit = execution x video)")
    p(f"  units                : {n:,}")
    p(f"  moment-cited (t=)    : {moments:,} ({moments / n:.1%})")
    p(f"  plain citations      : {n - moments:,}")
    p(f"  EFFECTIVE SAMPLE (rarer class): {min(moments, n - moments):,}")
    p(f"  -> supports ~{min(moments, n - moments) // 15} parameters at 15 events each")

    p("\nAudit A — video-metadata completeness (gate: >=95% before freeze)")
    for col in ["duration_seconds", "video_has_captions", "video_category",
                "video_view_count", "audience_size", "reactions_count"]:
        p(f"  {col:20s}: {primary[col].notna().mean():6.1%} covered")
    p(f"  similarity           : {primary['similarity'].notna().mean():6.1%} covered "
      "(null = page never fetched)")

    p("\nAudit B — outcome integrity")
    ts = primary[primary["moment_cited"] == 1]
    with_dur = ts[ts["duration_seconds"].notna()]
    if len(with_dur):
        bad = with_dur[with_dur["timestamp_seconds"] > with_dur["duration_seconds"]]
        p(f"  timestamps > duration : {len(bad):,} of {len(with_dur):,} checkable "
          f"({len(bad) / len(with_dur):.2%}) — robustness #7 excludes these")
    other = rows[(rows["platform"] != PRIMARY_PLATFORM)]
    leaked = int(other["timestamp_seconds"].notna().sum())
    p(f"  non-AIO rows with timestamps : {leaked:,} (spec §A expects 0)")

    p("\nAudit C — independence")
    p(f"  distinct videos      : {primary['video_id'].nunique():,}")
    repeats = n - primary["video_id"].nunique()
    p(f"  repeat appearances   : {repeats:,} ({repeats / n:.1%}) -> two-way clustering")
    per_exec = primary.groupby("execution_id").size()
    p(f"  executions           : {len(per_exec):,}; "
      f"multi-video executions: {(per_exec > 1).mean():.1%}")

    p("\nAudit D — snapshot timing: engagement/audience metrics are")
    p("  enrichment-time snapshots; noted as an article limitation.")

    p("\nCross-platform (descriptive companion, from citations.csv)")
    tab = rows.assign(has_ts=rows["timestamp_seconds"].notna()).pivot_table(
        index="platform", columns="citation_type", values="has_ts",
        aggfunc=["count", "sum"],
    ).fillna(0).astype(int)
    p(tab.to_string())

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "audit.txt").write_text(out.getvalue())
    print(f"\n  -> {RESULTS / 'audit.txt'}")


if __name__ == "__main__":
    main()
