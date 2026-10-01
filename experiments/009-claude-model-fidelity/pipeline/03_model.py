"""Stage 03 — pre-registered tests (spec §4, §5, §7) -> results/model_summary.txt
and results/model_results.json.

Sequence (spec §7: positive control first, exit 1 if it fails):

  H_pos   same-prompt minus cross-category cross-arm brand Jaccard (all API
          arms vs ui_default, pooled, same wave) >= 0.10 with the 90% CI
          excluding 0. Fails -> write the summary and exit 1.
  H_pla   H1b gap on odd minus even prompts, TOST +/-0.10, every primary arm.
  H1b     primary family (sonnet5_plain, sonnet5_leak_think, haiku45_leak),
          gap = mean(within:ui_default) - mean(cross:arm|ui_default) on
          brand-set Jaccard; Holm over the three: bootstrap TOST p = the
          larger one-sided tail probability at +/-0.10, tests ordered by p,
          each verdict from the CI at its Holm-adjusted level.
  H1b     secondary (sonnet5_leak_low, sonnet5_prod), unadjusted.
  H1-ref  H1b for the two Opus arms, with the fallback rule: if both fail,
          the cheap arms are also reported against opus55_plain.
  domains per-answer cited-domain and evaluated-domain gaps, every API arm,
          with the Audit A no-search rule (> 30% -> INCONCLUSIVE).
  RBO     gap on brand order, every API arm (also robustness R2).
  H1s/H1d panel comparisons per category, DESCRIPTIVE ONLY (spec deviation
          9): each API arm (and ui_think as a same-surface reference) vs
          ui_default, mean over categories with a 90% category-level
          cluster-bootstrap interval: RBO of the share-ranked vendor lists and
          Kendall tau-b over the pooled-share basket ("same vendors in the
          same order"); Jaccard of the vendors at share >= 1/3 and of all
          vendors named ("same vendors regardless of order"). Same for cited
          domains. No verdict. The pre-deviation noise-corrected RMSD
          (pipeline/shares.py) is kept in model_results.json under
          ``deprecated_rmsd`` only.
  H2      sonnet5_leak_think vs sonnet5_leak_low and ui_default vs ui_think:
          mean of the two within-arm floors minus the cross-arm mean, TOST.
  H3/H3b  the Opus gaps; gap(opus55_plain) - gap(opus55_leak), TOST.
  fair    gap(sonnet5_plain) - gap(opus55_plain), CI only.
  gradient same prompt / same category other intent / other category, CIs.
  descriptives  per arm and per arm x wave, incl. $/call with and without
          the calls that paid a 1-hour cache write.
  R1-R7   robustness (spec §7).

Inference: prompt-level cluster bootstrap with the dyadic weights of
``aeo_research.overlap.cluster_boot`` (2,000 draws, 90% percentile CI,
seed = freeze date 20260926). ``boot_combo`` below reproduces cluster_boot
draw for draw (same generator calls, same weights) and keeps the draws, so
TOST tail probabilities and Holm-level CIs come from the same draws, and it
also handles linear combinations of more than two condition means (H2,
H_pla).

Real data is gated: this stage refuses to run unless Audit D has passed and
been signed (results/audit_d_score.json), the domain map is frozen
(common.DOMAIN_MAP_SHA256 matches data/raw/domain_map_v1.csv) and the full
2,000 draws are used. ``--n-boot`` is for the synthetic dry run only.

Usage:
  uv run python experiments/009-claude-model-fidelity/pipeline/03_model.py
  uv run python .../03_model.py --synthetic planted --expect planted [--n-boot 300]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import shares
from brands import verify_lexicon
from common import (
    ALPHA,
    API_ARMS,
    AUDIT_D_SCORE,
    CHEAP_ARMS,
    DOMAIN_MAP,
    DOMAIN_MAP_SHA256,
    FALLBACK_REFERENCE,
    H_POS_MIN,
    N_BOOT,
    NO_SEARCH_MAX,
    PRIMARY_ARMS,
    RBO_P,
    REF_ARMS,
    REFERENCE,
    SECONDARY_H1B_ARMS,
    SEED,
    SESOI,
    SESOI_SHARE,
    SHARE_THRESHOLD,
    SOURCE_CLASSES,
    SYNTHETIC_WORLDS,
    TOP_K,
    build_pairs,
    cross,
    item_number,
    load_features,
    results_dir,
    sha256_file,
    within,
)
from scipy import stats as sps

from aeo_research.overlap import jaccard, rbo
from aeo_research.stats import Verdict

EQUIVALENT = (Verdict.NULL, Verdict.NEGLIGIBLE)

#: Pair metric -> (feature column, label). Brand metrics read ``brands``
#: (or the R4 replacement); domain metrics read the domain lists.
METRIC_LABELS = {
    "brand_j": "brand-set Jaccard",
    "top10_j": "top-10 brand Jaccard",
    "brand_rbo": "brand-order RBO",
    "cited_j": "cited-domain Jaccard",
    "eval_j": "evaluated-domain Jaccard",
}
DOMAIN_METRICS = ("cited_j", "eval_j")


# ------------------------------------------------------------ pair metrics


def add_metrics(pairs: pd.DataFrame, df: pd.DataFrame, brand_col: str = "brands") -> pd.DataFrame:
    pairs = pairs.copy()
    i, j = pairs["i"].to_numpy(), pairs["j"].to_numpy()
    b = list(df[brand_col])
    c = list(df["cited_domains"])
    e = list(df["evaluated_domains"])
    pairs["brand_j"] = [jaccard(set(b[x]), set(b[y])) for x, y in zip(i, j)]
    pairs["top10_j"] = [jaccard(set(b[x][:TOP_K]), set(b[y][:TOP_K])) for x, y in zip(i, j)]
    pairs["brand_rbo"] = [rbo(b[x], b[y], RBO_P) for x, y in zip(i, j)]
    pairs["cited_j"] = [jaccard(set(c[x]), set(c[y])) for x, y in zip(i, j)]
    pairs["eval_j"] = [jaccard(set(e[x]), set(e[y])) for x, y in zip(i, j)]
    return pairs


def frame_pairs(df: pd.DataFrame, brand_col: str = "brands") -> pd.DataFrame:
    df = df.reset_index(drop=True)
    return add_metrics(build_pairs(df), df, brand_col)


# ------------------------------------------------------------ bootstrap


@dataclass
class Boot:
    estimate: float
    draws: np.ndarray
    n_clusters: int
    n_pairs: int
    n_nan: int

    def ci(self, alpha: float = ALPHA) -> tuple[float, float]:
        if self.draws.size == 0:
            return float("nan"), float("nan")
        lo, hi = np.quantile(self.draws, [alpha / 2, 1 - alpha / 2])
        return float(lo), float(hi)

    def tost_p(self, sesoi: float = SESOI) -> float:
        """Bootstrap TOST p: the larger one-sided tail probability at the band edges."""
        if self.draws.size == 0:
            return float("nan")
        return float(max((self.draws <= -sesoi).mean(), (self.draws >= sesoi).mean()))


def boot_combo(
    pairs: pd.DataFrame,
    value_col: str,
    coefs: dict[str, float],
    *,
    n_boot: int = N_BOOT,
    seed: int = SEED,
    cluster_cols: tuple[str, str] = ("cluster_i", "cluster_j"),
) -> Boot:
    """Cluster bootstrap of sum_k coef_k * mean(condition_k), draws kept.

    Same resampling as ``aeo_research.overlap.cluster_boot``: clusters are
    factorized over the usable pairs in row order, each draw is
    ``rng.integers(0, n_clusters, n_clusters)``, and a pair's weight is
    c_i * c_j between clusters and c_i within one. With coefs {a: 1, b: -1}
    (or {a: 1}) the estimate and draws equal cluster_boot's exactly.
    """
    ci_col, cj_col = cluster_cols
    sel = pairs.loc[pairs["condition"].isin(list(coefs))]
    work = pd.DataFrame({value_col: sel[value_col], "condition": sel["condition"],
                         "_ci": sel[ci_col], "_cj": sel[cj_col]})
    ci_col, cj_col = "_ci", "_cj"
    n_nan = int(work[value_col].isna().sum())
    work = work.dropna(subset=[value_col]).reset_index(drop=True)
    missing = [c for c in coefs if not (work["condition"] == c).any()]
    if work.empty or missing:
        return Boot(float("nan"), np.array([]), 0, len(work), n_nan)
    all_clusters = pd.concat([work[ci_col], work[cj_col]])
    codes, clusters = pd.factorize(all_clusters)
    n_clusters = len(clusters)
    ci_codes = codes[: len(work)]
    cj_codes = codes[len(work):]
    same = ci_codes == cj_codes
    values = work[value_col].to_numpy(dtype=float)
    masks = [((work["condition"] == c).to_numpy(), float(k)) for c, k in coefs.items()]

    def stat(counts: np.ndarray) -> float:
        w = np.where(same, counts[ci_codes], counts[ci_codes] * counts[cj_codes])
        total = 0.0
        for m, k in masks:
            wm = w[m]
            s = wm.sum()
            if s <= 0:
                return float("nan")
            total += k * float((values[m] * wm).sum() / s)
        return total

    observed = stat(np.ones(n_clusters))
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot)
    for b in range(n_boot):
        draw = rng.integers(0, n_clusters, size=n_clusters)
        draws[b] = stat(np.bincount(draw, minlength=n_clusters).astype(float))
    draws = draws[~np.isnan(draws)]
    return Boot(float(observed), draws, n_clusters, len(work), n_nan)


def verdict_of(lo: float, hi: float, sesoi: float = SESOI) -> Verdict:
    """The four-way TOST mapping of cluster_boot / stats.tost."""
    if math.isnan(lo) or math.isnan(hi):
        return Verdict.INCONCLUSIVE
    equivalent = (lo > -sesoi) and (hi < sesoi)
    nonzero = (lo > 0) or (hi < 0)
    if equivalent and not nonzero:
        return Verdict.NULL
    if equivalent and nonzero:
        return Verdict.NEGLIGIBLE
    if nonzero:
        return Verdict.REAL
    return Verdict.INCONCLUSIVE


# ------------------------------------------------------------ context


class Ctx:
    """Shared state: the frame, its pairs, settings, and the output buffers."""

    def __init__(self, df: pd.DataFrame, n_boot: int):
        self.df = df.reset_index(drop=True)
        self.pairs = frame_pairs(self.df)
        self.n_boot = n_boot
        self.rows: list[dict] = []
        self.lines: list[str] = []
        self.boots: dict[str, Boot] = {}
        self.deprecated: list[dict] = []
        rate = self.df.groupby("arm")["n_searches"].apply(lambda s: float((s == 0).mean()))
        self.no_search = rate.to_dict()

    def rule_hit(self, *arms: str) -> list[str]:
        """Arms in a domain comparison over the Audit A no-search limit."""
        return [a for a in arms if self.no_search.get(a, 0.0) > NO_SEARCH_MAX]

    def say(self, line: str = "") -> None:
        self.lines.append(line)


def fmt_ci(est: float, lo: float, hi: float) -> str:
    return f"{est:+.3f} [{lo:+.3f}, {hi:+.3f}]"


def test_row(ctx: Ctx, *, section: str, test: str, metric: str, coefs: dict[str, float],
             arms: tuple[str, ...], pairs: pd.DataFrame | None = None, sesoi: float | None = SESOI,
             alpha: float = ALPHA, cluster_cols=("cluster_i", "cluster_j"),
             key: str | None = None, extra: dict | None = None) -> dict:
    """Bootstrap one contrast and record it. ``sesoi=None`` -> CI only."""
    pairs = ctx.pairs if pairs is None else pairs
    boot = boot_combo(pairs, metric, coefs, n_boot=ctx.n_boot, seed=SEED,
                      cluster_cols=cluster_cols)
    lo, hi = boot.ci(alpha)
    row = {
        "section": section, "test": test, "metric": metric, "arms": list(arms),
        "contrast": " ".join(f"{'+' if k > 0 else '-'}{abs(k):g}*{c}" for c, k in coefs.items()),
        "estimate": boot.estimate, "lo": lo, "hi": hi, "ci_level": 1 - alpha,
        "n_pairs": boot.n_pairs, "n_nan": boot.n_nan, "n_clusters": boot.n_clusters,
        "n_boot": int(boot.draws.size),
    }
    if sesoi is not None:
        v = verdict_of(lo, hi, sesoi)
        row |= {"sesoi": sesoi, "p_tost": boot.tost_p(sesoi), "verdict_ci": v.name,
                "verdict": v.name}
        if metric in DOMAIN_METRICS:
            hit = ctx.rule_hit(*arms)
            if hit:
                row["verdict"] = Verdict.INCONCLUSIVE.name
                row["rule"] = f"no-search rate > {NO_SEARCH_MAX:.0%}: {', '.join(hit)}"
    if extra:
        row |= extra
    ctx.rows.append(row)
    if key:
        ctx.boots[key] = boot
    return row


def gap_coefs(arm: str, ref: str = REFERENCE) -> dict[str, float]:
    return {within(ref): 1.0, cross(arm, ref): -1.0}


def line_for(row: dict) -> str:
    s = (f"  {row['test']:<34} {METRIC_LABELS.get(row['metric'], row['metric']):<26} "
         f"{fmt_ci(row['estimate'], row['lo'], row['hi'])}")
    if "verdict" in row:
        s += f" -> {row['verdict']}"
        if row.get("rule"):
            s += f" ({row['rule']}; CI alone: {row['verdict_ci']})"
    s += f"  (pairs {row['n_pairs']}, NaN {row['n_nan']})"
    return s


# ------------------------------------------------------------ H_pos, gradient


def relation_pairs(df: pd.DataFrame, arms=API_ARMS, ref: str = REFERENCE) -> pd.DataFrame:
    """API-arm x ui_default answer pairs in the same wave, labelled by relation."""
    out = []
    items = df["item_id"].to_numpy()
    cats = df["category"].to_numpy()
    for wave in sorted(df["wave"].unique()):
        a_idx = np.flatnonzero((df["wave"] == wave).to_numpy() & df["arm"].isin(arms).to_numpy())
        u_idx = np.flatnonzero((df["wave"] == wave).to_numpy() & (df["arm"] == ref).to_numpy())
        for i in a_idx:
            for j in u_idx:
                if items[i] == items[j]:
                    rel = "same_prompt"
                elif cats[i] == cats[j]:
                    rel = "same_category"
                else:
                    rel = "other_category"
                out.append((i, j, rel, items[i], items[j]))
    pairs = pd.DataFrame(out, columns=["i", "j", "condition", "cluster_i", "cluster_j"])
    b = list(df["brands"])
    pairs["brand_j"] = [jaccard(set(b[x]), set(b[y])) for x, y in zip(pairs["i"], pairs["j"])]
    return pairs


def h_pos(ctx: Ctx) -> bool:
    ctx.say("## H_pos (positive control; the study stops if it fails)")
    rel = relation_pairs(ctx.df)
    ctx.rel_pairs = rel
    row = test_row(ctx, section="H_pos", test="H_pos", metric="brand_j",
                   coefs={"same_prompt": 1.0, "other_category": -1.0}, arms=API_ARMS + (REFERENCE,),
                   pairs=rel, sesoi=None)
    passed = bool(row["estimate"] >= H_POS_MIN and row["lo"] > 0)
    row["passed"] = passed
    ctx.say(f"  same-prompt minus cross-category cross-arm brand Jaccard (all API arms vs "
            f"{REFERENCE}, same wave) = {fmt_ci(row['estimate'], row['lo'], row['hi'])}; "
            f"need >= {H_POS_MIN:.2f} with the CI excluding 0 -> "
            f"{'PASS' if passed else 'FAIL: STOP, extraction or the prompt join is broken'}")
    ctx.say(f"  (pairs {row['n_pairs']}, NaN {row['n_nan']}, prompts {row['n_clusters']})")
    return passed


def gradient(ctx: Ctx) -> None:
    ctx.say("\n## Descriptive gradient (cross-arm brand Jaccard, API arms vs ui_default, "
            "same wave; no test)")
    for rel, label in (("same_prompt", "same prompt"),
                       ("same_category", "same category, other intent"),
                       ("other_category", "different category")):
        row = test_row(ctx, section="gradient", test=f"gradient_{rel}", metric="brand_j",
                       coefs={rel: 1.0}, arms=API_ARMS + (REFERENCE,), pairs=ctx.rel_pairs,
                       sesoi=None)
        ctx.say(f"  {label:<30} {row['estimate']:.3f} [{row['lo']:.3f}, {row['hi']:.3f}] "
                f"(pairs {row['n_pairs']})")


# ------------------------------------------------------------ H_pla


def h_pla(ctx: Ctx) -> bool:
    ctx.say("\n## H_pla (placebo): H1b gap on odd minus even prompts, TOST +/-0.10")
    ok_all = True
    parity = ctx.pairs["cluster_i"].map(lambda x: "odd" if item_number(x) % 2 else "even")
    split = ctx.pairs.assign(condition=ctx.pairs["condition"] + "@" + parity)
    for arm in PRIMARY_ARMS:
        w, c = within(REFERENCE), cross(arm, REFERENCE)
        coefs = {f"{w}@odd": 1.0, f"{c}@odd": -1.0, f"{w}@even": -1.0, f"{c}@even": 1.0}
        row = test_row(ctx, section="H_pla", test=f"H_pla {arm}", metric="brand_j",
                       coefs=coefs, arms=(arm, REFERENCE), pairs=split)
        ok = row["verdict"] in (Verdict.NULL.name, Verdict.NEGLIGIBLE.name)
        row["passed"] = ok
        ok_all &= ok
        ctx.say(line_for(row) + ("" if ok else "  ** WARNING: placebo not null **"))
    return ok_all


# ------------------------------------------------------------ H1b


def holm(ctx: Ctx, rows: list[dict], keys: list[str]) -> None:
    """Holm over a family: rank by bootstrap TOST p, CI at alpha / (m - k + 1).

    Also records the step-down Holm-adjusted p and flags any test whose
    CI verdict claims equivalence after a lower-ranked test did not (strict
    step-down would stop there).
    """
    m = len(rows)
    order = sorted(range(m), key=lambda k: rows[k]["p_tost"])
    running, blocked = 0.0, False
    for rank, k in enumerate(order, start=1):
        row, boot = rows[k], ctx.boots[keys[k]]
        alpha_k = ALPHA / (m - rank + 1)
        lo, hi = boot.ci(alpha_k)
        v = verdict_of(lo, hi, SESOI)
        running = max(running, min(1.0, (m - rank + 1) * row["p_tost"]))
        row |= {"holm_rank": rank, "holm_alpha": alpha_k, "ci_level": 1 - alpha_k,
                "lo": lo, "hi": hi, "verdict_ci": v.name, "verdict": v.name,
                "p_holm": running, "lo_unadjusted": boot.ci(ALPHA)[0],
                "hi_unadjusted": boot.ci(ALPHA)[1]}
        equivalent = v in EQUIVALENT
        if equivalent and blocked:
            row["holm_stepdown_note"] = ("strict step-down would not claim equivalence: a "
                                         "lower-ranked test in the family did not")
        if not equivalent:
            blocked = True


def h1b(ctx: Ctx) -> None:
    ctx.say("\n## H1b primary family (brand-set Jaccard gap = within:ui_default - "
            "cross:arm|ui_default; TOST +/-0.10; Holm over 3)")
    rows, keys = [], []
    for arm in PRIMARY_ARMS:
        key = f"H1b:{arm}"
        rows.append(test_row(ctx, section="H1b_primary", test=f"H1b {arm}", metric="brand_j",
                             coefs=gap_coefs(arm), arms=(arm, REFERENCE), key=key))
        keys.append(key)
    holm(ctx, rows, keys)
    for row in sorted(rows, key=lambda r: r["holm_rank"]):
        ctx.say(line_for(row) + f"  [rank {row['holm_rank']}, {row['ci_level']:.4f} CI, "
                f"bootstrap TOST p {row['p_tost']:.4f}, Holm p {row['p_holm']:.4f}]")
        if row.get("holm_stepdown_note"):
            ctx.say(f"    NOTE: {row['holm_stepdown_note']}")

    ctx.say("\n## H1b secondary (no multiplicity correction)")
    for arm in SECONDARY_H1B_ARMS:
        ctx.say(line_for(test_row(ctx, section="H1b_secondary", test=f"H1b {arm}",
                                  metric="brand_j", coefs=gap_coefs(arm), arms=(arm, REFERENCE))))


def h1_ref(ctx: Ctx) -> None:
    ctx.say("\n## H1-ref (ceiling): H1b for the Opus arms")
    fails = []
    for arm in REF_ARMS:
        row = test_row(ctx, section="H1_ref", test=f"H1b {arm}", metric="brand_j",
                       coefs=gap_coefs(arm), arms=(arm, REFERENCE))
        ctx.say(line_for(row))
        fails.append(row["verdict"] not in (Verdict.NULL.name, Verdict.NEGLIGIBLE.name))
    ctx.fallback = all(fails)
    if not ctx.fallback:
        ctx.say("  At least one Opus arm reaches equivalence on H1b; the fallback reference "
                "is not triggered.")
        return
    ctx.say(f"  Both Opus arms fail H1b: no API configuration reproduces the UI at any price. "
            f"Cheap arms also reported against {FALLBACK_REFERENCE} (secondary reference):")
    for arm in CHEAP_ARMS:
        for metric in ("brand_j", "cited_j"):
            ctx.say(line_for(test_row(
                ctx, section="H1_ref_fallback", test=f"vs {FALLBACK_REFERENCE}: {arm}",
                metric=metric, coefs=gap_coefs(arm, FALLBACK_REFERENCE),
                arms=(arm, FALLBACK_REFERENCE))))


def domain_and_rbo_gaps(ctx: Ctx) -> None:
    ctx.say("\n## Per-answer domain gaps, every API arm (secondary; TOST +/-0.10; the pilot "
            "simulation puts false equivalence at 0.16 to 0.33, so a pass carries that caveat)")
    for metric in DOMAIN_METRICS:
        for arm in API_ARMS:
            ctx.say(line_for(test_row(ctx, section="domain_gap", test=f"gap {arm}",
                                      metric=metric, coefs=gap_coefs(arm),
                                      arms=(arm, REFERENCE))))
    ctx.say("\n## RBO gap on brand order, every API arm (secondary; also robustness R2)")
    for arm in API_ARMS:
        ctx.say(line_for(test_row(ctx, section="rbo_gap", test=f"gap {arm}", metric="brand_rbo",
                                  coefs=gap_coefs(arm), arms=(arm, REFERENCE))))


def levels(ctx: Ctx) -> None:
    """Condition means with CIs (the lead figure's points and band)."""
    ctx.say("\n## Levels (same-prompt Jaccard; the lead figure)")
    for metric in ("brand_j", "cited_j"):
        row = test_row(ctx, section="level", test=f"level {within(REFERENCE)}", metric=metric,
                       coefs={within(REFERENCE): 1.0}, arms=(REFERENCE,), sesoi=None)
        ctx.say(f"  {METRIC_LABELS[metric]:<26} {within(REFERENCE):<34} "
                f"{row['estimate']:.3f} [{row['lo']:.3f}, {row['hi']:.3f}]")
        for arm in API_ARMS:
            row = test_row(ctx, section="level", test=f"level {cross(arm, REFERENCE)}",
                           metric=metric, coefs={cross(arm, REFERENCE): 1.0},
                           arms=(arm, REFERENCE), sesoi=None)
            ctx.say(f"  {METRIC_LABELS[metric]:<26} {cross(arm, REFERENCE):<34} "
                    f"{row['estimate']:.3f} [{row['lo']:.3f}, {row['hi']:.3f}]")


# ------------------------------------------------------------ panel shares


#: The two questions Jim asks of a panel (spec deviation 9): panel statistics
#: per category, each API arm (and ui_think, as a same-surface reference)
#: against ui_default, averaged over categories. Descriptive only.
PANEL_STATS = {
    "panel_rbo": "same vendors in the same order: RBO of share-ranked lists",
    "panel_kendall": "same vendors in the same order: Kendall tau-b, pooled-share basket",
    "panel_jaccard_third": "same vendors regardless of order: Jaccard, share >= 1/3 in each arm",
    "panel_jaccard_all": "same vendors regardless of order: Jaccard, named at least once",
}
PANEL_COMPARISONS = API_ARMS + ("ui_think",)


def share_ranking(lists: list[list[str]]) -> tuple[list[str], dict[str, float]]:
    """Items ordered by share of answers naming them (desc), ties broken by
    mean first-mention position over the answers that name them, then name."""
    n = len(lists)
    count: dict[str, int] = {}
    pos: dict[str, list[int]] = {}
    for items in lists:
        for k, x in enumerate(dict.fromkeys(items)):
            count[x] = count.get(x, 0) + 1
            pos.setdefault(x, []).append(k)
    share = {x: c / n for x, c in count.items()} if n else {}
    order = sorted(share, key=lambda x: (-share[x], float(np.mean(pos[x])), x))
    return order, share


def category_panel(a_lists: list[list[str]], r_lists: list[list[str]]) -> dict[str, float]:
    """The four panel statistics for one category (NaN where undefined)."""
    nan = float("nan")
    a_order, a_share = share_ranking(a_lists)
    r_order, r_share = share_ranking(r_lists)
    out = {"panel_rbo": rbo(a_order, r_order, RBO_P) if (a_order or r_order) else nan}
    items = sorted(set(a_share) | set(r_share))
    sa = np.array([a_share.get(x, 0.0) for x in items])
    sr = np.array([r_share.get(x, 0.0) for x in items])
    basket = (sa + sr) / 2 >= SHARE_THRESHOLD - 1e-9
    tau = nan
    if basket.sum() >= 2:
        t = sps.kendalltau(sa[basket], sr[basket]).statistic
        tau = float(t) if np.isfinite(t) else nan
    out["panel_kendall"] = tau
    out["panel_jaccard_third"] = jaccard(
        {x for x, v in a_share.items() if v >= SHARE_THRESHOLD - 1e-9},
        {x for x, v in r_share.items() if v >= SHARE_THRESHOLD - 1e-9})
    out["panel_jaccard_all"] = jaccard(set(a_share), set(r_share))
    return out


def panel_table(df: pd.DataFrame, arm: str, col: str, ref: str = REFERENCE) -> pd.DataFrame:
    """One row per category with both arms present: the four statistics."""
    rows = []
    for cat, g in df[df["arm"].isin([arm, ref])].groupby("category", sort=True):
        a = list(g.loc[g["arm"] == arm, col])
        r = list(g.loc[g["arm"] == ref, col])
        if a and r:
            rows.append({"category": cat, **category_panel(a, r)})
    return pd.DataFrame(rows)


def category_mean_ci(values: np.ndarray, n_boot: int) -> tuple[float, float, float, int]:
    """Mean over categories with a category-level cluster-bootstrap interval
    (whole categories resampled with replacement, no prompt stage)."""
    v = values[np.isfinite(values)]
    if v.size == 0:
        return float("nan"), float("nan"), float("nan"), 0
    rng = np.random.default_rng(SEED)
    draws = v[rng.integers(0, v.size, size=(n_boot, v.size))].mean(axis=1)
    lo, hi = np.quantile(draws, [ALPHA / 2, 1 - ALPHA / 2])
    return float(v.mean()), float(lo), float(hi), int(v.size)


def panel_rows(ctx: Ctx, df: pd.DataFrame, arm: str, col: str, *, section: str,
               label: str) -> list[dict]:
    table = panel_table(df, arm, col)
    rows = []
    for stat in PANEL_STATS:
        values = table[stat].to_numpy(dtype=float) if not table.empty else np.array([])
        est, lo, hi, n = category_mean_ci(values, ctx.n_boot)
        row = {"section": section, "test": f"{label} {arm}", "metric": stat,
               "items": "brands" if col == "brands" else "cited_domains",
               "arms": [arm, REFERENCE], "estimate": est, "lo": lo, "hi": hi,
               "ci_level": 1 - ALPHA, "n_categories": n, "kind": "descriptive",
               "interval": "category-level cluster bootstrap"}
        if col == "cited_domains":
            hit = ctx.rule_hit(arm, REFERENCE)
            if hit:
                row["note"] = f"no-search rate > {NO_SEARCH_MAX:.0%}: {', '.join(hit)}"
        ctx.rows.append(row)
        rows.append(row)
    return rows


def panel_lines(rows: list[dict]) -> str:
    by = {r["metric"]: r for r in rows}
    arm = rows[0]["arms"][0]
    parts = [f"{k.removeprefix('panel_')} {by[k]['estimate']:.3f} "
             f"[{by[k]['lo']:.3f}, {by[k]['hi']:.3f}]" for k in PANEL_STATS]
    s = f"  {arm:<20} " + "; ".join(parts) + f" ({by['panel_rbo']['n_categories']} cat.)"
    if by["panel_rbo"].get("note"):
        s += f"  [{by['panel_rbo']['note']}]"
    return s


def deprecated_rmsd(ctx: Ctx) -> None:
    """The pre-deviation-9 statistic, kept in model_results.json only."""
    for col, label in (("brands", "H1s"), ("cited_domains", "H1d")):
        for arm in API_ARMS:
            cells = shares.build_cells(ctx.df, arm, REFERENCE, col)
            res = shares.share_test(cells, statistic="rmsd", basket_on="pooled",
                                    threshold=SHARE_THRESHOLD, sesoi=SESOI_SHARE, alpha=ALPHA,
                                    n_boot=ctx.n_boot, seed=SEED)
            ctx.deprecated.append({"test": f"{label} {arm}", "statistic": "rmsd",
                                   "estimate": res.rmsd, "lo": res.lower, "hi": res.upper,
                                   "basket_size": res.basket_size,
                                   "n_categories": res.n_categories})


def panel_descriptives(ctx: Ctx, df: pd.DataFrame | None = None, *, section_prefix: str = "",
                       cols=(("brands", "H1s"), ("cited_domains", "H1d")),
                       comparisons=PANEL_COMPARISONS) -> None:
    df = ctx.df if df is None else df
    for col, label in cols:
        section = f"{section_prefix}{label}"
        what = "brands" if col == "brands" else "cited domains"
        if not section_prefix:
            ctx.say(f"\n## {label} panel, {what} (descriptive; per category, arm vs "
                    f"{REFERENCE}, mean over categories, 90% category-bootstrap interval)")
            ctx.say("  rbo = share-ranked lists, p 0.9; kendall = tau-b over the pooled-share "
                    "basket; jaccard_third = items named in >= 1/3 of each arm's answers; "
                    "jaccard_all = items named at least once")
        for arm in comparisons:
            if arm == "ui_think" and not section_prefix:
                ctx.say("  reference, same surface (claude.ai High vs Medium):")
            ctx.say(panel_lines(panel_rows(ctx, df, arm, col, section=section,
                                           label=f"{section} panel")))


# ------------------------------------------------------------ H2, H3, fair


def h2(ctx: Ctx) -> None:
    ctx.say("\n## H2 (reasoning): mean of the two within-arm floors minus the cross-arm "
            "mean (same prompt, same wave); TOST +/-0.10")
    for a, b in (("sonnet5_leak_think", "sonnet5_leak_low"), ("ui_default", "ui_think")):
        for metric in ("brand_j", "cited_j"):
            ctx.say(line_for(test_row(
                ctx, section="H2", test=f"H2 {a} vs {b}", metric=metric,
                coefs={within(a): 0.5, within(b): 0.5, cross(a, b): -1.0}, arms=(a, b))))


def h3(ctx: Ctx) -> None:
    ctx.say("\n## H3 (API vs subscription, same model): the Opus gaps (rows above under "
            "H1-ref and the domain gaps)")
    for r in ctx.rows:
        if r["section"] in ("H1_ref", "domain_gap") and r["metric"] in ("brand_j", "cited_j") \
                and r["arms"][0] in REF_ARMS:
            ctx.say(line_for({**r, "test": f"H3 {r['arms'][0]}"}))
    ctx.say("\n## H3b: gap(opus55_plain) - gap(opus55_leak); TOST +/-0.10 (a positive REAL "
            "result means the leak moves the API closer to the UI; instrument divergence only)")
    for metric in ("brand_j", "cited_j"):
        ctx.say(line_for(test_row(
            ctx, section="H3b", test="H3b plain - leak", metric=metric,
            coefs={cross("opus55_leak", REFERENCE): 1.0, cross("opus55_plain", REFERENCE): -1.0},
            arms=("opus55_plain", "opus55_leak", REFERENCE))))


def fair_comparison(ctx: Ctx) -> None:
    ctx.say("\n## Fair model comparison (descriptive): gap(sonnet5_plain) - gap(opus55_plain)")
    for metric in ("brand_j", "cited_j"):
        ctx.say(line_for(test_row(
            ctx, section="fair", test="sonnet5_plain - opus55_plain", metric=metric,
            coefs={cross("opus55_plain", REFERENCE): 1.0, cross("sonnet5_plain", REFERENCE): -1.0},
            arms=("sonnet5_plain", "opus55_plain", REFERENCE), sesoi=None)))


# ------------------------------------------------------------ descriptives


def cost_cols(g: pd.DataFrame) -> dict:
    cost = g["cost_usd"].dropna()
    if cost.empty:
        return {"usd_call": float("nan"), "usd_call_no_cache_write": float("nan"),
                "cache_write_calls": 0}
    cw = g.loc[g["cost_usd"].notna(), "cache_write_1h"].fillna(False).astype(bool)
    return {"usd_call": float(cost.mean()),
            "usd_call_no_cache_write": float(cost[~cw.to_numpy()].mean()) if (~cw).any()
            else float("nan"),
            "cache_write_calls": int(cw.sum())}


def describe(g: pd.DataFrame) -> dict:
    return {
        "answers": len(g),
        "searches": float(g["n_searches"].mean()),
        "no_search_rate": float((g["n_searches"] == 0).mean()),
        "cited_urls": float(g["n_cited"].mean()),
        "cited_domains": float(g["n_cited_domains"].mean()),
        "evaluated_urls": float(g["n_evaluated"].mean()),
        "chars": float(g["chars"].mean()),
        "brands": float(g["n_brands"].mean()),
        **cost_cols(g),
    }


def source_mix(g: pd.DataFrame) -> dict | None:
    if g["cited_classes"].map(lambda v: v is None).any():
        return None
    counts = pd.Series([c for v in g["cited_classes"] for c in v]).value_counts()
    total = counts.sum()
    return {c: float(counts.get(c, 0) / total) if total else float("nan") for c in SOURCE_CLASSES}


def descriptives(ctx: Ctx) -> dict:
    df = ctx.df
    arms = [a for a in (REFERENCE, "ui_think", *API_ARMS) if a in set(df["arm"])]
    by_arm = [{"arm": a, **describe(df[df["arm"] == a])} for a in arms]
    by_wave = [{"arm": a, "wave": int(w), **describe(df[(df["arm"] == a) & (df["wave"] == w)])}
               for a in arms for w in sorted(df["wave"].unique())]
    mix = {a: source_mix(df[df["arm"] == a]) for a in arms}
    ctx.say("\n## Descriptive outcomes (no test)")
    ctx.say("  $/call = ledger batch-priced mean (cache effects included); "
            "`no_cw` excludes the calls that paid a 1-hour cache write (the batch's 'first "
            "calls': requests in a batch run concurrently, so several per arm pay the write).")
    t = pd.DataFrame(by_arm)
    ctx.say(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    ctx.say("\n  per wave:")
    ctx.say(pd.DataFrame(by_wave)[["arm", "wave", "answers", "searches", "no_search_rate",
                                   "cited_domains", "brands", "usd_call",
                                   "usd_call_no_cache_write", "cache_write_calls"]]
            .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if all(v is None for v in mix.values()):
        ctx.say("\n  Source-class mix: domain map not frozen; not reported.")
    else:
        ctx.say("\n  Source-class mix of cited domains (share of cited-domain occurrences):")
        ctx.say(pd.DataFrame(mix).T.to_string(float_format=lambda v: f"{v:.3f}"))
    return {"by_arm": by_arm, "by_arm_wave": by_wave, "source_mix": mix}


# ------------------------------------------------------------ robustness


def robustness(ctx: Ctx) -> None:
    ctx.say("\n## Robustness (spec §7; unadjusted 90% CIs, labelled)")
    df = ctx.df

    ctx.say("\nR1 top-10 brands instead of all brands (H1b gap):")
    for arm in API_ARMS:
        ctx.say(line_for(test_row(ctx, section="R1", test=f"R1 {arm}", metric="top10_j",
                                  coefs=gap_coefs(arm), arms=(arm, REFERENCE))))

    ctx.say("\nR2 RBO on brand order instead of set Jaccard: see 'RBO gap' above.")

    ctx.say("\nR3 answers with no search excluded (domain gaps, H1d):")
    r3 = df[df["n_searches"] > 0].reset_index(drop=True)
    r3_pairs = frame_pairs(r3)
    for metric in DOMAIN_METRICS:
        for arm in API_ARMS:
            ctx.say(line_for(test_row(ctx, section="R3", test=f"R3 {arm}", metric=metric,
                                      coefs=gap_coefs(arm), arms=(arm, REFERENCE),
                                      pairs=r3_pairs)))
    ctx.say("  H1d panel (descriptive), no-search answers excluded:")
    panel_descriptives(ctx, r3, section_prefix="R3 ", cols=(("cited_domains", "H1d"),),
                       comparisons=API_ARMS)

    ctx.say("\nR4 Haiku candidates mapped through the frozen lexicon instead of lexicon "
            "matching (H1b, H1s):")
    has = df["brands_haiku"].map(lambda v: v is not None)
    cov = has.groupby(df["wave"]).mean().to_dict()
    ctx.say(f"  candidate coverage by wave: { {int(k): round(v, 3) for k, v in cov.items()} }")
    ctx.r4_coverage = {int(k): float(v) for k, v in cov.items()}
    if not has.all():
        ctx.say("  R4 NOT RUN: the Haiku candidate cache does not cover every answer "
                "(run harness/lexicon_candidates.py --wave N for the missing waves).")
        ctx.rows.append({"section": "R4", "test": "R4", "status": "not run",
                         "coverage": ctx.r4_coverage})
    else:
        r4 = df.assign(brands=df["brands_haiku"]).reset_index(drop=True)
        r4_pairs = frame_pairs(r4)
        for arm in API_ARMS:
            ctx.say(line_for(test_row(ctx, section="R4", test=f"R4 {arm}", metric="brand_j",
                                      coefs=gap_coefs(arm), arms=(arm, REFERENCE),
                                      pairs=r4_pairs)))
        ctx.say("  H1s panel (descriptive) on the Haiku-candidate brands:")
        panel_descriptives(ctx, r4, section_prefix="R4 ", cols=(("brands", "H1s"),),
                           comparisons=API_ARMS)

    ctx.say("\nR5 drop one wave at a time (H1b, H1d):")
    for wave in sorted(df["wave"].unique()):
        sub = df[df["wave"] != wave].reset_index(drop=True)
        sub_pairs = frame_pairs(sub)
        for arm in API_ARMS:
            ctx.say(line_for(test_row(ctx, section="R5", test=f"R5 -w{int(wave)} {arm}",
                                      metric="brand_j", coefs=gap_coefs(arm),
                                      arms=(arm, REFERENCE), pairs=sub_pairs,
                                      extra={"dropped_wave": int(wave)})))
        ctx.say(f"  H1d panel (descriptive) without wave {int(wave)}:")
        panel_descriptives(ctx, sub, section_prefix=f"R5 -w{int(wave)} ",
                           cols=(("cited_domains", "H1d"),), comparisons=API_ARMS)

    ctx.say("\nR6 category-level cluster bootstrap (H1b; the H1s panel statistics already "
            "use the category-level bootstrap):")
    for arm in API_ARMS:
        ctx.say(line_for(test_row(ctx, section="R6", test=f"R6 {arm}", metric="brand_j",
                                  coefs=gap_coefs(arm), arms=(arm, REFERENCE),
                                  cluster_cols=("category", "category"))))

    ctx.say("\nR7 UI chats flagged in the collector notes excluded (H1b, cited-domain gap):")
    r7 = df[~((df["surface"] == "ui") & df["collector_notes"])].reset_index(drop=True)
    ctx.say(f"  {len(df) - len(r7)} UI answers excluded")
    r7_pairs = frame_pairs(r7)
    for metric in ("brand_j", "cited_j"):
        for arm in API_ARMS:
            ctx.say(line_for(test_row(ctx, section="R7", test=f"R7 {arm}", metric=metric,
                                      coefs=gap_coefs(arm), arms=(arm, REFERENCE),
                                      pairs=r7_pairs)))


# ------------------------------------------------------------ gate


def preregistration_gate(df: pd.DataFrame, n_boot: int) -> list[str]:
    """Reasons the real data may not be modeled yet (empty list = go)."""
    problems = []
    if int(df["synthetic"].max()) != 0:
        problems.append("the real feature frame contains synthetic rows")
    if n_boot != N_BOOT:
        problems.append(f"--n-boot {n_boot} != the pre-registered {N_BOOT}")
    if not AUDIT_D_SCORE.exists():
        problems.append("Audit D is not scored (02_audit.py --score-audit-d)")
    else:
        score = json.loads(AUDIT_D_SCORE.read_text())
        if not score.get("passes"):
            problems.append("Audit D did not pass (precision >= 0.95 and recall >= 0.90)")
        if not score.get("signed_by"):
            problems.append("Audit D is not signed (--signed-by)")
    if not DOMAIN_MAP_SHA256:
        problems.append("the domain map is not frozen (common.DOMAIN_MAP_SHA256 is unset)")
    elif not DOMAIN_MAP.exists() or sha256_file(DOMAIN_MAP) != DOMAIN_MAP_SHA256:
        problems.append("data/raw/domain_map_v1.csv is missing or does not match its hash")
    elif df["cited_classes"].map(lambda v: v is None).any():
        problems.append("features lack source classes; re-run 01_features.py after the freeze")
    return problems


# ------------------------------------------------------------ dry run


def dry_run_checks(ctx: Ctx, world: str, passed: bool, pla_ok: bool) -> list[tuple[str, bool, str]]:
    """Spec §8 step 3: the planted structure must come back out."""
    def find(section: str, test: str, metric: str) -> dict:
        return next(r for r in ctx.rows if r.get("section") == section and r.get("test") == test
                    and r.get("metric") == metric)

    checks = [("H_pos passes", passed, "")]
    for arm in ("sonnet5_plain", "sonnet5_leak_think"):
        r = find("H1b_primary", f"H1b {arm}", "brand_j")
        checks.append((f"H1b {arm} equivalent (planted)",
                       r["verdict"] in (Verdict.NULL.name, Verdict.NEGLIGIBLE.name),
                       f"{fmt_ci(r['estimate'], r['lo'], r['hi'])} {r['verdict']}"))
    r = find("H1b_primary", "H1b haiku45_leak", "brand_j")
    checks.append(("H1b haiku45_leak REAL (planted divergent)", r["verdict"] == Verdict.REAL.name,
                   f"{fmt_ci(r['estimate'], r['lo'], r['hi'])} {r['verdict']}"))
    for arm, want in (("sonnet5_plain", "equivalent"), ("haiku45_leak", "REAL")):
        r = find("domain_gap", f"gap {arm}", "cited_j")
        ok = (r["verdict"] in (Verdict.NULL.name, Verdict.NEGLIGIBLE.name) if want == "equivalent"
              else r["verdict"] == Verdict.REAL.name)
        checks.append((f"cited-domain gap {arm} {want}", ok,
                       f"{fmt_ci(r['estimate'], r['lo'], r['hi'])} {r['verdict']}"))
    panel = [r for r in ctx.rows if r.get("kind") == "descriptive"]
    inside = all(r["lo"] - 1e-12 <= r["estimate"] <= r["hi"] + 1e-12 for r in panel
                 if np.isfinite(r["estimate"]))
    checks.append(("every descriptive panel interval surrounds its estimate", inside,
                   f"{len(panel)} panel rows"))
    for section in ("H1s", "H1d"):
        for stat in ("panel_rbo", "panel_jaccard_third", "panel_jaccard_all"):
            def get(arm: str) -> dict:
                return find(section, f"{section} panel {arm}", stat)
            div = get("haiku45_leak")
            eq = [get(a) for a in ("sonnet5_plain", "sonnet5_leak_think")]
            ok = div["hi"] < min(r["lo"] for r in eq)
            checks.append((
                f"{section} {stat}: divergent arm clearly lower than equivalent arms", ok,
                f"haiku45_leak {div['estimate']:.3f} [{div['lo']:.3f}, {div['hi']:.3f}] vs "
                + ", ".join(f"{r['arms'][0]} {r['estimate']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]"
                            for r in eq)))
    return checks


def dry_run_info(ctx: Ctx, pla_ok: bool) -> list[str]:
    """Reported, not asserted: the spec's dry run asks only for the planted
    verdicts and the H_pos stop. The placebo halves the sample, so its CI is
    about twice as wide as H1b's and can be INCONCLUSIVE with no true effect."""
    out = [f"H_pla null or negligible for every primary arm: {pla_ok}"]
    for r in ctx.rows:
        if r.get("section") == "H_pla":
            out.append(f"  {r['test']}: {fmt_ci(r['estimate'], r['lo'], r['hi'])} {r['verdict']}")
    return out


# ------------------------------------------------------------------ main


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    ap.add_argument("--expect", choices=("planted",), default=None,
                    help="assert the planted dry-run structure (synthetic only)")
    ap.add_argument("--n-boot", type=int, default=N_BOOT,
                    help="bootstrap draws; values other than 2000 are for the synthetic dry run")
    a = ap.parse_args()

    df = load_features(synthetic=a.synthetic)
    if a.synthetic:
        if int(df["synthetic"].min()) != 1:
            raise SystemExit("the synthetic frame contains real rows; refusing")
    else:
        if a.expect:
            raise SystemExit("--expect is for synthetic worlds only")
        verify_lexicon()
        problems = preregistration_gate(df, a.n_boot)
        if problems:
            print("03_model refuses to run on the real data yet (pre-registration gate):")
            for p in problems:
                print(f"  - {p}")
            sys.exit(3)

    df = df[~df["ui_wrong_setting"].astype(bool)].reset_index(drop=True)
    ctx = Ctx(df, a.n_boot)
    tag = f" (SYNTHETIC/{a.synthetic})" if a.synthetic else ""
    ctx.say(f"# Experiment 009: model results{tag}")
    ctx.say(f"seed {SEED}, {a.n_boot} bootstrap draws, {1 - ALPHA:.0%} percentile CIs, SESOI "
            f"{SESOI} (Jaccard gaps), share reference line {SESOI_SHARE}; {len(df)} answers, "
            f"{df['item_id'].nunique()} prompts, {df['category'].nunique()} categories, waves "
            f"{sorted(int(w) for w in df['wave'].unique())}. Aggregates only.")
    ctx.say(f"Gap = mean(within:{REFERENCE}) - mean(cross:arm|{REFERENCE}); positive = the arm "
            "is further from the UI than the UI is from itself across days.")
    ctx.say("")
    ctx.say("Reading guide: the two questions and where they are answered")
    ctx.say("  (a) Same vendors in the same order? Per answer: the RBO gap on brand order "
            "(secondary test). Per category panel: panel RBO and Kendall tau (descriptive).")
    ctx.say("  (b) Same vendors regardless of order? Per answer: the H1b brand-set Jaccard gap "
            "(primary test). Per category panel: panel Jaccard (descriptive).")
    ctx.say("  Cited domains are answered the same way (cited-domain gap; H1d panel).")
    ctx.say("")
    ctx.say(f"No-search rates: { {k: round(v, 3) for k, v in ctx.no_search.items()} } "
            f"(> {NO_SEARCH_MAX:.0%} makes an arm's domain claims INCONCLUSIVE).\n")

    passed = h_pos(ctx)
    pla_ok, desc = False, {}
    if passed:
        gradient(ctx)
        pla_ok = h_pla(ctx)
        h1b(ctx)
        h1_ref(ctx)
        domain_and_rbo_gaps(ctx)
        panel_descriptives(ctx)
        deprecated_rmsd(ctx)
        h2(ctx)
        h3(ctx)
        fair_comparison(ctx)
        levels(ctx)
        desc = descriptives(ctx)
        robustness(ctx)

    out = results_dir(a.synthetic)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"seed": SEED, "n_boot": a.n_boot, "alpha": ALPHA, "sesoi": SESOI,
            "sesoi_share": SESOI_SHARE, "synthetic": a.synthetic, "h_pos_passed": passed,
            "h_pla_ok": pla_ok, "answers": len(df),
            "no_search_rate": ctx.no_search,
            "fallback_reference_triggered": getattr(ctx, "fallback", None),
            "r4_coverage": getattr(ctx, "r4_coverage", None)}
    (out / "model_results.json").write_text(json.dumps(
        jsonable({"meta": meta, "rows": ctx.rows, "descriptives": desc,
                  "deprecated_rmsd": {
                      "note": ("Noise-corrected RMSD of per-category shares (pipeline/shares.py), "
                               "replaced by the descriptive panel statistics under spec "
                               "deviation 9. Not reported in model_summary.txt."),
                      "rows": ctx.deprecated}}), indent=1) + "\n")
    summary = "\n".join(ctx.lines) + "\n"
    (out / "model_summary.txt").write_text(summary)
    print(summary)
    print(f"wrote {out / 'model_summary.txt'} and {out / 'model_results.json'}")

    if not passed:
        sys.exit(1)
    if a.expect:
        checks = dry_run_checks(ctx, a.expect, passed, pla_ok)
        print(f"\ndry-run check ({a.expect}):")
        for name, ok, detail in checks:
            print(f"  {'OK  ' if ok else 'FAIL'} {name}: {detail}")
        print("  info (not asserted):")
        for line in dry_run_info(ctx, pla_ok):
            print(f"    {line}")
        if not all(ok for _, ok, _ in checks):
            sys.exit(2)


if __name__ == "__main__":
    main()
