"""Power for the primary test (spec §5), simulated from experiment 009's real answer pairs.

009 has the design the full study repeats: 40 prompts, 3 waves, `ui_default` as reference.
Its `opus55_plain` pairs stand in for a Claude Code arm, because the feasibility run put
both at about the same gap. For each planted true gap: draw 40 prompts with replacement,
shift the cross pairs so the true gap is the planted one, run the prompt-level bootstrap,
and record how often the interval sits inside +/-0.10. Aggregates only.

Usage (repo root):
    uv run python experiments/011-claude-code-fidelity/pipeline/power_sim.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parents[1]
EXP009 = EXP.parent / "009-claude-model-fidelity"
SEED = 20261103
SESOI = 0.10
N_STUDIES = 1000
N_BOOT = 1000
GAPS = (0.0, 0.03, 0.055, 0.075, 0.10, 0.125)
ARM = "opus55_plain"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


brands = _load("exp009_brands_power", EXP009 / "pipeline" / "brands.py")


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else np.nan


def per_prompt_values() -> tuple[np.ndarray, np.ndarray]:
    patterns, _aliases, _sha = brands.frozen_lexicon()
    prompts = {}
    import csv

    with (EXP009 / "data" / "raw" / "prompts.csv").open(newline="") as handle:
        prompts = {row["item_id"]: row["category"] for row in csv.DictReader(handle)}

    def brand_set(arm: str, item: str, wave: int) -> set:
        path = EXP009 / "data" / "raw" / "responses" / f"w{wave}" / arm / f"{item}.json"
        text = json.loads(path.read_text())["normalized"]["answer_text"]
        return set(brands.lexicon_extract(text, patterns.get(prompts[item], [])))

    within, cross = [], []
    for item in sorted(prompts):
        ui = {w: brand_set("ui_default", item, w) for w in (1, 2, 3)}
        arm = {w: brand_set(ARM, item, w) for w in (1, 2, 3)}
        within.append(np.nanmean([jaccard(ui[a], ui[b]) for a, b in combinations((1, 2, 3), 2)]))
        cross.append(np.nanmean([jaccard(ui[w], arm[w]) for w in (1, 2, 3)]))
    return np.array(within), np.array(cross)


def main() -> None:
    within, cross = per_prompt_values()
    observed = float(np.mean(within - cross))
    print(f"009 {ARM}: gap {observed:+.3f} over {len(within)} prompts; per-prompt SD "
          f"{np.std(within - cross, ddof=1):.3f}")
    rng = np.random.default_rng(SEED)
    n = len(within)
    print("true gap | pass, 90% CI (Holm rank 2) | pass, 95% CI (Holm rank 1) | REAL, 90% CI | median half-width")
    for true_gap in GAPS:
        diffs = (within - cross) - observed + true_gap
        pass90 = pass95 = real = 0
        widths = []
        for _ in range(N_STUDIES):
            study = rng.choice(diffs, size=n, replace=True)
            draws = rng.integers(0, n, size=(N_BOOT, n))
            boots = study[draws].mean(axis=1)
            lo90, hi90 = np.quantile(boots, [0.05, 0.95])
            lo95, hi95 = np.quantile(boots, [0.025, 0.975])
            pass90 += lo90 > -SESOI and hi90 < SESOI
            pass95 += lo95 > -SESOI and hi95 < SESOI
            real += (lo90 > 0 or hi90 < 0) and not (lo90 > -SESOI and hi90 < SESOI)
            widths.append((hi90 - lo90) / 2)
        print(f"{true_gap:8.3f} | {pass90 / N_STUDIES:26.2f} | {pass95 / N_STUDIES:26.2f} | "
              f"{real / N_STUDIES:12.2f} | {np.median(widths):.3f}")


if __name__ == "__main__":
    main()
