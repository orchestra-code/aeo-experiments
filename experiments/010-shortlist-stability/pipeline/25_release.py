"""Stage 25: gate-checked Stage 1 public datasets -> data/public/ (spec §3, §8 step 6).

Three files, written through ``aeo_research.release_dataset``:

- ``ai-shortlist-stability-answers.csv``: one row per Stage 1 answer (all six
  datasets, every arm), derived counts and flags only.
- ``ai-shortlist-stability-mentions.csv``: one row per (answer, lexicon
  brand): brand code, first-mention position, the judge's status, best-for
  segment ids, caveat reason types. Joins the answers file on ``run_id``.
- ``ai-shortlist-stability-segments.csv``: the 20 frozen B2B best-for
  taxonomies (segment id, label, short definition).

What ships and what does not (spec §3, docs/data-policy.md, and 009's release
instruction of 2026-10-02 that no brand name from the answers appears in any
public output):

- SHIPS: dataset, platform, arm, model, study, wave, run date, the B2B item
  ids and categories of 009's public prompts file, intent, counts and flags,
  per-brand status and position, best-for segment ids, caveat reason types,
  and the B2B segment labels and definitions.
- CODED: brands ship as ``bNNNN`` codes. A brand experiment 009's public
  dataset coded keeps 009's code (so the claude.ai rows join that file's
  ``brand_codes``); every other brand in the frozen lexicons (lexicon v3 for
  B2B, 005's for headphones and agencies, in their own namespace) gets a new
  code after 009's last, in a seeded order over the whole frozen lexicon, so
  the codes do not depend on which brands a stage happened to observe and
  Stage 2 can reuse them. Headphone and agency item ids and categories ship
  as per-release codes (their prompts are never published).
- REWRITTEN: B2B segment labels, definitions and ids that name a vendor or
  product are rewritten generically (``REWRITES``; ``edited`` = 1 in the
  segments file; the mentions file uses the public ids). The table is keyed
  by a hash of the original id so this committed file names no vendor. The
  one headphone segment whose id names a brand gets a generic id the same way.
- NEVER SHIPS: answer text, best-for phrases, judge evidence, caveat reason
  text, question text for headphone and agency prompts, search queries,
  cited URLs, the R1 names outside the lexicon (counts only).

Checks before anything is written: the frame is the confirmatory Stage 1
frame built with the frozen lexicon v3 and taxonomy, Audit D passed and is
signed, 009's codes are reproduced exactly from its public file, every
segment label and definition is clean against every lexicon alias (009's
v2.1, lexicon v3, 005's lexicons, keep and drop rows) and a capitalized-name
heuristic, and every public value and datasheet passes an alias scan
(aliases of at least 4 characters, case-insensitive). After writing, the
files are scanned again; a hit deletes them.

The checklist ``results/release-checklist.md`` is written once and never
overwritten. Do not commit data/public/ until it is signed, and do not sync
the datasets to the site before that (``sync_site_assets.py --figures-only``).

Usage: uv run python experiments/010-shortlist-stability/pipeline/25_release.py --stage 1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import textwrap
from collections import Counter
from pathlib import Path

import pandas as pd
from common import (
    DATASETS,
    EXP,
    EXPLORE_TAXONOMY_CATEGORIES,
    INTERIM,
    JUDGE_PIN,
    LEXICON_V3,
    LEXICON_V3_SHA256,
    RAW,
    REC,
    RESULTS,
    SEED,
    SPEC,
    SRC_005,
    SRC_009,
    TAXONOMY_B2B,
    TAXONOMY_B2B_SHA256,
    TAXONOMY_EXPLORE_SHA256,
    Mode,
    audit_d_problems,
    instrument_problems,
    load_bestfor,
    load_module,
    merged_stage_taxonomy,
    read_jsonl,
    sha256_file,
    stage2_not_implemented,
)

from aeo_research import ColumnSpec, Datasheet, release_dataset

STUDY = "010-shortlist-stability"
PUBLIC = EXP / "data" / "public"
CHECKLIST_TEMPLATE = EXP.parents[1] / "templates" / "release-checklist.md"
ANSWERS_SLUG = "ai-shortlist-stability-answers"
MENTIONS_SLUG = "ai-shortlist-stability-mentions"
SEGMENTS_SLUG = "ai-shortlist-stability-segments"
SPEC_COMMIT = "6342963"
N_STAGE1 = 2770

PUB009_ANSWERS = SRC_009 / "data/public/claude-api-vs-claude-ai-answers.csv"
PUB009_PROMPTS = SRC_009 / "data/public/claude-api-vs-claude-ai-prompts.csv"
FEATURES_009 = SRC_009 / "data/interim/features.jsonl"
LEXICON_009 = SRC_009 / "data/raw/lexicon_v2_1.csv"

#: Brand code prefix. 009's release used ``bNNNN``; reusing its exact strings
#: lets the claude.ai rows join 009's public answers file. (spec §3 writes
#: "``v0001``, as in 009's release"; the checklist asks Jim to confirm.)
BRAND_PREFIX = "b"

STUDY_SLUGS = {
    "010": "010-shortlist-stability",
    "009": "009-claude-model-fidelity",
    "002": "002-prompt-consistency",
    "003": "003-synthetic-prompt-coverage",
    "005": "005-subintent-matched-panels",
}
PLATFORM = {"openai": "chatgpt", "gemini": "gemini", "claude": "claude"}
#: Coded categories and item-id prefixes for the datasets whose prompts are never published.
CODED = {"chatgpt_consumer": ("cat_c1", "consumer_"), "chatgpt_agency": ("cat_a1", "agency_")}
#: 005 lexicon namespace per coded dataset (a consumer brand never shares a
#: code with a B2B brand of the same spelling).
NAMESPACE = {"chatgpt_consumer": "headphones", "chatgpt_agency": "coffee"}
NO_SEGMENT = ("other", "unassigned")

# --------------------------------------------------------------- rewrites

#: (category, sha256(original id)[:12]) -> the public replacement for the
#: fields that named a vendor or product. Only the fields given change.
#: Keyed by hash so this file names no vendor; the originals are in
#: data/raw/bestfor_taxonomy_b2b/taxonomy.json and bestfor_explore/taxonomy.json.
#: ``why`` is what the original named, in generic terms, for the checklist.
REWRITES: dict[tuple[str, str], dict[str, str]] = {
    ("CRM", "759db5cd3355"): {
        "why": "definition named a software vendor",
        "definition": "Organizations choosing a CRM for compatibility with the productivity "
                      "suite, ERP, accounting, or other business systems they already use."},
    ("HRIS", "9d55ec82c617"): {
        "why": "definition named two workplace chat products",
        "definition": "Teams that prefer managing leave requests and lightweight HR tasks "
                      "through workplace chat or similar collaboration tools."},
    ("accounts payable automation", "34cf8ee38a68"): {
        "why": "definition named five ERP vendors or products",
        "definition": "Large organizations and teams running established enterprise ERP "
                      "suites or other complex ERP environments that need deep integration "
                      "and controls."},
    ("cloud data warehouse", "616d43e98f07"): {
        "why": "definition named five productivity, BI and cloud products",
        "definition": "Organizations already standardized on a major productivity suite, BI "
                      "tool, public cloud, or another major cloud ecosystem."},
    ("customer support helpdesk", "f8cd45c6f2e0"): {
        "why": "definition named three CRM vendors",
        "definition": "Teams prioritizing native integration with their CRM platform, CRM "
                      "data, sales, marketing, or customer records."},
    ("customer support helpdesk", "208c7a7449ed"): {
        "why": "definition named an ecommerce platform",
        "definition": "SaaS, subscription, ecommerce-platform, and product-led businesses "
                      "supporting customers with billing, orders, product questions, or "
                      "retention needs."},
    ("customer support helpdesk", "65f5c54bc2b5"): {
        "why": "definition named a messaging app",
        "definition": "Support organizations prioritizing phone, chat, in-app, website, "
                      "messaging-app, or broad channel coverage, especially when "
                      "conversations dominate."},
    ("e-signature", "4894e5828471"): {
        "why": "definition named seven software vendors or products",
        "definition": "Teams already invested in a major productivity, document, CRM, "
                      "cloud-storage, or similar software ecosystem."},
    ("endpoint security (EDR)", "240f767b9012"): {
        "why": "id, label and definition named a software vendor and four of its products",
        "id": "productivity_suite_ecosystem",
        "label": "Productivity Suite Ecosystem Teams",
        "definition": "Organizations invested in one major vendor's productivity suite, "
                      "device management, built-in endpoint protection, cloud, or licensing "
                      "that want native integration and unified security."},
    ("endpoint security (EDR)", "2da3822f4ab1"): {
        "why": "id, label and definition named a device maker, its computers and two MDM vendors",
        "id": "single_platform_mdm",
        "label": "Single-Platform MDM Environments",
        "definition": "Organizations whose devices come mainly from one platform maker and "
                      "that use device-management tools built for that platform, needing "
                      "platform-specific management and protection."},
    ("endpoint security (EDR)", "bfde844c95f4"): {
        "why": "definition named two desktop operating systems",
        "definition": "Organizations managing diverse desktop operating systems or other "
                      "endpoint systems that prioritize broad MDM compatibility, "
                      "cross-platform coverage, or vendor independence."},
    ("expense management", "086f92e1c755"): {
        "why": "definition named six accounting or ERP products",
        "definition": "Teams that need expense management connected to mainstream "
                      "accounting or ERP platforms."},
    ("expense management", "2b4f54ec4e57"): {
        "why": "definition named six legal practice and accounting products",
        "definition": "Law firms and legal teams that need matter-level tracking, client "
                      "billing, or integrations with legal practice management and legal "
                      "accounting platforms."},
    ("identity and SSO", "240f767b9012"): {
        "why": "id, label and definition named a software vendor and five of its products",
        "id": "directory_suite_ecosystem",
        "label": "Directory Suite Ecosystem Teams",
        "definition": "Organizations centered on one major vendor's productivity suite, "
                      "cloud, on-premises directory, desktop operating system, device "
                      "management, or related services."},
    ("identity and SSO", "9e9c8fd0ca45"): {
        "why": "id, label and definition named a software vendor and two of its products",
        "id": "cloud_workspace_ecosystem",
        "label": "Cloud Workspace Ecosystem Teams",
        "definition": "Organizations primarily using one major vendor's browser-based "
                      "productivity workspace, cloud, or related identity and collaboration "
                      "tools."},
    ("marketing automation", "b071b3a4bffe"): {
        "why": "id, label and definition named a CRM vendor",
        "id": "enterprise_crm_teams",
        "label": "Enterprise CRM Teams",
        "definition": "Organizations already using, standardizing on, or requiring tight "
                      "synchronization with a leading enterprise CRM for sales and "
                      "marketing."},
    ("mid-market ERP", "240f767b9012"): {
        "why": "id, label and definition named a software vendor and three of its products",
        "id": "productivity_suite_ecosystem",
        "label": "Productivity Suite Ecosystem",
        "definition": "Organizations already standardized on one major vendor's productivity "
                      "suite, cloud, BI, or related tools and seeking tight ecosystem "
                      "integration."},
    ("observability/APM", "49225c8435b7"): {
        "why": "id, label and definition named an open-source container orchestrator",
        "id": "container_native",
        "label": "Container-native teams",
        "definition": "Teams whose primary observability needs center on container "
                      "orchestration, containers, microservices, platform engineering, or "
                      "zero-code instrumentation."},
    ("observability/APM", "e2ba9d7ee630"): {
        "why": "definition named six open-source or commercial observability tools",
        "definition": "Teams already invested in open-source metrics, dashboarding, tracing, "
                      "or logging tools, or related open standards and integrations."},
    ("product analytics", "98429af864e6"): {
        "why": "definition named two mobile operating systems",
        "definition": "Teams analyzing native mobile apps, including mobile funnels, "
                      "gestures, screen behavior, crashes, and mobile UX issues."},
    ("project management", "1b0f4acf3940"): {
        "why": "definition named a design software vendor and two of its products",
        "definition": "Construction and engineering organizations whose workflows depend on "
                      "BIM, CAD and other design software, drawings, or "
                      "design-to-construction integration."},
    ("project management", "f5c1f49dca5c"): {
        "why": "id, label and definition named a software vendor and its productivity suite",
        "id": "productivity_suite_teams",
        "label": "Productivity suite teams",
        "definition": "Organizations already standardized on one major vendor's productivity "
                      "and collaboration suite and seeking connected project workflows."},
    ("sales engagement", "f8cd45c6f2e0"): {
        "why": "definition named three CRM vendors and two email products",
        "definition": "Teams choosing around an existing CRM or email environment and "
                      "wanting native integration or in-CRM engagement."},
    ("sales engagement", "88acb6c99b93"): {
        "why": "id, label and definition used a common word that is also the name of a "
               "sales engagement vendor in this category",
        "id": "multichannel_phone_selling",
        "label": "Phone and Multichannel Selling",
        "definition": "Teams prioritizing calling, texting, SMS, phone-heavy selling, or "
                      "coordinated contact across multiple channels."},
    ("sales engagement", "105d2a3c6650"): {
        "why": "definition used a common word that is also the name of a sales engagement "
               "vendor in this category",
        "definition": "Teams focused on high-volume prospecting, contact data, cadences, "
                      "multi-step sequences, automated follow-up, or systematic cold and "
                      "warm contact."},
    # Headphones (exploration taxonomy): only the id ships, in the mentions file.
    ("headphones", "908ed67320e9"): {
        "why": "id named a device maker (a brand in the headphone lexicon)",
        "id": "single_ecosystem_users"},
}

#: Common words that are also lexicon aliases, accepted where they appear as
#: ordinary words (each reviewed; listed in the checklist). Matched lowercase.
GENERIC_WORDS = {
    "teams": "ordinary word; a drop-row alias for a chat product",
    "stack": "ordinary word, as in full-stack; a drop-row alias",
    "front": "ordinary word, as in front-end; a helpdesk vendor in another category",
    "remote": "ordinary word, as in remote access; a payroll vendor in another category",
    "make": "ordinary word, as in make-to-order; a drop-row alias",
    "general": "the taxonomy's general segment",
}

#: Capitalized tokens allowed mid-sentence in a public definition: generic
#: acronyms and terms, no product names.
GENERIC_CAPS = {
    "AEC", "AI-supported", "AP", "APIs", "ATS", "B2B", "BI", "BIM", "BOM", "BOMs", "CAD",
    "CLM", "CPQ", "CRM", "DTC", "EHRs", "EPCs", "ERP", "ETL", "GRC", "HR", "HRIS", "HVAC",
    "IT", "MDM", "MDR", "MFA", "PDF", "PMS", "PTO", "SLAs", "SMB", "SMS", "SOC", "SOX",
    "SQL", "SSO", "SaaS", "UX", "WMS", "in-CRM",
}

#: Values the public-file alias scan may meet that are platform or study names
#: or ordinary words, not brands from the answers (each listed in the checklist).
SCAN_ALLOW = {
    "gemini": "a platform studied, in dataset and platform values; also a lexicon alias",
    "wave": "ordinary word, a collection wave; an alias in the B2B lexicon",
    "segment": "ordinary word, a use-case segment; a data vendor's name in the B2B lexicon",
    "nothing": "ordinary word in the gate's datasheet boilerplate; a headphone brand's "
               "canonical key, whose alias is a two-word product name",
}

# ---------------------------------------------------------------- columns

ANSWER_COLUMNS = [
    ColumnSpec("run_id", "Id of one answer evaluated in this study; joins the mentions file"),
    ColumnSpec(
        "dataset",
        "chatgpt_b2b, gemini_b2b, claude_api_b2b (new collection); claude_b2b (experiment "
        "009 holdout); chatgpt_consumer (headphones) and chatgpt_agency (brand-design "
        "agencies), holdouts of experiments 002, 003 and 005",
    ),
    ColumnSpec("platform", "chatgpt, gemini or claude"),
    ColumnSpec(
        "collection",
        "dataforseo (LLM scraper), anthropic_api (Batches API) or claude_ai_by_hand "
        "(claude.ai, collected by hand in experiment 009)",
    ),
    ColumnSpec(
        "arm",
        "Configuration: chatgpt, gemini, claude (Opus 5.5 API, effort medium, no system "
        "prompt); for claude_b2b, ui_default (claude.ai default), ui_think (claude.ai High "
        "reasoning) or opus55_plain (the API arm, as in 009)",
    ),
    ColumnSpec(
        "test_arm",
        "1 if the arm is the one the dataset's tests use (claude_b2b: ui_default); the "
        "other claude_b2b arms are for robustness and the arm comparison",
    ),
    ColumnSpec(
        "model",
        "Model string the platform reported (DataForSEO model field, Anthropic model id), "
        "'claude.ai' for the hand-collected arms; blank where the source study did not "
        "record it",
        public_fact=True,
    ),
    ColumnSpec("study", "Experiment that collected the answer"),
    ColumnSpec(
        "item_id",
        "Question id. B2B: b2b_01 to b2b_40, as in experiment 009's public prompts file "
        "(claude-api-vs-claude-ai-prompts.csv, which has the question text). Headphone and "
        "agency questions: per-release codes (consumer_NNN, agency_NNN); their text is "
        "never published",
    ),
    ColumnSpec(
        "category",
        "B2B software category (20 categories, 2 questions each); cat_c1 (consumer) and "
        "cat_a1 (agency) are per-release codes",
    ),
    ColumnSpec(
        "intent",
        "B2B only: shortlist (a buyer with a concrete company profile asks for options) or "
        "evaluate (a buyer describes a use case and asks how the top options compare)",
    ),
    ColumnSpec(
        "wave",
        "Run number within the study: 1 to 7 for the new collection (daily from "
        "2026-10-03), 1 to 3 for claude_b2b, and the source study's wave for the "
        "consumer and agency answers",
    ),
    ColumnSpec("run_date", "Date of the run (see the datasheet notes on time zones)"),
    ColumnSpec("n_lexicon_brands", "Count of distinct lexicon brands the answer named"),
    ColumnSpec("n_recommended", "Lexicon brands the judge labeled top choice or one of many (the shortlist)"),
    ColumnSpec("n_top_choice", "Lexicon brands labeled top choice (after the cap of two)"),
    ColumnSpec("n_cautioned", "Lexicon brands labeled cautioned against"),
    ColumnSpec("has_top_choice", "1 if any lexicon brand is a top choice"),
    ColumnSpec("has_caution", "1 if any lexicon brand is cautioned against"),
    ColumnSpec(
        "n_top_choice_raw",
        "Brands (any, inside or outside the lexicon) the judge's raw output labeled top "
        "choice, before answers with more than two were demoted to one of many",
    ),
    ColumnSpec(
        "n_brands_all",
        "Brands the judge listed, inside or outside the lexicon (the R1 robustness view); "
        "names outside the lexicon are not released",
    ),
    ColumnSpec("empty", "1 if the answer was empty"),
    ColumnSpec(
        "refusal",
        "1 if the answer is a refusal: a refusal-shaped opening and no lexicon brand "
        "(spec deviation 7). Refusals and empty answers are excluded from the analysis",
    ),
    ColumnSpec("refusal_phrase", "1 if the first 600 characters open like a refusal, whatever follows"),
    ColumnSpec("judge_ok", "1 if the judge returned a valid classification"),
]

MENTION_COLUMNS = [
    ColumnSpec("run_id", "Answer id; joins the answers file"),
    ColumnSpec(
        "brand_code",
        "Pseudonymous brand code. One code is one brand everywhere in this file; codes "
        "shared with experiment 009's public dataset mean the same brand there. No mapping "
        "to names is published",
    ),
    ColumnSpec("position", "First-mention order of the brand in the answer, 1 = named first"),
    ColumnSpec(
        "status",
        "The judge's label for the brand in this answer: top_choice, one_of_many, "
        "generic_mention, cautioned_against, or unclassified (named but not labeled by the "
        "judge)",
    ),
    ColumnSpec("n_best_for", "Count of best-for phrases the judge gave the brand (phrases are not released)"),
    ColumnSpec(
        "segment_ids",
        "Recommended brands only: pipe-joined distinct use-case segments of the brand's "
        "best-for phrases (classifier pass a, used in the analysis), first-seen order. B2B "
        "ids join the segments file on category and segment_id; headphone and agency "
        "labels are not released. Phrases outside every segment are left out",
    ),
    ColumnSpec("segment_ids_pass_b", "As segment_ids, from the second classifier pass (Audit G)"),
    ColumnSpec("n_caveats", "Count of caveats the judge attached to the brand"),
    ColumnSpec(
        "caveat_types",
        "Pipe-joined reason type of each caveat, in the judge's order (price, "
        "reliability_quality, missing_capability, complexity, company_size_fit, "
        "integration, reputation, support_service, security_compliance, other). The "
        "reason text is not released",
    ),
]

SEGMENT_COLUMNS = [
    ColumnSpec("category", "B2B software category"),
    ColumnSpec("segment_id", "Segment id, as used in the mentions file"),
    ColumnSpec("label", "Short segment label"),
    ColumnSpec("definition", "One-sentence definition, as the taxonomy model wrote it unless edited = 1"),
    ColumnSpec(
        "edited",
        "1 if Spyglasses rewrote the label, definition or id to remove a vendor or product "
        "name before release",
    ),
]


# ------------------------------------------------------------------ helpers


def id_hash(seg_id: str) -> str:
    return hashlib.sha256(seg_id.encode()).hexdigest()[:12]


def rank(unit: str) -> str:
    """Seeded order for code assignment (no first-appearance signal)."""
    return hashlib.sha256(f"{SEED}:release:{unit}".encode()).hexdigest()


def flag(x) -> int:
    return int(bool(x))


def read_lexicon_rows(path: Path) -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def all_aliases() -> dict[str, bool]:
    """Every alias of every lexicon (keep and drop rows) -> case-sensitive per its lexicon."""
    out: dict[str, bool] = {}
    for path in (LEXICON_V3, LEXICON_009):
        for r in read_lexicon_rows(path):
            for a in [r["canonical"], *r["aliases"].split("|")]:
                a = a.strip()
                if a:
                    out[a] = out.get(a, True) and r.get("match") == "cs"
    b5 = load_module(SRC_005 / "pipeline/brands.py", "x005_brands")
    for lex in b5.LEXICONS.values():
        for canon, aliases in lex.items():
            for a in [canon, *aliases]:
                out[a] = False
    return out


def alias_regex(aliases, min_len: int = 1) -> re.Pattern:
    """One case-insensitive word-boundary alternation, longest alias first."""
    terms = sorted({a for a in aliases if len(a) >= min_len}, key=len, reverse=True)
    if not terms:
        raise SystemExit("no aliases to scan with")
    body = "|".join(re.escape(a) for a in terms)
    return re.compile(rf"(?<![\w&])(?:{body})(?![\w&])", re.I)


# ------------------------------------------------------------------ inputs


def check_inputs() -> tuple[list[dict], dict]:
    problems = instrument_problems() + audit_d_problems(Mode("confirmatory", 1))
    meta_path = INTERIM / "stage1_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if meta.get("mode") != "confirmatory" or meta.get("stage") != 1:
        problems.append("stage1_answers.jsonl is not the confirmatory Stage 1 frame")
    if meta.get("lexicon_v3_sha256") != LEXICON_V3_SHA256:
        problems.append("the answer frame was built with another lexicon v3")
    if meta.get("taxonomy_b2b_sha256") != TAXONOMY_B2B_SHA256:
        problems.append("the answer frame was built with another B2B taxonomy")
    if meta.get("judge_rows_off_pin"):
        problems.append("judged rows off the judge pin")
    if problems:
        raise SystemExit("refusing to release:\n  - " + "\n  - ".join(problems))
    rows = read_jsonl(INTERIM / "stage1_answers.jsonl")
    if len(rows) != N_STAGE1:
        raise SystemExit(f"expected {N_STAGE1} Stage 1 answers, found {len(rows)}")
    if {r["dataset"] for r in rows} != {d.name for d in DATASETS}:
        raise SystemExit("unexpected dataset set in the frame")
    return rows, meta


def codes_009() -> dict[str, str]:
    """009's published brand codes, read back by aligning its public file with its features."""
    feats = {(r["item_id"], r["arm"], int(r["wave"])): r["brands"] for r in read_jsonl(FEATURES_009)}
    out: dict[str, str] = {}
    pub = pd.read_csv(PUB009_ANSWERS, dtype=str, keep_default_na=False)
    for r in pub.itertuples():
        brands = feats[(r.item_id, r.arm, int(r.wave))]
        codes = [c for c in r.brand_codes.split("|") if c]
        if len(codes) != len(brands):
            raise SystemExit(f"009 alignment failed at {r.item_id} {r.arm} w{r.wave}")
        for b, c in zip(brands, codes):
            if out.setdefault(b, c) != c:
                raise SystemExit(f"009 brand {b!r} has two codes")
    if len(set(out.values())) != len(out):
        raise SystemExit("009 codes are not one-to-one")
    return out


def brand_codes(rows: list[dict]) -> tuple[dict[str, str], dict[str, int]]:
    """(brand key -> code). B2B keys are canonicals; coded datasets' keys are namespaced."""
    reused = codes_009()
    b5 = load_module(SRC_005 / "pipeline/brands.py", "x005_brands")
    universe = {r["canonical"] for r in read_lexicon_rows(LEXICON_V3) if r["decision"] == "keep"}
    universe |= {r["canonical"] for r in read_lexicon_rows(LEXICON_009) if r["decision"] == "keep"}
    universe |= {f"{ns}:{c}" for ns, lex in b5.LEXICONS.items() for c in lex}
    observed = {key(r, b) for r in rows for b in r["order"]}
    unknown = observed - universe - set(reused)
    if unknown:
        raise SystemExit(f"{len(unknown)} observed brands are in no frozen lexicon: {sorted(unknown)[:5]}")
    start = max(int(c[1:]) for c in reused.values()) + 1
    new = sorted(universe - set(reused), key=rank)
    codes = {k: (c if BRAND_PREFIX == "b" else BRAND_PREFIX + c[1:]) for k, c in reused.items()}
    codes |= {k: f"{BRAND_PREFIX}{start + i:04d}" for i, k in enumerate(new)}
    stats = {"reused_009": len(reused), "new": len(new), "first_new": start,
             "observed": len(observed), "observed_reused": len(observed & set(reused))}
    return codes, stats


def key(row: dict, brand: str) -> str:
    ns = NAMESPACE.get(row["dataset"])
    return f"{ns}:{brand}" if ns else brand


def item_codes(rows: list[dict]) -> dict[tuple[str, str], str]:
    out = {}
    for ds, (_, prefix) in CODED.items():
        items = sorted({r["item_id"] for r in rows if r["dataset"] == ds}, key=lambda i: rank(f"item:{ds}:{i}"))
        out |= {(ds, i): f"{prefix}{n + 1:03d}" for n, i in enumerate(items)}
    return out


# ---------------------------------------------------------------- segments


def public_taxonomy() -> tuple[dict[tuple[str, str], str], pd.DataFrame, list[dict]]:
    """(category, original id) -> public id; the B2B segments frame; the edit log."""
    tax = merged_stage_taxonomy()
    used = set()
    seg_map: dict[tuple[str, str], str] = {}
    rows, log = [], []
    for cat, segs in tax.items():
        ids = [s["id"] for s in segs]
        for s in segs:
            rw = REWRITES.get((cat, id_hash(s["id"])))
            if rw:
                used.add((cat, id_hash(s["id"])))
            new_id = (rw or {}).get("id", s["id"])
            seg_map[(cat, s["id"])] = new_id
            if rw:
                log.append({"category": cat, "public_id": new_id, "why": rw["why"],
                            "fields": [f for f in ("id", "label", "definition") if f in rw]})
            if cat in EXPLORE_TAXONOMY_CATEGORIES:
                continue
            rows.append({"category": cat, "segment_id": new_id,
                         "label": (rw or {}).get("label", s["label"]),
                         "definition": (rw or {}).get("definition", s["definition"]),
                         "edited": int(bool(rw))})
        public_ids = [seg_map[(cat, i)] for i in ids]
        if len(set(public_ids)) != len(public_ids):
            raise SystemExit(f"{cat}: a rewritten id collides with another segment id")
    missing = set(REWRITES) - used
    if missing:
        raise SystemExit(f"rewrites that match no segment (taxonomy changed?): {sorted(missing)}")
    return seg_map, pd.DataFrame(rows), log


def taxonomy_scan(seg_map: dict, segments: pd.DataFrame) -> dict:
    """Every public segment label, definition and id against every lexicon alias.

    Two passes: every alias of any length, case-insensitively (stricter than
    each lexicon's own case rule; ids are scanned as words), allowing only
    the reviewed GENERIC_WORDS; and capitalized mid-sentence tokens in a
    definition, allowing only GENERIC_CAPS (catches product names that are
    in no lexicon, such as operating systems or open-source tools).
    """
    aliases = all_aliases()
    rx_all = alias_regex(aliases)
    hits = []
    texts = [(f"{r.category}/{r.segment_id}/{fld}", getattr(r, fld))
             for r in segments.itertuples() for fld in ("label", "definition")]
    texts += [(f"{c}/{i}/id", i.replace("_", " ")) for (c, _), i in seg_map.items()]
    generic = Counter()
    for where, text in texts:
        for m in rx_all.finditer(text):
            w = m.group(0).lower()
            if w in GENERIC_WORDS:
                generic[w] += 1
            else:
                hits.append((where, m.group(0)))
    for r in segments.itertuples():
        for tok in re.findall(r"[A-Za-z0-9][\w&.+-]*", r.definition)[1:]:
            tok = tok.rstrip(".,")
            if any(ch.isupper() for ch in tok) and tok not in GENERIC_CAPS:
                hits.append((f"{r.category}/{r.segment_id}/definition", tok))
    if hits:
        raise SystemExit(f"segment text names a vendor or product: {sorted(set(hits))}")
    return {"aliases": len(aliases), "texts": len(texts), "generic_word_hits": dict(generic)}


# ------------------------------------------------------------------- frames


def build_frames(rows: list[dict], codes: dict[str, str], items: dict, seg_map: dict, bf
                 ) -> tuple[pd.DataFrame, pd.DataFrame]:
    order = {d.name: k for k, d in enumerate(DATASETS)}

    def pub_item(r):
        return items.get((r["dataset"], r["item_id"]), r["item_id"])

    rows = sorted(rows, key=lambda r: (order[r["dataset"]], r["arm"], r["source_exp"],
                                       pub_item(r), int(r["wave"])))
    ans, men = [], []
    for n, r in enumerate(rows, start=1):
        rid = f"r{n:05d}"
        cats = r["cats"]
        coded = r["dataset"] in CODED
        collection = ("claude_ai_by_hand" if r["arm"] in ("ui_default", "ui_think")
                      else "anthropic_api" if r["platform"] == "claude" else "dataforseo")
        n_top = sum(cats[b] == "top_choice" for b in r["order"])
        n_c = sum(cats[b] == "cautioned_against" for b in r["order"])
        ans.append({
            "run_id": rid, "dataset": r["dataset"], "platform": PLATFORM[r["platform"]],
            "collection": collection, "arm": r["arm"],
            "test_arm": flag(r["arm"] == SPEC[r["dataset"]].arm),
            "model": r["model"] or "", "study": STUDY_SLUGS[r["source_exp"]],
            "item_id": pub_item(r),
            "category": CODED[r["dataset"]][0] if coded else r["category"],
            "intent": r["intent"] or "", "wave": int(r["wave"]), "run_date": r["run_date"],
            "n_lexicon_brands": len(r["order"]),
            "n_recommended": sum(cats[b] in REC for b in r["order"]),
            "n_top_choice": n_top, "n_cautioned": n_c,
            "has_top_choice": flag(n_top), "has_caution": flag(n_c),
            "n_top_choice_raw": int(r["n_raw_top_items"]), "n_brands_all": len(r["all_order"]),
            "empty": flag(r["empty"]), "refusal": flag(r["refusal"]),
            "refusal_phrase": flag(r["refusal_phrase"]), "judge_ok": flag(r["judge_ok"]),
        })
        sa = bf.seg_a.get(r["category"], {})
        sb = bf.seg_b.get(r["category"], {})
        for pos, b in enumerate(r["order"], start=1):
            phrases = r["best_for"].get(b, [])
            segs_a, segs_b = [], []
            if cats[b] in REC:
                for p in phrases:
                    for src, dst in ((sa, segs_a), (sb, segs_b)):
                        g = src.get(p)
                        if g and g not in NO_SEGMENT:
                            g = seg_map[(r["category"], g)]
                            if g not in dst:
                                dst.append(g)
            cav = r["caveat_types"].get(b, [])
            men.append({
                "run_id": rid, "brand_code": codes[key(r, b)], "position": pos,
                "status": cats[b], "n_best_for": len(phrases),
                "segment_ids": "|".join(segs_a), "segment_ids_pass_b": "|".join(segs_b),
                "n_caveats": len(cav), "caveat_types": "|".join(cav),
            })
    return pd.DataFrame(ans), pd.DataFrame(men)


def check_b2b_public(answers: pd.DataFrame) -> None:
    """B2B item ids, categories and intents must be exactly 009's public prompts file."""
    prompts = pd.read_csv(PUB009_PROMPTS, dtype=str).set_index("item_id")
    b2b = answers[~answers["dataset"].isin(CODED)]
    for r in b2b.drop_duplicates("item_id").itertuples():
        p = prompts.loc[r.item_id]
        if (p["category"], p["intent"]) != (r.category, r.intent):
            raise SystemExit(f"{r.item_id}: category or intent differs from 009's public prompts")


def check_codes_against_009(answers: pd.DataFrame, mentions: pd.DataFrame) -> int:
    """The claude_b2b rows' code lists must equal 009's public brand_codes for the same answers."""
    pub = pd.read_csv(PUB009_ANSWERS, dtype=str, keep_default_na=False)
    pub = {(r.item_id, r.arm, int(r.wave)): r.brand_codes for r in pub.itertuples()}
    lists = mentions.sort_values(["run_id", "position"]).groupby("run_id")["brand_code"].agg("|".join)
    n = 0
    for r in answers[answers["dataset"] == "claude_b2b"].itertuples():
        mine = lists.get(r.run_id, "")
        if mine != pub[(r.item_id, r.arm, int(r.wave))]:
            raise SystemExit(f"claude_b2b {r.item_id} {r.arm} w{r.wave}: codes differ from 009's file")
        n += 1
    return n


def value_scan(frames: dict[str, pd.DataFrame], extra_texts: dict[str, str]) -> dict:
    """Aliases of at least 4 characters, case-insensitive, over every public string value."""
    rx = alias_regex(all_aliases(), min_len=4)
    hits, allowed = [], Counter()
    for name, df in frames.items():
        for col in df.columns:
            if df[col].dtype != object:
                continue
            for v in set(df[col].astype(str)):
                for t in {m.group(0) for m in rx.finditer(v.replace("_", " "))}:
                    if t.lower() in SCAN_ALLOW or t.lower() in GENERIC_WORDS:
                        allowed[t.lower()] += 1
                    else:
                        hits.append((name, col, v, t))
    for name, text in extra_texts.items():
        for m in rx.finditer(text):
            t = m.group(0).lower()
            if t in SCAN_ALLOW or t in GENERIC_WORDS:
                allowed[t] += 1
            else:
                hits.append((name, "text", "", m.group(0)))
    return {"hits": hits, "allowed": dict(allowed)}


def file_scan(paths: list[Path]) -> dict:
    rx = alias_regex(all_aliases(), min_len=4)
    hits, allowed = [], Counter()
    for p in paths:
        text = p.read_text().replace("_", " ")
        for m in rx.finditer(text):
            t = m.group(0).lower()
            if t in SCAN_ALLOW or t in GENERIC_WORDS:
                allowed[t] += 1
            else:
                hits.append((p.name, m.group(0)))
    return {"hits": hits, "allowed": dict(allowed)}


# --------------------------------------------------------------- datasheets


def common_notes(meta: dict) -> list[str]:
    pin = json.loads(JUDGE_PIN.read_text())
    return [
        f"Pre-registered: spec frozen at commit {SPEC_COMMIT} (2026-10-03). Deviations 1 to 8 "
        "are listed in the spec's section 'Deviations from the frozen spec' "
        f"(experiments/{STUDY}/spec.md). Deviations 1 to 7 were made before any Stage 1 "
        "metric was computed; deviation 8 changes only the article's lead figure.",
        f"Instruments: lexicon v3 sha256 {LEXICON_V3_SHA256}; B2B best-for taxonomy sha256 "
        f"{TAXONOMY_B2B_SHA256} (both pinned in harness/instrument.py, frozen 2026-10-11 "
        "before any confirmatory metric).",
        "Collection. ChatGPT and Gemini: DataForSEO's LLM scraper (US location, English; web "
        "search forced on ChatGPT, which the Gemini endpoint does not accept; Gemini as "
        "served in the Gemini app). Claude: the Anthropic Batches API, Opus 5.5 at effort "
        "medium with no system prompt and the web search tool, user location Pittsburgh, "
        "Pennsylvania (experiment 009's opus55_plain arm). claude.ai: collected by hand in "
        "experiment 009 from one fresh Pro account. The headphone and agency answers are "
        "ChatGPT answers collected through DataForSEO in July and August 2026 by "
        "experiments 002, 003 and 005.",
        "Dates. A DataForSEO run date is the scraper's UTC timestamp, so answers submitted "
        "at 20:00 local time (US) carry the next day's date; a Claude API run date is its batch "
        "submission date. One ChatGPT task of wave 6 ran a day late and keeps its true "
        "date (deviation 2). ChatGPT reported gpt-5-6 in waves 1 to 5 and gpt-6 in waves 6 "
        "and 7.",
        "Brands. New collection: lexicon v3, experiment 009's lexicon v2.1 plus 40 curated brands or aliases, matched after removing citation "
        "links whose text is a domain (deviation 6); Audit D on 30 answers: precision 1.00, "
        "recall 1.00. claude_b2b keeps 009's frozen lexicon v2.1 and extraction; headphone "
        "and agency answers keep experiment 005's frozen lexicons.",
        "Statuses. The Spyglasses production recommendation judge, pinned "
        f"(harness/judge_pin.json: sha256 {pin['sha256']}, Spyglasses commit "
        f"{pin['commit'][:7]}, model {pin['model']}, reasoning effort "
        f"{pin['reasoningEffort']}, MENTION_ASSESSMENT_VERSION 2). Judge test-retest on a "
        "seeded 10% sample (Audit E): 96% category agreement, Cohen's kappa 0.89.",
    ]


def write_datasheets(answers, mentions, segments, meta, code_stats, log) -> dict[str, dict]:
    notes = common_notes(meta)
    n_by = answers.groupby("dataset").size().to_dict()
    tax_notes = [
        "Use-case segments. B2B: the 20 frozen taxonomies, built by the Spyglasses utility model (gpt-5.6-luna, reasoning effort medium) from "
        "6,014 distinct best-for phrases, 7 or 8 segments plus 'general' per category. "
        "Headphones and agencies: the exploration taxonomies (sha256 "
        f"{TAXONOMY_EXPLORE_SHA256}). Each phrase was classified twice (effort none); pass "
        "a is used in the analysis, and the two passes agree on 96% of distinct phrases "
        "(Audit G).",
    ]
    paths = {}
    paths["answers"] = release_dataset(
        answers, ANSWER_COLUMNS, PUBLIC,
        Datasheet(
            title="AI shortlist stability, Stage 1: answers on ChatGPT, Gemini and Claude",
            dataset_slug=ANSWERS_SLUG, study=STUDY, unit="answers",
            notes=[
                f"One row per answer evaluated in this study at Stage 1 ({len(answers):,}): "
                f"840 new answers to 40 synthetic B2B software questions, asked once a day "
                "for 7 days (2026-10-03 to 2026-10-09) on ChatGPT, Gemini and Claude "
                f"({n_by['chatgpt_b2b']} each); {n_by['claude_b2b']} answers from experiment "
                "009's holdout (26 questions x 3 runs x 3 arms, of which ui_default is the "
                f"tested arm); {n_by['chatgpt_consumer']:,} ChatGPT headphone answers (95 "
                f"questions, 17 runs each) and {n_by['chatgpt_agency']} brand-design agency "
                "answers (27 questions, 3 runs each) from the holdouts of experiments 002, "
                "003 and 005. The per-brand rows are in "
                f"{MENTIONS_SLUG}.csv (join on run_id).",
                "The B2B question text is public in experiment 009's release "
                "(claude-api-vs-claude-ai-prompts.csv; item_id joins). Headphone and agency "
                "question text is never published; those item ids and categories are "
                "per-release codes with no published mapping.",
                *notes,
                *tax_notes,
                f"Usable answers: {int((answers['judge_ok'].eq(1) & answers['empty'].eq(0) & answers['refusal'].eq(0)).sum()):,} "
                f"of {len(answers):,}. Under deviation 7 a refusal needs a refusal-shaped "
                f"opening and no lexicon brand; {int(answers['refusal_phrase'].sum())} answers "
                "open like a refusal and then answer, and none is a refusal.",
                "Answer text, best-for phrases, judge evidence, caveat reason text, search "
                "queries and cited URLs are not released.",
            ],
        ),
    )
    paths["mentions"] = release_dataset(
        mentions, MENTION_COLUMNS, PUBLIC,
        Datasheet(
            title="AI shortlist stability, Stage 1: each lexicon brand in each answer",
            dataset_slug=MENTIONS_SLUG, study=STUDY, unit="brand mentions",
            notes=[
                f"One row per lexicon brand named in an answer evaluated in this study "
                f"({len(mentions):,} rows from {len(answers):,} answers; answers that name no "
                f"lexicon brand have no rows). Join to {ANSWERS_SLUG}.csv on run_id.",
                "Brand codes. One code is one brand everywhere in this file. A brand that "
                "experiment 009's public dataset coded keeps 009's code, so the claude_b2b "
                "rows reproduce that file's brand_codes exactly. Every other brand in the "
                f"frozen lexicons was coded from {BRAND_PREFIX}{code_stats['first_new']:04d} "
                "on, in a seeded order over the whole lexicon rather than in order of "
                "appearance. Headphone and agency brands have their "
                "own codes. No mapping to names is published.",
                "Position is first-mention order among lexicon brands. Exact-position "
                "retention (spec: Pk) compares (brand_code, position) pairs; rank 1 is "
                "position 1.",
                "Status is the judge's label: top_choice (singled out as the pick; answers "
                "with more than two are demoted to one_of_many), one_of_many (recommended "
                "alongside others), generic_mention (named without endorsement), "
                "cautioned_against (steered away from for this asker), unclassified (named "
                "but not labeled). The shortlist is top_choice plus one_of_many. When the "
                "judge listed one brand more than once, the strongest label counts "
                "(cautioned_against, then top_choice, one_of_many, generic_mention).",
                *tax_notes,
                *notes,
                "Best-for phrases, judge evidence and caveat reason text are not released.",
            ],
        ),
    )
    n_edit = int(segments["edited"].sum())
    n_ids = sum(1 for e in log if "id" in e["fields"] and e["category"] not in EXPLORE_TAXONOMY_CATEGORIES)
    paths["segments"] = release_dataset(
        segments, SEGMENT_COLUMNS, PUBLIC,
        Datasheet(
            title="AI shortlist stability, Stage 1: the B2B best-for use-case segments",
            dataset_slug=SEGMENTS_SLUG, study=STUDY, unit="use-case segments",
            notes=[
                f"The {segments['category'].nunique()} frozen B2B best-for taxonomies used in "
                f"this study ({len(segments)} segments, including one 'general' segment per "
                f"category). The mentions file's segment_ids join on category and "
                "segment_id.",
                *tax_notes,
                f"Labels and definitions are as the model wrote them, except {n_edit} "
                "segments (edited = 1) whose label, definition or id named a vendor or "
                "product. Spyglasses rewrote those generically before release, keeping the "
                f"meaning; {n_ids} of them also got a new id, used throughout this release. "
                "Every label, definition and id was checked against every alias of the "
                "study's brand lexicons.",
                "Frozen at the instrument freeze (spec, 'Instrument freeze (STOP 2, "
                "2026-10-11)') before any best-for retention was computed.",
                *notes,
            ],
        ),
    )
    return paths


# ---------------------------------------------------------------- checklist


def write_checklist(answers, mentions, segments, code_stats, log, tax_scan, val_scan,
                    file_hits) -> None:
    """Fill the house template once; never overwrite (the file in results/ is the signed record)."""
    path = RESULTS / "release-checklist.md"
    if path.exists():
        signed = "Name: ______________  Date:" not in path.read_text()
        print(f"checklist kept ({'signed' if signed else 'unsigned'}): {path}")
        return
    text = CHECKLIST_TEMPLATE.read_text().replace("<experiment slug>", STUDY)
    text = text.replace('"citations evaluated in this study"', '"answers evaluated in this study"')
    n_codes_obs = mentions["brand_code"].nunique()
    notes = {
        "Every column is a **derived feature": (
            f"(010: {len(ANSWER_COLUMNS)} answer columns, {len(MENTION_COLUMNS)} mention "
            f"columns and {len(SEGMENT_COLUMNS)} segment columns, each allow-listed with a "
            "description in `pipeline/25_release.py`. The spec's `prompt_intent` ships as "
            "`intent` and the answer key as `run_id`, because the gate refuses column names "
            "containing 'prompt' or 'answer'.)"),
        "No customer prompt text": (
            "(010: no answer text, question text, best-for phrases, judge evidence, caveat "
            "reason text, search queries or URLs. The only model-written text is the B2B "
            "segment labels and definitions, see the decisions below.)"),
        "No customer, property": (
            "(010: no customer data was used. Brands ship as `bNNNN` codes "
            f"({n_codes_obs} distinct codes in the mentions file); headphone and agency "
            "item ids and categories as per-release codes. Answer ids `rNNNNN` are "
            "sequential in a sort by dataset, arm, study, item and wave, so they carry no "
            "information beyond those public columns.)"),
        "Free-text columns marked": (
            "(010: only `model` is marked public_fact. It holds the model strings the "
            "platforms reported: gpt-5-6, gpt-6, gpt-5-5, 3.5 Flash-Lite, "
            "claude-opus-5-5, claude.ai, or blank.)"),
        "The datasheet and every mention": (
            f"(010: {len(answers):,} answers evaluated in this study; the mentions file "
            f"reports {len(mentions):,} brand mentions in those answers; the segments file "
            f"{len(segments)} use-case segments.)"),
        "Nothing in the dataset, datasheet": (
            "(010: the brand-code range reveals the size of the frozen lexicons, which are "
            "study instruments, not the Spyglasses database.)"),
        "Could any set of rows": (
            "(010: no customer is involved. The new collection used Spyglasses' own "
            "DataForSEO and Anthropic accounts, and claude.ai rows come from 009's fresh "
            "Pro account. Brand names are withheld per 009's 2026-10-02 release "
            "instruction.)"),
        "Third-party data terms": (
            "(010: DataForSEO and Anthropic outputs appear only as derived counts, labels "
            "and codes, not raw payloads.)"),
    }
    lines = []
    for line in text.splitlines():
        if line.startswith("- Name:"):
            line = "- Name: ______________  Date: ______________"
        elif line.startswith("- Release gate run:"):
            line = "- Release gate run: `pipeline/25_release.py --stage 1` exit 0 on ______________"
        elif line.startswith("- [ ]"):
            line = "- [x]" + line[len("- [ ]"):]
        lines.append(line)
    out = "\n".join(lines) + "\n"
    for anchor, note in notes.items():
        start = out.index(anchor)
        ends = [out.find(sep, start) for sep in ("\n- [", "\n\n")]
        end = min(e for e in ends if e != -1)
        wrapped = textwrap.fill(note, 78, initial_indent="      ", subsequent_indent="      ")
        out = out[:end] + "\n" + wrapped + out[end:]

    def item(body: str) -> str:
        return textwrap.fill(body, 78, initial_indent="- [ ] ", subsequent_indent="      ")

    b2b_log = [e for e in log if e["category"] not in EXPLORE_TAXONOMY_CATEGORIES]
    hp_log = [e for e in log if e["category"] in EXPLORE_TAXONOMY_CATEGORIES]
    edits = "\n".join(
        textwrap.fill(f"{e['category']} / `{e['public_id']}`: {e['why']}; rewrote "
                      f"{', '.join(e['fields'])}.", 78, initial_indent="      - ",
                      subsequent_indent="        ")
        for e in b2b_log)
    generic = ", ".join(f"'{w}' ({GENERIC_WORDS[w]})" for w in sorted(tax_scan["generic_word_hits"]))
    allowed = ", ".join(f"'{w}' ({(SCAN_ALLOW | GENERIC_WORDS)[w]})"
                        for w in sorted(set(val_scan["allowed"]) | set(file_hits["allowed"])))
    decisions = "\n\n".join([
        "## Decisions to confirm when signing (tick each)",
        item(
            "Brand codes reuse 009's published `bNNNN` strings (spec §3 writes `v0001`, "
            "\"as in 009's release\", but 009 shipped `bNNNN`). Reusing the exact strings "
            f"lets the {int((answers['dataset'] == 'claude_b2b').sum())} claude_b2b rows "
            "join 009's public answers file (checked: their code lists equal 009's "
            f"`brand_codes` row for row). {code_stats['reused_009']} codes are 009's; "
            f"{code_stats['new']} new codes ({BRAND_PREFIX}{code_stats['first_new']:04d} "
            "on) cover every other brand of the frozen lexicons (lexicon v3 keep rows and "
            "005's headphone and agency lexicons), in a seeded order over the whole "
            "lexicon, so Stage 2 can keep them. A new code tells a reader the brand was "
            "not in 009's answers; nothing else. To ship `v` codes instead, set "
            "BRAND_PREFIX = \"v\" (the join to 009 then needs b -> v)."),
        item(
            "Headphone and agency brands are coded in their own namespace (one agency name "
            "is spelled like a B2B brand and is a different company). Note: 002, 003 and "
            "005 published headphone and agency brand names in the clear; this release is "
            "stricter, per spec §3."),
        item(
            "Headphone and agency categories ship as `cat_c1` and `cat_a1` and their item "
            "ids as per-release codes (spec §3). The categories themselves are public "
            "(002's release, the article), so this is belt and braces; the agency segment "
            "ids (for example `coffee_cafe_specialists`) also show the agency vertical."),
        item(
            "Headphone and agency segment ids ship in the mentions file without labels. "
            + (f"{len(hp_log)} headphone segment id named a device maker that is a brand in "
               f"the headphone lexicon; it ships as `{hp_log[0]['public_id']}`. "
               if hp_log else "")
            + "No agency segment id names a brand."),
        item(
            f"B2B segment text: {len(b2b_log)} of {len(segments)} segments named vendors or "
            "products in the model-written label, definition or id and were rewritten "
            "generically (the originals are in data/raw/bestfor_taxonomy_b2b/taxonomy.json, "
            "not committed; this list says what was named without repeating it):")
        + "\n" + edits,
        item(
            "The B2B definitions are model-written summaries of clusters of best-for "
            "phrases (an instrument, built from many answers), not answer text. If you read "
            "them as too close to AI response text, drop the `definition` column (remove it "
            "from SEGMENT_COLUMNS) and publish labels only."),
        item(
            "Scans, all clean: (1) every B2B label, definition and public id against "
            f"{tax_scan['aliases']:,} aliases (lexicon v3 and 009 v2.1, keep and drop "
            "rows, and 005's lexicons), case-insensitively, plus a capitalized-name check on every definition that "
            "catches product names in no lexicon. Accepted as ordinary words: "
            f"{generic}. (2) Every public value, every column description and note, and "
            "the written CSV and datasheet files against every alias of at least 4 "
            "characters, case-insensitively; accepted: "
            f"{allowed}. No other hit."),
        item(
            "Brand codes are pseudonyms, not anonymity. As with 009's codes, a reader who "
            "knows a market can guess the most frequent codes in a category, and a few "
            "segment ids sharpen the guess (for example the brand most often placed in a "
            "productivity-suite ecosystem segment, or in the headphone segment "
            "`single_ecosystem_users`). No name ships; confirm this is acceptable, as it was "
            "for 009."),
        item(
            "Answer-level flags: `refusal` follows deviation 7 (0 refusals of 2,770); "
            "`refusal_phrase` keeps the old heuristic's 3 flags for transparency."),
        item(
            "Not released: R1's names outside the lexicon (only the count "
            "`n_brands_all`), the Audit E second-pass labels, and the per-answer judge "
            "metadata (sha, version), which is constant and stated in the datasheets."),
    ])
    prereq = (
        "## Prerequisite\n\n- [x] Audit D signed by Jim Wrubel (`results/audit_d_score.json`,"
        "\n      scored at the instrument freeze, 2026-10-11): precision 1.00, recall 1.00\n"
        "      against gates 0.95 / 0.90.\n\n"
    )
    anchor = out.index("## Sign-off")
    out = out[:anchor] + decisions + "\n\n" + prereq + out[anchor:]
    path.write_text(out)
    print(f"checklist (unsigned): {path}")


# --------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True)
    a = ap.parse_args()
    if a.stage == 2:
        stage2_not_implemented()
    if sha256_file(TAXONOMY_B2B) != TAXONOMY_B2B_SHA256:
        raise SystemExit("taxonomy changed")

    rows, meta = check_inputs()
    bf = load_bestfor(RAW / "bestfor_stage1")
    if bf is None or bf.taxonomy != merged_stage_taxonomy():
        raise SystemExit("bestfor_stage1 files missing or not the frozen taxonomy")
    seg_map, segments, log = public_taxonomy()
    for cat, m in list(bf.seg_a.items()) + list(bf.seg_b.items()):
        bad = {g for g in m.values() if g not in NO_SEGMENT and (cat, g) not in seg_map}
        if bad:
            raise SystemExit(f"{cat}: classifier segments outside the taxonomy: {sorted(bad)}")
    tax_scan = taxonomy_scan(seg_map, segments)
    print(f"segment scan: {tax_scan['texts']} texts x {tax_scan['aliases']} aliases, "
          f"0 vendor names (generic words accepted: {tax_scan['generic_word_hits']})")

    codes, code_stats = brand_codes(rows)
    items = item_codes(rows)
    answers, mentions = build_frames(rows, codes, items, seg_map, bf)
    check_b2b_public(answers)
    n_join = check_codes_against_009(answers, mentions)
    print(f"brand codes: {code_stats}; claude_b2b rows matching 009's public codes: {n_join}")
    if len(answers) != N_STAGE1 or answers["refusal"].sum() or answers["empty"].sum():
        raise SystemExit("unexpected answer counts, refusals or empty answers")

    descriptions = " ".join(c.description for c in ANSWER_COLUMNS + MENTION_COLUMNS + SEGMENT_COLUMNS)
    val_scan = value_scan({"answers": answers, "mentions": mentions, "segments": segments},
                          {"column descriptions": descriptions,
                           "notes": " ".join(common_notes(meta))})
    if val_scan["hits"]:
        raise SystemExit(f"brand alias in a public value: {val_scan['hits'][:20]}")
    print(f"value scan: 0 hits (accepted: {val_scan['allowed']})")

    outputs = [PUBLIC / f"{s}{ext}" for s in (ANSWERS_SLUG, MENTIONS_SLUG, SEGMENTS_SLUG)
               for ext in (".csv", ".datasheet.md")]
    try:
        paths = write_datasheets(answers, mentions, segments, meta, code_stats, log)
    except Exception:
        for p in outputs:  # never leave a partial release behind
            p.unlink(missing_ok=True)
        raise
    written = [p for d in paths.values() for p in d.values()]
    file_hits = file_scan(written)
    if file_hits["hits"]:
        for p in written:
            p.unlink()
        raise SystemExit(f"brand alias in a written file, outputs deleted: {file_hits['hits'][:20]}")
    print(f"file scan: {len(written)} files, 0 hits (accepted: {file_hits['allowed']})")
    for p in written:
        print(f"released: {p}")
    print(f"rows: answers {len(answers):,}, mentions {len(mentions):,}, segments {len(segments)}")

    write_checklist(answers, mentions, segments, code_stats, log, tax_scan, val_scan, file_hits)
    print("Do not commit data/public/ or sync the datasets to the site until the release "
          "checklist is signed.")


if __name__ == "__main__":
    main()
