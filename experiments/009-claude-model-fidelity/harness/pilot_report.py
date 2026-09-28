"""Experiment 009 pilot report: brands, overlap vs the UI, noise floor, power.

Reads every normalized response under ``data/raw/pilot_responses/w<wave>/<arm>/``
(API arms from ``collect_anthropic.py``, ``ui_default`` from
``ingest_claude_export.py``) and the pilot ledger.

1. **Brand candidates.** claude-haiku-4-5 reads each answer once (structured
   output, ``output_config.format`` with a JSON schema) and lists the vendor or
   product brands the answer presents as options or mentions as alternatives,
   in order of first mention. Results are cached in
   ``data/raw/pilot_brand_candidates.jsonl`` keyed by (arm, item_id, wave,
   answer_sha256), so a rerun costs nothing. Names are canonicalized
   (:func:`canonical_brand`) and pooled into ``data/raw/lexicon_draft.csv``
   for human curation. This is a pilot instrument; the confirmatory lexicon is
   curated and frozen before wave 1.
2. **Overlap per arm**, against ``ui_default`` and against ``opus55_leak``,
   computed per prompt (same prompt, wave 0) and averaged over prompts: brand
   Jaccard (all brands), top-10 brand Jaccard, RBO of the brand order, cited
   registered-domain Jaccard, evaluated registered-domain Jaccard, grounding
   query token Jaccard. Plus searches, cited and evaluated counts, answer
   length and $/call from the ledger.
3. **Noise floor**: the same metrics within arm, wave 0 vs the same-day repeat
   (wave 90), for the arms that were repeated.
4. **Power simulation** for the confirmatory design (40 prompts, 3 waves,
   reference ``ui_default``; gap = J_within(ui) - J_cross(arm, ui); TOST band
   +/-0.10, 90% CI, prompt-level cluster bootstrap via
   ``aeo_research.overlap.cluster_boot``).
5. Writes ``results/pilot_report.md`` (tracked, so aggregates only: no prompt,
   answer, query or brand text) and prints the tables.

Usage (repo root):
    uv run python experiments/009-claude-model-fidelity/harness/pilot_report.py \
        [--env-file ...] [--no-extract] [--reps 300]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import re
import sys
import threading
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parents[1]
RAW = EXP / "data" / "raw"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(EXP / "pipeline"))

from aeo_research.overlap import cluster_boot, jaccard, rbo, token_set  # noqa: E402
from aeo_research.pricing import cost_from_usage  # noqa: E402
from aeo_research.stats import Verdict  # noqa: E402
from shares import build_cells, share_excess  # noqa: E402
from shares import power as share_power  # noqa: E402

RESPONSES = RAW / "pilot_responses"
LEDGER = RAW / "pilot_ledger.jsonl"
CACHE = RAW / "pilot_brand_candidates.jsonl"
LEXICON = RAW / "lexicon_draft.csv"
REPORT = EXP / "results" / "pilot_report.md"

EXTRACT_MODEL = "claude-haiku-4-5"
REFERENCES = ("ui_default", "opus55_leak")
BASE_WAVE = 0
REPEAT_WAVE = 90
SESOI = 0.10
ALPHA = 0.10
TOP_K = 10

# ------------------------------------------------------------ URL normalization
# Same rules as the 002/003/005 pipelines' common.py (normalize_url,
# registered_domain), copied because experiment pipelines are scripts, not
# importable library code.

TRACKING_PARAMS = re.compile(r"^(utm_\w+|gclid|fbclid|msclkid|ref|ref_src|src|si|feature)$", re.I)
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    netloc = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), query, ""))


def registered_domain(url_or_host: str) -> str:
    host = url_or_host
    if "//" in host:
        host = urlsplit(host).netloc
    host = host.lower().removeprefix("www.").split(":")[0]
    labels = [p for p in host.split(".") if p]
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def domains(urls: list[str]) -> set[str]:
    return {registered_domain(normalize_url(u)) for u in urls if u}


# ------------------------------------------------------------ brand canon

#: Product lines collapsed to their vendor (brand-level overlap). A starting
#: point for the curated lexicon, not a frozen list.
PARENT_PREFIXES = (
    "hubspot", "salesforce", "zoho", "microsoft dynamics", "oracle netsuite", "netsuite",
    "sap", "adobe", "datadog", "new relic", "dynatrace", "zendesk", "freshworks",
    "freshdesk", "freshservice", "atlassian", "jira", "oracle", "workday", "adp", "sage",
    "docusign", "google", "microsoft", "amazon", "aws", "ibm", "servicenow", "splunk",
    "okta", "crowdstrike", "sentinelone", "paychex", "ukg", "intuit", "quickbooks",
)
#: Exact rewrites after normalization.
ALIASES = {
    "microsoft dynamics 365": "microsoft dynamics",
    "dynamics 365": "microsoft dynamics",
    "business central": "microsoft dynamics",
    "netsuite": "oracle netsuite",
    "microsoft defender for endpoint": "microsoft defender",
    "defender for endpoint": "microsoft defender",
    "microsoft entra id": "microsoft entra",
    "entra id": "microsoft entra",
    "azure ad": "microsoft entra",
    "azure active directory": "microsoft entra",
    "google bigquery": "bigquery",
    "amazon redshift": "redshift",
    "aws redshift": "redshift",
    "bill.com": "bill",
    "adobe acrobat sign": "adobe sign",
    "dropbox sign (hellosign)": "dropbox sign",
    "hellosign": "dropbox sign",
    "sap concur": "concur",
    "grafana cloud": "grafana",
    "elastic observability": "elastic",
    "google analytics 4": "google analytics",
    "tempo": "grafana",
    "pyroscope": "grafana",
}
#: Names the extractor still returns despite its instructions: standards,
#: open-source projects and sources. Dropped after canonicalization.
EXCLUDE = frozenset({
    "opentelemetry", "otel", "prometheus", "jaeger", "kubernetes", "ebpf", "soc 2", "hipaa",
    "saml", "scim", "oauth", "openid connect", "gdpr", "iso 27001", "g2", "capterra",
    "gartner", "forrester", "trustradius", "reddit", "software advice", "getapp",
})
#: Trailing words dropped when they only name the category.
SUFFIXES = ("apm", "crm", "erp", "cpq", "clm", "ats", "hris", "edr", "xdr", "sso",
            "software", "platform", "inc", "inc.", "llc", "ltd", "corp")


def canonical_brand(name: str) -> str:
    """Case- and form-insensitive key for a brand name.

    NFKC + lowercase (the ``aeo_research.brand_match`` term key), trademark
    signs and parentheticals dropped, category suffixes stripped, then the
    alias map and the vendor-prefix collapse.
    """
    s = unicodedata.normalize("NFKC", name).lower()
    s = re.sub(r"[®™©]", "", s)
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .,:;-")
    s = ALIASES.get(s, s)
    words = s.split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    s = " ".join(words)
    s = ALIASES.get(s, s)
    for parent in sorted(PARENT_PREFIXES, key=len, reverse=True):
        if s == parent or s.startswith(parent + " "):
            return ALIASES.get(parent, parent)
    return s


def ordered_unique(items):
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ------------------------------------------------------------ loading


def load_responses() -> pd.DataFrame:
    rows = []
    for path in sorted(RESPONSES.glob("w*/*/*.json")):
        wave = int(path.parent.parent.name[1:])
        d = json.loads(path.read_text())
        n = d["normalized"]
        rows.append({
            "arm": path.parent.name,
            "item_id": path.stem,
            "wave": wave,
            "answer_text": n.get("answer_text") or "",
            "cited_urls": n.get("cited_urls") or [],
            "evaluated_urls": n.get("evaluated_urls") or [],
            "search_queries": n.get("search_queries") or [],
            "n_searches": n.get("n_searches") or 0,
            "n_fetches": n.get("n_fetches") or 0,
        })
    df = pd.DataFrame(rows)
    with (RAW / "prompts.csv").open(newline="") as f:
        category = {r["item_id"]: r["category"] for r in csv.DictReader(f)}
    df["category"] = df["item_id"].map(category)
    df["answer_sha256"] = df["answer_text"].map(lambda t: hashlib.sha256(t.encode()).hexdigest())
    return df


def ledger_costs() -> pd.DataFrame:
    recs = [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]
    df = pd.DataFrame(recs).groupby("task_id", as_index=False).last()
    df = df[df["status"] == "collected"]
    return df[["arm", "item_id", "wave", "cost_usd", "mode"]]


# ------------------------------------------------------------ extraction

EXTRACT_SYSTEM = (
    "You extract brand names from an AI assistant's answer to a business software "
    "buyer shopping in one software category. List every vendor or product brand in "
    "that category that the answer presents as an option, recommends, compares, or "
    "mentions as an alternative, in the order each is first mentioned. Use the name as "
    "written in the answer. Exclude: brands from other categories that appear only as "
    "integrations, add-ons, or the buyer's other systems; publishers, review "
    "sites, analysts and other sources (for example review marketplaces, research "
    "firms, news sites, forums); standards, protocols, regulations and certifications; "
    "open-source projects that are not sold as a product by a vendor; generic "
    "category terms; and the buyer's own existing systems when described generically. "
    "If the answer names no brands, return an empty list."
)
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"brands": {"type": "array", "items": {"type": "string"}}},
    "required": ["brands"],
    "additionalProperties": False,
}


def cache_key(r) -> str:
    return f"{r['arm']}|{r['item_id']}|{r['wave']}|{r['answer_sha256']}"


def load_cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    out = {}
    for line in CACHE.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["key"]] = rec
    return out


def extract_brands(client, answer: str, category: str) -> tuple[list[str], dict]:
    msg = client.messages.create(
        model=EXTRACT_MODEL,
        max_tokens=2000,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content":
                   f"Software category: {category}\n\n<answer>\n{answer}\n</answer>"}],
        output_config={"format": {"type": "json_schema", "schema": EXTRACT_SCHEMA}},
    )
    text = next(b.text for b in msg.content if b.type == "text")
    brands = [b.strip() for b in json.loads(text)["brands"] if b and b.strip()]
    return brands, msg.usage.to_dict()


def fill_cache(df: pd.DataFrame, env_file: str) -> float:
    cache = load_cache()
    todo = [r for r in df.to_dict("records") if cache_key(r) not in cache and r["answer_text"]]
    if not todo:
        return 0.0
    from anthropic_client import make_client

    client = make_client(env_file)
    lock = threading.Lock()
    spent = [0.0]

    def work(r):
        brands, usage = extract_brands(client, r["answer_text"], r["category"])
        cost = cost_from_usage(EXTRACT_MODEL, usage)["total"]
        rec = {"key": cache_key(r), "arm": r["arm"], "item_id": r["item_id"], "wave": r["wave"],
               "answer_sha256": r["answer_sha256"], "model": EXTRACT_MODEL, "brands": brands,
               "usage": usage, "cost_usd": cost,
               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with lock:
            with CACHE.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            spent[0] += cost

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, todo))
    print(f"extracted brands for {len(todo)} answers (${spent[0]:.4f})")
    return spent[0]


def attach_brands(df: pd.DataFrame) -> pd.DataFrame:
    cache = load_cache()
    raw, canon = [], []
    for r in df.to_dict("records"):
        names = cache.get(cache_key(r), {}).get("brands", [])
        raw.append(names)
        canon.append(ordered_unique(c for c in (canonical_brand(n) for n in names)
                                    if c not in EXCLUDE))
    df = df.copy()
    df["brands_raw"] = raw
    df["brands"] = canon
    return df


def write_lexicon(df: pd.DataFrame) -> int:
    aliases: dict[str, set] = defaultdict(set)
    answers: dict[str, set] = defaultdict(set)
    arms: dict[str, set] = defaultdict(set)
    for r in df.to_dict("records"):
        for name in r["brands_raw"]:
            c = canonical_brand(name)
            if c in EXCLUDE:
                continue
            aliases[c].add(name)
            answers[c].add((r["arm"], r["item_id"], r["wave"]))
            arms[c].add(r["arm"])
    rows = sorted(aliases, key=lambda c: (-len(answers[c]), c))
    with LEXICON.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical", "aliases", "n_answers", "arms_seen"])
        for c in rows:
            w.writerow([c, "|".join(sorted(aliases[c])), len(answers[c]),
                        "|".join(sorted(arms[c]))])
    return len(rows)


# ------------------------------------------------------------ lexicon v0
# data/raw/lexicon_v0.csv (curation rules: harness/lexicon_rules.md) holds one
# row per (vendor, prompt category): aliases, keep|drop, match mode (ci/cs).
# Deterministic extraction follows 003's brands.extract_brands: markdown
# links and markup stripped, longest alias first, word boundaries, order of
# first mention. Matched spans are consumed (so a longer alias shadows a
# shorter one inside it), and drop rows consume their spans without counting.

LEXICON_V0 = RAW / "lexicon_v0.csv"
_MD_URL = re.compile(r"\((?:https?|www)[^)]*\)|https?://\S+")
_MD_MARKUP = re.compile(r"[*_#>`]")


def load_lexicon(path: Path = LEXICON_V0) -> dict[str, list[tuple[re.Pattern, str, bool]]]:
    """category -> [(pattern, canonical, keep)], longest alias first."""
    by_cat: dict[str, list[tuple[str, str, bool, bool]]] = defaultdict(list)
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            for alias in row["aliases"].split("|"):
                if alias.strip():
                    by_cat[row["category"]].append(
                        (alias.strip(), row["canonical"], row["decision"] == "keep",
                         row["match"] == "cs"))
    out = {}
    for cat, entries in by_cat.items():
        entries = sorted(set(entries), key=lambda e: len(e[0]), reverse=True)
        out[cat] = [
            (re.compile(rf"(?<![\w&]){re.escape(a)}(?![\w&])", 0 if cs else re.I), canon, keep)
            for a, canon, keep, cs in entries
        ]
    return out


#: A "Sources" / "Sources referenced" label (heading, bold or plain) that ends
#: its line or is followed by a colon. The production discovery prompt asks
#: for the sources consulted, so sonnet5_prod answers end with one (deviation 3).
_SOURCES_LABEL = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*sources?(?:[ \t]+(?:referenced|consulted|cited|used))?"
    r"[ \t]*(?::\**|\**:|\**[ \t]*$)",
    re.I | re.M,
)
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+•]|\d+[.)])[ \t]")


def strip_sources(text: str) -> str:
    """Drop each sources block: the label line and the list items after it."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if _SOURCES_LABEL.match(lines[i]):
            i += 1
            while i < len(lines) and (not lines[i].strip() or _LIST_ITEM.match(lines[i])):
                i += 1
            out.append("")
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def lexicon_extract(text: str, patterns) -> list[str]:
    text = _MD_MARKUP.sub(" ", _MD_URL.sub(" ", strip_sources(text)))
    taken = np.zeros(len(text) + 1, dtype=bool)
    first: dict[str, int] = {}
    for pattern, canon, keep in patterns:
        for m in pattern.finditer(text):
            if taken[m.start():m.end()].any():
                continue
            taken[m.start():m.end()] = True
            if keep and (canon not in first or m.start() < first[canon]):
                first[canon] = m.start()
    return sorted(first, key=first.get)


def haiku_via_lexicon(raw_names: list[str], category: str, alias_map) -> list[str]:
    """Haiku candidates mapped through lexicon v0 (merges and drops applied)."""
    out = []
    for name in raw_names:
        hit = alias_map.get((category, name.strip().lower()))
        if hit and hit[1]:
            out.append(hit[0])
    return ordered_unique(out)


def lexicon_alias_map(path: Path = LEXICON_V0) -> dict[tuple[str, str], tuple[str, bool]]:
    amap = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            for alias in row["aliases"].split("|"):
                amap[(row["category"], alias.strip().lower())] = (
                    row["canonical"], row["decision"] == "keep")
    return amap


def brand_versions(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Three brand columns: Haiku canonical (draft), Haiku via v0, lexicon v0."""
    versions = {"haiku_draft": df}
    if not LEXICON_V0.exists():
        return versions
    pats, amap = load_lexicon(), lexicon_alias_map()
    via = df.copy()
    via["brands"] = [haiku_via_lexicon(r["brands_raw"], r["category"], amap)
                     for r in df.to_dict("records")]
    lex = df.copy()
    lex["brands"] = [lexicon_extract(r["answer_text"], pats.get(r["category"], []))
                     for r in df.to_dict("records")]
    versions["haiku_via_v0"] = via
    versions["lexicon_v0"] = lex
    return versions


# ------------------------------------------------------------ metrics

METRICS = ("brand_j", "top10_j", "brand_rbo", "cited_dom_j", "eval_dom_j", "query_j")


def pair_metrics(a: dict, b: dict) -> dict:
    return {
        "brand_j": jaccard(set(a["brands"]), set(b["brands"])),
        "top10_j": jaccard(set(a["brands"][:TOP_K]), set(b["brands"][:TOP_K])),
        "brand_rbo": rbo(a["brands"], b["brands"]),
        "cited_dom_j": jaccard(domains(a["cited_urls"]), domains(b["cited_urls"])),
        "eval_dom_j": jaccard(domains(a["evaluated_urls"]), domains(b["evaluated_urls"])),
        "query_j": jaccard(token_set(a["search_queries"]), token_set(b["search_queries"])),
    }


def per_prompt(df: pd.DataFrame, arm: str, ref: str, wave_a=BASE_WAVE, wave_b=BASE_WAVE):
    a = df[(df.arm == arm) & (df.wave == wave_a)].set_index("item_id")
    b = df[(df.arm == ref) & (df.wave == wave_b)].set_index("item_id")
    items = sorted(set(a.index) & set(b.index))
    rows = [{"item_id": i, **pair_metrics(a.loc[i].to_dict(), b.loc[i].to_dict())} for i in items]
    return pd.DataFrame(rows)


def overlap_table(df: pd.DataFrame, ref: str) -> pd.DataFrame:
    out = []
    for arm in sorted(df.arm.unique()):
        if arm == ref:
            continue
        pp = per_prompt(df, arm, ref)
        if pp.empty:
            continue
        out.append({"arm": arm, "n": len(pp), **{m: pp[m].mean() for m in METRICS}})
    return pd.DataFrame(out)


def descriptives(df: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    base = df[df.wave == BASE_WAVE].copy()
    base["n_cited"] = base["cited_urls"].map(len)
    base["n_eval"] = base["evaluated_urls"].map(len)
    base["chars"] = base["answer_text"].map(len)
    base["n_brands"] = base["brands"].map(len)
    base["zero_search"] = base["n_searches"] == 0
    base["zero_cited"] = base["n_cited"] == 0
    g = base.groupby("arm").agg(
        n=("item_id", "count"), searches=("n_searches", "mean"),
        zero_search=("zero_search", "sum"), cited=("n_cited", "mean"),
        zero_cited=("zero_cited", "sum"), evaluated=("n_eval", "mean"),
        brands=("n_brands", "mean"), chars=("chars", "mean"), fetches=("n_fetches", "mean"),
    )
    c = costs[costs.wave == BASE_WAVE].groupby("arm")["cost_usd"].mean().rename("usd_call")
    return g.join(c).reset_index()


# ------------------------------------------------------------ power


def simulate_power(gap: float, mean: float, sd_prompt: float, sd_pair: float, *,
                   n_prompts: int = 40, waves: int = 3, reps: int = 300, n_boot: int = 500,
                   independent_pairs: bool = True, seed: int = 20260926) -> dict:
    """Share of simulated studies whose TOST verdict is NULL or NEGLIGIBLE.

    Per prompt p: a level mu_p ~ N(mean, sd_prompt). ``within:ui`` pairs (the
    C(waves, 2) wave pairs) take mu_p + gap + e and ``cross:arm|ui`` pairs (one
    per wave, same prompt) take mu_p + e, e ~ N(0, sd_pair), clipped to [0, 1].
    With ``independent_pairs`` the 3 + 3 pairs per prompt are treated as
    independent (optimistic: they share responses). Without it, each prompt
    contributes one pair of each kind (conservative). Clipping to [0, 1]
    shrinks the gap near the floor, so the realized mean gap is reported too.
    """
    rng = np.random.default_rng(seed)
    n_within = waves * (waves - 1) // 2 if independent_pairs else 1
    n_cross = waves if independent_pairs else 1
    hits = 0
    realized = []
    verdicts: dict[str, int] = defaultdict(int)
    for rep in range(reps):
        mu = rng.normal(mean, sd_prompt, n_prompts)
        rows = []
        for p in range(n_prompts):
            for _ in range(n_within):
                rows.append(("within:ui", p, np.clip(mu[p] + gap + rng.normal(0, sd_pair), 0, 1)))
            for _ in range(n_cross):
                rows.append(("cross:arm|ui", p, np.clip(mu[p] + rng.normal(0, sd_pair), 0, 1)))
        pairs = pd.DataFrame(rows, columns=["condition", "cluster_i", "value"])
        pairs["cluster_j"] = pairs["cluster_i"]
        res = cluster_boot(pairs, contrast=("within:ui", "cross:arm|ui"), sesoi=SESOI,
                           alpha=ALPHA, n_boot=n_boot, seed=seed + rep)
        verdicts[res.verdict.name] += 1
        realized.append(res.estimate)
        hits += res.verdict in (Verdict.NULL, Verdict.NEGLIGIBLE)
    return {"gap": gap, "realized_gap": float(np.mean(realized)), "p_equivalent": hits / reps,
            "verdicts": dict(verdicts)}


def variance_inputs(df: pd.DataFrame, metric: str) -> dict:
    """Pilot per-prompt SDs. The UI within-arm floor is not observed in the
    pilot (one UI wave), so the API floor (opus55_leak, sonnet5_leak_think,
    wave 0 vs 90) stands in for it. Stated as an assumption in the report."""
    floors, cross = [], []
    for arm in ("opus55_leak", "sonnet5_leak_think"):
        f = per_prompt(df, arm, arm, BASE_WAVE, REPEAT_WAVE)
        c = per_prompt(df, arm, "ui_default")
        if f.empty or c.empty:
            continue
        m = f[["item_id", metric]].merge(c[["item_id", metric]], on="item_id",
                                         suffixes=("_floor", "_cross"))
        floors.append(m)
        cross.append(c[metric])
    m = pd.concat(floors).dropna()
    level = m[[f"{metric}_floor", f"{metric}_cross"]].mean(axis=1)
    diff = m[f"{metric}_floor"] - m[f"{metric}_cross"]
    return {
        "mean_cross": float(pd.concat(cross).mean()),
        "sd_prompt": float(level.std(ddof=1)),
        "sd_pair": float(diff.std(ddof=1) / np.sqrt(2)),
        "n_prompt_obs": int(len(m)),
    }


# ------------------------------------------------------------ panel shares

#: Confirmatory arms present in the pilot (sonnet5_plain was added after it).
PILOT_CORE = ("ui_default", "opus55_plain", "opus55_leak", "sonnet5_leak_think",
              "sonnet5_leak_low", "sonnet5_prod", "haiku45_leak")
SHARE_CONFIGS = (
    ("excess", "ref", 1 / 3, "excess MAD, basket on UI share >= 1/3 (as proposed)"),
    ("rmsd", "pooled", 1 / 3, "noise-corrected RMSD, basket on pooled share >= 1/3"),
    ("rmsd", "pooled", 1 / 4, "noise-corrected RMSD, basket on pooled share >= 1/4"),
)


def with_domains(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["domains"] = df["cited_urls"].map(lambda u: sorted(domains(u)))
    return df


def share_pool(df: pd.DataFrame, col: str) -> list[np.ndarray]:
    """Pilot-scale true shares: per category, the share of wave-0 answers in the
    confirmatory arms (UI included, pooled) that name each item."""
    w0 = df[(df.wave == BASE_WAVE) & df.arm.isin(PILOT_CORE)]
    pool = []
    for _, g in w0.groupby("category"):
        counts: dict[str, int] = defaultdict(int)
        for items in g[col]:
            for x in set(items):
                counts[x] += 1
        pool.append(np.array([v / len(g) for v in counts.values()]))
    return pool


def share_pilot_table(df: pd.DataFrame) -> pd.DataFrame:
    """Point estimates per arm vs ui_default, wave 0 only (illustrative: one
    answer per arm per category, 10 categories)."""
    w0 = df[df.wave == BASE_WAVE]
    rows = []
    for col, label in (("brands", "brands"), ("domains", "cited domains")):
        for arm in PILOT_CORE[1:]:
            cells = build_cells(w0, arm, "ui_default", col)
            ref = share_excess(cells, 1 / 3, "ref")
            pooled = share_excess(cells, 1 / 3, "pooled")
            rows.append({"metric": label, "arm": arm, "basket_ref": ref["basket_size"],
                         "mad": ref["mad"], "excess": ref["excess"],
                         "basket_pooled": pooled["basket_size"], "rmsd": pooled["rmsd"]})
    return pd.DataFrame(rows)


def share_power_table(df: pd.DataFrame, reps: int, n_boot: int) -> tuple[pd.DataFrame, dict]:
    rows, pools = [], {}
    for col, label in (("brands", "brands"), ("domains", "cited domains")):
        pool = share_pool(df, col)
        pools[label] = {"categories": len(pool),
                        "items_per_category": float(np.mean([len(p) for p in pool])),
                        "items_share_ge_1_3": float(np.mean([(p >= 1 / 3).sum() for p in pool]))}
        for stat, basket_on, thr, _ in SHARE_CONFIGS:
            for kappa in (None, 4.0):
                for excess in (0.0, 0.025, 0.05, 0.10):
                    r = share_power(pool, excess, reps=reps, n_boot=n_boot, threshold=thr,
                                    statistic=stat, basket_on=basket_on, kappa=kappa)
                    rows.append({"metric": label, "statistic": stat, "basket": basket_on,
                                 "threshold": round(thr, 3),
                                 "prompt_effect": "none" if kappa is None else f"beta k={kappa:g}",
                                 "true_diff": excess, "p_pass": r["p_pass"],
                                 "p_real": r["p_real"], "estimate": r["estimate_mean"],
                                 "basket_mean": r["basket_mean"]})
    return pd.DataFrame(rows), pools


# ------------------------------------------------------------ report


def fmt(df: pd.DataFrame, digits: int = 2) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df.itertuples(index=False):
        cells = []
        for v in r:
            if isinstance(v, float):
                cells.append("" if np.isnan(v) else f"{v:.{digits}f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    from anthropic_client import DEFAULT_ENV_FILE

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    ap.add_argument("--no-extract", action="store_true", help="use the cache only")
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--n-boot", type=int, default=500)
    ap.add_argument("--share-reps", type=int, default=200)
    ap.add_argument("--share-boot", type=int, default=1000)
    a = ap.parse_args()

    df = load_responses()
    spent = 0.0 if a.no_extract else fill_cache(df, a.env_file)
    df = attach_brands(df)
    n_lex = write_lexicon(df)
    costs = ledger_costs()

    desc = descriptives(df, costs)
    vs = {ref: overlap_table(df, ref) for ref in REFERENCES}
    floor_rows = []
    for arm in sorted(df[df.wave == REPEAT_WAVE].arm.unique()):
        pp = per_prompt(df, arm, arm, BASE_WAVE, REPEAT_WAVE)
        floor_rows.append({"arm": arm, "n": len(pp), **{m: pp[m].mean() for m in METRICS}})
    floor = pd.DataFrame(floor_rows)

    versions = brand_versions(df)
    brand_cols = ["brand_j", "top10_j", "brand_rbo"]
    cmp_rows, agree_rows = [], []
    for name, vdf in versions.items():
        t = overlap_table(vdf, "ui_default")
        for r in t.itertuples():
            cmp_rows.append({"extraction": name, "arm": r.arm,
                             **{c: getattr(r, c) for c in brand_cols}})
        for arm in sorted(vdf[vdf.wave == REPEAT_WAVE].arm.unique()):
            pp = per_prompt(vdf, arm, arm, BASE_WAVE, REPEAT_WAVE)
            cmp_rows.append({"extraction": name, "arm": f"floor:{arm}",
                             **{c: pp[c].mean() for c in brand_cols}})
        agree_rows.append({"extraction": name,
                           "brands_per_answer": vdf["brands"].map(len).mean(),
                           "answers_with_none": int((vdf["brands"].map(len) == 0).sum())})
    compare = pd.DataFrame(cmp_rows).pivot(index="arm", columns="extraction", values="brand_j")
    compare = compare.reset_index()
    if "lexicon_v0" in versions:
        via_df, lex_df = versions["haiku_via_v0"], versions["lexicon_v0"]
        per_answer = [jaccard(set(x), set(y))
                      for x, y in zip(via_df["brands"], lex_df["brands"])]
        agree = pd.DataFrame(agree_rows)
        agree_note = (f"Per-answer agreement, Haiku via v0 vs lexicon v0: mean Jaccard "
                      f"{np.nanmean(per_answer):.2f}, median {np.nanmedian(per_answer):.2f}, "
                      f"identical sets in {sum(1 for v in per_answer if v == 1.0)} of "
                      f"{len(per_answer)} answers.")
    else:
        agree, agree_note = pd.DataFrame(agree_rows), "lexicon_v0.csv not found."

    power_rows, inputs = [], {}
    metric_sets = [("brand_j", "brands", df), ("cited_dom_j", "cited domains", df)]
    if "lexicon_v0" in versions:
        metric_sets.insert(1, ("brand_j", "brands (lexicon v0)", versions["lexicon_v0"]))
    for metric, label, mdf in metric_sets:
        vi = variance_inputs(mdf, metric)
        inputs[label] = vi
        for independent, pairing in ((True, "3+3 pairs (optimistic)"),
                                     (False, "1+1 pair (conservative)")):
            for gap in (0.0, 0.05, 0.10):
                res = simulate_power(gap, vi["mean_cross"], vi["sd_prompt"], vi["sd_pair"],
                                     reps=a.reps, n_boot=a.n_boot,
                                     independent_pairs=independent)
                power_rows.append({
                    "metric": label, "pairing": pairing, "true_gap": gap,
                    "realized_gap": res["realized_gap"], "p_equivalent": res["p_equivalent"],
                    "verdicts": ", ".join(f"{k} {v}" for k, v in sorted(res["verdicts"].items())),
                })
    power = pd.DataFrame(power_rows)

    share_df = with_domains(versions.get("lexicon_v0", df))
    share_pilot = share_pilot_table(share_df)
    share_pow, pools = share_power_table(share_df, a.share_reps, a.share_boot)
    pools_df = pd.DataFrame([{"metric": k, **v} for k, v in pools.items()])
    inputs_df = pd.DataFrame([{"metric": k, **v} for k, v in inputs.items()])

    n_ans = len(df)
    n_brand_ans = int((df["brands"].map(len) > 0).sum())
    sections = [
        "# Experiment 009 pilot report",
        "",
        f"Generated {datetime.now(timezone.utc).date().isoformat()} by "
        "`harness/pilot_report.py`. Aggregates only: no prompt, answer, query or brand "
        "text. Pilot data: 10 prompts, wave 0 (all arms) and a same-day repeat, wave 90 "
        "(`opus55_leak`, `sonnet5_leak_think`). API calls used Boston as the search "
        "location (pilot deviation); the UI account signs in from Pittsburgh.",
        "",
        f"Brand candidates: {EXTRACT_MODEL} with a JSON-schema output, one call per "
        f"answer, {n_ans} answers ({n_brand_ans} with at least one brand), {n_lex} "
        "canonical names in the draft lexicon (uncurated). Brand metrics are provisional "
        "until the lexicon is curated and frozen. Brand columns in the profile and overlap "
        "tables below use the Haiku draft names; the extraction comparison section shows "
        "lexicon v0.",
        "",
        "## Per-arm profile (wave 0)",
        "",
        "Means per answer. `zero_search` and `zero_cited` count answers. `usd_call` is "
        "the ledger's batch-priced mean (first-call cache writes included).",
        "",
        fmt(desc),
        "",
        "## Overlap with ui_default (same prompt, wave 0, mean over prompts)",
        "",
        fmt(vs["ui_default"]),
        "",
        "## Overlap with opus55_leak (same prompt, wave 0, mean over prompts)",
        "",
        fmt(vs["opus55_leak"]),
        "",
        "## Noise floor (same arm, wave 0 vs wave 90, same prompt)",
        "",
        fmt(floor),
        "",
        "## Brand extraction: Haiku candidates vs lexicon v0",
        "",
        "Brand-set Jaccard with `ui_default` (same prompt, wave 0, mean over prompts) and "
        "the within-arm floor (wave 0 vs 90), under three extractions: `haiku_draft` "
        "(Haiku candidates, draft canonical names), `haiku_via_v0` (the same candidates "
        "mapped through lexicon v0, so merges and drops apply) and `lexicon_v0` "
        "(deterministic lexicon matching over the answer text, 003 method). Lexicon v0 "
        "is a first curation pass built from the pilot's own candidates, so this checks "
        "whether deterministic matching reproduces the model pass, not out-of-sample "
        "recall.",
        "",
        fmt(compare),
        "",
        fmt(agree),
        "",
        agree_note,
        "",
        "## Power simulation (confirmatory design)",
        "",
        "40 prompts, 3 waves, reference `ui_default`. Gap = J_within(ui) - "
        "J_cross(arm, ui); equivalence when the 90% prompt-level cluster-bootstrap CI "
        f"sits inside +/-{SESOI:.2f}. `p_equivalent` is the share of {a.reps} simulated "
        f"studies ({a.n_boot} bootstrap draws each) that conclude NULL or NEGLIGIBLE. At "
        "a true gap of 0.10 it is the false-equivalence rate. `realized_gap` is the mean "
        "estimated gap across simulations; clipping at 0 shrinks it when the metric sits "
        "near the floor (cited domains), which inflates false equivalence there.",
        "",
        "Assumptions: the UI within-arm floor is not observed in the pilot (one UI wave), "
        "so the API floor (`opus55_leak`, `sonnet5_leak_think`) stands in for it. "
        "Per-prompt level SD and pair noise SD come from the pilot (below). The optimistic "
        "rows treat the 3 within-UI and 3 cross pairs per prompt as independent; the "
        "conservative rows keep one of each, bracketing the dependence between pairs that "
        "share a response.",
        "",
        fmt(inputs_df, 3),
        "",
        fmt(power, 3),
        "",
        "## Panel-share test (H1s brands, H1d cited domains)",
        "",
        "Per-category shares: the fraction of an arm's answers in a category that name "
        "a brand (lexicon v0) or cite a registered domain. Statistics "
        "(`pipeline/shares.py`): `excess` = MAD over the basket minus the MAD expected "
        "from sampling alone (exact binomial expectation at the UI shares); `rmsd` = "
        "noise-corrected root-mean-square difference. Equivalence passes when the "
        "95th-percentile upper bound of a two-stage (category, then prompt) cluster "
        "bootstrap is below 0.05.",
        "",
        "### Pilot point estimates (illustrative only)",
        "",
        "One wave, 10 of 20 categories, one answer per arm per category, so every share "
        "is 0 or 1 and the sampling corrections are degenerate. Shown to exercise the "
        "code, not to estimate anything.",
        "",
        fmt(share_pilot, 3),
        "",
        "### Power at the confirmatory design",
        "",
        f"20 categories drawn from the pilot's 10 (with replacement), 2 prompts x 3 waves "
        f"(6 answers per arm per category), {a.share_reps} simulated studies with "
        f"{a.share_boot} bootstrap draws each. True UI shares per category come from the "
        "pilot (wave 0, confirmatory arms pooled with the UI). The arm's true share is the "
        "UI share plus or minus `true_diff` on every cell, so the true MAD and the true "
        "RMSD both equal `true_diff`. `prompt_effect` beta k=4 gives each prompt its own "
        "shares (shared by both arms). `p_pass` = equivalence passes (at `true_diff` 0.05 "
        "it is the false-pass rate); `p_real` = the lower bound is above 0; `estimate` = "
        "mean point estimate; `basket_mean` = mean basket size over 20 categories.",
        "",
        fmt(pools_df, 1),
        "",
        fmt(share_pow, 3),
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(sections))
    print("\n".join(sections))
    print(f"\nwrote {REPORT} and {LEXICON}; extraction spend ${spent:.4f}")


if __name__ == "__main__":
    main()
