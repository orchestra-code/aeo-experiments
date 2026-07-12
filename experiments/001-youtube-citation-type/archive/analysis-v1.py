#!/usr/bin/env python3
"""
Does audience size predict AI citation? — YouTube study
Implements the pre-analysis plan in youtube-citation-study-spec.md

Usage:
    python analysis.py --data enriched_citations.csv
    python analysis.py --synthetic            # demo on simulated data
    python analysis.py --synthetic --true-effect 0.25   # sanity-check the test has teeth

Expects the schema in §3 of the spec. Columns that are missing are skipped with a warning
rather than crashing, so you can run this on a partial enrichment.

Requires: pandas numpy statsmodels matplotlib scipy
"""

import argparse
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Pre-registered constants — DO NOT CHANGE AFTER SEEING THE DATA
# ---------------------------------------------------------------------------
SESOI_OR = 1.10                       # smallest odds ratio worth caring about, per SD
SESOI_LOGODDS = np.log(SESOI_OR)      # 0.0953
ALPHA = 0.10                          # two-sided; TOST uses ALPHA/2 per one-sided test
Z_CRIT = stats.norm.ppf(1 - ALPHA / 2)  # 1.645 -> 90% CI

PRIMARY = ["log_subs", "engagement_rate", "log_views"]   # H1, H2, H3
POSITIVE_CONTROL = "similarity"                          # H4
PLACEBO = "placebo_dow"                                  # H5


# ---------------------------------------------------------------------------
# Data prep
# ---------------------------------------------------------------------------
def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Build the derived variables from §3 of the spec."""
    df = df.copy()

    df["log_subs"] = np.log10(df["subscriber_count"].fillna(0) + 1)
    df["log_views"] = np.log10(df["view_count"].fillna(0) + 1)

    likes = df["like_count"].fillna(0)
    comments = df["comment_count"].fillna(0)
    df["log_engagement"] = np.log10(likes + comments + 1)
    df["engagement_rate"] = (likes + comments) / (df["view_count"].fillna(0) + 1)
    # engagement_rate is itself right-skewed; log1p it so a handful of viral
    # comment-brigaded videos don't dictate the fit
    df["engagement_rate"] = np.log1p(df["engagement_rate"] * 100)

    if "duration_sec" in df:
        df["log_duration"] = np.log10(df["duration_sec"].fillna(0) + 1)
    if "age_days" in df:
        df["log_age"] = np.log10(df["age_days"].clip(lower=0).fillna(0) + 1)

    # Placebo (H5): day-of-week of publication cannot plausibly affect citation.
    # If this shows an effect, our standard errors are too small.
    if "published_at" in df:
        df[PLACEBO] = pd.to_datetime(df["published_at"], errors="coerce").dt.dayofweek.fillna(0)

    # Standardize continuous predictors so coefficients are per-SD and the
    # SESOI in §5 is interpretable across variables.
    to_z = [c for c in ["log_subs", "log_views", "log_engagement", "engagement_rate",
                        "similarity", "log_duration", "log_age",
                        "n_sources_evaluated", PLACEBO] if c in df]
    for c in to_z:
        sd = df[c].std()
        df[c] = (df[c] - df[c].mean()) / sd if sd > 0 else 0.0

    return df


def audit(df: pd.DataFrame) -> None:
    """§2 + §6.2 — the checks that determine whether the study is viable at all."""
    print("=" * 74)
    print("PRE-FLIGHT AUDIT")
    print("=" * 74)

    n = len(df)
    cited = int(df["cited"].sum())
    print(f"  rows                     : {n:,}")
    print(f"  cited (inline)           : {cited:,} ({cited/n:.1%})")
    print(f"  evaluated, not cited     : {n-cited:,} ({1-cited/n:.1%})")

    # §6.2 — the rarer class is the real sample size
    events = min(cited, n - cited)
    print(f"\n  EFFECTIVE SAMPLE (rarer class): {events:,}")
    print(f"  -> supports ~{events // 15} predictors at 15 events/variable")

    # §2 Audit C — deduplication
    if "video_id" in df:
        dupes = n - df["video_id"].nunique()
        print(f"\n  distinct videos          : {df['video_id'].nunique():,} "
              f"({dupes:,} repeat appearances)")
        if dupes > n * 0.15:
            print("  !! >15% repeats. Cluster on video_id too, and run robustness #5.")

    # §6.2 — which design are we in?
    if "response_id" in df:
        per_resp = df.groupby("response_id").size()
        singletons = int((per_resp == 1).sum())
        print(f"\n  responses                : {len(per_resp):,}")
        print(f"  single-YouTube-source    : {singletons:,} ({singletons/len(per_resp):.1%})")

        discordant = (
            df.groupby("response_id")["cited"]
            .agg(["sum", "size"])
            .query("sum > 0 and sum < size")
        )
        print(f"  DISCORDANT SETS          : {len(discordant):,}")
        if len(discordant) < 100:
            print("  -> Too few for conditional logit, as expected.")
            print("     Using pooled logit + cluster-robust SEs. This is the right call.")

    # §2 Audit A — the failed-fetch problem
    if "fetch_ok" in df:
        failed = int((df["fetch_ok"] == 0).sum())
        if failed:
            uncited_fails = int(((df["fetch_ok"] == 0) & (df["cited"] == 0)).sum())
            print(f"\n  !! FETCH FAILURES        : {failed:,} "
                  f"({uncited_fails:,} of them in the not-cited class)")
            print(f"     That is {uncited_fails/(n-cited):.1%} of your negatives.")
            print("     If >10%, these are page-accessibility artifacts, not editorial")
            print("     decisions. See spec §2 Audit A. Run robustness #7.")
    else:
        print("\n  !! NO `fetch_ok` COLUMN. You cannot distinguish 'model declined to cite'")
        print("     from 'fetch failed'. See spec §2 Audit A before trusting any result.")
    print()


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def collinearity_check(df: pd.DataFrame) -> float:
    """
    Spec §5a. log_subs and log_views measure nearly the same latent thing
    ('how big is this channel'). Putting both in one model inflates the SE on each
    to the point where the equivalence test cannot conclude anything -- you get
    INCONCLUSIVE even when the true effect is exactly zero. This is the single
    biggest threat to the power of this study, and it is entirely self-inflicted.
    """
    r = df[["log_subs", "log_views"]].corr().iloc[0, 1]
    print("=" * 74)
    print("COLLINEARITY CHECK (spec §5a)")
    print("=" * 74)
    print(f"  corr(log_subs, log_views) = {r:.3f}")
    if abs(r) > 0.7:
        print("  -> HIGH. Fitting log_subs and log_views in SEPARATE models.")
        print("     Together they would roughly double each other's standard error")
        print("     and destroy the equivalence test. See spec §5a.\n")
    else:
        print("  -> Acceptable. Separate models used anyway for consistency.\n")
    return r


def fit_focal(df: pd.DataFrame, focal: str):
    """
    Pooled logistic regression with cluster-robust SEs, fitted SEPARATELY for each
    focal predictor to avoid the subs/views collinearity trap.

    Spec §5: we do NOT use conditional/fixed-effects logit -- it discards every
    response without within-response outcome variation, which is nearly all of them
    when each response has one YouTube source. Clustering handles the dependence
    without throwing away the singletons.

    engagement_rate is a RATIO (likes+comments)/views, so it is already decorrelated
    from raw channel size (VIF ~1) and stays in every model as a control.
    """
    terms = [POSITIVE_CONTROL, focal]
    if focal != "engagement_rate" and "engagement_rate" in df:
        terms.append("engagement_rate")
    terms += [c for c in ["log_duration", "log_age", "n_sources_evaluated"] if c in df]

    formula = "cited ~ " + " + ".join(dict.fromkeys(terms))
    if "assistant" in df and df["assistant"].nunique() > 1:
        formula += " + C(assistant)"

    groups = df["response_id"] if "response_id" in df else np.arange(len(df))
    model = smf.logit(formula, data=df).fit(
        disp=False, cov_type="cluster", cov_kwds={"groups": groups}
    )
    return model, formula


def tost(model, var: str) -> dict:
    """
    §5 + §6.3 — Two One-Sided Tests.

    A non-significant p-value does not establish absence of effect. TOST asks the
    right question: is the entire 90% CI inside the band we've declared negligible?
    """
    b = model.params[var]
    se = model.bse[var]
    lo, hi = b - Z_CRIT * se, b + Z_CRIT * se

    # H0_lower: beta <= -SESOI   |  H0_upper: beta >= +SESOI
    # Reject both => the effect is inside the band => practically equivalent to zero.
    p_lower = stats.norm.sf((b + SESOI_LOGODDS) / se)   # P(reject beta <= -SESOI)
    p_upper = stats.norm.cdf((b - SESOI_LOGODDS) / se)  # P(reject beta >= +SESOI)
    p_tost = max(p_lower, p_upper)

    equivalent = (lo > -SESOI_LOGODDS) and (hi < SESOI_LOGODDS)
    nonzero = (lo > 0) or (hi < 0)

    if equivalent and not nonzero:
        verdict = "NULL — practically equivalent to zero"
    elif equivalent and nonzero:
        verdict = "detectable but NEGLIGIBLE (inside SESOI)"
    elif nonzero:
        verdict = "REAL EFFECT — exceeds SESOI"
    else:
        verdict = "INCONCLUSIVE — underpowered, do NOT claim a null"

    return {
        "var": var, "beta": b, "se": se,
        "or": np.exp(b), "or_lo": np.exp(lo), "or_hi": np.exp(hi),
        "p_nhst": model.pvalues[var], "p_tost": p_tost,
        "verdict": verdict,
    }


def report(df: pd.DataFrame) -> pd.DataFrame:
    print("=" * 74)
    print("RESULTS")
    print("=" * 74)
    print(f"  n = {len(df):,}")
    print(f"  SESOI: odds ratio within [{1/SESOI_OR:.3f}, {SESOI_OR:.3f}] per SD")
    print(f"  Intervals are {int((1-ALPHA)*100)}% CIs.")
    print("  Each focal predictor is fitted in its own model (see §5a).\n")

    # H4 first — the canary. If similarity doesn't predict citation, nothing else
    # in this output means anything.
    m0, _ = fit_focal(df, "log_subs")
    r = tost(m0, POSITIVE_CONTROL)
    print(f"  [H4] POSITIVE CONTROL  similarity")
    print(f"       OR = {r['or']:.3f}  [{r['or_lo']:.3f}, {r['or_hi']:.3f}]   "
          f"p = {r['p_nhst']:.2e}")
    if r["p_nhst"] < 0.05 and r["beta"] > 0:
        print("       PASS — similarity predicts citation. The data can detect things.\n")
    else:
        print("       *** FAIL *** similarity does NOT predict citation.")
        print("       STOP. Either the similarity metric is broken or `cited` is noise.")
        print("       A null on H1-H3 would be meaningless. Fix this first.\n")

    rows = []
    labels = {"log_subs": "[H1] log10 subscribers",
              "engagement_rate": "[H2] engagement rate",
              "log_views": "[H3] log10 views"}
    for v in PRIMARY:
        if v not in df:
            continue
        model, _ = fit_focal(df, v)
        r = tost(model, v)
        rows.append(r)
        print(f"  {labels[v]}  (per SD)")
        print(f"       OR = {r['or']:.3f}  [{r['or_lo']:.3f}, {r['or_hi']:.3f}]   "
              f"SE = {r['se']:.4f}")
        print(f"       p(nhst) = {r['p_nhst']:.3f}   p(TOST) = {r['p_tost']:.4f}")
        print(f"       --> {r['verdict']}\n")

    # H5 placebo
    if PLACEBO in df:
        pl = smf.logit(f"cited ~ {PLACEBO}", data=df).fit(disp=False)
        p = pl.pvalues[PLACEBO]
        print(f"  [H5] PLACEBO  publish day-of-week")
        print(f"       OR = {np.exp(pl.params[PLACEBO]):.3f}   p = {p:.3f}")
        print("       PASS — placebo is null, SEs look honest.\n" if p > 0.05 else
              "       *** WARN *** placebo shows an effect. SEs are too small;\n"
              "       you are probably under-clustered. Do not trust the CIs above.\n")

    return pd.DataFrame(rows)


def decile_plot(df: pd.DataFrame, path: str) -> None:
    """
    Spec §7.3 / §9 — the money graphic.

    A flat line here is more persuasive to a general reader than any coefficient.
    It also catches nonlinearity: subscribers might only matter at the extremes,
    which a linear term would miss entirely.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = df.copy()
    d["decile"] = pd.qcut(d["log_subs"], 10, labels=False, duplicates="drop")
    g = d.groupby("decile")["cited"].agg(["mean", "count", "sum"])
    # Wilson interval — correct for proportions near the boundaries
    lo, hi = sm.stats.proportion_confint(g["sum"], g["count"], alpha=ALPHA, method="wilson")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.errorbar(g.index + 1, g["mean"], yerr=[g["mean"] - lo, hi - g["mean"]],
                fmt="o-", capsize=4, lw=2, ms=7, color="#2563eb")
    ax.axhline(d["cited"].mean(), ls="--", c="#94a3b8", lw=1.5,
               label=f"overall rate ({d['cited'].mean():.1%})")
    ax.set_xlabel("Channel subscriber count — decile (1 = smallest)")
    ax.set_ylabel("Share cited inline")
    ax.set_title("Citation rate by channel size\n"
                 "(among videos the assistant already retrieved)", loc="left")
    ax.set_ylim(0, 1)
    ax.set_xticks(range(1, len(g) + 1))
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    print(f"  chart -> {path}\n")


# ---------------------------------------------------------------------------
# Synthetic data — lets you verify the pipeline has teeth before real data lands
# ---------------------------------------------------------------------------
def synthesize(n=5500, cited_target=3900, true_effect=0.0, seed=42) -> pd.DataFrame:
    """
    Simulates the stated data shape, INCLUDING the collider structure of §6.1:
    retrieval is caused by BOTH similarity and subscribers, and we only observe
    retrieved videos. This is what makes the naive (no-similarity-control) model
    produce a spurious NEGATIVE subscriber coefficient.

    true_effect = the real causal log-odds effect of log_subs on citation.
                  Set to 0.0 to confirm the test correctly finds a null;
                  set to 0.25 to confirm it can detect a real effect.
    """
    rng = np.random.default_rng(seed)
    pool = n * 6   # oversample, then filter on retrieval -> induces the collider

    sim = rng.normal(0, 1, pool)
    subs = rng.normal(0, 1, pool)   # independent of similarity in the POPULATION

    # Retrieval: caused by both. Conditioning on this scrambles them (§6.1).
    retrieved = rng.random(pool) < 1 / (1 + np.exp(-(-1.0 + 1.2 * sim + 1.0 * subs)))
    idx = np.flatnonzero(retrieved)[:n]
    if len(idx) < n:
        raise RuntimeError("retrieval pool too small; raise `pool`")
    sim, subs = sim[idx], subs[idx]

    # Citation: driven by similarity. Subscribers enter only via `true_effect`.
    intercept = np.log(cited_target / (n - cited_target))
    eta = intercept + 1.4 * sim + true_effect * subs
    cited = (rng.random(n) < 1 / (1 + np.exp(-eta))).astype(int)

    subs_raw = np.clip(10 ** (rng.normal(4.2, 1.1, n) + 0.35 * subs), 10, 3e8)
    views_raw = np.clip(subs_raw * rng.lognormal(-0.6, 1.3, n), 10, 5e9)

    return pd.DataFrame({
        "response_id": [f"r{i}" for i in range(n)],          # all singletons, as expected
        "video_id": [f"v{i}" for i in rng.integers(0, int(n * 0.93), n)],
        "cited": cited,
        "similarity": sim,
        "subscriber_count": subs_raw.round(),
        "view_count": views_raw.round(),
        "like_count": (views_raw * rng.beta(2, 60, n)).round(),
        "comment_count": (views_raw * rng.beta(1.5, 400, n)).round(),
        "duration_sec": rng.lognormal(6.2, 0.9, n).round(),
        "age_days": rng.integers(5, 2600, n),
        "published_at": pd.Timestamp("2026-07-11") - pd.to_timedelta(rng.integers(5, 2600, n), "D"),
        "n_sources_evaluated": rng.integers(3, 25, n),
        "assistant": rng.choice(["chatgpt", "gemini", "claude", "aio"], n),
        "fetch_ok": 1,
    })


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--true-effect", type=float, default=0.0,
                    help="synthetic only: the real log-odds effect of log_subs")
    ap.add_argument("--out", default="citation_by_channel_size.png")
    a = ap.parse_args()

    if a.synthetic:
        print(f"\n*** SYNTHETIC DATA (true log_subs effect = {a.true_effect}) ***\n")
        df = synthesize(true_effect=a.true_effect)
    elif a.data:
        df = pd.read_csv(a.data)
    else:
        ap.error("pass --data <csv> or --synthetic")

    df = derive(df)
    audit(df)

    # §6.1 — demonstrate the collider trap before avoiding it.
    naive = smf.logit("cited ~ log_subs", data=df).fit(disp=False)
    nb, np_ = naive.params["log_subs"], naive.pvalues["log_subs"]
    print("=" * 74)
    print("THE COLLIDER TRAP (spec §6.1) — what you'd get WITHOUT controlling")
    print("for similarity. This is the number not to publish.")
    print("=" * 74)
    print(f"  naive:  cited ~ log_subs   ->  OR = {np.exp(nb):.3f}   p = {np_:.4f}")
    if nb < 0 and np_ < 0.05:
        print("  Reads as 'BIG CHANNELS GET CITED LESS'. It is an artifact of")
        print("  conditioning on retrieval. Adding `similarity` dissolves it. -->\n")
    else:
        print("  (No strong spurious signal in this run — but still control for it.)\n")

    collinearity_check(df)
    results = report(df)
    decile_plot(df, a.out)

    if len(results):
        results.to_csv("results_summary.csv", index=False)
        print("  summary -> results_summary.csv")

    # Headline
    r = results[results["var"] == "log_subs"]
    if len(r):
        r = r.iloc[0]
        print("\n" + "=" * 74)
        print("HEADLINE")
        print("=" * 74)
        if r["verdict"].startswith("NULL"):
            pct = max(abs(r["or_lo"] - 1), abs(r["or_hi"] - 1)) * 100
            print("  Among videos an assistant has already retrieved, channel subscriber")
            print("  count does not predict inline citation. We could have detected a")
            print(f"  {SESOI_OR-1:.0%} shift in citation odds per SD of log-subscribers;")
            print(f"  the observed effect is bounded within {pct:.1f}%.")
            print("\n  Reminder (spec §1): this is the CITATION step only. Audience may")
            print("  still buy RETRIEVAL. Do not overclaim.")
        elif r["verdict"].startswith("REAL"):
            print(f"  Subscriber count DOES predict citation: OR = {r['or']:.3f} per SD")
            print(f"  [{r['or_lo']:.3f}, {r['or_hi']:.3f}]. The working thesis is wrong.")
            print("  Investigate what subscribers proxy for that the model CAN see.")
        else:
            print(f"  {r['verdict']}.")
            print("  Do not write the blog post from this. See spec §6.3.")
        print()


if __name__ == "__main__":
    main()
