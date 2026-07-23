"""Exploratory (NOT pre-registered): do prompts sharing a sub-intent converge
in the retrieval layer — grounding searches and cited domains — and not just
in recommended brands?

For each coded prompt attribute, same-wave between-prompt pairs are split
into both-have-it / mixed / neither. Two regimes emerge:

- FRAME attributes (travel, music, noise-cancelling): sharing the flag =
  sharing the sub-intent -> both-pairs converge (travel converges at every
  layer, grounding most of all).
- VALUED attributes (dollar budget, recipient, form factor): the flag
  carries a value, and different values are different markets -> both-pairs
  overlap LESS than attribute-free pairs, which cluster on the default
  answer. The budget-bucket check confirms it: same-price-bucket pairs
  overlap far more than different-bucket pairs.

Inference: prompt-level cluster bootstrap (90% CIs).
Outputs: results/subintent_retrieval.md + figures/subintent-retrieval
(travel vs budget, all three layers).
"""

from __future__ import annotations

import importlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import ALPHA, FIGURES, N_BOOT, RESULTS, SEED, load_responses

from aeo_research.overlap import cluster_boot, jaccard
from aeo_research.plotting import CATEGORICAL, INK_MUTED, save_figure, theme

feats_mod = importlib.import_module("91_exploratory_figures")

FEATURES = [
    ("f_budget_specific", "Specific dollar budget"),
    ("f_recipient_named", "Named gift recipient"),
    ("f_usage_music", "Music usage"),
    ("f_travel_context", "Travel context"),
    ("f_noise_cancel", "Noise-cancelling"),
    ("f_form_factor", "Form factor"),
]
LAYERS = [
    ("brand_set", "brands"),
    ("fanout_token_set", "grounding_tokens"),
    ("domain_set", "domains"),
]


def build_pairs(hp: pd.DataFrame) -> pd.DataFrame:
    """Same-wave between-prompt pairs with per-layer Jaccard values."""
    rows = []
    for _, sub in hp.groupby("wave"):
        sub = sub.reset_index(drop=True)
        sets = {col: list(sub[col]) for col, _ in LAYERS}
        ids = sub["item_id"].to_numpy()
        flags = {f: sub[f].to_numpy() for f, _ in FEATURES}
        n = len(sub)
        for i in range(n):
            for j in range(i + 1, n):
                if ids[i] == ids[j]:
                    continue
                row = {"cluster_i": ids[i], "cluster_j": ids[j]}
                for col, name in LAYERS:
                    row[name] = jaccard(sets[col][i], sets[col][j])
                for f, _ in FEATURES:
                    a, b = flags[f][i], flags[f][j]
                    row[f] = "both" if a and b else ("neither" if not a and not b else "mixed")
                rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    theme()
    df = load_responses().reset_index(drop=True)
    hp = df[df["intent"] == "headphones"].copy()
    for col, parse in [
        ("brand_set", "brands"), ("domain_set", "domains"),
    ]:
        hp[col] = hp[parse].fillna("").str.split(r"\|").map(
            lambda x: frozenset(d for d in x if d)
        )
    hp["fanout_token_set"] = hp["fanout_tokens"].fillna("").str.split().map(frozenset)

    # merge feature flags from the 91 loader (same regex coding as 90)
    coded, _ = feats_mod.load()
    flag_cols = ["item_id"] + [f for f, _ in FEATURES]
    hp = hp.merge(coded[flag_cols].drop_duplicates("item_id"), on="item_id")

    pairs = build_pairs(hp)
    lines = [
        "# Exploratory: sub-intent convergence in the retrieval layer",
        "",
        "Same-wave between-prompt pairs, split per attribute into both/mixed/",
        "neither. Values are mean pairwise Jaccard; Δ rows are cluster-bootstrap",
        f"contrasts (90% CI, n_boot={N_BOOT}, seed={SEED}). NOT pre-registered.",
        "",
    ]
    fig_rows = []
    for f, label in FEATURES:
        lines.append(f"## {label}")
        for _, layer in LAYERS:
            sub = pairs.rename(columns={layer: "value", f: "condition"})
            means = {
                c: sub.loc[sub["condition"] == c, "value"].mean()
                for c in ("both", "mixed", "neither")
            }
            res = cluster_boot(
                sub, contrast=("both", "mixed"),
                alpha=ALPHA, n_boot=N_BOOT, seed=SEED,
            )
            sig = "*" if (res.lo > 0 or res.hi < 0) else ""
            lines.append(
                f"- {layer}: both {means['both']:.3f} / mixed {means['mixed']:.3f}"
                f" / neither {means['neither']:.3f}; Δ(both−mixed) ="
                f" {res.estimate:+.3f} [{res.lo:+.3f}, {res.hi:+.3f}] {sig}"
            )
            if f in ("f_budget_specific", "f_travel_context"):
                fig_rows.append((f, layer, means))
        lines.append("")

    lines += budget_bucket_check(hp)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "subintent_retrieval.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    # Figure: travel (frame attribute, converges) vs budget (valued
    # attribute, fragments) across the three layers
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    panels = [
        ("f_travel_context", "Travel context\n(a frame: no value attached)",
         "Both prompts mention it"),
        ("f_budget_specific", "Dollar budget\n(a valued attribute)",
         "Both prompts state one"),
    ]
    conds = [("both", CATEGORICAL[2]), ("mixed", CATEGORICAL[1]),
             ("neither", CATEGORICAL[0])]
    layer_labels = ["Recommended\nbrands", "Grounding\nsearches", "Cited\ndomains"]
    for ax, (f, title, both_label) in zip(axes, panels):
        rows = [(layer, means) for ff, layer, means in fig_rows if ff == f]
        x = np.arange(len(rows))
        width = 0.27
        for k, (cond, color) in enumerate(conds):
            lab = {"both": both_label, "mixed": "One does, one doesn't",
                   "neither": "Neither does"}[cond]
            ax.bar(x + (k - 1) * width, [m[cond] for _, m in rows],
                   width * 0.9, color=color, label=lab)
        ax.set_xticks(x, layer_labels)
        ax.set_title(title, fontsize=11)
        ax.legend(frameon=False, fontsize=8.5)
    axes[0].set_ylabel("Mean pairwise Jaccard overlap")
    fig.suptitle("Frames converge; valued attributes fragment", y=0.98)
    save_figure(fig, FIGURES, "subintent-retrieval")
    print(f"figure -> {FIGURES / 'subintent-retrieval'}")


def budget_bucket_check(hp: pd.DataFrame) -> list[str]:
    """Among budget-stated prompts: do similar amounts converge? (internal
    prompt text is read here; only derived aggregates are emitted)."""
    import re

    from common import PROMPTS_CSV

    prompts = pd.read_csv(PROMPTS_CSV)
    hpp = prompts[prompts.intent == "headphones"].copy()

    def amount(t: str):
        m = re.findall(
            r"[\$€£]\s?(\d{2,4})|(\d{2,4})\s?(?:dollars|bucks|euros?|pounds)",
            t.lower(),
        )
        vals = [int(a or b) for a, b in m if (a or b)]
        return max(vals) if vals else None

    hpp["amt"] = hpp.text.map(amount)
    amts = hpp.dropna(subset=["amt"]).set_index("item_id").amt
    lo = set(amts[amts <= 150].index)
    hi = set(amts[amts > 150].index)

    sub = hp[hp.item_id.isin(amts.index)]
    rows = []
    for _, s in sub.groupby("wave"):
        s = s.reset_index(drop=True)
        sets = list(s["brand_set"])
        ids = s["item_id"].to_numpy()
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                if ids[i] == ids[j]:
                    continue
                rows.append(
                    (ids[i], ids[j], (ids[i] in lo) == (ids[j] in lo),
                     jaccard(sets[i], sets[j]))
                )
    pf = pd.DataFrame(rows, columns=["a", "b", "same", "jac"]).dropna()
    obs = pf[pf.same].jac.mean() - pf[~pf.same].jac.mean()
    rng = np.random.default_rng(SEED)
    ids_all = list(lo | hi)
    draws = []
    for _ in range(N_BOOT):
        take = set(rng.choice(ids_all, len(ids_all)))
        s = pf[pf.a.isin(take) & pf.b.isin(take)]
        if s.same.nunique() == 2:
            draws.append(s[s.same].jac.mean() - s[~s.same].jac.mean())
    qlo, qhi = np.quantile(draws, [0.05, 0.95])
    return [
        "## Budget-bucket check (valued-attribute mechanism)",
        f"Among the {len(amts)} budget prompts with a parseable amount "
        f"(range {int(amts.min())}-{int(amts.max())}), split at 150:",
        f"- same-bucket brand Jaccard {pf[pf.same].jac.mean():.3f} vs "
        f"different-bucket {pf[~pf.same].jac.mean():.3f}; "
        f"Δ = {obs:+.3f} [{qlo:+.3f}, {qhi:+.3f}]",
        "- i.e. the sub-intent unit is the attribute VALUE, not the flag: "
        "two prompts naming similar budgets converge; different budgets are "
        "different markets.",
        "",
    ]


if __name__ == "__main__":
    main()
