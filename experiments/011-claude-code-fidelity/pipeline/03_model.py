"""Stage 03: pre-registered tests (spec §4, §5, §7) -> results/model_report.md and
results/model_results.json.

Sequence (spec §7: positive control first, exit 1 if it fails):

  H_pos   same-prompt minus cross-category cross-arm brand Jaccard (all arms vs ui_default,
          pooled, same wave) at least 0.10 with the 90% CI excluding 0.
  H_pla   H1 gap on odd minus even prompts, TOST +/-0.10, each primary arm. Does not gate.
  H1      gap = mean(within:ui_default) - mean(cross:arm|ui_default), brand-set Jaccard. Holm over
          cc_stock_full and sched_kit: bootstrap TOST p = the larger one-sided tail probability
          at +/-0.10, ordered by p, each verdict from the CI at its Holm-adjusted level (95% for
          the first, 90% for the second). cc_none_search and opus55_plain are secondary.
  H2      gap(arm) - gap(opus55_plain), each Claude Code arm, TOST +/-0.10. The within term
          cancels, so the contrast is mean(cross:opus55_plain|ui) - mean(cross:arm|ui), paired
          within prompt because the bootstrap resamples prompts jointly.
  H3      sched_kit vs cc_stock_full: mean of the two within-arm floors minus their same-wave
          cross-arm overlap, TOST +/-0.10.
  RBO     gap on brand order, every arm (also R2).
  descriptive  cited-domain and evaluated-domain gaps, behavior, cost, run time, usage. No verdicts.
  R1-R7   robustness on the H1 gap, every arm, unadjusted 90% CIs.

Inference: prompt-level cluster bootstrap with the dyadic weights of
``aeo_research.overlap.cluster_boot`` (2,000 draws, 90% percentile CI, seed 20261103).
``boot_combo`` reproduces cluster_boot draw for draw and keeps the draws, so TOST tail
probabilities and Holm-level CIs come from the same draws, and it also handles linear
combinations of more than two condition means (H3, H_pla).

Real data is gated: this stage refuses to run unless the lexicon is frozen and matches, Audit D
has passed and been signed against that lexicon, and the full 2,000 draws are used. ``--n-boot``
is for the synthetic dry run only.

Usage (repo root):
  uv run python experiments/011-claude-code-fidelity/pipeline/03_model.py
  uv run python .../03_model.py --synthetic planted --expect planted
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass

import brands
import numpy as np
import pandas as pd
from common import (
    ALL_ARMS,
    ALPHA,
    ANCHOR,
    CLAUDE_CODE_ARMS,
    COMPARE_ARMS,
    EVALUATED_ARMS,
    H3_PAIR,
    H_POS_MIN,
    LOCAL_ARMS,
    N_BOOT,
    NO_SEARCH_MAX,
    PRIMARY_ARMS,
    RBO_P,
    REFERENCE,
    RESULTS,
    SCHEDULED,
    SECONDARY_ARMS,
    SEED,
    SESOI,
    SYNTH_ANSWER_MARK,
    SYNTH_QUERY_MARK,
    SYNTHETIC_WORLDS,
    TOP_K,
    USAGE_PLAN,
    WAVES,
    build_pairs,
    cross,
    features_path,
    item_number,
    load_features,
    md_table,
    results_dir,
    within,
)

from aeo_research.overlap import jaccard, rbo
from aeo_research.stats import Verdict

EQUIVALENT = (Verdict.NULL, Verdict.NEGLIGIBLE)
#: Spec §5 decision table.
CONCLUSION = {
    "NULL": "Practically equivalent: passes",
    "NEGLIGIBLE": "Detectable but negligible: passes",
    "REAL": "Real gap: report its size",
    "INCONCLUSIVE": "Inconclusive: do not claim a null",
}
METRIC_LABELS = {
    "brand_j": "brand-set Jaccard",
    "top10_j": "top-10 brand Jaccard",
    "brand_rbo": "brand-order RBO",
    "cited_j": "cited-domain Jaccard",
    "eval_j": "evaluated-domain Jaccard",
}


# ------------------------------------------------------------ pair metrics


def add_metrics(pairs: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    pairs = pairs.copy()
    i, j = pairs["i"].to_numpy(), pairs["j"].to_numpy()
    b, c, e = list(df["brands"]), list(df["cited_domains"]), list(df["evaluated_domains"])
    pairs["brand_j"] = [jaccard(set(b[x]), set(b[y])) for x, y in zip(i, j)]
    pairs["top10_j"] = [jaccard(set(b[x][:TOP_K]), set(b[y][:TOP_K])) for x, y in zip(i, j)]
    pairs["brand_rbo"] = [rbo(b[x], b[y], RBO_P) for x, y in zip(i, j)]
    pairs["cited_j"] = [jaccard(set(c[x]), set(c[y])) for x, y in zip(i, j)]
    pairs["eval_j"] = [jaccard(set(e[x]), set(e[y])) for x, y in zip(i, j)]
    return pairs


def frame_pairs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    return add_metrics(build_pairs(df), df)


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


def boot_combo(pairs: pd.DataFrame, value_col: str, coefs: dict[str, float], *, n_boot: int = N_BOOT,
               seed: int = SEED, cluster_cols: tuple[str, str] = ("cluster_i", "cluster_j")) -> Boot:
    """Cluster bootstrap of sum_k coef_k * mean(condition_k), draws kept.

    Same resampling as ``aeo_research.overlap.cluster_boot``: clusters are factorized over the
    usable pairs in row order, each draw is ``rng.integers(0, n_clusters, n_clusters)``, and a
    pair's weight is c_i * c_j between clusters and c_i within one.
    """
    sel = pairs.loc[pairs["condition"].isin(list(coefs))]
    work = pd.DataFrame({value_col: sel[value_col], "condition": sel["condition"],
                         "_ci": sel[cluster_cols[0]], "_cj": sel[cluster_cols[1]]})
    n_nan = int(work[value_col].isna().sum())
    work = work.dropna(subset=[value_col]).reset_index(drop=True)
    missing = [c for c in coefs if not (work["condition"] == c).any()]
    if work.empty or missing:
        return Boot(float("nan"), np.array([]), 0, len(work), n_nan)
    codes, clusters = pd.factorize(pd.concat([work["_ci"], work["_cj"]]))
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
    return Boot(float(observed), draws[~np.isnan(draws)], n_clusters, len(work), n_nan)


def verdict_of(lo: float, hi: float, sesoi: float = SESOI) -> Verdict:
    """The four-way TOST mapping (spec §5 decision table)."""
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
        rate = self.df.groupby("arm")["searched"].apply(lambda s: float((~s.astype(bool)).mean()))
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
    """Bootstrap one contrast and record it. ``sesoi=None`` means CI only, no verdict."""
    pairs = ctx.pairs if pairs is None else pairs
    boot = boot_combo(pairs, metric, coefs, n_boot=ctx.n_boot, seed=SEED, cluster_cols=cluster_cols)
    lo, hi = boot.ci(alpha)
    row = {
        "section": section, "test": test, "metric": metric, "arms": list(arms),
        "contrast": " ".join(f"{'+' if k > 0 else '-'}{abs(k):g}*{c}" for c, k in coefs.items()),
        "estimate": boot.estimate, "lo": lo, "hi": hi, "ci_level": 1 - alpha,
        "n_pairs": boot.n_pairs, "n_nan": boot.n_nan, "n_clusters": boot.n_clusters,
        "n_boot": int(boot.draws.size),
    }
    if sesoi is not None:
        row |= {"sesoi": sesoi, "p_tost": boot.tost_p(sesoi), "verdict": verdict_of(lo, hi, sesoi).name}
    if extra:
        row |= extra
    ctx.rows.append(row)
    if key:
        ctx.boots[key] = boot
    return row


def gap_coefs(arm: str, ref: str = REFERENCE) -> dict[str, float]:
    return {within(ref): 1.0, cross(arm, ref): -1.0}


def h2_coefs(arm: str) -> dict[str, float]:
    """gap(arm) - gap(anchor) = (W - C_arm) - (W - C_anchor) = C_anchor - C_arm."""
    return {cross(ANCHOR, REFERENCE): 1.0, cross(arm, REFERENCE): -1.0}


def h3_coefs(a: str, b: str) -> dict[str, float]:
    return {within(a): 0.5, within(b): 0.5, cross(a, b): -1.0}


def verdict_table(rows: list[dict]) -> str:
    """A markdown table of tests with verdicts and the spec's conclusion wording."""
    records = []
    for r in rows:
        records.append({
            "Test": r["test"], "Metric": METRIC_LABELS.get(r["metric"], r["metric"]),
            "Estimate [CI]": fmt_ci(r["estimate"], r["lo"], r["hi"]),
            "CI": f"{r['ci_level']:.0%}", "Verdict": r["verdict"],
            "Conclusion": CONCLUSION[r["verdict"]], "Pairs": r["n_pairs"], "NaN": r["n_nan"],
            "Note": r.get("note", ""),
        })
    return md_table(pd.DataFrame(records))


def ci_table(rows: list[dict]) -> str:
    """A markdown table of descriptive contrasts: estimate and CI, no verdict."""
    records = [{
        "Test": r["test"], "Metric": METRIC_LABELS.get(r["metric"], r["metric"]),
        "Estimate [CI]": fmt_ci(r["estimate"], r["lo"], r["hi"]), "CI": f"{r['ci_level']:.0%}",
        "Pairs": r["n_pairs"], "NaN": r["n_nan"], "Note": r.get("note", ""),
    } for r in rows]
    return md_table(pd.DataFrame(records))


# ------------------------------------------------------------ H_pos


def relation_pairs(df: pd.DataFrame, arms=COMPARE_ARMS, ref: str = REFERENCE) -> pd.DataFrame:
    """Arm x ui_default answer pairs in the same wave: same prompt, or a different category.

    Pairs from the same category and a different prompt are in neither term of H_pos.
    """
    out = []
    items, cats = df["item_id"].to_numpy(), df["category"].to_numpy()
    for wave in sorted(df["wave"].unique()):
        in_wave = (df["wave"] == wave).to_numpy()
        a_idx = np.flatnonzero(in_wave & df["arm"].isin(arms).to_numpy())
        u_idx = np.flatnonzero(in_wave & (df["arm"] == ref).to_numpy())
        for i in a_idx:
            for j in u_idx:
                if items[i] == items[j]:
                    out.append((i, j, "same_prompt", items[i], items[j]))
                elif cats[i] != cats[j]:
                    out.append((i, j, "other_category", items[i], items[j]))
    pairs = pd.DataFrame(out, columns=["i", "j", "condition", "cluster_i", "cluster_j"])
    b = list(df["brands"])
    pairs["brand_j"] = [jaccard(set(b[x]), set(b[y])) for x, y in zip(pairs["i"], pairs["j"])]
    return pairs


def h_pos_reason(row: dict) -> str | None:
    """Why H_pos failed, or None when it passed."""
    if math.isnan(row["estimate"]):
        return "no usable pairs"
    if row["estimate"] < H_POS_MIN:
        return f"estimate {row['estimate']:+.3f} is below {H_POS_MIN:.2f}"
    if not row["lo"] > 0:
        return f"the 90% CI [{row['lo']:+.3f}, {row['hi']:+.3f}] includes 0"
    return None


def h_pos(ctx: Ctx) -> bool:
    ctx.say("## H_pos (positive control; the study stops if it fails)\n")
    row = test_row(ctx, section="H_pos", test="H_pos", metric="brand_j",
                   coefs={"same_prompt": 1.0, "other_category": -1.0}, arms=ALL_ARMS,
                   pairs=relation_pairs(ctx.df), sesoi=None)
    reason = h_pos_reason(row)
    row["passed"] = reason is None
    row["reason"] = reason
    ctx.say(f"Same-prompt minus cross-category cross-arm brand Jaccard (all arms vs {REFERENCE}, "
            f"pooled, same wave) = {fmt_ci(row['estimate'], row['lo'], row['hi'])}; need at least "
            f"{H_POS_MIN:.2f} with the 90% CI excluding 0: "
            + ("**PASS**" if reason is None else
               f"**FAIL: STOP. {reason}. Extraction or the prompt join is broken.**"))
    ctx.say(f"\nPairs {row['n_pairs']}, NaN {row['n_nan']}, prompts {row['n_clusters']}.")
    return reason is None


# ------------------------------------------------------------ H_pla


def h_pla(ctx: Ctx) -> None:
    ctx.say("\n## H_pla (placebo): H1 gap on odd minus even prompts, TOST +/-0.10\n")
    ctx.say("Reported for each primary arm. It does not gate the analysis, because the split "
            "doubles the interval width. A REAL placebo gap is a caveat on that arm's H1.\n")
    parity = ctx.pairs["cluster_i"].map(lambda x: "odd" if item_number(x) % 2 else "even")
    split = ctx.pairs.assign(condition=ctx.pairs["condition"] + "@" + parity)
    rows = []
    for arm in PRIMARY_ARMS:
        w, c = within(REFERENCE), cross(arm, REFERENCE)
        coefs = {f"{w}@odd": 1.0, f"{c}@odd": -1.0, f"{w}@even": -1.0, f"{c}@even": 1.0}
        row = test_row(ctx, section="H_pla", test=f"H_pla {arm}", metric="brand_j", coefs=coefs,
                       arms=(arm, REFERENCE), pairs=split)
        if row["verdict"] == Verdict.REAL.name:
            row["note"] = f"CAVEAT on H1 {arm}: placebo gap is real"
        rows.append(row)
    ctx.say(verdict_table(rows))


# ------------------------------------------------------------ H1


def holm(ctx: Ctx, rows: list[dict], keys: list[str]) -> None:
    """Holm over a family: rank by bootstrap TOST p, CI at alpha / (m - rank + 1).

    Tied p values (two arms with no draw past the band) keep the spec's arm order.
    Also records the step-down Holm-adjusted p and flags any test whose CI verdict claims
    equivalence after a lower-ranked test did not (strict step-down would stop there).
    """
    m = len(rows)
    sort_p = [math.inf if math.isnan(r["p_tost"]) else r["p_tost"] for r in rows]
    order = sorted(range(m), key=lambda k: sort_p[k])
    running, blocked = 0.0, False
    for rank, k in enumerate(order, start=1):
        row, boot = rows[k], ctx.boots[keys[k]]
        alpha_k = ALPHA / (m - rank + 1)
        lo, hi = boot.ci(alpha_k)
        v = verdict_of(lo, hi, SESOI)
        if not math.isnan(row["p_tost"]):
            running = max(running, min(1.0, (m - rank + 1) * row["p_tost"]))
        lo90, hi90 = boot.ci(ALPHA)
        row |= {"holm_rank": rank, "holm_alpha": alpha_k, "ci_level": 1 - alpha_k, "lo": lo, "hi": hi,
                "verdict": v.name, "p_holm": running, "lo_unadjusted": lo90, "hi_unadjusted": hi90}
        equivalent = v in EQUIVALENT
        if equivalent and blocked:
            row["holm_stepdown_note"] = ("strict step-down would not claim equivalence: a "
                                         "lower-ranked test in the family did not")
        if not equivalent:
            blocked = True


def h1(ctx: Ctx) -> None:
    ctx.say(f"\n## H1 primary family (brand-set Jaccard gap = within:{REFERENCE} - "
            f"cross:arm|{REFERENCE}; TOST +/-0.10; Holm over {len(PRIMARY_ARMS)})\n")
    rows, keys = [], []
    for arm in PRIMARY_ARMS:
        key = f"H1:{arm}"
        rows.append(test_row(ctx, section="H1_primary", test=f"H1 {arm}", metric="brand_j",
                             coefs=gap_coefs(arm), arms=(arm, REFERENCE), key=key))
        keys.append(key)
    holm(ctx, rows, keys)
    for r in rows:
        r["note"] = (f"Holm rank {r['holm_rank']}, bootstrap TOST p {r['p_tost']:.4f}, "
                     f"Holm p {r['p_holm']:.4f}")
        if r.get("holm_stepdown_note"):
            r["note"] += f"; {r['holm_stepdown_note']}"
    ctx.say(verdict_table(sorted(rows, key=lambda r: r["holm_rank"])))

    ctx.say("\n## H1 secondary (no multiplicity correction)\n")
    ctx.say(verdict_table([
        test_row(ctx, section="H1_secondary", test=f"H1 {arm}", metric="brand_j",
                 coefs=gap_coefs(arm), arms=(arm, REFERENCE),
                 extra={"note": "replicates 009 (+0.067)" if arm == ANCHOR else "secondary"})
        for arm in SECONDARY_ARMS]))


# ------------------------------------------------------------ H2, H3, RBO


def h2_h3_rbo(ctx: Ctx) -> None:
    ctx.say(f"\n## H2 (secondary): gap(arm) - gap({ANCHOR}), TOST +/-0.10\n")
    ctx.say("Positive means the arm is further from claude.ai than the API is.\n")
    ctx.say(verdict_table([
        test_row(ctx, section="H2", test=f"H2 {arm}", metric="brand_j", coefs=h2_coefs(arm),
                 arms=(arm, ANCHOR, REFERENCE)) for arm in CLAUDE_CODE_ARMS]))

    a, b = H3_PAIR
    ctx.say(f"\n## H3 (secondary): {a} vs {b}, mean of the two within-arm floors minus their "
            "same-wave cross-arm overlap, TOST +/-0.10\n")
    ctx.say("This tests the kit as built against a local run. It does not separate the cloud "
            "surface from the subagent and its added instruction.\n")
    ctx.say(verdict_table([test_row(ctx, section="H3", test=f"H3 {a} vs {b}", metric="brand_j",
                                    coefs=h3_coefs(a, b), arms=(a, b))]))

    ctx.say("\n## RBO gap on brand order, every arm (secondary; also R2)\n")
    ctx.say(verdict_table([
        test_row(ctx, section="RBO", test=f"RBO {arm}", metric="brand_rbo", coefs=gap_coefs(arm),
                 arms=(arm, REFERENCE)) for arm in COMPARE_ARMS]))


def levels(ctx: Ctx) -> None:
    ctx.say("\n## Levels (same-prompt brand Jaccard; no test)\n")
    conditions = [(within(a), a) for a in (REFERENCE, *H3_PAIR)]
    conditions += [(cross(a, REFERENCE), a) for a in COMPARE_ARMS]
    conditions.append((cross(*H3_PAIR), H3_PAIR[0]))
    ctx.say(ci_table([test_row(ctx, section="level", test=f"level {c}", metric="brand_j",
                               coefs={c: 1.0}, arms=(a,), sesoi=None) for c, a in conditions]))


# ------------------------------------------------------------ descriptive


def domain_gaps(ctx: Ctx) -> None:
    ctx.say("\n## Domain gaps (descriptive; no verdicts)\n")
    ctx.say("Links in the answer for Claude Code, citation objects elsewhere, so a difference may "
            "be partly the measure. Evaluated domains are not observed on `sched_kit`. An arm over "
            f"the Audit A limit ({NO_SEARCH_MAX:.0%} no-search answers) has its domain claims "
            "INCONCLUSIVE whatever the interval.\n")
    rows = []
    for metric, arms in (("cited_j", COMPARE_ARMS),
                         ("eval_j", tuple(a for a in COMPARE_ARMS if a in EVALUATED_ARMS))):
        for arm in arms:
            hit = ctx.rule_hit(arm, REFERENCE)
            note = f"domain claims INCONCLUSIVE: no-search rate over limit for {', '.join(hit)}" if hit else ""
            rows.append(test_row(ctx, section="domain_gap", test=f"gap {arm}", metric=metric,
                                 coefs=gap_coefs(arm), arms=(arm, REFERENCE), sesoi=None,
                                 extra={"note": note}))
    ctx.say(ci_table(rows))


def num_mean(s: pd.Series) -> float:
    values = pd.to_numeric(s, errors="coerce")
    return float(values.mean()) if values.notna().any() else float("nan")


def describe(g: pd.DataFrame) -> dict:
    return {
        "answers": len(g),
        "searches": num_mean(g["n_searches"]),
        "no_search_rate": float((~g["searched"].astype(bool)).mean()),
        "fetches": num_mean(g["n_fetches"]),
        "backend_searches": num_mean(g["n_backend_searches"]),
        "subagent_tool_uses": num_mean(g["subagent_tool_uses"]),
        "evaluated_urls": num_mean(g["n_evaluated"]),
        "links": float(g["n_links"].mean()),
        "cited_domains": float(g["n_cited_domains"].mean()),
        "brands": float(g["n_brands"].mean()),
        "chars": float(g["chars"].mean()),
        "usd_estimate": num_mean(g["cost_usd"]),
        "seconds": num_mean(g["duration_ms"].fillna(g["subagent_ms"])) / 1000,
    }


def usage_rows(df: pd.DataFrame) -> list[dict]:
    """Window utilization change per arm x wave and pooled per plan, from ledger readings.

    Sorted by start time, the change runs from the first reading to the last. The reading rounds
    to 1% and other work on the account moves it. A five-hour window that resets inside a run
    shows up as a negative change, so the implied rate uses the seven-day window.
    """
    rows, pooled = [], {}
    for (arm, wave), g in df[df["arm"].isin(USAGE_PLAN)].groupby(["arm", "wave"], sort=False):
        g = g.dropna(subset=["five_hour_first", "seven_day_first"]).sort_values("started")
        if g.empty:
            continue
        n = len(g)
        five = float(g["five_hour_last"].iloc[-1] - g["five_hour_first"].iloc[0])
        seven = float(g["seven_day_last"].iloc[-1] - g["seven_day_first"].iloc[0])
        plan = USAGE_PLAN[arm]
        rows.append({"plan": plan, "arm": arm, "wave": int(wave), "answers": n, "five_hour_change": five,
                     "seven_day_change": seven, "five_hour_per_answer": five / n,
                     "seven_day_per_answer": seven / n, "prompts_per_day_implied": float("nan")})
        totals = pooled.setdefault(plan, [0, 0.0, 0.0])
        totals[0] += n
        totals[1] += five
        totals[2] += seven
    for plan, (n, five, seven) in pooled.items():
        rows.append({"plan": plan, "arm": "all local", "wave": "all", "answers": n, "five_hour_change": five,
                     "seven_day_change": seven, "five_hour_per_answer": five / n,
                     "seven_day_per_answer": seven / n,
                     "prompts_per_day_implied": n / (7 * seven) if seven > 0 else float("nan")})
    return rows


def descriptives(ctx: Ctx) -> dict:
    df = ctx.df
    arms = [a for a in ALL_ARMS if a in set(df["arm"])]
    by_arm = [{"arm": a, **describe(df[df["arm"] == a])} for a in arms]
    by_wave = [{"arm": a, "wave": int(w), **describe(df[(df["arm"] == a) & (df["wave"] == w)])}
               for a in arms for w in sorted(df["wave"].unique())]
    ctx.say("\n## Behavior per answer (descriptive; no test)\n")
    ctx.say("`n/a` means the surface does not report it. `sched_kit` has no search count (a "
            "subagent's searches are not in the pulled transcript); its no-search rate uses the "
            "record's `searched` flag. `usd_estimate` is Claude Code's client-side estimate or the "
            "API ledger's batch price, for comparison only. `seconds` is the run's duration or, on "
            "`sched_kit`, the subagent's.\n")
    ctx.say(md_table(pd.DataFrame(by_arm)))
    ctx.say("\nPer wave:\n")
    ctx.say(md_table(pd.DataFrame(by_wave)[["arm", "wave", "answers", "searches", "no_search_rate",
                                            "links", "brands", "chars", "usd_estimate", "seconds"]]))
    usage = usage_rows(df)
    ctx.say("\n## Usage on the plan (descriptive; ledger readings, local arms)\n")
    if usage:
        ctx.say("Change in window utilization as a fraction of the window. The value rounds to 1% "
                "and other work on the account moves it, so read these as rough. "
                "`prompts_per_day_implied` is answers / (7 x seven-day change), pooled over the "
                "study. `sched_kit` and claude.ai write no readings; Pro is measured separately "
                "(`harness/pro_usage_check.md`), in a ledger this pipeline does not read.\n")
        ctx.say(md_table(pd.DataFrame(usage), digits=4))
    else:
        ctx.say("No readings in the ledger.")
    return {"by_arm": by_arm, "by_arm_wave": by_wave, "usage": usage}


# ------------------------------------------------------------ robustness


def r4_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    """The frame with nothing censored, or None if the Haiku cache misses any answer."""
    if df["brands_all"].map(lambda v: v is None).any():
        return None
    return df.assign(brands=df["brands_all"]).reset_index(drop=True)


def robustness(ctx: Ctx) -> dict:
    ctx.say("\n## Robustness (spec §7; H1 gap, every arm, unadjusted 90% CIs)\n")
    df = ctx.df
    info: dict = {}

    def gaps(section: str, prefix: str, *, metric: str = "brand_j", pairs: pd.DataFrame | None = None,
             cluster_cols=("cluster_i", "cluster_j"), extra: dict | None = None) -> list[dict]:
        return [test_row(ctx, section=section, test=f"{prefix} {arm}", metric=metric,
                         coefs=gap_coefs(arm), arms=(arm, REFERENCE), pairs=pairs,
                         cluster_cols=cluster_cols, extra=extra) for arm in COMPARE_ARMS]

    ctx.say("### R1: top-10 brands instead of all brands\n")
    ctx.say(verdict_table(gaps("R1", "R1", metric="top10_j")))

    ctx.say("\n### R2: RBO on brand order\n")
    r2 = [{**r, "section": "R2", "test": f"R2 {r['arms'][0]}"} for r in ctx.rows
          if r["section"] == "RBO"]
    ctx.rows += r2
    ctx.say(verdict_table(r2))

    ctx.say("\n### R3: drop one wave at a time\n")
    rows = []
    for wave in sorted(df["wave"].unique()):
        sub_pairs = frame_pairs(df[df["wave"] != wave].reset_index(drop=True))
        rows += gaps("R3", f"R3 -w{int(wave)}", pairs=sub_pairs, extra={"dropped_wave": int(wave)})
    ctx.say(verdict_table(rows))

    ctx.say("\n### R4: nothing censored (unplaced Haiku names added on both sides)\n")
    has = df["brands_all"].map(lambda v: v is not None)
    info["r4_coverage"] = {int(k): float(v) for k, v in has.groupby(df["wave"]).mean().items()}
    ctx.say(f"Candidate coverage by wave: {info['r4_coverage']}.\n")
    r4 = r4_frame(df)
    if r4 is None:
        ctx.say("R4 NOT RUN: the Haiku candidate cache does not cover every answer "
                "(`harness/lexicon_candidates.py --wave N`).")
        ctx.rows.append({"section": "R4", "test": "R4", "status": "not run"})
    else:
        ctx.say(verdict_table(gaps("R4", "R4", pairs=frame_pairs(r4))))

    ctx.say("\n### R5: category-level cluster bootstrap\n")
    ctx.say(verdict_table(gaps("R5", "R5", cluster_cols=("category", "category"))))

    ctx.say("\n### R6: claude.ai chats flagged in collector notes excluded\n")
    r6 = df[~((df["arm"] == REFERENCE) & df["collector_notes"].astype(bool))].reset_index(drop=True)
    info["r6_excluded"] = len(df) - len(r6)
    ctx.say(f"{info['r6_excluded']} claude.ai answers excluded.\n")
    ctx.say(verdict_table(gaps("R6", "R6", pairs=frame_pairs(r6))))

    ctx.say("\n### R7: answers with no search excluded (ui_default included)\n")
    r7 = df[df["searched"].astype(bool)].reset_index(drop=True)
    info["r7_excluded"] = df[~df["searched"].astype(bool)].groupby("arm").size().to_dict()
    ctx.say(f"Answers excluded per arm: {info['r7_excluded']}.\n")
    ctx.say(verdict_table(gaps("R7", "R7", pairs=frame_pairs(r7))))
    return info


# ------------------------------------------------------------ gate


def preregistration_gate(df: pd.DataFrame, n_boot: int, *, score_path=None,
                         lexicon_sha256: str | None = brands.LEXICON_SHA256) -> list[str]:
    """Reasons the real data may not be modeled yet (empty list = go)."""
    score_path = score_path or (RESULTS / "audit_d_score.json")
    problems = []
    if int(df["synthetic"].max()) != 0:
        problems.append("the real feature frame contains synthetic rows")
    if n_boot != N_BOOT:
        problems.append(f"--n-boot {n_boot} != the pre-registered {N_BOOT}")
    if not score_path.exists():
        problems.append("Audit D is not scored (02_audit.py --score-audit-d)")
    else:
        score = json.loads(score_path.read_text())
        if not score.get("passes"):
            problems.append("Audit D did not pass (precision >= 0.95 and recall >= 0.90)")
        if not score.get("signed_by"):
            problems.append("Audit D is not signed (--signed-by)")
        if score.get("lexicon_sha256") != lexicon_sha256:
            problems.append("Audit D was scored against a different lexicon; re-check it")
    return problems


# ------------------------------------------------------------ dry run


def dry_run_checks(ctx: Ctx, world: str, passed: bool, frame: pd.DataFrame) -> list[tuple[str, bool, str]]:
    """Spec §8 step 3: the planted structure must come back out."""

    def find(section: str, test: str, metric: str = "brand_j") -> dict:
        return next(r for r in ctx.rows if r.get("section") == section and r.get("test") == test
                    and r.get("metric") == metric)

    def show(r: dict) -> str:
        return f"{fmt_ci(r['estimate'], r['lo'], r['hi'])} at {r['ci_level']:.0%}: {r['verdict']}"

    def eq(r: dict) -> bool:
        return r["verdict"] in (Verdict.NULL.name, Verdict.NEGLIGIBLE.name)

    def real(r: dict) -> bool:
        return r["verdict"] == Verdict.REAL.name

    checks: list[tuple[str, bool, str]] = [("H_pos passes", passed, "")]
    want = {"cc_stock_full": eq, "opus55_plain": eq}
    both_pass = world == "planted_equiv"
    want[SCHEDULED] = eq if both_pass else real
    for arm, ok in want.items():
        section = "H1_primary" if arm in PRIMARY_ARMS else "H1_secondary"
        r = find(section, f"H1 {arm}")
        checks.append((f"H1 {arm} {'equivalent' if ok is eq else 'REAL'}", ok(r), show(r)))

    primary = sorted((find("H1_primary", f"H1 {a}") for a in PRIMARY_ARMS), key=lambda r: r["holm_rank"])
    checks.append(("Holm levels are 95% for rank 1, 90% for rank 2",
                   [round(r["ci_level"], 4) for r in primary] == [0.95, 0.90],
                   ", ".join(f"{r['test']} rank {r['holm_rank']} at {r['ci_level']:.0%}" for r in primary)))
    checks.append(("Holm order follows the bootstrap TOST p", primary[0]["p_tost"] <= primary[1]["p_tost"],
                   f"{primary[0]['p_tost']:.4f} <= {primary[1]['p_tost']:.4f}"))
    first = primary[0]
    checks.append(("rank 1 CI is at least as wide as its unadjusted 90% CI",
                   first["lo"] <= first["lo_unadjusted"] and first["hi"] >= first["hi_unadjusted"],
                   f"[{first['lo']:+.3f}, {first['hi']:+.3f}] vs "
                   f"[{first['lo_unadjusted']:+.3f}, {first['hi_unadjusted']:+.3f}]"))
    second = primary[1]
    checks.append(("rank 2 CI equals its unadjusted 90% CI",
                   (second["lo"], second["hi"]) == (second["lo_unadjusted"], second["hi_unadjusted"]), ""))
    if not both_pass:
        checks.append(("the passing arm ranks first", primary[0]["test"] == "H1 cc_stock_full",
                       primary[0]["test"]))

    r = find("H2", "H2 cc_stock_full")
    checks.append(("H2 cc_stock_full equivalent", eq(r), show(r)))
    r = find("H2", f"H2 {SCHEDULED}")
    checks.append((f"H2 {SCHEDULED} {'equivalent' if both_pass else 'REAL'}",
                   eq(r) if both_pass else real(r), show(r)))
    a, b = H3_PAIR
    r = find("H3", f"H3 {a} vs {b}")
    checks.append((f"H3 {'equivalent' if both_pass else 'REAL'}", eq(r) if both_pass else real(r), show(r)))

    # The Audit A rule, read from the arm's own search fields.
    checks.append(("cc_none_search is over the no-search limit", ctx.no_search["cc_none_search"] > NO_SEARCH_MAX,
                   f"{ctx.no_search['cc_none_search']:.3f}"))
    n_flagged = int((~ctx.df.loc[ctx.df["arm"] == SCHEDULED, "searched"].astype(bool)).sum())
    checks.append(("sched_kit no-search count comes from its searched flag and missing joins",
                   n_flagged == 3, f"{n_flagged} of 120 ({ctx.no_search[SCHEDULED]:.3f})"))
    noted = find("domain_gap", "gap cc_none_search", "cited_j")
    checks.append(("domain gaps have no verdict, and the rule is noted",
                   "verdict" not in noted and "INCONCLUSIVE" in noted.get("note", ""), noted.get("note", "")))
    checks.append(("sched_kit has no evaluated-domain gap",
                   not any(x.get("test") == f"gap {SCHEDULED}" and x.get("metric") == "eval_j"
                           for x in ctx.rows), ""))
    # Bookkeeping planted in 01_features: one failed audit, one retry, one uncollected task.
    n_all, n_counted = len(frame), len(ctx.df)
    checks.append(("a run that failed the audit does not count", n_all - n_counted == 1,
                   f"{n_all} answers on disk, {n_counted} counted"))
    checks.append(("an uncollected API task leaves 599 answers on disk", n_all == 599, str(n_all)))
    for section in ("R1", "R2", "R3", "R4", "R5", "R6", "R7"):
        got = {r["arms"][0] for r in ctx.rows if r.get("section") == section and "arms" in r}
        checks.append((f"{section} ran for every arm", got == set(COMPARE_ARMS), f"{len(got)} arms"))
    return checks


def leak_check(paths: list) -> list[str]:
    """Paths holding a fake answer or query marker."""
    bad = []
    for path in paths:
        text = path.read_text()
        if SYNTH_ANSWER_MARK in text or SYNTH_QUERY_MARK in text:
            bad.append(str(path))
    return bad


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
    ap.add_argument("--expect", choices=("planted", "planted_equiv"), default=None,
                    help="assert the planted dry-run structure (synthetic only)")
    ap.add_argument("--n-boot", type=int, default=N_BOOT,
                    help="bootstrap draws; values other than 2000 are for the synthetic dry run")
    a = ap.parse_args()

    if a.expect and a.expect != a.synthetic:
        raise SystemExit("--expect must name the --synthetic world being run")
    if not a.synthetic:
        brands.verify_lexicon()
    frame = load_features(synthetic=a.synthetic)
    if a.synthetic:
        if int(frame["synthetic"].min()) != 1:
            raise SystemExit("the synthetic frame contains real rows; refusing")
    else:
        problems = preregistration_gate(frame, a.n_boot)
        if problems:
            print("03_model refuses to run on the real data yet (pre-registration gate):")
            for p in problems:
                print(f"  - {p}")
            sys.exit(3)

    df = frame[frame["run_ok"].astype(bool)].reset_index(drop=True)
    ctx = Ctx(df, a.n_boot)
    tag = f" (SYNTHETIC/{a.synthetic})" if a.synthetic else ""
    ctx.say(f"# Experiment 011: model results{tag}\n")
    ctx.say(f"Seed {SEED}, {a.n_boot} bootstrap draws, {1 - ALPHA:.0%} percentile CIs unless a row "
            f"says otherwise, SESOI {SESOI} (Jaccard gaps). {len(df)} answers counted of "
            f"{len(frame)} on disk, {df['item_id'].nunique()} prompts, {df['category'].nunique()} "
            f"categories, waves {sorted(int(w) for w in df['wave'].unique())}. Aggregates only: no "
            "answer text and no search query text.\n")
    ctx.say(f"Gap = mean(within:{REFERENCE}) - mean(cross:arm|{REFERENCE}). Positive means the arm "
            "is further from claude.ai than claude.ai is from itself across days.\n")
    expected = df["item_id"].nunique()
    short = [f"{arm} w{w}: {n}/{expected}" for arm in ALL_ARMS for w in WAVES
             if (n := int(((df["arm"] == arm) & (df["wave"] == w)).sum())) != expected]
    ctx.say("Answers per arm x wave: " + ("all complete.\n" if not short else "; ".join(short) + ".\n"))
    ctx.say(f"No-search rates: { {k: round(v, 3) for k, v in ctx.no_search.items()} }. "
            f"Local arms: {list(LOCAL_ARMS)}.\n")

    passed = h_pos(ctx)
    desc, info = {}, {}
    if passed:
        h_pla(ctx)
        h1(ctx)
        h2_h3_rbo(ctx)
        levels(ctx)
        domain_gaps(ctx)
        desc = descriptives(ctx)
        info = robustness(ctx)

    out = results_dir(a.synthetic)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"seed": SEED, "n_boot": a.n_boot, "alpha": ALPHA, "sesoi": SESOI, "synthetic": a.synthetic,
            "h_pos_passed": passed, "answers_counted": len(df), "answers_on_disk": len(frame),
            "no_search_rate": ctx.no_search, **info}
    results_json = out / "model_results.json"
    results_json.write_text(json.dumps(jsonable({"meta": meta, "rows": ctx.rows, "descriptives": desc}),
                                       indent=1) + "\n")
    report = out / "model_report.md"
    report.write_text("\n".join(ctx.lines) + "\n")
    print("\n".join(ctx.lines))
    print(f"\nwrote {report} and {results_json}")

    if not passed:
        h_pos_row = next(r for r in ctx.rows if r["section"] == "H_pos")
        print(f"\nH_pos FAILED: {h_pos_row['reason']}. Stopping; nothing else was computed.")
        sys.exit(1)
    if a.expect:
        checks = dry_run_checks(ctx, a.expect, passed, frame)
        scanned = [report, results_json, features_path(a.synthetic), out / "audit_report.md"]
        leaks = leak_check([p for p in scanned if p.exists()])
        checks.append(("no answer or query text in the frame or reports", not leaks, ", ".join(leaks)))
        named = [p.name for p in (report, out / "audit_report.md") if p.exists() and "Zq" in p.read_text()]
        checks.append(("the reports name no brand", not named, ", ".join(named)))
        print(f"\ndry-run check ({a.expect}):")
        for name, ok, detail in checks:
            print(f"  {'OK  ' if ok else 'FAIL'} {name}: {detail}")
        print("  info (not asserted):")
        for r in ctx.rows:
            if r.get("section") == "H_pla" or r.get("test") == "H1 cc_none_search":
                print(f"    {r['test']}: {fmt_ci(r['estimate'], r['lo'], r['hi'])} {r['verdict']}")
        if not all(ok for _, ok, _ in checks):
            sys.exit(2)


if __name__ == "__main__":
    main()
