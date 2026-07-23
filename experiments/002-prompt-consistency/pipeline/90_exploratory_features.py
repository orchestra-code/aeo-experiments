"""Exploratory: code headphone prompts by phrasing features, slice brand outcomes.

Prompt text is SparkToro's and stays internal; only derived flags/aggregates
leave this script.
"""
import re

import numpy as np
import pandas as pd

EXP = "/Users/jcw/projects/aeo-experiments/experiments/002-prompt-consistency"

prompts = pd.read_csv(f"{EXP}/data/raw/prompts.csv")
hp_prompts = prompts[prompts.intent == "headphones"].copy()
t = hp_prompts.text.str.lower()

# --- feature coding (regex heuristics over prompt text) -------------------
hp_prompts["f_budget_specific"] = t.str.contains(
    r"[\$€£]\s?\d|\d+\s?(dollars|bucks|euros?|pounds)|under \d|less than \d|budget of"
)
hp_prompts["f_value_language"] = t.str.contains(
    r"best value|good value|affordable|cheap|budget[- ]friendly|not too expensive|reasonabl|won'?t break the bank|bang for"
)
hp_prompts["f_recipient_named"] = t.str.contains(
    r"\b(sister|brother|wife|husband|mom|mother|dad|father|daughter|son|aunt|uncle|niece|nephew|girlfriend|boyfriend|partner|friend|cousin|grandm|grandf|in[- ]law)\b"
)
hp_prompts["f_age_mentioned"] = t.str.contains(r"\b\d{2}[s\-]?\s?(year|yr|s\b)|(early|mid|late)\s\d{2}s|\bage[ds]?\b")
hp_prompts["f_noise_cancel"] = t.str.contains(r"noise[- ]?cancel|\banc\b|noise[- ]reduc")
hp_prompts["f_form_factor"] = t.str.contains(r"over[- ]?(the[- ])?ear|on[- ]ear|in[- ]ear|earbud|ear[- ]bud")
hp_prompts["f_wireless"] = t.str.contains(r"wireless|bluetooth|cordless")
hp_prompts["f_battery"] = t.str.contains(r"battery|charge|charging")
hp_prompts["f_comfort"] = t.str.contains(r"comfort|comfy|long flight|hours")
hp_prompts["f_output_count"] = t.str.contains(
    r"\b(top|best|give me|list|recommend)\s?(the\s)?\d\b|\d\s(options|choices|recommendations|suggestions|picks|models|brands)"
)
hp_prompts["f_output_format"] = t.str.contains(r"\btable\b|\bformat\b|bullet|column|rank(ed|ing)?\b|compare.*side")
hp_prompts["f_reviews_stars"] = t.str.contains(r"\bstar\b|\bstars\b|rated|rating|review")
hp_prompts["f_usage_movies"] = t.str.contains(r"movie|video|film|netflix|show")
hp_prompts["f_usage_music"] = t.str.contains(r"music|listen|song|audio ?book|podcast")
hp_prompts["f_travel_context"] = t.str.contains(r"travel|flight|plane|airplane|trip|commut|airport")

FEATS = [c for c in hp_prompts.columns if c.startswith("f_")]
print("=== feature prevalence (of 143 headphone prompts) ===")
print(hp_prompts[FEATS].mean().round(2).sort_values(ascending=False).to_string())

# --- join to outcomes ------------------------------------------------------
resp = pd.read_csv(f"{EXP}/data/interim/responses.csv")
hp = resp[resp.intent == "headphones"].copy()
hp["bset"] = hp.brands.fillna("").str.split(r"\|").map(lambda x: frozenset(d for d in x if d))
hp = hp.merge(hp_prompts[["item_id"] + FEATS], on="item_id")

BRANDS = ["sony", "bose", "sennheiser", "anker", "apple", "jbl"]
for b in BRANDS:
    hp[f"hit_{b}"] = hp.bset.map(lambda s, b=b: b in s)

print("\n=== brand mention rate by feature (rows = feature true/false; only features with n>=15 prompts both sides) ===")
rows = []
for f in FEATS:
    n_true = hp_prompts[f].sum()
    if n_true < 15 or n_true > 143 - 15:
        continue
    g = hp.groupby(f)[[f"hit_{b}" for b in BRANDS] + ["n_brands", "n_sources"]].mean()
    delta = (g.loc[True] - g.loc[False]).round(2)
    rows.append(pd.Series(delta, name=f"{f} (n={n_true})"))
out = pd.DataFrame(rows)
out.columns = BRANDS + ["n_brands", "n_sources"]
print(out.to_string())

# --- cluster-bootstrap CI on the biggest deltas (prompt-level resample) ----
print("\n=== 90% prompt-cluster bootstrap CIs for notable feature deltas ===")
rng = np.random.default_rng(20260716)


def boot_delta(feat, brand, n_boot=2000):
    per = hp.groupby("item_id").agg(p=(f"hit_{brand}", "mean"), f=(feat, "first"))
    a = per[per.f].p.to_numpy()
    b = per[~per.f].p.to_numpy()
    obs = a.mean() - b.mean()
    draws = [
        rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean()
        for _ in range(n_boot)
    ]
    lo, hi = np.quantile(draws, [0.05, 0.95])
    return obs, lo, hi


for feat, brand in [
    ("f_budget_specific", "apple"), ("f_budget_specific", "anker"),
    ("f_budget_specific", "sony"), ("f_value_language", "apple"),
    ("f_value_language", "anker"), ("f_noise_cancel", "sony"),
    ("f_noise_cancel", "anker"), ("f_usage_movies", "apple"),
    ("f_recipient_named", "apple"), ("f_output_count", "jbl"),
]:
    if feat in hp.columns:
        obs, lo, hi = boot_delta(feat, brand)
        sig = "*" if lo > 0 or hi < 0 else " "
        print(f"{feat:20s} -> {brand:10s} delta={obs:+.2f} [{lo:+.2f},{hi:+.2f}] {sig}")

# --- does sharing a feature profile raise between-prompt overlap? ----------
print("\n=== between-prompt brand Jaccard: feature-profile similarity vs overlap ===")
per_item = hp_prompts.set_index("item_id")[FEATS].astype(int)
items = hp.item_id.unique()
# mean per-prompt brand set per wave pairing is heavy; sample pairs same-wave
from itertools import combinations

vals = {"same": [], "diff": []}
sets_by = hp.set_index(["item_id", "wave"]).bset
waves = sorted(hp.wave.unique())
key_feats = ["f_budget_specific", "f_value_language", "f_noise_cancel", "f_form_factor"]
for w in waves:
    sub = hp[hp.wave == w].set_index("item_id")
    ids = sub.index.tolist()
    for i, j in combinations(ids, 2):
        si, sj = sub.bset[i], sub.bset[j]
        if not si and not sj:
            continue
        jac = len(si & sj) / len(si | sj)
        match = (per_item.loc[i, key_feats] == per_item.loc[j, key_feats]).sum()
        vals.setdefault(match, []).append(jac)
for k in sorted([k for k in vals if isinstance(k, (int, np.integer))]):
    v = vals[k]
    print(f"matching key features {k}/4: mean brand Jaccard {np.mean(v):.3f} (n={len(v)} pairs)")
