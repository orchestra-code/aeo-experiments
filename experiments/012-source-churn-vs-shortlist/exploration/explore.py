"""Exploratory, NOT pre-registered: cited sources vs the shortlist, run to run.

Reads existing data only: experiment 010's Stage 1 answer frame (new collection
waves 1 to 7, holdouts) and the raw responses behind it. Stage 2 waves (8 and up)
are never opened. Same answers, same pairs and same pooled Dice with a
prompt-level cluster bootstrap as 010's Stage 1, so source and shortlist numbers
share a scale.

Domain labels: automatic name match against the brands named in the panel, then
data/raw/domain_overrides.csv (gitignored, names domains). Writes
results/exploration.md and results/exploration.json (aggregates only).

Usage: uv run python experiments/012-source-churn-vs-shortlist/exploration/explore.py
"""
from __future__ import annotations

import csv
import importlib.util
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

HERE = Path(__file__).resolve().parents[1]
EXP = HERE.parent
E10 = EXP / "010-shortlist-stability"
sys.path.insert(0, str(E10 / "pipeline"))


def _load(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    sys.modules[name] = m
    s.loader.exec_module(m)
    return m


cm = _load(E10 / "pipeline/common.py", "common")
reg = _load(EXP / "002-prompt-consistency/pipeline/common.py", "c002").registered_domain

SEED, NB, ALPHA = 20261003, 2000, 0.10
EXCLUDE = {"google.com"}  # Gemini shopping cards link to google.com/search; not a source
OVERRIDES = {r["domain"]: r["label"] for r in csv.DictReader((HERE / "data/raw/domain_overrides.csv").open())}
PANELS = [("chatgpt_b2b", None, "ChatGPT"), ("gemini_b2b", None, "Gemini"),
          ("claude_api_b2b", None, "Claude API"), ("claude_b2b", "ui_default", "claude.ai")]
GENERAL = [("chatgpt_consumer", None, "ChatGPT, headphones"), ("chatgpt_agency", None, "ChatGPT, agencies")]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().removeprefix("x:"))


def urlkey(u):
    p = urlsplit(u)
    return p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")


def clean(urls):
    urls = [u for u in urls if u]
    return {reg(u) for u in urls} - EXCLUDE, {urlkey(u) for u in urls if reg(u) not in EXCLUDE}


def load_new():
    out = {}
    for p in ("chatgpt", "gemini"):
        rec = {}
        for line in (E10 / f"data/raw/ledger_main_{p}.jsonl").read_text().splitlines():
            r = json.loads(line)
            rec.setdefault(r["task_id"], {}).update(r)
        for tid, r in rec.items():
            if r.get("status") != "collected" or int(r["wave"]) > 7:
                continue
            f = E10 / f"data/raw/responses_main_{p}/w{r['wave']}/{tid}.json"
            if f.exists():
                d = json.loads(f.read_text())
                dom, url = clean([s.get("url") for s in d.get("sources") or []])
                ret = {reg(s["url"]) for s in d.get("search_results") or [] if s.get("url")} - EXCLUDE
                out[(f"{p}_b2b", r["item_id"], int(r["wave"]))] = dict(dom=dom, url=url, ret=ret, model=d.get("model"))
    for w in range(1, 8):
        for f in (E10 / f"data/raw/responses_main_claude/w{w}/opus55_plain").glob("*.json"):
            n = json.loads(f.read_text())["normalized"]
            dom, url = clean(n["cited_urls"])
            out[("claude_api_b2b", f.stem, w)] = dict(dom=dom, url=url, ret={reg(u) for u in n["evaluated_urls"]} - EXCLUDE,
                                                      model=n["model"], n_search=n["n_searches"])
    return out


def load_holdout():
    out = {}
    for r in cm.read_jsonl(EXP / "009-claude-model-fidelity/data/interim/features.jsonl"):
        if r["arm"] in ("ui_default", "ui_think"):
            out[("claude_b2b", r["arm"], r["item_id"], int(r["wave"]))] = dict(
                dom=set(r["cited_domains"]) - EXCLUDE, url=set(), ret=set(r["evaluated_domains"] or []) - EXCLUDE,
                n_search=r["n_searches"] or 0)
    for exp in ("002-prompt-consistency", "003-synthetic-prompt-coverage", "005-subintent-matched-panels"):
        with (EXP / exp / "data/interim/responses.csv").open() as fh:
            for r in csv.DictReader(fh):
                if (r.get("arm") or "hum") not in ("hum", "coffee"):
                    continue
                ds = "chatgpt_consumer" if r["intent"] == "headphones" else "chatgpt_agency"
                out[(ds, exp[:3], r["item_id"], int(r["wave"]))] = dict(
                    dom={x for x in (r["domains"] or "").split("|") if x} - EXCLUDE,
                    url={urlkey(x) for x in (r["urls"] or "").split("|") if x}, ret=set())
    return out


answers = [a for a in cm.read_jsonl(E10 / "data/interim/stage1_answers.jsonl") if cm.usable(a)]
assert max(a["wave"] for a in answers if a["source_exp"] == "010") <= 7, "Stage 2 waves must stay unread"
new, hold = load_new(), load_holdout()
kept = []
for a in answers:
    cm.derive(a, None)
    ds = a["dataset"]
    if a["source_exp"] == "010":
        c = new.get((ds, a["item_id"], a["wave"]))
    elif ds == "claude_b2b":
        c = hold.get((ds, a["arm"], a["item_id"], a["wave"]))
    else:
        c = hold.get((ds, a["source_exp"], a["item_id"], a["wave"]))
    if c is not None:
        a["cit"] = c
        kept.append(a)

brandkeys = {norm(b) for a in kept if a["dataset"] in cm.B2B_DATASETS for b in a["all_order"]}
longkeys = {k for k in brandkeys if len(k) >= 5}
PFX, SFX = ("get", "try", "use", "go"), ("hq", "app", "inc")


def auto_vendor(d):
    lab = norm(d.split(".")[0])
    return (lab in brandkeys
            or any(lab.startswith(p) and lab[len(p):] in brandkeys for p in PFX)
            or any(lab.endswith(s) and lab[:-len(s)] in brandkeys for s in SFX)
            or (len(lab) >= 5 and any(lab in k for k in longkeys)))


def is_vendor(d):
    if d in OVERRIDES:
        return OVERRIDES[d] == "vendor"
    return auto_vendor(d)


for a in kept:
    c, S = a["cit"], a["S"]
    S["dom"], S["url"], S["ret"] = c["dom"], c["url"], c["ret"]
    S["third"] = {d for d in c["dom"] if not is_vendor(d)}
    S["vendor"] = {d for d in c["dom"] if is_vendor(d)}
    S["third_auto"] = {d for d in c["dom"] if not auto_vendor(d)}
    S["ret3"] = {d for d in c["ret"] if not is_vendor(d)}
    S["retv"] = {d for d in c["ret"] if is_vendor(d)}


def dice(x, y):
    return 2 * len(x & y), len(x) + len(y)


def jac(x, y):
    u = x | y
    return len(x & y) / len(u) if u else np.nan


def panel(ds, arm, keep=lambda a: True):
    return [a for a in kept if a["dataset"] == ds and (arm is None or a["arm"] == arm) and keep(a)]


def within(ans):
    g = defaultdict(list)
    for a in ans:
        g[a["item_id"]].append(a)
    return [(i, x, y) for i, l in g.items() for x, y in itertools.combinations(l, 2) if cm.run_key(x) != cm.run_key(y)]


def between(ans):
    g = defaultdict(list)
    for a in ans:
        g[(cm.run_key(a), a["category"])].append(a)
    return [(x["item_id"], x, y) for l in g.values() for x, y in itertools.combinations(l, 2) if x["item_id"] != y["item_id"]]


def weights(n):
    return np.random.default_rng(SEED).multinomial(n, np.full(n, 1 / n), size=NB).astype(float)


def boot(pairs, keys, items):
    idx = {u: i for i, u in enumerate(items)}
    W = weights(len(items))
    res = {}
    for k in keys:
        n, d = np.zeros(len(items)), np.zeros(len(items))
        for i, x, y in pairs:
            a, b = dice(x["S"][k], y["S"][k])
            n[idx[i]] += a
            d[idx[i]] += b
        den = W @ d
        res[k] = (float(n.sum() / d.sum()) if d.sum() else float("nan"), (W @ n) / np.where(den > 0, den, np.nan))
    return res


def ci(v):
    return [float(x) for x in np.nanquantile(v, [ALPHA / 2, 1 - ALPHA / 2])]


def pooled(pairs, k):
    t = np.sum([dice(x["S"][k], y["S"][k]) for _, x, y in pairs], axis=0)
    return float(t[0] / t[1])


out, md = {"panels": {}}, ["# Experiment 012 exploration: cited sources vs the shortlist", "",
                           "Exploratory, not pre-registered. Existing data only; 010 Stage 2 waves unread. Aggregates only. Generated by `exploration/explore.py`.", ""]

# 1 levels
md += ["## 1. Share repeated between two runs of a prompt (pooled Dice, 90% CI)", "",
       "| Panel | prompts / pairs | shortlist | cited, all domains | cited, vendor | cited, third party | retrieved, third party | answers with no citation |",
       "|---|---|---|---|---|---|---|---|"]
KEYS = ["R", "R_all", "M", "dom", "vendor", "third", "third_auto", "url", "ret", "ret3", "retv"]
for ds, arm, label in PANELS + GENERAL:
    ans = panel(ds, arm)
    items = sorted({a["item_id"] for a in ans})
    p = within(ans)
    r = boot(p, KEYS, items)
    f = lambda k: f"{r[k][0]:.2f} [{ci(r[k][1])[0]:.2f}, {ci(r[k][1])[1]:.2f}]"
    b2b = ds in cm.B2B_DATASETS
    has_ret = any(a["S"]["ret"] for a in ans)
    gap3, gapr = r["R"][1] - r["third"][1], r["R"][1] - r["ret3"][1]
    vshare = sum(len(a["S"]["vendor"]) for a in ans) / max(1, sum(len(a["S"]["dom"]) for a in ans))
    named_here = 0
    for a in ans:
        names = {norm(b) for b in a["all_order"]}
        for d in a["S"]["vendor"]:
            lab = norm(d.split(".")[0])
            named_here += any(lab == n or (len(lab) >= 5 and lab in n) for n in names)
    n_vendor = sum(len(a["S"]["vendor"]) for a in ans)
    out["panels"][label] = {
        "prompts": len(items), "pairs": len(p), "answers": len(ans),
        **{k: {"est": r[k][0], "ci": ci(r[k][1])} for k in KEYS},
        "gap_R_third": {"est": r["R"][0] - r["third"][0], "ci": ci(gap3)},
        "gap_R_ret3": {"est": r["R"][0] - r["ret3"][0], "ci": ci(gapr)} if has_ret else None,
        "vendor_share": vshare, "vendor_named_same_answer": named_here / max(1, n_vendor),
        "size": {k: float(np.mean([len(a["S"][k]) for a in ans])) for k in ("R", "dom", "third", "vendor", "ret3", "retv")},
        "no_citation": sum(not a["S"]["dom"] for a in ans), "has_ret": has_ret,
    }
    md.append(f"| {label} | {len(items)} / {len(p)} | {f('R')} | {f('dom')} | {f('vendor') if b2b else 'n/a'} | {f('third') if b2b else 'n/a'} | "
              f"{f('ret3') if b2b and has_ret else 'n/a'} | {out['panels'][label]['no_citation']}/{len(ans)} |")

md += ["", "## 2. Composition", "",
       "| Panel | vendor share of cited domains | of those, vendor named in the same answer | mean per answer: shortlist / cited all / third party / retrieved third party | third party, unreviewed labels | R minus third party | R minus retrieved third party |",
       "|---|---|---|---|---|---|---|"]
for _, _, label in PANELS:
    o = out["panels"][label]
    s = o["size"]
    gr = o["gap_R_ret3"]
    md.append(f"| {label} | {o['vendor_share']:.2f} | {o['vendor_named_same_answer']:.2f} | {s['R']:.1f} / {s['dom']:.1f} / {s['third']:.1f} / {s['ret3']:.1f} | {o['third_auto']['est']:.2f} | "
              f"{o['gap_R_third']['est']:.2f} [{o['gap_R_third']['ci'][0]:.2f}, {o['gap_R_third']['ci'][1]:.2f}] | "
              + (f"{gr['est']:.2f} [{gr['ci'][0]:.2f}, {gr['ci'][1]:.2f}] |" if gr else "n/a |"))

# 3 Muck Rack scale
md += ["", "## 3. One-day gap, Jaccard and Dice (for comparison with published repeat figures)", "",
       "| Panel | domains Jaccard, one-day | domains Dice, one-day | shortlist Jaccard, one-day | shortlist Dice, one-day |", "|---|---|---|---|---|"]
out["one_day"] = {}
for ds, arm, label in PANELS + GENERAL[:1]:
    p1 = [t for t in within(panel(ds, arm)) if t[1]["source_exp"] == t[2]["source_exp"] and abs(t[1]["wave"] - t[2]["wave"]) == 1]
    J = lambda k: float(np.nanmean([jac(x["S"][k], y["S"][k]) for _, x, y in p1]))
    row = dict(dom_j=J("dom"), dom_d=pooled(p1, "dom"), R_j=J("R"), R_d=pooled(p1, "R"), pairs=len(p1))
    out["one_day"][label] = row
    md.append(f"| {label} | {row['dom_j']:.2f} | {row['dom_d']:.2f} | {row['R_j']:.2f} | {row['R_d']:.2f} |")

# 4 chance + size
md += ["", "## 4. Controls for scale", "",
       "Chance-corrected = (within - between) / (1 - between), between = different prompts, same category, platform and wave. Size-matched = shortlist thinned at random in each answer to that answer's third-party count (20 repeats).", "",
       "| Panel | third party | shortlist | shortlist size-matched | third party chance-corrected | shortlist chance-corrected | gap chance-corrected |", "|---|---|---|---|---|---|---|"]
out["controls"] = {}
for ds, arm, label in PANELS:
    ans = panel(ds, arm)
    items = sorted({a["item_id"] for a in ans})
    pw, pb = within(ans), between(ans)
    w, b = boot(pw, ["R", "third"], items), boot(pb, ["R", "third"], items)
    cc = lambda k: (w[k][0] - b[k][0]) / (1 - b[k][0])
    ccd = lambda k: (w[k][1] - b[k][1]) / (1 - b[k][1])
    lo, hi = ci(ccd("R") - ccd("third"))
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(20):
        th = {}
        for a in ans:
            rr = sorted(a["S"]["R"])
            kk = min(len(a["S"]["third"]), len(rr))
            th[a["task_id"]] = set(rng.choice(rr, kk, replace=False)) if kk else set()
        t = np.sum([dice(th[x["task_id"]], th[y["task_id"]]) for _, x, y in pw], axis=0)
        vals.append(t[0] / t[1])
    out["controls"][label] = dict(size_matched=float(np.mean(vals)), cc_third=cc("third"), cc_R=cc("R"), cc_gap=[cc("R") - cc("third"), lo, hi])
    md.append(f"| {label} | {w['third'][0]:.2f} | {w['R'][0]:.2f} | {np.mean(vals):.2f} | {cc('third'):.2f} | {cc('R'):.2f} | {cc('R')-cc('third'):.2f} [{lo:.2f}, {hi:.2f}] |")

# 5 coupling
md += ["", "## 5. Inside one prompt, does the shortlist move when third-party sources move?", "",
       "Prompt means removed. Swing = predicted change in shortlist Jaccard from the 10th to the 90th percentile of within-prompt source change. No-shared = shortlist Jaccard in pairs sharing no third-party domain minus pairs sharing at least one, same prompt, prompts with both kinds only.", "",
       "| Panel | sources | slope | shortlist swing | no-shared minus shared | prompts / no-shared pairs |", "|---|---|---|---|---|---|"]
out["coupling"] = {}
for ds, arm, label, keep in [(d, a, l, lambda a: True) for d, a, l in PANELS] + [("chatgpt_b2b", None, "ChatGPT, gpt-5-6 only", lambda a: a["cit"]["model"] == "gpt-5-6")]:
    ans = panel(ds, arm, keep)
    items = sorted({a["item_id"] for a in ans})
    p = within(ans)
    W = weights(len(items))
    for k, kl in (("dom", "all"), ("third", "third party")):
        rows = [(i, jac(x["S"][k], y["S"][k]), jac(x["S"]["R"], y["S"]["R"]), len(x["S"][k] & y["S"][k]))
                for i, x, y in p if x["S"][k] and y["S"][k] and x["S"]["R"] and y["S"]["R"]]
        ids = np.array([r[0] for r in rows])
        sx, ry, sh = (np.array([r[j] for r in rows]) for j in (1, 2, 3))
        dx, dy = sx.copy(), ry.copy()
        for u in items:
            m = ids == u
            if m.any():
                dx[m] -= sx[m].mean()
                dy[m] -= ry[m].mean()
        slope = float(dx @ dy / (dx @ dx))
        n = np.array([dx[ids == u] @ dy[ids == u] for u in items])
        d = np.array([dx[ids == u] @ dx[ids == u] for u in items])
        lo, hi = ci((W @ n) / np.where(W @ d > 0, W @ d, np.nan))
        sw = float(np.quantile(dx, .9) - np.quantile(dx, .1))
        diffs = np.full(len(items), np.nan)
        for j, u in enumerate(items):
            m = ids == u
            z, nz = ry[m & (sh == 0)], ry[m & (sh > 0)]
            if len(z) and len(nz):
                diffs[j] = z.mean() - nz.mean()
        ok = ~np.isnan(diffs)
        est = float(diffs[ok].mean()) if ok.any() else float("nan")
        cl, ch = ci((W[:, ok] @ diffs[ok]) / np.where(W[:, ok].sum(1) > 0, W[:, ok].sum(1), np.nan)) if ok.any() else (float("nan"), float("nan"))
        out["coupling"][f"{label}|{k}"] = dict(slope=[slope, lo, hi], swing=slope * sw, no_shared=[est, cl, ch], prompts=int(ok.sum()), no_shared_pairs=int((sh == 0).sum()))
        md.append(f"| {label} | {kl} | {slope:.2f} [{lo:.2f}, {hi:.2f}] | {slope*sw:.2f} | {est:.2f} [{cl:.2f}, {ch:.2f}] | {int(ok.sum())} / {int((sh==0).sum())} |")

# 6 no search
md += ["", "## 6. Answers with no web search (exp 009 features, mentioned brands, all 40 prompts)", "",
       "| Arm | no-search answers | both searched | one searched | neither | same prompt: one searched minus both searched | prompts |", "|---|---|---|---|---|---|---|"]
out["no_search"] = {}
for arm in ("ui_default", "sonnet5_leak_low"):
    g = defaultdict(list)
    for r in cm.read_jsonl(EXP / "009-claude-model-fidelity/data/interim/features.jsonl"):
        if r["arm"] == arm and not r["empty_answer"] and not r["refusal"]:
            g[r["item_id"]].append(r)
    tally, per = defaultdict(lambda: np.zeros(2)), []
    for l in g.values():
        v = defaultdict(list)
        for x, y in itertools.combinations(l, 2):
            bx, by = set(x["brands"]), set(y["brands"])
            s = int((x["n_searches"] or 0) > 0) + int((y["n_searches"] or 0) > 0)
            tally[s] += dice(bx, by)
            if bx or by:
                v[s].append(2 * len(bx & by) / (len(bx) + len(by)))
        if v[2] and v[1]:
            per.append(np.mean(v[1]) - np.mean(v[2]))
    c = np.array(per)
    rng = np.random.default_rng(SEED)
    lo, hi = ci(np.array([rng.choice(c, len(c)).mean() for _ in range(NB)]))
    fm = lambda k: float(tally[k][0] / tally[k][1]) if tally[k][1] else None
    nos = sum((r["n_searches"] or 0) == 0 for l in g.values() for r in l)
    out["no_search"][arm] = dict(no_search=nos, both=fm(2), one=fm(1), neither=fm(0), diff=[float(c.mean()), lo, hi], prompts=len(c))
    md.append(f"| {arm} | {nos} | {fm(2):.2f} | {fm(1):.2f} | {fm(0):.2f} | {c.mean():.2f} [{lo:.2f}, {hi:.2f}] | {len(c)} |")

# 7 robustness
md += ["", "## 7. Robustness", ""]
for tag, keep in (("gpt-5-6 only, waves 1 to 5", lambda a: a["cit"]["model"] == "gpt-5-6"), ("gpt-6 only, waves 6 and 7", lambda a: a["cit"]["model"] != "gpt-5-6")):
    p = within(panel("chatgpt_b2b", None, keep))
    md.append(f"- ChatGPT, {tag}: shortlist {pooled(p,'R'):.2f}, all domains {pooled(p,'dom'):.2f}, third party {pooled(p,'third'):.2f}, retrieved third party {pooled(p,'ret3'):.2f}")
for ds, arm, label in PANELS:
    p = [t for t in within(panel(ds, arm)) if t[1]["S"]["dom"] and t[2]["S"]["dom"]]
    md.append(f"- {label}, pairs where both answers cite something ({len(p)}): shortlist {pooled(p,'R'):.2f}, domains {pooled(p,'dom'):.2f}, third party {pooled(p,'third'):.2f}")

# 8 precision for the spec
md += ["", "## 8. Interval widths for the spec's power section", "",
       "90% half-width on this data, resampling prompts. Within-run placebo = shortlist retention on runs {1,2,3} minus runs {4,5,6}, a stand-in for any arm contrast.", "",
       "| Panel | shortlist minus retrieved third party, 7 runs | same, 3 runs | same, 7 runs, 20 prompts | placebo contrast half-width, 40 prompts, 3 runs per arm |", "|---|---|---|---|---|"]
out["precision"] = {}
hw = lambda v: float((np.nanquantile(v, .95) - np.nanquantile(v, .05)) / 2)
for ds, arm, label in (PANELS[0], PANELS[2]):
    ans = panel(ds, arm)
    items = sorted({a["item_id"] for a in ans})
    a7 = boot(within(ans), ["R", "ret3"], items)
    a3 = boot(within([a for a in ans if a["wave"] <= 3]), ["R", "ret3"], items)
    sub = items[:20]
    a20 = boot(within([a for a in ans if a["item_id"] in sub]), ["R", "ret3"], sub)
    o1 = boot(within([a for a in ans if a["wave"] <= 3]), ["R"], items)["R"][1]
    o2 = boot(within([a for a in ans if 4 <= a["wave"] <= 6]), ["R"], items)["R"][1]
    row = dict(h7=hw(a7["R"][1] - a7["ret3"][1]), h3=hw(a3["R"][1] - a3["ret3"][1]), h20=hw(a20["R"][1] - a20["ret3"][1]), placebo=hw(o1 - o2))
    out["precision"][label] = row
    md.append(f"| {label} | {row['h7']:.3f} | {row['h3']:.3f} | {row['h20']:.3f} | {row['placebo']:.3f} |")

(HERE / "results/exploration.md").write_text("\n".join(md) + "\n")
(HERE / "results/exploration.json").write_text(json.dumps(out, indent=1))

rows = Counter(d for a in kept if a["dataset"] in cm.B2B_DATASETS for d in a["S"]["dom"])
with (HERE / "data/raw/domain_labels.csv").open("w") as fh:
    w = csv.writer(fh)
    w.writerow(["domain", "appearances", "auto_vendor", "final_vendor"])
    for d, n in rows.most_common():
        w.writerow([d, n, int(auto_vendor(d)), int(is_vendor(d))])
print("\n".join(md))
