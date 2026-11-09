"""Stage 05: gate-checked public dataset -> data/public/.

One file, ``claude-code-vs-claude-ai-answers.csv``: one row per answer (prompt x arm x
wave), derived features only, with its datasheet. All five arms ship, ``opus55_plain``
included, because the study is pre-registered. The prompts are not released again: they
are 009's 40 synthetic prompts, already public as
``/datasets/009-claude-model-fidelity/claude-api-vs-claude-ai-prompts.csv``, and
``item_id`` joins the two files.

What ships and what does not (spec §3, docs/data-policy.md, and 009's release instruction
that no brand name from the answers appears in any public output):

- SHIPS: item, category, intent, arm, surface, wave, run date, model and Claude Code
  version strings, counts (brands, searches, fetches, cited URLs and domains, evaluated
  URLs and domains, subagent tool uses, answer length), protocol flags, the ORDERED brand
  list as per-release ``bNNNN`` codes, and the cited and evaluated registered-domain lists
  with their source class from 009's frozen domain map.
- PSEUDONYMIZED: brand names, always. Domains ship as ``site_NNNN`` codes when 009's map
  classes them as ``vendor``, when the map does not cover them (011 met many domains 009
  never saw, and an unreviewed domain may be a vendor's own site), when they look like a
  cuid, or when the domain's name matches a name in 011's frozen lexicon (a site 009
  classed as a publisher can be a brand 011's answers present as an option). Codes are
  assigned in a seeded random order, so a code says nothing about when or where a brand
  first appeared. No mapping is published.
- NEVER SHIPS: answer text, its hash, search-query text, full URLs, chat names, collector
  notes (only a 0/1 flag), account identifiers, and the Max and Pro plan ledgers (cost
  estimates, window usage).

After the gate, every cell and the datasheet are scanned with the lexicon's own matching
rule (each alias, case-sensitive or not as the lexicon says, on word boundaries). One hit
stops the release.

The technical gate (``aeo_research.release_dataset``) enforces the allow-list and the
content scans; the human checklist in ``results/release-checklist.md`` covers the
judgment calls. Do not commit data/public/ until that checklist is signed.

Usage (repo root):
  uv run python experiments/011-claude-code-fidelity/pipeline/05_release.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from brands import LEXICON
from common import (
    ALL_ARMS,
    EXP,
    EXP009,
    RAW,
    RESULTS,
    SEED,
    load_features,
)

from aeo_research import ColumnSpec, Datasheet, release_dataset
from aeo_research.anonymize import CUID_PATTERN

SLUG = "claude-code-vs-claude-ai-answers"
STUDY = "011-claude-code-fidelity"
PUBLIC = EXP / "data" / "public"
DOMAIN_MAP_009 = EXP009 / "data" / "raw" / "domain_map_v1.csv"
SCHED_LEDGER = RAW / "routine" / "ledger_sched.jsonl"
AUDIT_D = RESULTS / "audit_d_score.json"
PROMPTS_DATASET = "/datasets/009-claude-model-fidelity/claude-api-vs-claude-ai-prompts.csv"

#: Domains of these classes name a vendor, so they ship as codes.
PSEUDONYMIZED_CLASSES = {"vendor"}
#: A lexicon name at least SUBSTRING_MIN long hides any domain whose name contains it, one
#: at least PREFIX_MIN long hides a domain whose name starts with it, and any name hides an
#: exact match (``pin.com``), so common short words do not hide every publisher.
SUBSTRING_MIN = 5
PREFIX_MIN = 4
UNCLASSIFIED = "unclassified"

ARM_DESCRIPTION = {
    "ui_default": "claude.ai, Opus 5.5, Medium reasoning (the default), typed by hand on one "
                  "Pro account (the reference)",
    "cc_stock_full": "Claude Code run locally with claude -p on a Max plan, Opus 5.5, effort "
                     "medium, Claude Code's own system prompt, web search and web fetch",
    "sched_kit": "a scheduled Claude Code task in the cloud on the same Max plan, which starts one "
                 "new subagent per prompt with a fixed instruction to research the question "
                 "with web search and answer it",
    "cc_none_search": "Claude Code run locally, the system prompt replaced by a 136-character "
                      "one, web search only",
    "opus55_plain": "Claude API (Batches), Opus 5.5, effort medium, no system prompt, web search "
                    "with the user location set to Pittsburgh, Pennsylvania (replicates 009)",
}

COLUMNS = [
    ColumnSpec("item_id", "Study prompt id, b2b_01 to b2b_40; joins 009's prompts file"),
    ColumnSpec("category", "Software category the prompt is about (20 categories, 2 prompts each)"),
    ColumnSpec("intent", "shortlist (a buyer with a concrete company profile asks for options) "
                         "or evaluate (a buyer describes a use case and asks how the top "
                         "options compare)"),
    ColumnSpec("arm", "Setup that produced the answer; see the notes for the five arms"),
    ColumnSpec("surface", "claude.ai (by hand), local (Claude Code on a computer), scheduled "
                          "(Claude Code scheduled task in the cloud) or api (Claude API)"),
    ColumnSpec("wave", "Collection day, 1 to 3"),
    ColumnSpec("run_date", "Collection date of the wave. For sched_kit, the date the scheduled "
                           "tasks were set to fire"),
    ColumnSpec("model_version", "Model string the run reported, or 'claude.ai' for the "
                                "hand-collected arm", public_fact=True),
    ColumnSpec("claude_code_version", "Claude Code version of the pinned binary (local arms "
                                      "only; empty elsewhere)", public_fact=True),
    ColumnSpec("n_brands", "Count of distinct in-category brands the answer named (frozen "
                           "lexicon v1.2)"),
    ColumnSpec("brand_codes", "Pipe-joined pseudonymous brand codes in first-mention order. "
                              "One code is one brand everywhere in this file; the mapping to "
                              "names is not published"),
    ColumnSpec("searched", "1 if the answer ran at least one web search (for sched_kit, from "
                           "the subagent's reported tool list)"),
    ColumnSpec("n_searches", "Count of web searches the answer ran. Empty for sched_kit, whose "
                             "subagent searches are not in the transcript"),
    ColumnSpec("n_backend_searches", "Count of searches the search tool reported running "
                                     "behind the calls (local arms only)"),
    ColumnSpec("n_fetches", "Count of web page fetches (local arms and the API arm; empty "
                            "where not observed)"),
    ColumnSpec("subagent_tool_uses", "Tool calls the subagent reported (sched_kit only)"),
    ColumnSpec("fetched", "1 if the subagent fetched a web page (sched_kit only)"),
    ColumnSpec("copied_exactly", "1 if the scheduled task printed the subagent's result "
                                 "unchanged (sched_kit only)"),
    ColumnSpec("instruction_exact", "1 if the scheduled task gave the subagent the frozen "
                                    "instruction exactly (sched_kit only)"),
    ColumnSpec("cited_source", "Where cited URLs come from: citations (structured citation "
                               "objects), answer_links (links written in the final text) or "
                               "markdown_links"),
    ColumnSpec("n_cited_urls", "Count of cited URLs"),
    ColumnSpec("n_cited_domains", "Count of distinct registered domains cited"),
    ColumnSpec("cited_domains", "Pipe-joined registered domains cited, first-seen order. "
                                "Domains 009's frozen map classes as publisher, review "
                                "marketplace, analyst or other appear as domains (public web "
                                "facts); vendor, unmapped and brand-named domains appear as "
                                "site_NNNN codes", public_fact=True),
    ColumnSpec("cited_domain_classes", "Pipe-joined source class of each cited domain, aligned "
                                       "with cited_domains (009's frozen domain map v1; "
                                       "'unclassified' when the map does not cover it)",
               public_fact=True),
    ColumnSpec("n_evaluated_urls", "Count of search-result URLs the answer's searches "
                                   "returned. Empty for sched_kit (not observed)"),
    ColumnSpec("n_evaluated_domains", "Count of distinct registered domains in those search "
                                      "results. Empty for sched_kit"),
    ColumnSpec("evaluated_domains", "Pipe-joined registered domains in the search results, same "
                                    "coding as cited_domains. Empty for sched_kit",
               public_fact=True),
    ColumnSpec("chars", "Length of the scored text in characters"),
    ColumnSpec("coding_flag", "1 if the pattern check for coding behavior fired (Audit A; "
                              "every flagged case was read and cleared)"),
    ColumnSpec("clarifying_questions", "1 if claude.ai asked clarifying questions first"),
    ColumnSpec("collector_note", "1 if the hand collector left a note on the chat; the note "
                                 "itself is not released"),
]


# ----------------------------------------------------------------- lexicon


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def lexicon_names(path: Path = LEXICON) -> list[tuple[str, bool]]:
    """Every alias in the lexicon (keep and drop rows) with its row's case-sensitivity flag,
    plus the canonical name of every case-insensitive row.

    The canonical of a case-sensitive row is a lowercased key for a name that is also a
    common word (its aliases hold the real spelling, and the matcher uses only those), so
    matching it in any case would flag ordinary English.
    """
    names: set[tuple[str, bool]] = set()
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            cs = r.get("match") == "cs"
            for a in r["aliases"].split("|"):
                if a.strip():
                    names.add((a.strip(), cs))
            if not cs and r["canonical"].strip():
                names.add((r["canonical"].strip(), False))
    return sorted(names)


def name_patterns(names: list[tuple[str, bool]]) -> list[re.Pattern]:
    """The lexicon's matching rule: word boundaries that also treat & as part of a word."""
    return [re.compile(rf"(?<![\w&]){re.escape(a)}(?![\w&])", 0 if cs else re.I)
            for a, cs in names]


def lexicon_hits(text: str, patterns: list[re.Pattern]) -> list[str]:
    return [p.pattern for p in patterns if p.search(text)]


def normed_names(names: list[tuple[str, bool]]) -> set[str]:
    """Lexicon names reduced to letters and digits, with '&' also spelled 'and'
    (``Zone & Co`` -> ``zoneco`` and ``zoneandco``)."""
    out = set()
    for a, _ in names:
        for variant in (a, a.replace("&", " and ")):
            if norm(variant):
                out.add(norm(variant))
    return out


def brand_named_domain(domain: str, normed: set[str]) -> bool:
    """True if the domain's name (everything before the last label) is a lexicon name,
    starts with one of at least PREFIX_MIN characters, or contains one of at least
    SUBSTRING_MIN characters. Over-hiding a publisher costs a little data; under-hiding
    would publish a brand."""
    label = norm(domain.rsplit(".", 1)[0])
    return any(label == n or (len(n) >= PREFIX_MIN and label.startswith(n))
               or (len(n) >= SUBSTRING_MIN and n in label) for n in normed)


# ----------------------------------------------------------------- build


def code_map(values: set[str], prefix: str, rng: np.random.Generator) -> dict[str, str]:
    """Per-release codes in a seeded random order (no first-appearance signal)."""
    ordered = sorted(values)
    perm = rng.permutation(len(ordered))
    return {ordered[k]: f"{prefix}{i + 1:04d}" for i, k in enumerate(perm)}


def load_classes(path: Path = DOMAIN_MAP_009) -> dict[str, str]:
    out = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            cls = (r.get("reviewer_class") or "").strip() or (r.get("suggested_class") or "").strip()
            out[r["registered_domain"]] = cls or "other"
    return out


def sched_fire_dates(path: Path = SCHED_LEDGER) -> dict[int, str]:
    """Wave -> the date the scheduled tasks were set to fire (one date per wave)."""
    dates: dict[int, set[str]] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            dates.setdefault(int(r["wave"]), set()).add(r["run_once_at"][:10])
    if any(len(v) != 1 for v in dates.values()):
        raise SystemExit(f"scheduled tasks fired on more than one day in a wave: {dates}")
    return {w: v.pop() for w, v in dates.items()}


def flag(series: pd.Series) -> pd.Series:
    """bool/None -> nullable 0/1."""
    return series.map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v))
                      else int(bool(v))).astype("Int64")


def count(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").round().astype("Int64")


def build_release(df: pd.DataFrame, classes: dict[str, str], names: list[tuple[str, bool]],
                  fire_dates: dict[int, str], seed: int = SEED):
    """The public frame plus the two code maps (never published)."""
    rng = np.random.default_rng(seed)
    brand_codes = code_map({b for bs in df["brands"] for b in bs}, "b", rng)

    normed = normed_names(names)
    all_domains = {d for col in ("cited_domains", "evaluated_domains") for ds in df[col] for d in ds}
    hidden = {d for d in all_domains
              if classes.get(d) in PSEUDONYMIZED_CLASSES or d not in classes
              or CUID_PATTERN.search(d) or brand_named_domain(d, normed)}
    site_codes = code_map(hidden, "site_", rng)

    def show(domains: list[str]) -> str:
        return "|".join(site_codes.get(d, d) for d in domains)

    def cls(d: str) -> str:
        return classes.get(d, UNCLASSIFIED)

    sched = df["arm"] == "sched_kit"
    observed_eval = ~sched
    run_date = df["run_date"].where(~sched, df["wave"].map(fire_dates))
    model = df["model"].where(df["model"].notna(), df["resolved_model"])
    model = model.where(df["arm"] != "ui_default", "claude.ai")

    out = pd.DataFrame({
        "item_id": df["item_id"],
        "category": df["category"],
        "intent": df["intent"],
        "arm": df["arm"],
        "surface": df["surface"],
        "wave": df["wave"].astype(int),
        "run_date": run_date,
        "model_version": model,
        "claude_code_version": df["claude_code_version"].where(df["claude_code_version"].notna(), None),
        "n_brands": df["n_brands"].astype(int),
        "brand_codes": df["brands"].map(lambda bs: "|".join(brand_codes[b] for b in bs)),
        "searched": flag(df["searched"]),
        "n_searches": count(df["n_searches"]),
        "n_backend_searches": count(df["n_backend_searches"]),
        "n_fetches": count(df["n_fetches"]),
        "subagent_tool_uses": count(df["subagent_tool_uses"]),
        "fetched": flag(df["fetched"]),
        "copied_exactly": flag(df["report_match"]),
        "instruction_exact": flag(df["instruction_exact"]),
        "cited_source": df["cited_urls_source"],
        "n_cited_urls": df["n_links"].astype(int),
        "n_cited_domains": df["n_cited_domains"].astype(int),
        "cited_domains": df["cited_domains"].map(show),
        "cited_domain_classes": df["cited_domains"].map(lambda ds: "|".join(cls(d) for d in ds)),
        "n_evaluated_urls": count(df["n_evaluated"]).where(observed_eval, pd.NA),
        "n_evaluated_domains": df["evaluated_domains"].map(len).astype("Int64").where(
            observed_eval, pd.NA),
        "evaluated_domains": df["evaluated_domains"].map(show).where(observed_eval, None),
        "chars": df["chars"].astype(int),
        "coding_flag": flag(df["coding_flag"]),
        "clarifying_questions": flag(df["clarifying_questions"]),
        "collector_note": flag(df["collector_notes"]),
    })
    if out["run_date"].isna().any() or (out["run_date"] == "").any():
        raise SystemExit("a row has no run date")
    if out["model_version"].isna().any():
        raise SystemExit("a row has no model string")
    # Every arm's rows for one wave share one date.
    per_wave = out.groupby("wave")["run_date"].nunique()
    if (per_wave != 1).any():
        raise SystemExit(f"arms disagree on a wave's date: {per_wave.to_dict()}")
    # Belt and braces: no pseudonymized value may appear in the clear.
    for col in ("brand_codes", "cited_domains", "evaluated_domains"):
        tokens = {t for v in out[col].dropna() for t in v.split("|") if t}
        if tokens & (hidden | set(brand_codes)):
            raise SystemExit(f"{col}: a withheld name appears in the clear")
    return out, brand_codes, site_codes


def scan_text(text: str, patterns: list[re.Pattern], where: str) -> None:
    hits = lexicon_hits(text, patterns)
    if hits:
        raise SystemExit(f"{where}: lexicon name found ({len(hits)} patterns, e.g. {hits[:3]})")


def scan_frame(out: pd.DataFrame, patterns: list[re.Pattern], normed: set[str]) -> None:
    """Every distinct cell value through the lexicon's matching rule; domain tokens also
    through the domain-name rule."""
    for col in out.columns:
        values = {str(v) for v in out[col].dropna().unique()}
        for v in values:
            for token in v.split("|"):
                if re.fullmatch(r"(b|site_)\d{4}", token):
                    continue
                scan_text(token, patterns, f"column {col}")
                if col in ("cited_domains", "evaluated_domains") and brand_named_domain(token, normed):
                    raise SystemExit(f"column {col}: a brand-named domain is in the clear")


def main() -> None:
    df = load_features()
    if int(df["synthetic"].max()) == 1:
        raise SystemExit("refusing to release a SYNTHETIC frame")
    if set(df["arm"]) != set(ALL_ARMS):
        raise SystemExit(f"unexpected arms: {sorted(set(df['arm']))}")

    names = lexicon_names()
    patterns = name_patterns(names)
    normed = normed_names(names)
    out, brand_codes, site_codes = build_release(df, load_classes(), names, sched_fire_dates())
    scan_frame(out, patterns, normed)

    audit = json.loads(AUDIT_D.read_text())
    api_cost = df[df["arm"] == "opus55_plain"]["cost_usd"].mean()
    waves = out.groupby("wave")["run_date"].first()
    paths = release_dataset(
        out,
        COLUMNS,
        PUBLIC,
        Datasheet(
            title="Claude Code vs claude.ai: brands named and domains cited, 40 B2B software "
                  "prompts, 5 setups, 3 days",
            dataset_slug=SLUG,
            study=STUDY,
            unit="answers",
            notes=[
                f"One row per answer evaluated in this study: {out['item_id'].nunique()} "
                f"synthetic B2B software prompts x {out['arm'].nunique()} setups (arms) x "
                f"{out['wave'].nunique()} waves ("
                + ", ".join(f"wave {w}: {d}" for w, d in waves.items()) + ").",
                "The prompts are the 40 synthetic prompts of experiment 009, already "
                f"published as {PROMPTS_DATASET}. They are not repeated here; item_id joins "
                "the two files.",
                "The arms are: " + "; ".join(f"`{a}`: {ARM_DESCRIPTION[a]}" for a in ALL_ARMS)
                + ".",
                "Brands are the in-category brands an answer names, matched with the frozen "
                f"lexicon v1.2 (Audit D on {audit['rows']} answers: precision "
                f"{audit['precision']:.2f}, recall {audit['recall']:.2f}). They ship as "
                f"bNNNN codes ({len(brand_codes)} codes). Vendor sites, domains 009's frozen "
                "source-class map does not cover, and domains whose name matches a lexicon "
                f"name ship as site_NNNN codes ({len(site_codes)} codes). Codes are per "
                "release and no mapping is published.",
                "Cited URLs are structured citation objects for claude.ai and the API, and "
                "the links written in the final text for the three Claude Code arms "
                "(cited_source), so part of any difference in cited domains may come from "
                "the measure.",
                "sched_kit runs each prompt in a subagent whose searches are not in the "
                "transcript the study can pull, so its search count and evaluated URLs are "
                "empty (unknown), not zero.",
                "The Claude Code arms and claude.ai cannot be told where the user is, so "
                "this data says nothing about location-specific answers. The API arm set "
                "Pittsburgh, Pennsylvania as the user location.",
                "Mean estimated cost per call for opus55_plain (token and search counts at "
                "list prices, batch pricing; not reconciled with billing): "
                f"USD {api_cost:.3f}. The Claude Code and claude.ai arms run on "
                "subscription plans, whose usage is not released.",
                "Answer text, answer hashes, search-query text, full URLs, chat names, "
                "collector notes and account identifiers are not released.",
            ],
        ),
    )
    scan_text(paths["datasheet"].read_text(), patterns, "datasheet")
    print(f"released: {paths['csv']}\n          {paths['datasheet']}")
    print(f"rows {len(out)}, columns {len(out.columns)}, brand codes {len(brand_codes)}, "
          f"site codes {len(site_codes)}")
    print("lexicon scan: 0 hits in the CSV and the datasheet")
    print("Do not commit data/public/ until results/release-checklist.md is signed.")


if __name__ == "__main__":
    main()
