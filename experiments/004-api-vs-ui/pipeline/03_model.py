"""Stage 03: pre-registered tests (spec §4, §5, §7) -> results/model_report.md and
results/model_results.json. Aggregates only.

Per platform, ``ref`` is the UI arm (``cg_ui``, ``gm_ui``). Pairs never cross platforms.

  H_pos   first, per platform: same-prompt cross-arm brand Jaccard (the platform's API arms
          against its UI, pooled, same wave) minus cross-category cross-arm brand Jaccard, at
          least 0.10 with the 90% CI excluding 0. If either platform fails, the stage writes
          the H_pos section only and exits 1.
  H_pla   H1 gap on odd minus even prompts, TOST +/-0.10, each primary arm. Does not gate.
  H1      gap = mean(within:ref) - mean(cross:arm|ref), brand-set Jaccard, TOST +/-0.10.
          ChatGPT: cg_api_low and cg_api_plain, Holm over 2: bootstrap TOST p = the larger of
          the two one-sided tail probabilities at +/-0.10, ordered by p, each verdict from the
          CI at its Holm-adjusted level (95% for the first, 90% for the second). Gemini:
          gm_api_plain, one test, 90% CI.
  H2      cg_api_low vs cg_api_plain: mean of the two within-arm floors minus their same-wave
          cross-arm overlap, TOST +/-0.10 (secondary, unadjusted).
  RBO     the gap on brand order, every API arm (secondary; also R2).
  levels, cited- and evaluated-domain gaps, behavior, models and cost: descriptive.
  R1-R10  robustness on the H1 gap, every API arm, unadjusted 90% CIs (spec §7).

Inference: 011's ``boot_combo`` (draw-for-draw the resampling of
``aeo_research.overlap.cluster_boot``, prompt-level clusters, draws kept), 2,000 draws,
seed 20261106, and 011's ``holm`` and ``verdict_of``, all loaded from 011's frozen code
(``common.m011``).

Real data is gated: the stage refuses to run unless the frame was built with the pinned
study lexicon, Audit D has passed and been signed against it, and the full 2,000 draws are
used. ``--n-boot`` is for the synthetic dry run only. ``--pilot`` is the gap reproduction
check (spec §8 item 2): it computes only the H1 gaps on the pilot frame, with the pilot's
seed, and compares them with ``results/pilot_report.md``.

Usage (repo root):
  uv run python experiments/004-api-vs-ui/pipeline/03_model.py
  uv run python .../03_model.py --synthetic planted --expect planted
  uv run python .../03_model.py --pilot
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

import common
import pandas as pd
from common import (
    ALPHA,
    API_ARMS,
    H2_PAIR,
    N_BOOT,
    NO_SEARCH_MAX,
    PLATFORMS,
    SEED,
    SESOI,
    SYNTH_ANSWER_MARK,
    SYNTH_BRAND_PREFIX,
    SYNTH_QUERY_MARK,
    Mode,
    m011,
    md_table,
)

from aeo_research.stats import Verdict

within, cross = m011.within, m011.cross
EQUIVALENT = (Verdict.NULL.name, Verdict.NEGLIGIBLE.name)
METRIC_LABELS = m011.METRIC_LABELS


# ------------------------------------------------------------ pairs and rows


def frame_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """011's same-prompt pairs (within:<arm>, cross:<a>|<b>) with every pair metric."""
    df = df.reset_index(drop=True)
    return m011.add_metrics(m011.build_pairs(df), df)


class Ctx:
    """The frame, its per-platform pairs, settings, and the output buffers."""

    def __init__(self, df: pd.DataFrame, n_boot: int, seed: int = SEED):
        self.df = df.reset_index(drop=True)
        self.n_boot = n_boot
        self.seed = seed
        self.rows: list[dict] = []
        self.lines: list[str] = []
        self.boots: dict[str, m011.Boot] = {}
        self.sub = {p: self.df[self.df["platform"] == p].reset_index(drop=True) for p in PLATFORMS}
        self.pairs = {p: frame_pairs(d) for p, d in self.sub.items()}
        self.no_search = self.df.groupby("arm")["searched"].apply(
            lambda s: float((~s.astype(bool)).mean())).to_dict()

    def say(self, line: str = "") -> None:
        self.lines.append(line)

    def rule_hit(self, *arms: str) -> list[str]:
        return [a for a in arms if self.no_search.get(a, 0.0) > NO_SEARCH_MAX]


def test_row(ctx: Ctx, *, section: str, test: str, metric: str, coefs: dict[str, float],
             arms: tuple[str, ...], pairs: pd.DataFrame, sesoi: float | None = SESOI,
             alpha: float = ALPHA, cluster_cols=("cluster_i", "cluster_j"),
             key: str | None = None, extra: dict | None = None) -> dict:
    """Bootstrap one contrast and record it (011's ``test_row`` with 004's seed)."""
    boot = m011.boot_combo(pairs, metric, coefs, n_boot=ctx.n_boot, seed=ctx.seed,
                           cluster_cols=cluster_cols)
    lo, hi = boot.ci(alpha)
    row = {"section": section, "test": test, "metric": metric, "arms": list(arms),
           "platform": common.platform_of(arms[0]),
           "contrast": " ".join(f"{'+' if k > 0 else '-'}{abs(k):g}*{c}" for c, k in coefs.items()),
           "estimate": boot.estimate, "lo": lo, "hi": hi, "ci_level": 1 - alpha,
           "n_pairs": boot.n_pairs, "n_nan": boot.n_nan, "n_clusters": boot.n_clusters,
           "n_boot": int(boot.draws.size)}
    if sesoi is not None:
        row |= {"sesoi": sesoi, "p_tost": boot.tost_p(sesoi),
                "verdict": m011.verdict_of(lo, hi, sesoi).name}
    if extra:
        row |= extra
    ctx.rows.append(row)
    if key:
        ctx.boots[key] = boot
    return row


def gap_coefs(arm: str) -> dict[str, float]:
    return m011.gap_coefs(arm, PLATFORMS[common.platform_of(arm)].ref)


def gap_row(ctx: Ctx, arm: str, section: str, prefix: str, *, metric: str = "brand_j",
            pairs: pd.DataFrame | None = None, alpha: float = ALPHA, sesoi: float | None = SESOI,
            cluster_cols=("cluster_i", "cluster_j"), key: str | None = None,
            extra: dict | None = None) -> dict:
    """The gap of one API arm to its UI: mean(within:ref) - mean(cross:arm|ref)."""
    p = common.platform_of(arm)
    return test_row(ctx, section=section, test=f"{prefix} {arm}", metric=metric,
                    coefs=gap_coefs(arm), arms=(arm, PLATFORMS[p].ref),
                    pairs=ctx.pairs[p] if pairs is None else pairs, sesoi=sesoi, alpha=alpha,
                    cluster_cols=cluster_cols, key=key, extra=extra)


def verdict_table(rows: list[dict]) -> str:
    return m011.verdict_table(rows)


def ci_table(rows: list[dict]) -> str:
    return m011.ci_table(rows)


# ------------------------------------------------------------ H_pos


def h_pos(ctx: Ctx) -> bool:
    ctx.say("## H_pos (positive control, per platform; the study stops if it fails)\n")
    ok = True
    for p, spec in PLATFORMS.items():
        rel = m011.relation_pairs(ctx.sub[p], arms=spec.primary, ref=spec.ref)
        row = test_row(ctx, section="H_pos", test=f"H_pos {spec.label}", metric="brand_j",
                       coefs={"same_prompt": 1.0, "other_category": -1.0},
                       arms=(*spec.primary, spec.ref), pairs=rel, sesoi=None)
        reason = m011.h_pos_reason(row)
        row["passed"], row["reason"] = reason is None, reason
        ok &= reason is None
        ctx.say(f"- {spec.label}: same-prompt minus cross-category cross-arm brand Jaccard "
                f"({', '.join(spec.primary)} vs {spec.ref}, pooled, same wave) = "
                f"{m011.fmt_ci(row['estimate'], row['lo'], row['hi'])}; need at least "
                f"{common.H_POS_MIN:.2f} with the 90% CI excluding 0: "
                + ("**PASS**" if reason is None else
                   f"**FAIL: STOP. {reason}. Extraction or the prompt join is broken.**")
                + f" Pairs {row['n_pairs']}, NaN {row['n_nan']}, prompts {row['n_clusters']}.")
    return ok


# ------------------------------------------------------------ H_pla


def h_pla(ctx: Ctx) -> None:
    ctx.say("\n## H_pla (placebo): H1 gap on odd minus even prompts, TOST +/-0.10\n")
    ctx.say("Reported for each primary arm. It does not gate the analysis, because the split "
            "doubles the interval width. A REAL placebo gap is a caveat on that arm's H1.\n")
    rows = []
    for p, spec in PLATFORMS.items():
        pairs = ctx.pairs[p]
        parity = pairs["cluster_i"].map(lambda x: "odd" if common.item_number(x) % 2 else "even")
        split = pairs.assign(condition=pairs["condition"] + "@" + parity)
        for arm in spec.primary:
            w, c = within(spec.ref), cross(arm, spec.ref)
            coefs = {f"{w}@odd": 1.0, f"{c}@odd": -1.0, f"{w}@even": -1.0, f"{c}@even": 1.0}
            row = test_row(ctx, section="H_pla", test=f"H_pla {arm}", metric="brand_j",
                           coefs=coefs, arms=(arm, spec.ref), pairs=split)
            if row["verdict"] == Verdict.REAL.name:
                row["note"] = f"CAVEAT on H1 {arm}: the placebo gap is real"
            rows.append(row)
    ctx.say(verdict_table(rows))


# ------------------------------------------------------------ H1


def h1(ctx: Ctx) -> None:
    for p, spec in PLATFORMS.items():
        holm = len(spec.primary) > 1
        ctx.say(f"\n## H1 {spec.label} (brand-set Jaccard gap = within:{spec.ref} - "
                f"cross:arm|{spec.ref}; TOST +/-0.10; "
                + (f"Holm over {len(spec.primary)})\n" if holm else "one test, 90% CI)\n"))
        rows, keys = [], []
        for arm in spec.primary:
            key = f"H1:{arm}"
            rows.append(gap_row(ctx, arm, "H1", "H1", key=key))
            keys.append(key)
        if holm:
            m011.holm(ctx, rows, keys)
            for r in rows:
                r["note"] = (f"Holm rank {r['holm_rank']}, bootstrap TOST p {r['p_tost']:.4f}, "
                             f"Holm p {r['p_holm']:.4f}")
                if r.get("holm_stepdown_note"):
                    r["note"] += f"; {r['holm_stepdown_note']}"
            rows = sorted(rows, key=lambda r: r["holm_rank"])
        else:
            for r in rows:
                r["note"] = f"bootstrap TOST p {r['p_tost']:.4f}"
        ctx.say(verdict_table(rows))


def h2_rbo_levels(ctx: Ctx) -> None:
    a, b = H2_PAIR
    ctx.say(f"\n## H2 (secondary): {a} vs {b}, mean of the two within-arm floors minus their "
            "same-wave cross-arm overlap, TOST +/-0.10\n")
    ctx.say("This tests whether turning reasoning off changes the brands. No multiplicity "
            "correction.\n")
    ctx.say(verdict_table([test_row(ctx, section="H2", test=f"H2 {a} vs {b}", metric="brand_j",
                                    coefs=m011.h3_coefs(a, b), arms=(a, b),
                                    pairs=ctx.pairs["chatgpt"])]))
    ctx.say("\n## RBO gap on brand order, every API arm (secondary; also R2)\n")
    ctx.say(verdict_table([gap_row(ctx, arm, "RBO", "RBO", metric="brand_rbo") for arm in API_ARMS]))
    ctx.say("\n## Levels (same-prompt brand Jaccard; no test)\n")
    rows = []
    for p, spec in PLATFORMS.items():
        conds = [(within(spec.ref), spec.ref)] + [(within(x), x) for x in spec.primary]
        conds += [(cross(x, spec.ref), x) for x in spec.primary]
        if p == "chatgpt":
            conds.append((cross(*H2_PAIR), H2_PAIR[0]))
        rows += [test_row(ctx, section="level", test=f"level {c}", metric="brand_j", coefs={c: 1.0},
                          arms=(arm,), pairs=ctx.pairs[p], sesoi=None) for c, arm in conds]
    ctx.say(ci_table(rows))
    ctx.say("\nFor reading alongside (no pooled estimate, no test across studies): 009's "
            "published gap for Opus 5.5 through the API against claude.ai was +0.067.")


# ------------------------------------------------------------ descriptive


def domain_gaps(ctx: Ctx) -> None:
    ctx.say("\n## Domain gaps (descriptive; no verdicts)\n")
    ctx.say("Cited: DataForSEO `sources` (UI), `url_citation` annotations (OpenAI), grounding "
            "chunks a support cites (Gemini API, domain from the chunk title). Evaluated: "
            "DataForSEO `search_results` (ChatGPT UI; `sources` for the Gemini app), "
            "`web_search_call` sources (OpenAI), every grounding chunk (Gemini API). The "
            "instruments expose different fields, so these gaps are partly the measure. An arm "
            f"over the Audit A limit ({NO_SEARCH_MAX:.0%} no-search answers) has its domain "
            "results INCONCLUSIVE whatever the interval.\n")
    rows = []
    for metric in ("cited_j", "eval_j"):
        for arm in API_ARMS:
            hit = ctx.rule_hit(arm, PLATFORMS[common.platform_of(arm)].ref)
            note = f"INCONCLUSIVE: no-search rate over the limit for {', '.join(hit)}" if hit else ""
            rows.append(gap_row(ctx, arm, "domain_gap", "gap", metric=metric, sesoi=None,
                                extra={"note": note}))
    ctx.say(ci_table(rows))


def describe(g: pd.DataFrame) -> dict:
    n = len(g)
    cost = common.num_mean(g["cost_usd"])
    return {"answers": n, "searched": float(g["searched"].astype(bool).mean()) if n else float("nan"),
            "no_search_rate": float((~g["searched"].astype(bool)).mean()) if n else float("nan"),
            "search_calls": common.num_mean(g["n_search_calls"]),
            "queries": common.num_mean(g["n_queries"]),
            "cited_urls": float(g["n_cited"].mean()), "evaluated_urls": float(g["n_evaluated"].mean()),
            "cited_domains": float(g["n_cited_domains"].mean()), "brands": float(g["n_brands"].mean()),
            "chars": float(g["chars"].mean()), "usd_per_answer": cost, "usd_per_1000": cost * 1000}


def descriptives(ctx: Ctx) -> dict:
    df = ctx.df
    arms = [a for a in common.ALL_ARMS if a in set(df["arm"])]
    by_arm = [{"arm": a, **describe(df[df["arm"] == a])} for a in arms]
    by_wave = [{"arm": a, "wave": int(w), **describe(df[(df["arm"] == a) & (df["wave"] == w)])}
               for a in arms for w in sorted(df["wave"].unique())]
    ctx.say("\n## Behavior per answer (descriptive; no test)\n")
    ctx.say("`n/a` means the instrument does not report it: search calls are OpenAI "
            "`web_search_call` items; queries are DataForSEO fan-out queries (ChatGPT UI), "
            "OpenAI search-action queries and Gemini `webSearchQueries`; the Gemini app reports "
            "no queries, so \"searched\" there means sources were reported. Costs are estimates "
            f"at list prices checked {common.exp004.PRICES_CHECKED} (UI: DataForSEO task cost, "
            "resubmissions included).\n")
    ctx.say(md_table(pd.DataFrame(by_arm)))
    ctx.say("\nPer wave:\n")
    ctx.say(md_table(pd.DataFrame(by_wave)[["arm", "wave", "answers", "no_search_rate", "search_calls",
                                            "queries", "cited_urls", "brands", "chars",
                                            "usd_per_answer"]]))
    models = {a: dict(Counter(df.loc[df["arm"] == a, "model"].fillna("(none)"))) for a in arms}
    ctx.say("\nModels reported, per arm: "
            + "; ".join(f"`{a}` " + ", ".join(f"`{m}` {n}" for m, n in sorted(c.items()))
                        for a, c in models.items()) + ".")
    return {"by_arm": by_arm, "by_arm_wave": by_wave, "models": models}


# ------------------------------------------------------------ robustness


def robustness(ctx: Ctx) -> dict:
    ctx.say("\n## Robustness (spec §7; H1 gap, every API arm, unadjusted 90% CIs)\n")
    df = ctx.df
    info: dict = {}

    def gaps(section: str, sub: pd.DataFrame | None = None, *, metric: str = "brand_j",
             cluster_cols=("cluster_i", "cluster_j"), arms=API_ARMS, prefix: str | None = None,
             extra: dict | None = None):
        out = []
        for arm in arms:
            pairs = None
            if sub is not None:
                p = common.platform_of(arm)
                pairs = frame_pairs(sub[sub["platform"] == p])
            out.append(gap_row(ctx, arm, section, prefix or section, metric=metric, pairs=pairs,
                               cluster_cols=cluster_cols, extra=extra))
        return out

    ctx.say("### R1: top-10 brands instead of all brands\n")
    ctx.say(verdict_table(gaps("R1", metric="top10_j")))

    ctx.say("\n### R2: RBO on brand order\n")
    r2 = [{**r, "section": "R2", "test": f"R2 {r['arms'][0]}"} for r in ctx.rows if r["section"] == "RBO"]
    ctx.rows += r2
    ctx.say(verdict_table(r2))

    ctx.say("\n### R3: drop one wave at a time\n")
    rows = []
    for wave in sorted(df["wave"].unique()):
        rows += gaps("R3", df[df["wave"] != wave], prefix=f"R3 -w{int(wave)}",
                     extra={"dropped_wave": int(wave)})
    ctx.say(verdict_table(rows))

    ctx.say("\n### R4: nothing censored (unplaced Haiku names added on both sides)\n")
    covered = df["brands_all"].map(lambda v: v is not None)
    info["r4_coverage"] = {int(k): float(v) for k, v in covered.groupby(df["wave"]).mean().items()}
    ctx.say(f"Haiku candidate coverage by wave: {info['r4_coverage']}.\n")
    if not covered.all():
        ctx.say("R4 NOT RUN: the Haiku candidate cache does not cover every answer "
                "(`01_frame.py --haiku`).")
        ctx.rows.append({"section": "R4", "test": "R4", "status": "not run"})
    else:
        ctx.say(verdict_table(gaps("R4", df.assign(brands=df["brands_all"]))))

    ctx.say("\n### R5: category-level cluster bootstrap\n")
    ctx.say(verdict_table(gaps("R5", cluster_cols=("category", "category"))))

    ctx.say("\n### R6: `gm_ui` with the Gemini app's follow-up chip markup kept\n")
    changed = int(((df["arm"] == "gm_ui") & (df["brands"].map(tuple) != df["brands_markup"].map(tuple))).sum())
    info["r6_changed_brand_sets"] = changed
    ctx.say(f"{changed} of {int((df['arm'] == 'gm_ui').sum())} `gm_ui` brand sets change when the "
            "markup is kept. ChatGPT arms have no such markup, so R6 is the Gemini arm only.\n")
    ctx.say(verdict_table(gaps("R6", df.assign(brands=df["brands_markup"]),
                               arms=PLATFORMS["gemini"].primary)))

    ctx.say("\n### R7: answers with no search excluded (UI answers included)\n")
    info["r7_excluded"] = df[~df["searched"].astype(bool)].groupby("arm").size().to_dict()
    ctx.say(f"Answers excluded per arm: {info['r7_excluded']}.\n")
    ctx.say(verdict_table(gaps("R7", df[df["searched"].astype(bool)])))

    ctx.say("\n### R8: UI answers whose reported model is not `gpt-6` or `3.5 Flash-Lite` excluded\n")
    keep = ~(df["arm"].isin(common.UI_ARMS) & ~df["model_ok"].astype(bool))
    info["r8_excluded"] = int((~keep).sum())
    ctx.say(f"{info['r8_excluded']} UI answers excluded.\n")
    ctx.say(verdict_table(gaps("R8", df[keep])))

    ctx.say("\n### R9: the 10 pilot prompts excluded\n")
    ctx.say(verdict_table(gaps("R9", df[~df["pilot_prompt"].astype(bool)])))

    ctx.say("\n### R10: UI answers that needed a resubmission excluded\n")
    keep = ~(df["arm"].isin(common.UI_ARMS) & df["resubmitted"].astype(bool))
    info["r10_excluded"] = int((~keep).sum())
    ctx.say(f"{info['r10_excluded']} UI answers excluded.\n")
    ctx.say(verdict_table(gaps("R10", df[keep])))
    return info


# ------------------------------------------------------------ gate


def preregistration_gate(df: pd.DataFrame, meta: dict, n_boot: int, score_path=None) -> list[str]:
    """Reasons the real data may not be modeled yet (empty list = go)."""
    score_path = score_path or (common.RESULTS / "audit_d_score.json")
    problems = []
    if int(df["synthetic"].max()) != 0:
        problems.append("the real frame contains synthetic rows")
    if n_boot != N_BOOT:
        problems.append(f"--n-boot {n_boot} != the pre-registered {N_BOOT}")
    if meta.get("lexicon_sha256") != common.STUDY_LEXICON_SHA256:
        problems.append("the frame was not built with the pinned study lexicon "
                        "(common.STUDY_LEXICON_SHA256)")
    if not score_path.exists():
        problems.append("Audit D is not scored and signed (results/audit_d_score.json)")
    else:
        score = json.loads(score_path.read_text())
        if not score.get("passes"):
            problems.append("Audit D did not pass (precision >= 0.95 and recall >= 0.90)")
        if not score.get("signed_by"):
            problems.append("Audit D is not signed")
        if score.get("lexicon_sha256") != common.STUDY_LEXICON_SHA256:
            problems.append("Audit D was scored against a different lexicon; re-check it")
    return problems


# ------------------------------------------------------------ pilot reproduction


PILOT_ROW = re.compile(r"^\| `(?P<arm>[a-z_]+)` \| (?P<est>[+-]\d\.\d{3}) \[(?P<lo>[+-]\d\.\d{3}), "
                       r"(?P<hi>[+-]\d\.\d{3})\] \|")


def pilot_expected(path=None) -> dict[str, tuple[float, float, float]]:
    """The pilot report's G4 gaps: arm -> (estimate, lo, hi), read from the tracked report."""
    path = path or (common.RESULTS / "pilot_report.md")
    out = {}
    for line in path.read_text().splitlines():
        m = PILOT_ROW.match(line)
        if m and m["arm"] in API_ARMS:
            out[m["arm"]] = (float(m["est"]), float(m["lo"]), float(m["hi"]))
    return out


def pilot_check(df: pd.DataFrame) -> int:
    """Spec §8 item 2: the gap function on the pilot frame gives the pilot report's gaps."""
    ctx = Ctx(df, N_BOOT, seed=common.PILOT_SEED)
    expected = pilot_expected()
    print("Pilot reproduction (sanity check only; same-day rounds stand in for waves, each API "
          f"answer set against every round; seed {common.PILOT_SEED}, {N_BOOT} draws, 90% CI)")
    ok = True
    for arm in API_ARMS:
        r = gap_row(ctx, arm, "pilot", "pilot", sesoi=None)
        want = expected.get(arm)
        got = (round(r["estimate"], 3), round(r["lo"], 3), round(r["hi"], 3))
        match = want is not None and all(abs(g - w) < 5e-4 for g, w in zip(got, want, strict=True))
        ok &= match
        print(f"  {'OK  ' if match else 'FAIL'} {arm}: {m011.fmt_ci(*got)} "
              f"(pilot_report.md: {m011.fmt_ci(*want) if want else 'missing'}; "
              f"{r['n_clusters']} prompts, {r['n_pairs']} pairs)")
    changed = int(((df["arm"] == "gm_ui") & (df["brands"].map(tuple) != df["brands_markup"].map(tuple))).sum())
    print(f"  gm_ui brand sets changed by stripping the app markup: {changed} of "
          f"{int((df['arm'] == 'gm_ui').sum())}")
    return 0 if ok else 2


# ------------------------------------------------------------ dry run


def dry_run_checks(ctx: Ctx, world: str, meta: dict, info: dict) -> list[tuple[str, bool, str]]:
    """Spec §8 item 2: the planted structure must come back out."""

    def find(section: str, test: str, metric: str = "brand_j") -> dict:
        return next(r for r in ctx.rows if r.get("section") == section and r.get("test") == test
                    and r.get("metric") == metric)

    def show(r: dict) -> str:
        return f"{m011.fmt_ci(r['estimate'], r['lo'], r['hi'])} at {r['ci_level']:.0%}: {r['verdict']}"

    def eq(r):
        return r["verdict"] in EQUIVALENT

    def real(r):
        return r["verdict"] == Verdict.REAL.name

    flip = world == "planted_flip"
    want = {"cg_api_low": eq, "cg_api_plain": eq if flip else real, "gm_api_plain": real if flip else eq}
    checks = [("H_pos passes on both platforms", all(r["passed"] for r in ctx.rows
                                                     if r["section"] == "H_pos"), "")]
    for arm, ok in want.items():
        r = find("H1", f"H1 {arm}")
        label = "equivalent (passes)" if ok is eq else "REAL (Real gap: report its size)"
        checks.append((f"H1 {arm} {label}", ok(r), show(r)))
    cg = sorted((find("H1", f"H1 {a}") for a in PLATFORMS["chatgpt"].primary), key=lambda r: r["holm_rank"])
    checks.append(("ChatGPT Holm levels are 95% for rank 1, 90% for rank 2",
                   [round(r["ci_level"], 4) for r in cg] == [0.95, 0.90],
                   ", ".join(f"{r['test']} rank {r['holm_rank']}" for r in cg)))
    checks.append(("Holm order follows the bootstrap TOST p", cg[0]["p_tost"] <= cg[1]["p_tost"],
                   f"{cg[0]['p_tost']:.4f} <= {cg[1]['p_tost']:.4f}"))
    if not flip:
        checks.append(("the passing ChatGPT arm ranks first", cg[0]["test"] == "H1 cg_api_low", cg[0]["test"]))
    gm = find("H1", "H1 gm_api_plain")
    checks.append(("Gemini's single test uses the 90% CI", round(gm["ci_level"], 4) == 0.90,
                   f"{gm['ci_level']:.0%}"))
    h2 = find("H2", "H2 cg_api_low vs cg_api_plain")
    checks.append((f"H2 {'equivalent' if flip else 'REAL'}", eq(h2) if flip else real(h2), show(h2)))
    checks.append(("R6 sees the planted chip brands", info.get("r6_changed_brand_sets", 0) > 0,
                   str(info.get("r6_changed_brand_sets"))))
    r6 = find("R6", "R6 gm_api_plain")
    checks.append(("R6 moves the Gemini gap", abs(r6["estimate"] - gm["estimate"]) > 1e-9,
                   f"{gm['estimate']:+.3f} -> {r6['estimate']:+.3f}"))
    checks.append(("R8 excludes the 2 off-model UI answers", info.get("r8_excluded") == 2,
                   str(info.get("r8_excluded"))))
    checks.append(("R10 excludes the 2 resubmitted UI answers", info.get("r10_excluded") == 2,
                   str(info.get("r10_excluded"))))
    checks.append(("gm_api_plain is over the no-search limit",
                   ctx.no_search.get("gm_api_plain", 0) > NO_SEARCH_MAX,
                   f"{ctx.no_search.get('gm_api_plain', 0):.3f}"))
    noted = find("domain_gap", "gap gm_api_plain", "cited_j")
    checks.append(("domain gaps have no verdict, and the rule is noted",
                   "verdict" not in noted and "INCONCLUSIVE" in noted.get("note", ""), noted.get("note", "")))
    missing = meta.get("missing", [])
    checks.append(("the API prompt that failed 3 attempts is the one missing answer",
                   [(m["arm"], m["wave"], m["item_id"]) for m in missing] == [("gm_api_plain", 2, "b2b_33")],
                   str(len(missing))))
    checks.append(("599 answers counted", len(ctx.df) == 599, str(len(ctx.df))))
    for section in ("R1", "R2", "R3", "R5", "R7", "R8", "R9", "R10"):
        got = {r["arms"][0] for r in ctx.rows if r.get("section") == section and "arms" in r}
        checks.append((f"{section} ran for every API arm", got == set(API_ARMS), f"{len(got)} arms"))
    return checks


def leak_check(paths: list) -> list[str]:
    bad = []
    for path in paths:
        text = path.read_text()
        if SYNTH_ANSWER_MARK in text or SYNTH_QUERY_MARK in text:
            bad.append(str(path))
    return bad


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_mode_args(ap)
    ap.add_argument("--expect", choices=("planted", "planted_flip"), default=None,
                    help="assert the planted dry-run structure (synthetic only)")
    ap.add_argument("--n-boot", type=int, default=N_BOOT,
                    help="bootstrap draws; values other than 2000 are for the synthetic dry run")
    a = ap.parse_args()
    mode: Mode = common.mode_from(a)
    if a.expect and a.expect != a.synthetic:
        raise SystemExit("--expect must name the --synthetic world being run")
    frame, meta = common.load_frame(mode)
    if mode.pilot:
        sys.exit(pilot_check(frame))
    if mode.synthetic:
        if int(frame["synthetic"].min()) != 1:
            raise SystemExit("the synthetic frame contains real rows; refusing")
    else:
        problems = preregistration_gate(frame, meta, a.n_boot)
        if problems:
            print("03_model refuses to run on the real data yet (pre-registration gate):")
            for p in problems:
                print(f"  - {p}")
            sys.exit(3)

    ctx = Ctx(frame, a.n_boot)
    tag = f" (SYNTHETIC/{a.synthetic})" if a.synthetic else ""
    ctx.say(f"# Experiment 004: model results{tag}\n")
    ctx.say(f"Seed {SEED}, {a.n_boot} bootstrap draws, {1 - ALPHA:.0%} percentile CIs unless a row "
            f"says otherwise, SESOI {SESOI} (Jaccard gaps). {len(frame)} answers evaluated, "
            f"{frame['item_id'].nunique()} prompts, {frame['category'].nunique()} categories, waves "
            f"{sorted(int(w) for w in frame['wave'].unique())}. Lexicon `{meta['lexicon']}` sha256 "
            f"`{meta['lexicon_sha256'][:12]}`. Aggregates only: no brand, answer or query text.\n")
    ctx.say("Gap = mean(within:UI) - mean(cross:arm|UI). Positive means the arm is further from "
            "the UI than the UI is from itself across days.\n")
    miss = Counter((m["arm"], m["wave"]) for m in meta.get("missing", []))
    ctx.say("Missing answers (excluded and logged): "
            + ("none.\n" if not miss else "; ".join(f"{a} w{w}: {n}" for (a, w), n in sorted(miss.items()))
               + ".\n"))
    ctx.say(f"No-search rates: { {k: round(v, 3) for k, v in ctx.no_search.items()} }.\n")

    passed = h_pos(ctx)
    desc, info = {}, {}
    if passed:
        h_pla(ctx)
        h1(ctx)
        h2_rbo_levels(ctx)
        domain_gaps(ctx)
        desc = descriptives(ctx)
        info = robustness(ctx)

    out = mode.results
    out.mkdir(parents=True, exist_ok=True)
    results_json = out / "model_results.json"
    meta_out = {"seed": SEED, "n_boot": a.n_boot, "alpha": ALPHA, "sesoi": SESOI, "mode": mode.label,
                "h_pos_passed": passed, "answers": len(frame), "lexicon_sha256": meta["lexicon_sha256"],
                "missing": len(meta.get("missing", [])), "no_search_rate": ctx.no_search, **info}
    results_json.write_text(json.dumps(common.jsonable({"meta": meta_out, "rows": ctx.rows,
                                                        "descriptives": desc}), indent=1) + "\n")
    report = out / "model_report.md"
    report.write_text("\n".join(ctx.lines) + "\n")
    print("\n".join(ctx.lines))
    print(f"\nwrote {report} and {results_json}")

    if not passed:
        failed = [r for r in ctx.rows if r["section"] == "H_pos" and not r["passed"]]
        print("\nH_pos FAILED: " + "; ".join(f"{r['test']}: {r['reason']}" for r in failed)
              + ". Stopping; nothing else was computed.")
        sys.exit(1)
    if a.expect:
        checks = dry_run_checks(ctx, a.expect, meta, info)
        scanned = [report, results_json, mode.frame_path, mode.meta_path, out / "audit_report.md",
                   out / "audit.json"]
        leaks = leak_check([p for p in scanned if p.exists()])
        checks.append(("no answer or query text in the frame or reports", not leaks, ", ".join(leaks)))
        named = [p.name for p in (report, results_json, out / "audit_report.md", out / "audit.json")
                 if p.exists() and SYNTH_BRAND_PREFIX in p.read_text()]
        checks.append(("the reports name no brand", not named, ", ".join(named)))
        print(f"\ndry-run check ({a.expect}):")
        for name, ok, detail in checks:
            print(f"  {'OK  ' if ok else 'FAIL'} {name}: {detail}")
        print("  info (not asserted): " + "; ".join(
            f"{r['test']} {m011.fmt_ci(r['estimate'], r['lo'], r['hi'])} {r['verdict']}"
            for r in ctx.rows if r.get("section") == "H_pla"))
        if not all(ok for _, ok, _ in checks):
            sys.exit(2)


if __name__ == "__main__":
    main()
