"""Descriptive-layer figures F1–F4, F6 (exploratory; spec §8 step 2).

Publication rules honored here:
- shares/rates only — no absolute counts on any axis or label;
- timelines end 2026-08-24: the nightly DataForSEO capture path lost fan-out
  visibility on 2026-08-25 (spec Audit E) — F1 shows the two capture paths
  separately so the claim doesn't lean on the broken one;
- partial current week dropped.

Usage: uv run python experiments/007-site-consultations-observational/pipeline/04_figures.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from aeo_research.plotting import (  # noqa: E402
    BRAND_BLUE,
    INK_MUTED,
    PLATFORM_COLORS,
    PLATFORM_LABELS,
    save_figure,
    theme,
)

EXP = Path(__file__).resolve().parents[1]
FIGURES = EXP / "figures"
CLIFF = date(2026, 8, 25)      # nightly DataForSEO capture loss (Audit E)
LAST_FULL_WEEK = date(2026, 8, 24)  # last week start fully before the cliff
MIN_WEEK_N = 150               # suppress noisy tiny-denominator weeks

#: F6 category map over the top third-party consulted domains (data-driven,
#: committed for reproducibility). Tail and unmapped domains fold into
#: "Other businesses & sites".
DOMAIN_KINDS: dict[str, str] = {}
GOV_HINTS = ("leg.", "legislature", "courts", "senate", "capitol")
KIND_LISTS = {
    "Bar & professional associations": [
        "floridabar.org", "americanbar.org", "texasbar.com", "calbar.ca.gov",
        "actec.org", "content.naic.org", "nysba.org", "osbar.org",
    ],
    "Healthcare systems": [
        "mayoclinic.org", "uwmedicine.org", "swedish.org", "allinahealth.org",
        "bannerhealth.com", "med.umn.edu", "clevelandclinic.org", "hopkinsmedicine.org",
    ],
    "Directories & ratings": [
        "chambers.com", "ambest.com", "clutch.co", "lawyers.com",
        "energysage.com", "avvo.com", "g2.com", "capterra.com", "trustpilot.com",
    ],
    "Academic & reference": [
        "law.cornell.edu", "en.wikipedia.org",
    ],
    "News & media": [
        "artemis.bm", "reuters.com", "techcrunch.com",
    ],
}
for kind, domains in KIND_LISTS.items():
    for d in domains:
        DOMAIN_KINDS[d] = kind


def domain_kind(domain: str) -> str:
    if domain in DOMAIN_KINDS:
        return DOMAIN_KINDS[domain]
    if domain.endswith(".gov") or any(h in domain for h in GOV_HINTS):
        return "Government & law"
    if domain.endswith(".edu"):
        return "Academic & reference"
    if domain.startswith("*."):
        return "Wildcard artifacts"
    return "Businesses (incl. untracked competitors)"


def load() -> pd.DataFrame:
    df = pd.read_csv(EXP / "data" / "interim" / "features.csv",
                     keep_default_na=False, na_values=[""])
    df["week"] = pd.to_datetime(df["week"]).dt.date
    df["day"] = pd.to_datetime(df["day"]).dt.date
    return df[df["week"] <= LAST_FULL_WEEK].copy()


def f1_site_scope_timeline(df: pd.DataFrame) -> None:
    """Weekly site: share on CATEGORY-LEVEL prompts, by capture path.

    Discovery-class only, so the two capture paths compare like for like.
    Weeks below the volume floor become gaps (NaN), never interpolated lines.
    """
    d = df[(df["platform"] == "openai") & (df["prompt_class"] == "discovery")]
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    styles = {"report_direct": ("--", "API capture (reports)"),
              "nightly_dfs": ("-", "UI-scrape capture (nightly)")}
    weeks = pd.Index(sorted(d["week"].unique()))
    for path, (ls, label) in styles.items():
        sub = d[d["capture_path"] == path]
        g = sub.groupby("week").agg(n=("scoped", "size"), scoped=("scoped", "sum"))
        pct = (100 * g["scoped"] / g["n"]).where(g["n"] >= 75).reindex(weeks)
        ax.plot(weeks, pct.values, ls, color=BRAND_BLUE, label=label,
                marker="o", ms=5)
    step_week = date(2026, 7, 27)
    ax.axvline(step_week, color=INK_MUTED, lw=1.2, ls=":")
    ax.annotate("week of Jul 27:\nsite: switches on", xy=(step_week, 40),
                xytext=(date(2026, 6, 20), 42), fontsize=10, color=INK_MUTED,
                arrowprops={"arrowstyle": "->", "color": INK_MUTED, "lw": 1.2})
    ax.set_title("ChatGPT switched on site:-scoped research in one week — late July 2026")
    ax.set_ylabel("share of grounding searches using site:\non category-level prompts  (%)")
    ax.set_xlabel("")
    ax.set_ylim(0)
    ax.legend(loc="upper left")
    fig.autofmt_xdate(rotation=0, ha="center")
    save_figure(fig, FIGURES, "f1-site-scope-emergence")


def f2_named_brand_timeline(df: pd.DataFrame) -> None:
    """Monthly share of non-scoped searches that name a brand, by platform.

    Monthly buckets: weekly slices are too thin for the Claude add-on tail
    and would show capture noise as behavior.
    """
    d = df[(~df["scoped"]) & df["platform"].isin(["openai", "gemini", "claude"])]
    d = d.assign(
        named=d["named_class"].isin(["own", "competitor", "both"]),
        month=pd.to_datetime(d["day"].astype(str)).dt.to_period("M").dt.to_timestamp(),
    )
    months = pd.Index(sorted(d["month"].unique()))
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    for platform in ["openai", "gemini", "claude"]:
        sub = d[d["platform"] == platform]
        g = sub.groupby("month").agg(n=("named", "size"), named=("named", "sum"))
        pct = (100 * g["named"] / g["n"]).where(g["n"] >= 300).reindex(months)
        if pct.notna().sum() == 0:
            continue
        ax.plot(months, pct.values, color=PLATFORM_COLORS[platform],
                label=PLATFORM_LABELS[platform], marker="o", ms=6)
    ax.set_title("Naming a brand in the search predates the site: operator — on every platform")
    ax.set_ylabel("share of open-web grounding searches\nnaming a brand  (%)")
    ax.set_xlabel("")
    ax.set_ylim(0)
    ax.legend(loc="upper left")
    fig.autofmt_xdate(rotation=0, ha="center")
    save_figure(fig, FIGURES, "f2-named-brand-share")


def f3_scope_class_mix(df: pd.DataFrame) -> None:
    d = df[df["scoped"] & df["scope_class"].notna()]
    shares = (d["scope_class"].value_counts(normalize=True) * 100).reindex(
        ["third_party", "competitor", "own"]
    )
    labels = {
        "third_party": "Third-party sites",
        "competitor": "A tracked competitor's site",
        "own": "The brand's own site",
    }
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    bars = ax.barh([labels[k] for k in shares.index], shares.values,
                   color=BRAND_BLUE, height=0.62)
    for bar, v in zip(bars, shares.values):
        ax.text(v + 1, bar.get_y() + bar.get_height() / 2, f"{v:.0f}%",
                va="center", fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of site:-scoped searches  (%)")
    ax.set_title("When AI consults a site directly, it's usually not the brand being asked about")
    ax.grid(axis="x", alpha=0.6)
    ax.grid(axis="y", visible=False)
    save_figure(fig, FIGURES, "f3-consultation-mix")


def f4_consult_rate_by_prompt_class(df: pd.DataFrame) -> None:
    d = df[df["platform"] == "openai"]
    per_answer = d.groupby(["prompt_class", "discovery_execution_id"])["scoped"].any()
    g = per_answer.groupby("prompt_class").agg(["mean", "count", "sum"])
    g = g.reindex(["brand", "comparison", "discovery"])
    lo, hi = proportion_confint(g["sum"], g["count"], alpha=0.05, method="wilson")
    labels = {
        "brand": "Brand-identity\nprompts",
        "comparison": "Brand-comparison\nprompts",
        "discovery": "Category-level\nprompts",
    }
    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    x = range(len(g))
    ax.bar(x, 100 * g["mean"], color=BRAND_BLUE, width=0.56)
    ax.errorbar(x, 100 * g["mean"],
                yerr=[100 * (g["mean"] - lo), 100 * (hi - g["mean"])],
                fmt="none", ecolor=INK_MUTED, capsize=5, lw=1.5)
    for xi, v in zip(x, g["mean"]):
        ax.text(xi, 100 * v + 2.2, f"{100 * v:.0f}%", ha="center", fontsize=12)
    ax.set_xticks(list(x), [labels[k] for k in g.index])
    ax.set_ylabel("ChatGPT answers with ≥1 direct site consultation  (%)")
    ax.set_title("Comparison questions are what send AI straight to a website")
    ax.set_ylim(0, 100 * g["mean"].max() * 1.35)
    save_figure(fig, FIGURES, "f4-consult-rate-by-prompt-class")


def f6_third_party_kinds(df: pd.DataFrame) -> None:
    d = df[df["scope_class"] == "third_party"].copy()
    d["kind"] = d["scoped_domain"].map(domain_kind)
    shares = (d["kind"].value_counts(normalize=True) * 100)
    shares = shares[shares.index != "Wildcard artifacts"]
    fig, ax = plt.subplots(figsize=(9.6, 5.2))
    bars = ax.barh(shares.index, shares.values, color=BRAND_BLUE, height=0.62)
    for bar, v in zip(bars, shares.values):
        ax.text(v + 0.8, bar.get_y() + bar.get_height() / 2, f"{v:.0f}%",
                va="center", fontsize=11)
    ax.invert_yaxis()
    ax.set_xlabel("share of third-party site consultations  (%)")
    ax.set_title("AI's trusted-source list is institutional, not social")
    ax.grid(axis="x", alpha=0.6)
    ax.grid(axis="y", visible=False)
    save_figure(fig, FIGURES, "f6-third-party-kinds")
    print("\nF6 kind shares (%):")
    print(shares.round(1).to_string())
    reddit = int((d["scoped_domain"] == "reddit.com").sum())
    print(f"reddit.com third-party consultations: {reddit} "
          f"({reddit / len(d):.2%} of third-party)")


def main() -> None:
    theme()
    df = load()
    print(f"{len(df):,} rows through {LAST_FULL_WEEK}")
    f1_site_scope_timeline(df)
    f2_named_brand_timeline(df)
    f3_scope_class_mix(df)
    f4_consult_rate_by_prompt_class(df)
    f6_third_party_kinds(df)
    print(f"\nfigures -> {FIGURES}")


if __name__ == "__main__":
    main()
