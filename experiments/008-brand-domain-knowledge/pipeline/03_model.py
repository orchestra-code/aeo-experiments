"""Stage 03 — pre-registered tests (spec §4/§5) -> results/model_*.{csv,txt}.

Sequence (house rule: positive control FIRST — exit 1 if it fails):

  H_pos  tier-A call-level accuracy >= 0.90 when a site: query is emitted
  H_pla  alphabetical rank of the brand name does not predict accuracy
  H1     site:-emission rates by tier x template, Wilson CIs, pilot alongside
  H2     NOT IDENTIFIABLE as pre-registered — the observed agreement and the
         spec's plug-in baseline are the same quantity, so their difference
         cannot separate the mechanisms. Reported with the estimator note,
         plus an exploratory brand-specificity permutation and a POST-HOC
         sensitivity against the frozen candidate set (1/K under uniform
         guessing), which is identifying where K >= 2.
  H3     error content: stale share tier C vs B, guess share tier B vs C
  H4     day-over-day transitions: P(correct t+1 | wrong t) vs
         P(correct t+1 | correct t); the agreement of the WRONG DOMAIN within
         day vs across days (the identifying companion to H2); and the
         within-day replicate reference
  H5     accuracy by tier, ordering A >= B and A >= C
  robustness  (a) any-wrong-in-call (b) drop wave-1 replicates
              (c) stale counted as correct (d) observation vs call level
              (e) first site: query of any kind (competitor sites included)

The primary outcome is the first BRAND-ATTRIBUTABLE site: query — see
scoring.py and the Deviations section of results/audit.txt.

Every pooled rate clusters on brand for its CI (Audit C): rows go through
``common.brand_pairs_frame`` into ``aeo_research.overlap.cluster_boot``,
which resamples brands and weights each row by its brand's draw count.

Usage:
  uv run python experiments/008-brand-domain-knowledge/pipeline/03_model.py
  uv run python .../03_model.py --synthetic lookup --expect lookup
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from itertools import combinations

import numpy as np
import pandas as pd
from common import (
    ALPHA,
    PANEL,
    ERROR_KINDS,
    H_POS_MIN,
    MAX_WAVE,
    N_BOOT,
    N_PERM,
    PILOT_EMISSION,
    SEED,
    STOCHASTIC_DELTA,
    SYNTHETIC_WORLDS,
    SYSTEMIC_DELTA,
    TEMPLATE_LABELS,
    TEMPLATES,
    TIERS,
    apply_resolution,
    brand_bootstrap,
    brand_pairs_frame,
    fmt_rate,
    load_observations,
    load_responses,
    results_dir,
    rule_of_three,
    slug,
)
from annotations import OWN_PROPERTY, UNREVIEWED
from scipy import stats as sps
from scoring import frozen_candidate_set

from aeo_research.overlap import cluster_boot, permutation_pvalue
from aeo_research.stats import wilson_interval

#: An own-domain error: a site: consultation that is wrong ABOUT THE BRAND
#: ASKED. Third-party consultations (the comparison template's competitor
#: and review sites) are not claims about the brand's domain.
OWN_ERROR_KINDS = (
    "stale_old_domain",
    "morphological_guess",
    "name_bearing_other",
    "nonexistent",
)

NOT_IDENTIFIABLE = "NOT IDENTIFIABLE as pre-registered — see note"
MIN_AGREEMENT_PAIRS = 10  # floor for asserting on a dry-run agreement rate
SYSTEMIC = "SYSTEMIC"
STOCHASTIC = "STOCHASTIC"
MIXTURE = "MIXTURE/INCONCLUSIVE"
UNDERPOWERED = "INCONCLUSIVE — too few brands"


def emitting(calls: pd.DataFrame) -> pd.DataFrame:
    """The analysis set: calls that made a BRAND-ATTRIBUTABLE site: search.

    A call whose only site: searches pointed at competitor or reference sites
    never committed to a domain for the brand it was asked about (spec §5:
    "a site: fan-out naming the brand"), so it is non-emitting for this
    outcome — counted in H1's funnel, excluded from every rate.
    """
    return calls[calls["emitted_brand_site_query"] == 1]


def own_errors(obs: pd.DataFrame) -> pd.DataFrame:
    return obs[(obs["label"] != "correct") & obs["error_kind"].isin(OWN_ERROR_KINDS)]


def rate_row(df: pd.DataFrame, value_col: str, label: str) -> dict:
    """Wilson CI on the pooled rate + the brand-clustered CI beside it."""
    k = int(df[value_col].sum())
    n = len(df)
    if n == 0:
        return {"test": label, "k": 0, "n": 0, "rate": float("nan")}
    lo, hi = wilson_interval(k, n, alpha=ALPHA)
    row = {"test": label, "k": k, "n": n, "rate": k / n,
           "wilson_lo": float(lo), "wilson_hi": float(hi),
           "rule_of_three": rule_of_three(n) if k == 0 else float("nan")}
    if df["slug"].nunique() > 1:
        res = cluster_boot(
            brand_pairs_frame(df.assign(_c="all"), value_col, "_c"),
            contrast=("all", None), alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
        )
        row |= {"cluster_lo": res.lo, "cluster_hi": res.hi, "n_brands": res.n_clusters}
    return row


def contrast_row(df: pd.DataFrame, value_col: str, cond_col: str,
                 a: str, b: str, label: str) -> dict | None:
    """Brand-clustered difference of two group means (a - b)."""
    sub = df[df[cond_col].isin((a, b))]
    if sub.empty or sub[cond_col].nunique() < 2:
        return None
    res = cluster_boot(
        brand_pairs_frame(sub, value_col, cond_col),
        contrast=(a, b), alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
    )
    return {"test": label, "contrast": f"{a} - {b}", "estimate": res.estimate,
            "lo": res.lo, "hi": res.hi, "n": res.n_pairs, "n_brands": res.n_clusters}


# --------------------------------------------------------- H_pos / H_pla


def h_pos(calls: pd.DataFrame, obs: pd.DataFrame, rows: list, lines: list) -> bool:
    tier_a = emitting(calls[calls["tier"] == "A"])
    row = rate_row(tier_a, "first_site_correct", "H_pos")
    passed = bool(row["n"]) and row["rate"] >= H_POS_MIN
    rows.append(row | {"passed": passed})
    lines.append(
        f"H_pos (gate): tier-A call-level accuracy = "
        f"{fmt_rate(row['k'], row['n'], row.get('wilson_lo', float('nan')), row.get('wilson_hi', float('nan')))}"
        f" -> {'PASS' if passed else f'FAIL — below {H_POS_MIN}, the instrument is broken'}"
    )
    obs_a = obs[obs["tier"] == "A"]
    row_o = rate_row(obs_a.assign(ok=(obs_a["label"] == "correct").astype(int)), "ok",
                     "H_pos_observation_level")
    own_a = obs_a[obs_a["error_kind"] != "third_party"]
    row_own = rate_row(own_a.assign(ok=(own_a["label"] == "correct").astype(int)), "ok",
                       "H_pos_observation_level_own_domain")
    rows += [row_o, row_own]
    lines.append(
        f"        observation level, every site: query = "
        f"{fmt_rate(row_o['k'], row_o['n'], row_o.get('wilson_lo', float('nan')), row_o.get('wilson_hi', float('nan')))}"
        " — most of the shortfall is the comparison template consulting"
    )
    lines.append(
        "        competitors on purpose; excluding third-party consultations = "
        f"{fmt_rate(row_own['k'], row_own['n'], row_own.get('wilson_lo', float('nan')), row_own.get('wilson_hi', float('nan')))}"
    )
    return passed


def h_pla(calls: pd.DataFrame, rows: list, lines: list) -> None:
    """Placebo: within tier, alphabetical rank must not predict accuracy."""
    per_brand = (
        emitting(calls).groupby(["tier", "slug"])["first_site_correct"].mean().reset_index()
    )
    per_brand["rank"] = per_brand.groupby("tier")["slug"].rank(method="average")
    per_brand["rank_norm"] = per_brand.groupby("tier")["rank"].transform(
        lambda r: (r - r.mean()) / r.std(ddof=0) if r.std(ddof=0) else 0.0
    )
    per_brand["acc_c"] = per_brand.groupby("tier")["first_site_correct"].transform(
        lambda a: a - a.mean()
    )
    table = per_brand.set_index("slug")

    def stat(keys: list[str]) -> float:
        sub = table.loc[keys]
        if sub["rank_norm"].std(ddof=0) == 0:
            return float("nan")
        return float(np.polyfit(sub["rank_norm"], sub["acc_c"], 1)[0])

    est, lo, hi = brand_bootstrap(list(table.index), stat, n_boot=N_BOOT, seed=SEED)
    spearman = float(
        sps.spearmanr(per_brand["rank_norm"], per_brand["acc_c"]).statistic
    )
    ok = lo <= 0 <= hi
    rows.append({"test": "H_pla", "estimate": est, "lo": lo, "hi": hi,
                 "spearman": spearman, "passed": ok})
    lines.append(
        f"H_pla (placebo): within-tier slope of accuracy on alphabetical rank = "
        f"{est:+.4f} [{lo:+.4f}, {hi:+.4f}], Spearman {spearman:+.3f} -> "
        f"{'null as required' if ok else '** WARNING: placebo is NOT null — clustering/CIs suspect **'}"
    )


# ------------------------------------------------------------------- H1


def h1_emission(calls: pd.DataFrame, rows: list, lines: list) -> None:
    lines.append("\n-- H1: site:-emission rate (descriptive, no gate) --")
    for template in TEMPLATES:
        pilot_k, pilot_n = PILOT_EMISSION[template]
        lines.append(f"  {TEMPLATE_LABELS[template]} (pilot §8c: {pilot_k}/{pilot_n}):")
        for tier in TIERS:
            sub = calls[(calls["tier"] == tier) & (calls["template"] == template)]
            row = rate_row(sub, "emitted_site_query", f"H1_any_site_{tier}_{template}")
            brand_row = rate_row(sub, "emitted_brand_site_query",
                                 f"H1_brand_site_{tier}_{template}")
            rows += [row, brand_row]
            lines.append(
                f"    tier {tier}: any site: "
                f"{fmt_rate(row['k'], row['n'], row.get('wilson_lo', np.nan), row.get('wilson_hi', np.nan))}"
                f" | brand-attributable "
                f"{fmt_rate(brand_row['k'], brand_row['n'], brand_row.get('wilson_lo', np.nan), brand_row.get('wilson_hi', np.nan))}"
            )
    for col, label in (("emitted_site_query", "any site: query"),
                       ("emitted_brand_site_query", "brand-attributable site: query")):
        overall = rate_row(calls, col, f"H1_overall_{col}")
        rows.append(overall)
        lines.append(
            f"  all calls, {label}: "
            f"{fmt_rate(overall['k'], overall['n'], overall.get('wilson_lo', np.nan), overall.get('wilson_hi', np.nan))}"
        )
    funnel = (
        calls.assign(searched=(calls["n_search_actions"] > 0).astype(int))
        .groupby(["tier", "template"])
        .agg(calls=("item_id", "size"), with_search=("searched", "sum"),
             with_site=("emitted_site_query", "sum"),
             with_brand_site=("emitted_brand_site_query", "sum"))
    )
    lines.append(
        "  funnel (calls -> >=1 search action -> >=1 site: query -> >=1 "
        "BRAND-ATTRIBUTABLE site: query):"
    )
    lines.append(funnel.to_string())
    dropped = int((calls["emitted_site_query"] - calls["emitted_brand_site_query"]).sum())
    lines.append(
        f"  {dropped} call(s) ran site: searches that named ONLY third-party "
        "sites — the comparison template opens on a competitor's or a review "
        "site by design (adyen.com while answering about Stripe, vrbo.com "
        "about Airbnb). Those calls never committed to a domain for the brand "
        "they were asked about, so they are non-emitting for this outcome "
        "rather than wrong; every rate below is conditioned on the last stage "
        "of this funnel."
    )


# ------------------------------------------------------------------- H2


def _agreement(brands: np.ndarray, domains: np.ndarray) -> tuple[float, float]:
    """(observed pairwise same-domain agreement, plug-in Sigma p^2 baseline).

    Both are pair-weighted across brands. ``observed`` is the U-statistic form
    Sigma_d C(n_d,2) / C(n,2); ``plug`` is Sigma (n_d/n)^2 — the spec's stated
    baseline, computed from the same observations.
    """
    same = total = plug = 0.0
    for brand in np.unique(brands):
        counts = Counter(domains[brands == brand])
        n = sum(counts.values())
        if n < 2:
            continue
        pairs = n * (n - 1) / 2
        same += sum(c * (c - 1) / 2 for c in counts.values())
        total += pairs
        plug += pairs * sum((c / n) ** 2 for c in counts.values())
    if total == 0:
        return float("nan"), float("nan")
    return same / total, plug / total


def _entering(errors: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    counts = errors.groupby("slug").size()
    keep = set(counts[counts >= 2].index)
    return errors[errors["slug"].isin(keep)], len(keep)


H2_NOTE = """
  Why: the quantity H2 asks for is not identified by this design.
  (1) Estimator. Under ANY model in which a call's wrong domain is drawn
      independently from that brand's own distribution p — which is exactly
      what "per-run guessing" means — the observed pairwise agreement is an
      UNBIASED estimator of Sigma p^2. The plug-in Sigma p_hat^2 computed from
      the same observations is its biased twin and is always >= it. So
      observed - baseline has expectation 0 under the guessing hypothesis and
      is bounded above by 0 in the plug-in form: it cannot separate the two
      mechanisms, and cannot reach the systemic band on any data set.
  (2) Substitution. Shuffling wrong-domain labels ACROSS brands (reported
      below as exploratory) tests whether wrong domains are brand-specific.
      They are, near-tautologically: Meta's old domain is facebook.com and
      GoTo's is logmein.com, and a per-run guesser generating from the brand's
      own name would be just as brand-specific. That test answers a different
      question and is not evidence for either mechanism.
  What carries the mechanism claim instead, both pre-registered:
      H3 — error CONTENT by tier (stale vs morphological), and
      H4 — temporal structure (day-over-day transitions, and the within-day
           vs across-day agreement of the wrong domain itself).
  A post-hoc sensitivity with an EXTERNAL baseline (uniform over the frozen
  candidate set) is reported after them, clearly labelled post-hoc.
"""


def h2_not_identifiable(errors: pd.DataFrame, level: str, rows: list, lines: list) -> None:
    """H2 as pre-registered: report the pieces, refuse the verdict."""
    entering, n_brands = _entering(errors)
    lines.append(f"\n-- H2 ({level}): repeat structure of wrong domains --")
    lines.append(
        f"  {len(errors)} own-domain error observations over "
        f"{errors['slug'].nunique()} brands; {n_brands} brands with >= 2 enter "
        "(Audit C effective sample)"
    )
    if n_brands < 3:
        lines.append(
            f"  ** {UNDERPOWERED}: {n_brands} brand(s) with >= 2 wrong "
            "observations. Nothing is estimable here — an upper-bound "
            "situation, not evidence of absence. **"
        )
        rows.append({"test": f"H2_{level}", "n_brands": n_brands, "verdict": UNDERPOWERED})
        return
    observed, plug = _agreement(entering["slug"].to_numpy(),
                                entering["registered_domain"].to_numpy())
    rows.append({"test": f"H2_{level}", "n_brands": n_brands, "n": len(entering),
                 "observed_agreement": observed, "plugin_sigma_p2": plug,
                 "verdict": NOT_IDENTIFIABLE})
    lines.append(f"  VERDICT: {NOT_IDENTIFIABLE}")
    lines.append(
        f"  observed same-wrong-domain agreement = {observed:.3f}; the spec's "
        f"plug-in Sigma p_hat^2 baseline = {plug:.3f} (reported for "
        "transparency only — the difference is not interpretable)"
    )
    lines.append(H2_NOTE.rstrip())


def h2_exploratory_brand_specificity(errors: pd.DataFrame, level: str,
                                     rows: list, lines: list) -> None:
    """EXPLORATORY: are wrong domains brand-specific at all? (not H2)"""
    entering, n_brands = _entering(errors)
    lines.append(
        f"\n-- EXPLORATORY ({level}) — brand-specificity of wrong domains "
        "(NOT the pre-registered H2) --"
    )
    if n_brands < 3:
        lines.append(f"  {UNDERPOWERED} ({n_brands} brands)")
        return
    brands = entering["slug"].to_numpy()
    domains = entering["registered_domain"].to_numpy()
    observed, _ = _agreement(brands, domains)

    def perm_stat(rng: np.random.Generator) -> float:
        return _agreement(brands, rng.permutation(domains))[0]

    p_perm = permutation_pvalue(observed, perm_stat, n_perm=N_PERM, seed=SEED)
    rng = np.random.default_rng(SEED)
    baseline = float(np.mean([perm_stat(rng) for _ in range(200)]))
    rows.append({"test": f"H2_exploratory_brand_specificity_{level}",
                 "n_brands": n_brands, "n": len(entering), "observed_agreement": observed,
                 "permutation_baseline": baseline, "estimate": observed - baseline,
                 "p_perm": p_perm})
    lines.append(
        f"  within-brand agreement {observed:.3f} vs {baseline:.3f} when wrong "
        f"domains are shuffled across brands (difference {observed - baseline:+.3f}, "
        f"permutation p = {p_perm:.4f}). Reads as: a brand's wrong domains are "
        "its own. Both mechanisms predict this, so it decides nothing."
    )


def h2_posthoc_frozen_baseline(errors: pd.DataFrame, rows: list, lines: list
                               ) -> tuple[str, float]:
    """POST-HOC sensitivity: agreement vs a uniform draw from the frozen set.

    External baseline: if the model generated the wrong domain fresh each call
    from the brand's frozen candidate set (old_domains + expected_guess, minus
    the truth — K domains), two wrong observations would agree with
    probability 1/K. A stored association agrees with probability 1. This is
    the only pre-registered notion of the candidate space that does not come
    from the observations being tested, so it is identifying — but it is
    POST-HOC and K is a property of the instrument, not of the model.
    """
    lines.append(
        "\n-- POST-HOC SENSITIVITY (not pre-registered): agreement vs a uniform "
        "draw from the frozen candidate set --"
    )
    candidates = {slug(b.canonical): frozen_candidate_set(b) for b in PANEL}
    per_brand = []
    for brand_slug, sub in errors.groupby("slug"):
        n = len(sub)
        if n < 2:
            continue
        counts = Counter(sub["registered_domain"])
        pairs = n * (n - 1) / 2
        k = len(candidates[brand_slug])
        per_brand.append({
            "brand": sub["brand"].iat[0], "tier": sub["tier"].iat[0], "slug": brand_slug,
            "K_frozen": k, "n_wrong": n, "pairs": pairs,
            "agreement": sum(c * (c - 1) / 2 for c in counts.values()) / pairs,
            "baseline": 1.0 / k if k else float("nan"),
        })
    table = pd.DataFrame(per_brand)
    if table.empty:
        lines.append("  no brand has >= 2 own-domain errors — nothing to estimate")
        return UNDERPOWERED, float("nan")
    lines.append(
        table[["brand", "tier", "K_frozen", "n_wrong", "agreement", "baseline"]]
        .round(3).to_string(index=False)
    )
    blind = table[table["K_frozen"] <= 1]
    if not blind.empty:
        lines.append(
            f"  {len(blind)} brand(s) excluded as NOT SEPARABLE BY DESIGN "
            f"({', '.join(blind['brand'])}): the frozen panel gives them "
            "K <= 1 candidate wrong domains, so a repeated stored error and a "
            "repeated guess are the same observation. This is a limitation of "
            "the instrument, not a finding about the model."
        )
    identifying = table[table["K_frozen"] >= 2].set_index("slug")
    if len(identifying) < 3:
        lines.append(
            f"  ** {UNDERPOWERED}: only {len(identifying)} brand(s) where the "
            "test is identifying (K >= 2 and >= 2 wrong observations). **"
        )
        rows.append({"test": "H2_posthoc_frozen", "n_brands": len(identifying),
                     "verdict": UNDERPOWERED})
        return UNDERPOWERED, float("nan")

    def pooled(keys: list[str]) -> float:
        sub = identifying.loc[keys]
        weight = sub["pairs"].to_numpy()
        return float(
            np.average(sub["agreement"], weights=weight)
            - np.average(sub["baseline"], weights=weight)
        )

    est, lo, hi = brand_bootstrap(list(identifying.index), pooled,
                                  n_boot=N_BOOT, seed=SEED)
    weight = identifying["pairs"].to_numpy()
    observed = float(np.average(identifying["agreement"], weights=weight))
    baseline = float(np.average(identifying["baseline"], weights=weight))
    if est >= SYSTEMIC_DELTA:
        verdict = SYSTEMIC
    elif abs(est) <= STOCHASTIC_DELTA and lo > -STOCHASTIC_DELTA and hi < STOCHASTIC_DELTA:
        verdict = STOCHASTIC
    else:
        verdict = MIXTURE
    rows.append({"test": "H2_posthoc_frozen", "n_brands": len(identifying),
                 "n": int(identifying["n_wrong"].sum()), "observed_agreement": observed,
                 "frozen_baseline": baseline, "estimate": est, "lo": lo, "hi": hi,
                 "verdict": verdict})
    lines.append(
        f"  {len(identifying)} identifying brands: observed agreement "
        f"{observed:.3f} vs frozen-set baseline {baseline:.3f} -> "
        f"{est:+.3f} [{lo:+.3f}, {hi:+.3f}] (brand cluster bootstrap) "
        f"against the frozen bands (systemic >= {SYSTEMIC_DELTA}, stochastic "
        f"within +/-{STOCHASTIC_DELTA}) -> {verdict}"
    )
    return verdict, est


# ------------------------------------------------------------------- H3


def kind_detail(frame: pd.DataFrame) -> pd.Series:
    """Error kind, with name_bearing_other split by Audit D's signed attribution."""
    detail = frame["error_kind"].astype(str)
    attribution = frame.get("attribution", pd.Series("", index=frame.index)).fillna("")
    return detail.where(
        detail != "name_bearing_other",
        "name_bearing:" + attribution.replace("", UNREVIEWED),
    )


def h3_error_content(errors: pd.DataFrame, obs: pd.DataFrame, rows: list, lines: list) -> None:
    lines.append("\n-- H3: error content by tier --")
    counts = (
        errors.assign(one=1, kind=kind_detail(errors))
        .pivot_table(index="tier", columns="kind", values="one",
                     aggfunc="sum", fill_value=0)
        .reindex(list(TIERS), fill_value=0)
    )
    lines.append(
        "  own-domain error kinds by tier (name_bearing split by the signed "
        "Audit D attribution — own_property is the brand's own orbit, "
        "other_company is objectively wrong, unreviewed reopens Audit D):"
    )
    lines.append(counts.to_string() if not counts.empty else "  (no own-domain errors)")

    for kind, (a, b) in (("stale_old_domain", ("C", "B")), ("morphological_guess", ("B", "C"))):
        frame = errors.assign(value=(errors["error_kind"] == kind).astype(int))
        n_a = int((frame["tier"] == a).sum())
        n_b = int((frame["tier"] == b).sum())
        if not n_a or not n_b:
            empty = a if not n_a else b
            all_obs = obs[obs["tier"] == empty]
            lines.append(
                f"  {kind} share, tier {a} vs {b}: NOT ESTIMABLE — tier {empty} has "
                f"zero own-domain errors (rule-of-three upper bound on its error "
                f"rate: {rule_of_three(len(all_obs)):.4f} over {len(all_obs)} "
                "site: observations)"
            )
            rows.append({"test": f"H3_{kind}", "contrast": f"{a} - {b}",
                         "verdict": "not estimable", "n_a": n_a, "n_b": n_b})
            continue
        row = contrast_row(frame, "value", "tier", a, b, f"H3_{kind}")
        rows.append(row)
        excl = row["lo"] > 0 or row["hi"] < 0
        lines.append(
            f"  {kind} share, tier {a} ({n_a} errors) vs {b} ({n_b}): "
            f"{row['estimate']:+.3f} [{row['lo']:+.3f}, {row['hi']:+.3f}] "
            f"-> {'directional, CI excludes 0' if excl else 'CI includes 0'}"
        )


# ------------------------------------------------------------------- H4


def transitions(calls: pd.DataFrame, state_col: str) -> pd.DataFrame:
    """Day-over-day (wave t -> t+1) state pairs on the core r0 series."""
    core = calls[(calls["intent"] == "core") & (calls["replicate"] == 0)
                 & (calls["emitted_site_query"] == 1)]
    out = []
    for (brand_slug, template), sub in core.groupby(["slug", "template"]):
        by_wave = sub.set_index("wave")[state_col].to_dict()
        tier = sub["tier"].iat[0]
        for wave in range(1, MAX_WAVE):
            if wave in by_wave and wave + 1 in by_wave:
                out.append({
                    "slug": brand_slug, "tier": tier, "template": template, "wave": wave,
                    "prev": "correct" if by_wave[wave] else "wrong",
                    "next_correct": int(by_wave[wave + 1]),
                })
    return pd.DataFrame(out)


def h4_transitions(calls: pd.DataFrame, rows: list, lines: list,
                   state_col: str = "first_site_correct", tag: str = "H4") -> float:
    lines.append(f"\n-- {tag}: day-over-day self-correction ({state_col}) --")
    trans = transitions(calls, state_col)
    if trans.empty or trans["prev"].nunique() < 2:
        lines.append("  no wrong->next transitions on the core series — NOT ESTIMABLE")
        rows.append({"test": tag, "verdict": "not estimable",
                     "n": len(trans)})
        return float("nan")

    erred = set(trans.loc[trans["prev"] == "wrong", "slug"])
    matched_gap = float("nan")
    scopes = (("all brands", trans),
              ("brands that erred at least once (composition-matched)",
               trans[trans["slug"].isin(erred)]))
    for scope, frame in scopes:
        if frame.empty or frame["prev"].nunique() < 2:
            continue
        after_wrong = rate_row(frame[frame["prev"] == "wrong"], "next_correct",
                               f"{tag}_correct_given_wrong [{scope}]")
        after_ok = rate_row(frame[frame["prev"] == "correct"], "next_correct",
                            f"{tag}_correct_given_correct [{scope}]")
        gap = contrast_row(frame, "next_correct", "prev", "correct", "wrong",
                           f"{tag}_gap [{scope}]")
        rows += [after_wrong, after_ok, gap]
        lines.append(f"  {scope}:")
        lines.append(
            f"    P(correct at t+1 | wrong at t)   = "
            f"{fmt_rate(after_wrong['k'], after_wrong['n'], after_wrong.get('wilson_lo', np.nan), after_wrong.get('wilson_hi', np.nan))}"
        )
        lines.append(
            f"    P(correct at t+1 | correct at t) = "
            f"{fmt_rate(after_ok['k'], after_ok['n'], after_ok.get('wilson_lo', np.nan), after_ok.get('wilson_hi', np.nan))}"
        )
        lines.append(
            f"    gap = {gap['estimate']:+.3f} [{gap['lo']:+.3f}, {gap['hi']:+.3f}] "
            f"(brand cluster bootstrap, {gap['n_brands']} brands)"
        )
        if "composition-matched" in scope:
            matched_gap = float(gap["estimate"])
    return matched_gap


def _domain_pairs(wrong: pd.DataFrame, domain_col: str, k_of: dict) -> dict[str, pd.DataFrame]:
    """Within-day (wave-1 replicates) and across-day (consecutive core waves)
    pairs of WRONG calls for the same brand x template, with their K.

    ``wrong`` must already be restricted to calls that named a wrong domain.
    """
    pairs: dict[str, list] = {"within_day": [], "across_day": []}
    for (brand_slug, template), sub in wrong.groupby(["slug", "template"]):
        k = k_of[brand_slug]
        w1 = sub[sub["wave"] == 1]
        for a, b in combinations(w1.to_dict("records"), 2):
            pairs["within_day"].append({"slug": brand_slug, "K": k,
                                        "same": int(a[domain_col] == b[domain_col])})
        core = sub[(sub["intent"] == "core") & (sub["replicate"] == 0)]
        by_wave = dict(zip(core["wave"], core[domain_col]))
        for wave in sorted(by_wave):
            if wave + 1 in by_wave:
                pairs["across_day"].append({"slug": brand_slug, "K": k,
                                            "same": int(by_wave[wave] == by_wave[wave + 1])})
    return {name: pd.DataFrame(rec) for name, rec in pairs.items()}


def h4_domain_agreement(calls: pd.DataFrame, rows: list, lines: list) -> dict:
    """H4 companion: when the model is wrong twice, is it wrong the SAME way?

    Identifying where the spec's H2 is not: a stored association predicts both
    the within-day and the across-day agreement of the WRONG DOMAIN at ~1 and
    equal to each other; a per-run guess over the brand's K frozen candidates
    predicts both at ~1/K. Within-day pairs are the wave-1 r0/r1/r2
    replicates, across-day pairs consecutive core waves.

    Two wrong-call definitions, because the strict one is thin: the call's
    first COMMITMENT was wrong, and the wider "the call named a wrong domain
    for this brand ANYWHERE" (first_error_domain). And two scopes, because for
    a K = 1 brand both mechanisms predict agreement 1 and a pooled number just
    counts how many such brands erred: all brands, and K >= 2 only.
    """
    lines.append(
        "\n-- H4 companion: agreement of the WRONG DOMAIN, within day vs across days --"
    )
    k_of = {slug(b.canonical): len(frozen_candidate_set(b)) for b in PANEL}
    out: dict = {}
    attributable = calls[calls["emitted_brand_site_query"] == 1].copy()
    attributable["first_error_domain"] = attributable["first_error_domain"].fillna("")
    sources = (
        ("commitment", "first_site_domain",
         "calls whose FIRST commitment was wrong",
         attributable[attributable["first_site_own_error"] == 1]),
        ("any", "first_error_domain",
         "calls naming a wrong domain for this brand anywhere in the call",
         attributable[attributable["first_error_domain"] != ""]),
    )
    for prefix, column, label, wrong in sources:
        lines.append(f"  {label} ({len(wrong)} calls):")
        frames = _domain_pairs(wrong, column, k_of)
        for name, frame in frames.items():
            for scope, sub in (("all brands", frame),
                               ("K >= 2", frame[frame["K"] >= 2] if not frame.empty else frame)):
                key = f"{prefix}_{name}_{'id' if scope == 'K >= 2' else 'all'}"
                if sub.empty:
                    lines.append(f"    {name.replace('_', '-')}, {scope}: "
                                 "0 qualifying pairs — NOT ESTIMABLE")
                    rows.append({"test": f"H4_domain_agreement_{key}", "n": 0,
                                 "verdict": "not estimable"})
                    out[key], out[f"{key}_baseline"], out[f"{key}_n"] = (
                        float("nan"), float("nan"), 0)
                    continue
                row = rate_row(sub, "same", f"H4_domain_agreement_{key}")
                baseline = float((1.0 / sub["K"].replace(0, np.nan)).mean())
                row["guess_baseline_1_over_k"] = baseline
                rows.append(row)
                cluster = (f", brand-clustered [{row['cluster_lo']:.3f}, {row['cluster_hi']:.3f}]"
                           if "cluster_lo" in row else "")
                lines.append(
                    f"    {name.replace('_', '-')}, {scope}: "
                    f"{fmt_rate(row['k'], row['n'], row.get('wilson_lo', np.nan), row.get('wilson_hi', np.nan))}"
                    f"{cluster} over {sub['slug'].nunique()} brand(s); a uniform "
                    f"guess over the frozen sets would give {baseline:.3f}"
                )
                out[key], out[f"{key}_baseline"], out[f"{key}_n"] = (
                    row["rate"], baseline, row["n"])
    lines.append(
        "  A stored association predicts both agreements near 1 and equal to "
        "each other; a per-run guess predicts both near the 1/K figure beside "
        "them. For K = 1 brands the two predictions coincide, which is why the "
        "K >= 2 rows are the ones that carry the contrast."
    )
    return out


def within_day_reference(calls: pd.DataFrame, rows: list, lines: list) -> None:
    """Wave-1 r0/r1/r2 concordance — the within-day stochasticity reference."""
    wave1 = calls[(calls["wave"] == 1) & (calls["emitted_site_query"] == 1)]
    pairs = []
    for (brand_slug, template), sub in wave1.groupby(["slug", "template"]):
        recs = sub[["replicate", "first_site_correct", "first_site_domain"]].to_dict("records")
        for a, b in combinations(recs, 2):
            pairs.append({
                "slug": brand_slug, "template": template,
                "same_label": int(a["first_site_correct"] == b["first_site_correct"]),
                "same_domain": int(a["first_site_domain"] == b["first_site_domain"]),
            })
    frame = pd.DataFrame(pairs)
    if frame.empty:
        lines.append("  (no wave-1 replicate pairs)")
        return
    for col, name in (("same_label", "same correct/wrong label"),
                      ("same_domain", "same first site: domain")):
        row = rate_row(frame, col, f"H4_within_day_{col}")
        rows.append(row)
        lines.append(
            f"  within-day (wave 1, {len(frame)} replicate pairs), {name}: "
            f"{fmt_rate(row['k'], row['n'], row.get('wilson_lo', np.nan), row.get('wilson_hi', np.nan))}"
        )


# ------------------------------------------------------------------- H5


def h5_tier_accuracy(calls: pd.DataFrame, rows: list, lines: list) -> None:
    lines.append("\n-- H5: call-level accuracy by tier (descriptive, no gate) --")
    emit = emitting(calls)
    for tier in TIERS:
        sub = emit[emit["tier"] == tier]
        row = rate_row(sub, "first_site_correct", f"H5_{tier}")
        rows.append(row)
        cluster = (
            f" (brand-clustered [{row['cluster_lo']:.3f}, {row['cluster_hi']:.3f}])"
            if "cluster_lo" in row else ""
        )
        lines.append(
            f"  tier {tier}: {fmt_rate(row['k'], row['n'], row.get('wilson_lo', np.nan), row.get('wilson_hi', np.nan))}{cluster}"
        )
    for other in ("B", "C"):
        row = contrast_row(emit, "first_site_correct", "tier", "A", other, f"H5_A_vs_{other}")
        if row is None:
            continue
        rows.append(row)
        lines.append(
            f"  A - {other} = {row['estimate']:+.3f} [{row['lo']:+.3f}, {row['hi']:+.3f}] "
            f"-> ordering A >= {other} "
            f"{'holds (CI above 0)' if row['lo'] > 0 else 'not separated by the CI'}"
        )


def zero_cell_table(calls: pd.DataFrame, obs: pd.DataFrame, lines: list) -> None:
    lines.append("\n-- error kinds by tier x template, with rule-of-three bounds --")
    lines.append("  (denominator = all site: observations in the cell)")
    kinds = [k for k in ERROR_KINDS if k != "third_party"] + ["third_party"]
    table = (
        obs.assign(one=1)
        .pivot_table(index=["tier", "template"], columns="error_kind", values="one",
                     aggfunc="sum", fill_value=0)
        .reindex(columns=kinds, fill_value=0)
    )
    sizes = obs.groupby(["tier", "template"]).size()
    lines.append(table.to_string())
    zeros = [
        f"    tier {tier}/{template} {kind}: 0/{sizes[(tier, template)]} "
        f"-> upper bound {rule_of_three(sizes[(tier, template)]):.4f}"
        for (tier, template), row in table.iterrows()
        for kind, value in row.items()
        if value == 0
    ]
    lines.append("  zero cells (3/n upper bound on the rate):")
    lines += zeros or ["    (none)"]


# ----------------------------------------------------------- robustness


def robustness(calls: pd.DataFrame, obs: pd.DataFrame, errors: pd.DataFrame,
               rows: list, lines: list) -> None:
    lines.append("\n-- robustness --")
    emit = emitting(calls)

    # (a) any non-correct, non-third-party site: query anywhere in the call.
    alt = emit.assign(ok=1 - emit["any_wrong_incl_stale"])
    for tier in TIERS:
        row = rate_row(alt[alt["tier"] == tier], "ok", f"R_a_any_wrong_{tier}")
        rows.append(row)
    lines.append(
        "  (a) accuracy using 'no own-domain error anywhere in the call': "
        + ", ".join(
            f"{t} {alt[alt['tier'] == t]['ok'].mean():.3f}" for t in TIERS
        )
    )

    # (b) drop the wave-1 replicates.
    core_only = emit[emit["replicate"] == 0]
    lines.append(
        "  (b) core series only (wave-1 replicates dropped): "
        + ", ".join(
            f"{t} {core_only[core_only['tier'] == t]['first_site_correct'].mean():.3f}"
            for t in TIERS
        )
    )
    for tier in TIERS:
        rows.append(rate_row(core_only[core_only["tier"] == tier],
                             "first_site_correct", f"R_b_core_only_{tier}"))

    # (c) stale counted as correct (the "old domain still redirects" reading).
    lenient = emit.assign(ok=emit["first_site_label"].isin(("correct", "stale")).astype(int))
    lines.append(
        "  (c) stale counted as correct: "
        + ", ".join(f"{t} {lenient[lenient['tier'] == t]['ok'].mean():.3f}" for t in TIERS)
    )
    for tier in TIERS:
        rows.append(rate_row(lenient[lenient["tier"] == tier], "ok", f"R_c_stale_ok_{tier}"))

    # (d) observation level rather than call level.
    obs_ok = obs.assign(ok=(obs["label"] == "correct").astype(int))
    own = obs[obs["error_kind"] != "third_party"].assign(
        ok=lambda d: (d["label"] == "correct").astype(int)
    )
    lines.append(
        "  (d) observation level, all site: queries: "
        + ", ".join(f"{t} {obs_ok[obs_ok['tier'] == t]['ok'].mean():.3f}" for t in TIERS)
        + "; excluding third-party consultations: "
        + ", ".join(f"{t} {own[own['tier'] == t]['ok'].mean():.3f}" for t in TIERS)
    )
    for tier in TIERS:
        rows.append(rate_row(obs_ok[obs_ok["tier"] == tier], "ok", f"R_d_observation_{tier}"))

    # (e) the raw first site: query of any kind (competitor sites included) —
    # the pre-rework primary, kept so both readings are reconstructable.
    any_first = calls[calls["emitted_site_query"] == 1]
    lines.append(
        "  (e) first site: query of ANY kind (third-party consultations count "
        "as not-canonical): "
        + ", ".join(
            f"{t} {any_first[any_first['tier'] == t]['first_any_correct'].mean():.3f}"
            for t in TIERS
        )
        + " — the difference from H5 is the comparison template opening on "
        "competitors, not domain error."
    )
    for tier in TIERS:
        rows.append(rate_row(any_first[any_first["tier"] == tier],
                             "first_any_correct", f"R_e_first_any_{tier}"))

    # (f) Audit D layer: a first commitment on the brand's OWN property
    # (atmeta.com for Meta, sony.co.jp for Sony) is not a wrong answer about
    # who the brand is. Amie/amieapp.com is another company and stays wrong.
    own_ok = emit.assign(
        ok=((emit["first_site_correct"] == 1)
            | (emit["first_site_attribution"] == OWN_PROPERTY)).astype(int)
    )
    lines.append(
        "  (f) own-property first commitments counted as correct (Audit D "
        "sign-off, labelled layer — the primary is unchanged): "
        + ", ".join(
            f"{t} {own_ok[own_ok['tier'] == t]['ok'].mean():.3f}" for t in TIERS
        )
    )
    for tier in TIERS:
        rows.append(rate_row(own_ok[own_ok["tier"] == tier], "ok", f"R_f_own_property_{tier}"))

    genuine = emit.assign(
        wrong=((emit["first_site_correct"] == 0)
               & (emit["first_site_attribution"] != OWN_PROPERTY)).astype(int)
    )
    parts = []
    for tier in TIERS:
        sub = genuine[genuine["tier"] == tier]
        row = rate_row(sub, "wrong", f"R_f_genuinely_wrong_{tier}")
        rows.append(row)
        parts.append(
            f"{tier} {row['k']}/{row['n']}"
            + (f" (3/n bound {rule_of_three(row['n']):.4f})" if row["k"] == 0
               else f" = {row['rate']:.4f}")
        )
    lines.append(
        "  GENUINELY wrong first commitments (stale + morphological guess + "
        "another company + unreviewed; own-property excluded): " + "; ".join(parts)
    )
    kinds = genuine[genuine["wrong"] == 1]
    if not kinds.empty:
        breakdown = kinds.assign(kind=kind_detail(
            kinds.rename(columns={"first_site_error_kind": "error_kind",
                                  "first_site_attribution": "attribution"})
        ))
        lines.append(
            "    by kind: "
            + ", ".join(f"{k} {v}" for k, v in
                        breakdown["kind"].value_counts().items())
        )

    # H2 on the call-level first-commitment error set (same three tests).
    first_errors = emit[emit["first_site_own_error"] == 1].copy()
    first_errors["registered_domain"] = first_errors["first_site_domain"]
    h2_not_identifiable(first_errors, "call level, first commitment", rows, lines)
    h2_exploratory_brand_specificity(first_errors, "call level, first commitment",
                                     rows, lines)


# ------------------------------------------------------------------ main


def ok(passed: bool) -> str:
    return "OK" if passed else "FAIL"


def dry_run_checks(world: str, verdict, posthoc: float, h4_gap: float,
                   agreement: dict) -> list[tuple[str, str, str]]:
    """Spec §5 dry run: what each planted world must produce.

    The lookup world repeats one stored domain, so the post-hoc sensitivity
    must read systemic and both wrong-domain agreements must be ~1. The guess
    world draws uniformly from the FROZEN candidate set, whose K is 1-3 for
    most of this panel; with K that small the bootstrap CI cannot always fit
    inside a +/-0.05 band, so an inconclusive verdict with a point estimate
    inside the band is an accepted pass — the band is never widened and the
    guess space is never inflated to force one.
    """
    checks: list[tuple[str, str, str]] = []
    if world == "lookup":
        checks.append(("H2 post-hoc verdict", ok(verdict == SYSTEMIC),
                       f"{verdict} (want {SYSTEMIC})"))
        checks.append(("H4 day-over-day gap", ok(h4_gap >= 0.25),
                       f"{h4_gap:+.3f} (want >= +0.250)"))
    else:
        checks.append((
            "H2 post-hoc verdict", ok(verdict in (STOCHASTIC, MIXTURE, UNDERPOWERED)),
            f"{verdict} (want stochastic, or inconclusive with the estimate in band)"))
        checks.append(("H2 post-hoc point estimate", ok(abs(posthoc) <= STOCHASTIC_DELTA),
                       f"{posthoc:+.3f} (want |x| <= {STOCHASTIC_DELTA})"))
        checks.append(("H4 day-over-day gap", ok(abs(h4_gap) <= 0.05),
                       f"{h4_gap:+.3f} (want |x| <= 0.050)"))
    for name in ("within_day", "across_day"):
        rate = agreement.get(f"any_{name}_id", float("nan"))
        base = agreement.get(f"any_{name}_id_baseline", float("nan"))
        n = agreement.get(f"any_{name}_id_n", 0)
        label = f"{name.replace('_', '-')} wrong-domain agreement, K >= 2"
        if n < MIN_AGREEMENT_PAIRS:
            checks.append((label, "SKIP",
                           f"{n} pair(s) — under the {MIN_AGREEMENT_PAIRS}-pair floor, "
                           "nothing to assert (both mechanisms need both calls wrong "
                           "on the same brand x template)"))
        elif world == "lookup":
            checks.append((label, ok(rate >= 0.95), f"{rate:.3f} over {n} pairs (want ~1, >= 0.95)"))
        else:
            checks.append((label, ok(abs(rate - base) <= 0.15),
                           f"{rate:.3f} vs 1/K baseline {base:.3f} over {n} pairs "
                           "(want within 0.15)"))
    return checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    ap.add_argument("--expect", choices=SYNTHETIC_WORLDS, default=None,
                    help="assert the dry-run verdicts for that planted world")
    a = ap.parse_args()

    calls = load_responses(synthetic=a.synthetic)
    obs = load_observations(synthetic=a.synthetic)
    obs, resolution_note = apply_resolution(obs)
    synthetic = int(calls.get("synthetic", pd.Series([0])).max()) == 1

    rows: list[dict] = []
    lines: list[str] = [
        f"# Experiment 008 — model results{f' (SYNTHETIC/{a.synthetic})' if synthetic else ''}",
        f"alpha={ALPHA} (95% intervals), n_boot={N_BOOT}, n_perm={N_PERM}, seed={SEED}",
        f"{len(calls)} study calls, {len(obs)} site: observations, "
        f"{calls['slug'].nunique()} brands, waves {calls['wave'].min()}-{calls['wave'].max()}",
        f"error-kind resolution: {resolution_note}",
        "",
    ]

    passed = h_pos(calls, obs, rows, lines)
    verdict, h4_gap, posthoc = None, float("nan"), float("nan")
    agreement: dict = {}
    if passed:
        h_pla(calls, rows, lines)
        h1_emission(calls, rows, lines)
        errors = own_errors(obs)
        h2_not_identifiable(errors, "observation level", rows, lines)
        h2_exploratory_brand_specificity(errors, "observation level", rows, lines)
        h3_error_content(errors, obs, rows, lines)
        h4_gap = h4_transitions(calls, rows, lines)
        agreement = h4_domain_agreement(calls, rows, lines)
        within_day_reference(calls, rows, lines)
        verdict, posthoc = h2_posthoc_frozen_baseline(errors, rows, lines)
        h5_tier_accuracy(calls, rows, lines)
        zero_cell_table(calls, obs, lines)
        robustness(calls, obs, errors, rows, lines)

    out = results_dir(a.synthetic)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "model_results.csv", index=False)
    summary = "\n".join(lines) + "\n"
    (out / "model_summary.txt").write_text(summary)
    print(summary)
    print(f"wrote {out / 'model_results.csv'} and {out / 'model_summary.txt'}")

    if not passed:
        sys.exit(1)
    if a.expect:
        checks = dry_run_checks(a.expect, verdict, posthoc, h4_gap, agreement)
        print(f"\ndry-run check ({a.expect}):")
        for name, status, detail in checks:
            print(f"  {status:<4} {name}: {detail}")
        if any(status == "FAIL" for _, status, _ in checks):
            sys.exit(2)


if __name__ == "__main__":
    main()
