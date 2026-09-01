"""Pre-freeze exploration: refined trusted-source taxonomy, panel-mix skew,
and instrument selection for the correlational layer.

DISCLOSED DEVIATION from clean pre-registration: this script looks at joint
distributions (consulted-vs-cited × authority metrics) BEFORE the spec
freezes, at the study owner's direction, to select which predictors the
frozen model carries (HC, AIPVS tier, and PageRank/ETV only if materially
different). The correlational layer is therefore labelled
exploratory-with-disclosed-selection in the article, not confirmatory.

Inputs: interim/features.csv, interim/domain_kinds.json, raw/domains.csv,
raw/aipvs.csv, raw/citations.csv, raw/context.csv.

Usage: uv run python experiments/007-site-consultations-observational/pipeline/03_prefreeze_explore.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import load_context  # noqa: E402

EXP = Path(__file__).resolve().parents[1]
RAW, INTERIM = EXP / "data" / "raw", EXP / "data" / "interim"
TOTAL_GRAPH_NODES = 121_091_933  # common_crawl_metadata, counts C5

KIND_LABELS = {
    "law_firm": "Law firms",
    "government_or_courts": "Government & courts",
    "bar_or_professional_association": "Bar & professional associations",
    "healthcare_provider": "Healthcare providers",
    "financial_or_insurance": "Financial & insurance",
    "ai_or_software_vendor": "AI & software vendors",
    "agency_or_consultancy": "Agencies & consultancies",
    "directory_or_ratings": "Directories & ratings",
    "news_or_media": "News & media",
    "academic_or_reference": "Academic & reference",
    "nonprofit_or_foundation": "Nonprofits & foundations",
    "ecommerce_or_retail": "E-commerce & retail",
    "other_business": "Other businesses",
    "unknown": "Unclassified",
}


def norm_domain(d: str) -> str:
    return d.lower().removeprefix("www.")


def load_inputs():
    features = pd.read_csv(INTERIM / "features.csv",
                           keep_default_na=False, na_values=[""])
    kinds = json.loads((INTERIM / "domain_kinds.json").read_text())
    domains = pd.read_csv(RAW / "domains.csv", keep_default_na=False,
                          na_values=[""]).set_index("domain")
    aipvs = pd.read_csv(RAW / "aipvs.csv").set_index("domain")
    citations = pd.read_csv(RAW / "citations.csv", keep_default_na=False,
                            na_values=[""])
    context = pd.read_csv(RAW / "context.csv", dtype=str, keep_default_na=False)
    return features, kinds, domains, aipvs, citations, context


def property_sectors(context: pd.DataFrame, kinds: dict[str, str]) -> pd.Series:
    first = context.drop_duplicates("property_id").set_index("property_id")
    return first["property_domain"].map(
        lambda d: kinds.get(norm_domain(d), "unknown") if d and "." in d else "unknown"
    )


def part1_taxonomy_and_skew(features, kinds, context) -> None:
    print("=" * 72)
    print("PART 1 — third-party consultations by kind (LLM taxonomy) + skew")
    tp = features[(features["scope_class"] == "third_party")
                  & (~features["scoped_domain"].str.startswith("*", na=False))].copy()
    tp["kind"] = tp["scoped_domain"].map(kinds).fillna("unknown")
    shares = (tp["kind"].value_counts(normalize=True) * 100).round(1)
    print(f"\nconsultation-weighted kind shares (n={len(tp):,} consultations):")
    print(shares.to_string())

    sectors = property_sectors(context, kinds)
    tp["trigger_sector"] = tp["property_id"].map(sectors).fillna("unknown")
    trig = (tp["trigger_sector"].value_counts(normalize=True) * 100).round(1)
    print("\nshare of third-party consultations BY TRIGGERING property sector:")
    print(trig.head(8).to_string())

    law_triggered = tp["trigger_sector"] == "law_firm"
    for label, mask in [("law-firm-client-triggered", law_triggered),
                        ("all other clients", ~law_triggered)]:
        s = (tp.loc[mask, "kind"].value_counts(normalize=True) * 100).round(1)
        print(f"\nkind mix within {label} (n={int(mask.sum()):,}):")
        print(s.head(8).to_string())

    # Sector-balanced view: every triggering sector weighted equally.
    sector_kind = (
        tp.groupby("trigger_sector")["kind"]
        .value_counts(normalize=True).rename("share").reset_index()
    )
    balanced = (sector_kind.groupby("kind")["share"].mean() * 100).round(1)
    print("\nsector-balanced kind shares (each client sector weighted equally):")
    print(balanced.sort_values(ascending=False).head(10).to_string())
    tp.to_csv(INTERIM / "third_party_consultations.csv", index=False)


def build_pool(features, citations, context, kinds):
    """Per-execution pool of third-party domains: consulted vs cited-only,
    discovery-class prompts only, own/competitor domains excluded on BOTH
    sides via the property context."""
    contexts = load_context(RAW / "context.csv")
    disc = features[features["prompt_class"] == "discovery"]
    exec_prop = disc.drop_duplicates("discovery_execution_id").set_index(
        "discovery_execution_id")["property_id"]

    consulted = (
        disc[disc["scope_class"] == "third_party"]
        .assign(domain=lambda d: d["scoped_domain"])
        [["discovery_execution_id", "property_id", "domain"]]
        .dropna().drop_duplicates()
        .assign(consulted=True)
    )

    cit = citations[citations["discovery_execution_id"].isin(exec_prop.index)].copy()
    cit["property_id"] = cit["discovery_execution_id"].map(exec_prop)
    cit["domain"] = cit["cited_domain"].map(norm_domain)
    keep = []
    for pid, group in cit.groupby("property_id"):
        ctx = contexts.get(pid)
        if ctx is None:
            continue
        cls = {d: ctx.scope_class(d) for d in group["domain"].unique()}
        keep.append(group[group["domain"].map(cls) == "third_party"])
    cited = (
        pd.concat(keep)[["discovery_execution_id", "property_id", "domain"]]
        .drop_duplicates().assign(consulted=False)
    )

    pool = pd.concat([consulted, cited], ignore_index=True)
    # A domain both consulted and cited in one execution counts as consulted.
    pool = (pool.sort_values("consulted", ascending=False)
                .drop_duplicates(["discovery_execution_id", "domain"]))
    return pool


def part2_metric_contrast(features, kinds, domains, aipvs, citations, context) -> None:
    print("\n" + "=" * 72)
    print("PART 2 — consulted vs cited-only (discovery prompts, third-party)")
    pool = build_pool(features, citations, context, kinds)
    n_cons = int(pool["consulted"].sum())
    print(f"pool rows: {len(pool):,}  (consulted {n_cons:,}, "
          f"cited-only {len(pool) - n_cons:,}; "
          f"{pool['domain'].nunique():,} distinct domains)")

    d = pool.join(domains, on="domain")
    d["hc_pct"] = 100 * (1 - d["hc_rank"] / TOTAL_GRAPH_NODES)
    d["pr_pct"] = 100 * (1 - d["page_rank_rank"] / TOTAL_GRAPH_NODES)
    d = d.join(aipvs[["aipvs", "tier_label", "confidence"]], on="domain")

    rows = []
    for metric in ["hc_pct", "pr_pct", "etv_percentile", "aipvs"]:
        for consulted, g in d.groupby("consulted"):
            v = g[metric].dropna()
            rows.append({
                "metric": metric,
                "class": "consulted" if consulted else "cited_only",
                "coverage": f"{len(v) / len(g):.0%}",
                "median": round(v.median(), 1) if len(v) else None,
                "p25": round(v.quantile(0.25), 1) if len(v) else None,
                "p75": round(v.quantile(0.75), 1) if len(v) else None,
            })
    print("\nmetric contrast (per pool row):")
    print(pd.DataFrame(rows).to_string(index=False))

    print("\nAIPVS tier mix (rows with a score):")
    tier = (d.dropna(subset=["tier_label"])
             .groupby("consulted")["tier_label"]
             .value_counts(normalize=True).mul(100).round(1))
    print(tier.to_string())

    print("\nunranked-in-CommonCrawl share (Audit D — missingness IS signal):")
    print((d.groupby("consulted")["hc_rank"]
            .apply(lambda s: f"{s.isna().mean():.1%} unranked")).to_string())

    # Domain-level view: one row per (domain, class) — a domain consulted
    # anywhere counts as consulted. Removes row-frequency weighting, which
    # otherwise distorts the sampled-AIPVS coverage.
    import numpy as np
    dl = (d.sort_values("consulted", ascending=False)
            .drop_duplicates("domain")
            .assign(log10_hc_rank=lambda x: np.log10(x["hc_rank"])))
    print(f"\nDOMAIN-level contrast ({int(dl['consulted'].sum()):,} consulted, "
          f"{int((~dl['consulted']).sum()):,} cited-only domains):")
    rows = []
    for metric in ["hc_rank", "log10_hc_rank", "aipvs", "etv_percentile"]:
        for consulted, g in dl.groupby("consulted"):
            v = g[metric].dropna()
            rows.append({
                "metric": metric,
                "class": "consulted" if consulted else "cited_only",
                "coverage": f"{len(v) / len(g):.0%}",
                "median": round(float(v.median()), 2) if len(v) else None,
            })
    print(pd.DataFrame(rows).to_string(index=False))
    print("\ndomain-level ranked-in-CommonCrawl share:")
    print((dl.groupby("consulted")["hc_rank"]
             .apply(lambda s: f"{1 - s.isna().mean():.1%} ranked")).to_string())
    print("\ndomain-level AIPVS tier mix (scored domains):")
    print((dl.dropna(subset=["tier_label"])
             .groupby("consulted")["tier_label"]
             .value_counts(normalize=True).mul(100).round(1)).to_string())
    d.to_csv(INTERIM / "pool_with_metrics.csv", index=False)


def main() -> None:
    features, kinds, domains, aipvs, citations, context = load_inputs()
    part1_taxonomy_and_skew(features, kinds, context)
    part2_metric_contrast(features, kinds, domains, aipvs, citations, context)


if __name__ == "__main__":
    main()
