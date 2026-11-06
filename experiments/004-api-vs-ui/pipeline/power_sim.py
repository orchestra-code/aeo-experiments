"""Power for H1 (spec §5), simulated from 010 Stage 1 and the 004 pilot -> results/power.md.

Sources, aggregates only in the output:

- within:ui across days: experiment 010 Stage 1, waves 1 to 7 ONLY (submitted Oct 3 to 10,
  2026, daily), the same 40 prompts through the same DataForSEO ChatGPT and Gemini
  settings as 004's UI arms. HARD RULE: 010 Stage 2 (wave 8 and later) is blind until its
  own analysis. The loader drops every ledger record outside waves 1 to 7 before it looks
  at a result path, asserts the waves, submission dates and result folders of what it
  keeps, and opens no other response file. Brands: 010's ``extract_new`` with lexicon v3
  (hash-checked), with the Gemini app markup stripped as 004's primary extraction does.
- the per-prompt spread of the cross-arm overlap: the 004 pilot frame (``01_frame.py
  --pilot``), per prompt D = mean(within:ui) - mean(cross:arm|ui), centered within arm.
  ChatGPT pools ``cg_api_low`` and ``cg_api_plain`` (20 values), Gemini uses
  ``gm_api_plain`` (10).

Scheme A (the spec's, used for the table). One simulated study: draw 3 of the 7 Stage 1
waves without replacement; W_p is prompt p's mean Jaccard over the 3 pairs of those waves;
d_p is drawn with replacement from the pilot's centered deviations; the cross overlap is
C_p = W_p - g - d_p, clipped to [0, 1], for a planted true gap g. The gap estimate is the
mean over prompts of W_p - C_p, with a prompt-level bootstrap (1,000 draws) as in the
model, and a study passes when its interval lies inside +/-0.10. With equal pairs per
prompt this is the model's pair-weighted gap. Under A the interval width comes from the
pilot deviations, and 010 matters only through the clip, so two brackets are reported:

- Scheme B (no covariance): C_p = mean(W) - g + c_p, with c_p drawn from the pilot's
  centered per-prompt cross overlaps. It drops the pilot's positive link between a
  prompt's UI stability and its cross overlap, so its intervals are wider (conservative).
- Scheme C (exchangeable days, 010 only): draw 6 of the 7 waves; 3 play the UI and 3 the
  API arm, and C_p is the mean Jaccard of the 3 matched UI and arm days, shifted by g. It
  asks what the test does if the API varied like one more day of the UI, with no
  prompt-level gap spread beyond that, using no pilot data at all.

Clipping C_p to [0, 1] moves the mean estimate slightly off the planted gap; the report
shows the mean estimate next to each pass rate.

The pilot's within-UI overlap is same-day and its cross overlap has one API answer per
prompt, not three. Both make its deviations a rough stand-in for the study's.

1,000 studies x 1,000 bootstrap draws per gap, seed 20261106, common random numbers across
gaps. ChatGPT is reported at the 95% and 90% intervals (its Holm levels), Gemini at 90%.

Usage (repo root):
    uv run python experiments/004-api-vs-ui/pipeline/01_frame.py --pilot
    uv run python experiments/004-api-vs-ui/pipeline/power_sim.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import common
import numpy as np
from common import SEED, SESOI, Mode

sys.path.insert(0, str(common.HARNESS))
import answers  # noqa: E402
import exp004  # noqa: E402

from aeo_research.overlap import jaccard  # noqa: E402

EXP010_RAW = exp004.EXP010_RAW  # main checkout: gitignored 010 data lives only there
STAGE1_WAVES = tuple(range(1, 8))
STAGE1_DATES = (date(2026, 10, 3), date(2026, 10, 10))
N_STUDIES = 1000
N_BOOT = 1000
GAPS = (0.0, 0.025, 0.05, 0.075, 0.10, 0.125)
UI_ARM = {"chatgpt": "cg_ui", "gemini": "gm_ui"}
LEVELS = {"chatgpt": (0.95, 0.90), "gemini": (0.90,)}


# ---------------------------------------------------------------- 010 Stage 1


def stage1_records(platform: str, raw: Path = EXP010_RAW) -> list[dict]:
    """010's main-ledger records for waves 1 to 7 only; later waves are dropped unread."""
    path = raw / f"ledger_main_{platform}.jsonl"
    kept = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if int(rec["wave"]) not in STAGE1_WAVES:  # Stage 2: never used, never followed
            continue
        kept.append(rec)
    assert kept and all(int(r["wave"]) in STAGE1_WAVES for r in kept)
    return kept


def stage1_finals(platform: str, raw: Path = EXP010_RAW) -> dict[tuple[str, int], Path]:
    """(item, wave) -> result path of the last collected task, Stage 1 only, asserted."""
    tasks: dict[str, dict] = {}
    for r in stage1_records(platform, raw):
        tasks.setdefault(r["task_id"], {}).update(r)
    out: dict[tuple[str, int], tuple[str, Path]] = {}
    for t in tasks.values():
        wave = int(t["wave"])
        assert wave in STAGE1_WAVES
        day = datetime.fromisoformat(t["submitted_at"]).astimezone(ZoneInfo("America/New_York")).date()
        assert STAGE1_DATES[0] <= day <= STAGE1_DATES[1], f"Stage 1 task submitted {day}"
        if t["status"] != "collected":
            continue
        path = Path(t["result_path"])
        assert path.parent.name == f"w{wave}" and path.parent.parent.name == f"responses_main_{platform}"
        key = (t["item_id"], wave)
        if key not in out or (t.get("collected_at") or "") > out[key][0]:
            out[key] = (t.get("collected_at") or "", path)
    return {k: p for k, (_s, p) in out.items()}


def stage1_brands(platform: str, raw: Path = EXP010_RAW) -> tuple[dict, Counter]:
    """(item, wave) -> brand set (None for the app's error message), and model labels."""
    prompts = exp004.load_prompts(raw / "prompts_b2b.csv")
    patterns = common.b9.load_lexicon(exp004.verify_lexicon())
    arm = UI_ARM[platform]
    out, models = {}, Counter()
    for (item, wave), path in sorted(stage1_finals(platform, raw).items()):
        assert wave in STAGE1_WAVES
        result = json.loads(path.read_text())
        norm = answers.from_dataforseo(result)
        models[norm.get("model") or "(none)"] += 1
        if answers.is_error_answer(norm["answer_text"]):
            out[(item, wave)] = None
            continue
        text = answers.brand_text(arm, norm["answer_text"])
        out[(item, wave)] = set(common.extract(text, patterns.get(prompts[item]["category"], [])))
    return out, models


def jaccard_cube(brands: dict, items: list[str]) -> np.ndarray:
    """J[p, i, j]: brand Jaccard of prompt p between Stage 1 waves i+1 and j+1 (NaN if absent)."""
    n = len(STAGE1_WAVES)
    cube = np.full((len(items), n, n), np.nan)
    for p, item in enumerate(items):
        for i, j in itertools.combinations(range(n), 2):
            a, b = brands.get((item, i + 1)), brands.get((item, j + 1))
            if a is not None and b is not None:
                cube[p, i, j] = cube[p, j, i] = jaccard(a, b)
    return cube


def observed_within(cube: np.ndarray) -> dict:
    n = cube.shape[1]
    pairs = [cube[:, i, j] for i, j in itertools.combinations(range(n), 2)]
    pair_vals = np.concatenate(pairs)
    per_prompt = np.nanmean(np.stack(pairs, axis=1), axis=1)
    triples = [np.nanmean(np.stack([cube[:, a, b] for a, b in itertools.combinations(t, 2)], 1), 1)
               for t in itertools.combinations(range(n), 3)]
    triple_means = [float(np.nanmean(t)) for t in triples]
    adjacent = np.concatenate([cube[:, i, i + 1] for i in range(n - 1)])
    return {"pairs": int(np.isfinite(pair_vals).sum()), "pair_mean": float(np.nanmean(pair_vals)),
            "prompt_mean": float(np.nanmean(per_prompt)),
            "prompt_sd": float(np.nanstd(per_prompt, ddof=1)),
            "adjacent_day_mean": float(np.nanmean(adjacent)),
            "three_wave_min": min(triple_means), "three_wave_max": max(triple_means)}


# ---------------------------------------------------------------- pilot


def pilot_spread() -> dict[str, dict[str, np.ndarray]]:
    """Per platform: centered per-prompt deviations D_p and cross overlaps C_p from the pilot."""
    df, _meta = common.load_frame(Mode(pilot=True))
    out = {}
    for platform, spec in common.PLATFORMS.items():
        devs, crosses = [], []
        ui = df[df["arm"] == spec.ref]
        for arm in spec.primary:
            d_arm, c_arm = [], []
            api = df[df["arm"] == arm]
            for item, g in ui.groupby("item_id"):
                sets = {int(r.wave): set(r.brands) for r in g.itertuples()}
                w = [jaccard(sets[a], sets[b]) for a, b in itertools.combinations(sorted(sets), 2)]
                mine = api[api["item_id"] == item]
                c = [jaccard(set(r.brands), sets[int(r.wave)]) for r in mine.itertuples()
                     if int(r.wave) in sets]
                if np.isfinite(w).any() and np.isfinite(c).any():
                    d_arm.append(np.nanmean(w) - np.nanmean(c))
                    c_arm.append(np.nanmean(c))
            devs += list(np.array(d_arm) - np.mean(d_arm))
            crosses += list(np.array(c_arm) - np.mean(c_arm))
        out[platform] = {"dev": np.array(devs), "cross": np.array(crosses)}
    return out


# ---------------------------------------------------------------- simulation


def simulate(cube: np.ndarray, spread: dict, scheme: str, gap: float, seed: int,
             levels=(0.95, 0.90), n_studies: int = N_STUDIES, n_boot: int = N_BOOT) -> dict:
    """Pass rate and mean CI half-width per level for one planted gap."""
    rng = np.random.default_rng(seed)  # same seed per gap: common random numbers
    n_p, n_w = cube.shape[0], cube.shape[1]
    passes = {lv: 0 for lv in levels}
    widths = {lv: [] for lv in levels}
    estimates = []
    for _ in range(n_studies):
        if scheme == "C":
            waves = rng.choice(n_w, 6, replace=False)
            ui_w, arm_w = waves[:3], waves[3:]
        else:
            ui_w = rng.choice(n_w, 3, replace=False)
        w = np.nanmean(np.stack([cube[:, a, b] for a, b in itertools.combinations(ui_w, 2)], 1), 1)
        if scheme == "A":
            c = np.clip(w - gap - rng.choice(spread["dev"], n_p, replace=True), 0, 1)
        elif scheme == "B":
            c = np.clip(np.nanmean(w) - gap + rng.choice(spread["cross"], n_p, replace=True), 0, 1)
        else:
            c = np.nanmean(np.stack([cube[:, a, b] for a, b in zip(ui_w, arm_w, strict=True)], 1), 1) - gap
        d = (w - c)[np.isfinite(w - c)]
        estimates.append(d.mean())
        boots = d[rng.integers(0, d.size, size=(n_boot, d.size))].mean(axis=1)
        for lv in levels:
            lo, hi = np.quantile(boots, [(1 - lv) / 2, 1 - (1 - lv) / 2])
            passes[lv] += bool(lo > -SESOI and hi < SESOI)
            widths[lv].append((hi - lo) / 2)
    return {"gap": gap, "scheme": scheme, "mean_estimate": float(np.mean(estimates)),
            **{f"pass_{int(lv * 100)}": passes[lv] / n_studies for lv in levels},
            **{f"half_width_{int(lv * 100)}": float(np.mean(widths[lv])) for lv in levels}}


def pct(x: float) -> str:
    return f"{x:.0%}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--studies", type=int, default=N_STUDIES)
    ap.add_argument("--boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    started = time.monotonic()
    items = sorted(exp004.load_prompts(EXP010_RAW / "prompts_b2b.csv"))
    spread = pilot_spread()
    cubes, observed, models = {}, {}, {}
    for platform in ("chatgpt", "gemini"):
        brands, models[platform] = stage1_brands(platform)
        assert {w for _i, w in brands} <= set(STAGE1_WAVES)
        cubes[platform] = jaccard_cube(brands, items)
        observed[platform] = observed_within(cubes[platform]) | {
            "answers": sum(v is not None for v in brands.values()),
            "error_answers": sum(v is None for v in brands.values())}
    results = {}
    for platform in ("chatgpt", "gemini"):
        for k, scheme in enumerate("ABC"):
            seed = SEED * 10 + k + (0 if platform == "chatgpt" else 5)
            results[(platform, scheme)] = [
                simulate(cubes[platform], spread[platform], scheme, g, seed, LEVELS[platform],
                         a.studies, a.boot) for g in GAPS]
    elapsed = time.monotonic() - started

    lines = ["# Experiment 004: power for H1 (spec §5)", "",
             f"Simulated with `pipeline/power_sim.py`: {a.studies:,} studies x {a.boot:,} bootstrap "
             f"draws per true gap, seed {SEED}, SESOI +/-{SESOI}. A study passes when its interval "
             "lies inside the band. Aggregates only. Method and its limits: the script's docstring.",
             "", "## Inputs", "",
             "within:ui across days, experiment 010 Stage 1 (waves 1 to 7 only, submitted Oct 3 "
             "to 10, 2026; 010 Stage 2 was not read), brand-set Jaccard with 010's `extract_new` "
             "and lexicon v3:", "",
             "| Platform | Answers | App error answers | Pairs | Mean over pairs | Mean over prompts "
             "(SD) | Adjacent days | Any 3 waves, range |", "|---|---|---|---|---|---|---|---|"]
    for platform, o in observed.items():
        lines.append(f"| {common.PLATFORMS[platform].label} | {o['answers']} | {o['error_answers']} | "
                     f"{o['pairs']} | {o['pair_mean']:.3f} | {o['prompt_mean']:.3f} "
                     f"({o['prompt_sd']:.3f}) | {o['adjacent_day_mean']:.3f} | "
                     f"{o['three_wave_min']:.3f} to {o['three_wave_max']:.3f} |")
    lines += ["", "Models the UI scrapes reported in those answers: "
              + "; ".join(f"{common.PLATFORMS[p].label} " + ", ".join(f"`{m}` {n}" for m, n in c.most_common())
                          for p, c in models.items()) + ". The ChatGPT label then was not `gpt-6`, so "
              "today's floor may differ.", "",
              "Per-prompt spread from the 004 pilot (10 prompts, one day, centered): SD of the "
              "deviations D_p = within - cross, and of the cross overlap C_p:", "",
              "| Platform | Values | SD of D_p | SD of C_p |", "|---|---|---|---|"]
    for platform, s in spread.items():
        lines.append(f"| {common.PLATFORMS[platform].label} | {len(s['dev'])} | "
                     f"{np.std(s['dev'], ddof=1):.3f} | {np.std(s['cross'], ddof=1):.3f} |")
    lines += ["", "## Pass rates, scheme A (the spec's)", "",
              "| True gap | ChatGPT pass, 95% CI | ChatGPT pass, 90% CI | Gemini pass, 90% CI | "
              "Mean half-width: ChatGPT 95%, ChatGPT 90%, Gemini 90% | Mean estimate: ChatGPT, "
              "Gemini |", "|---|---|---|---|---|---|"]
    cg, gm = results[("chatgpt", "A")], results[("gemini", "A")]
    for r, s in zip(cg, gm, strict=True):
        label = " (false pass)" if r["gap"] >= SESOI else ""
        lines.append(f"| {r['gap']:.3f}{label} | {pct(r['pass_95'])} | {pct(r['pass_90'])} | "
                     f"{pct(s['pass_90'])} | {r['half_width_95']:.3f}, {r['half_width_90']:.3f}, "
                     f"{s['half_width_90']:.3f} | {r['mean_estimate']:+.3f}, {s['mean_estimate']:+.3f} |")
    lines += ["", "## Brackets: scheme B (no covariance) and scheme C (exchangeable days)", "",
              "| True gap | Scheme | ChatGPT pass, 95% | ChatGPT pass, 90% | Gemini pass, 90% | "
              "Mean half-width: ChatGPT 95%, Gemini 90% | Mean estimate: ChatGPT, Gemini |",
              "|---|---|---|---|---|---|---|"]
    for scheme in "BC":
        for r, s in zip(results[("chatgpt", scheme)], results[("gemini", scheme)], strict=True):
            lines.append(f"| {r['gap']:.3f} | {scheme} | {pct(r['pass_95'])} | {pct(r['pass_90'])} | "
                         f"{pct(s['pass_90'])} | {r['half_width_95']:.3f}, {s['half_width_90']:.3f} | "
                         f"{r['mean_estimate']:+.3f}, {s['mean_estimate']:+.3f} |")
    lines += ["", "Reading: \"pass\" at a true gap of 0.100 or more is a false pass. ChatGPT's first "
              "Holm test is read at 95% and its second at 90%; Gemini's single test at 90%.",
              "", f"Draws were not reduced: {a.studies:,} studies x {a.boot:,} draws for every cell."]
    out = common.RESULTS / "power.md"
    out.write_text("\n".join(lines) + "\n")
    (common.RESULTS / "power.json").write_text(json.dumps(common.jsonable({
        "observed_within_ui_010_stage1": observed, "studies": a.studies, "boot": a.boot, "seed": SEED,
        "results": {f"{p}:{s}": v for (p, s), v in results.items()}}), indent=1) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out} ({elapsed:.0f} s)")


if __name__ == "__main__":
    main()
