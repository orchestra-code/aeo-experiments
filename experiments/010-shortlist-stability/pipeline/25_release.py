"""Stage 25: gate-checked public datasets -> data/public/ (spec §3, §8 steps 6 and 8).

``--stage 1`` is the signed Stage 1 release (2026-10-11: new-collection waves
1 to 7 and the holdouts). ``--stage 2`` is the Stage 2 update: the same three
files, names and columns, now with waves 1 to 11 of the new collection (the
holdout rows are unchanged). The Stage 2 update keeps every Stage 1 row byte
for byte, in the same place at the top of each file, with the same run ids,
brand codes and segment ids; the waves 8 to 11 rows follow, numbered on from
the last Stage 1 run id. Before writing, Stage 2 rebuilds the Stage 1 release
in-process, checks it against the sha256 of the signed Stage 1 files, and
checks that each Stage 2 file starts with exactly those bytes; after writing,
it checks the written files again.

Three files, written through ``aeo_research.release_dataset``:

- ``ai-shortlist-stability-answers.csv``: one row per answer of the stage
  (all six datasets, every arm), derived counts and flags only.
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

Checks before anything is written: the frame is the stage's confirmatory
frame built with the frozen lexicon v3 and taxonomy (Stage 2: built after
every wave 8 to 11 task and the Stage 2 re-judge sample were judged OK, with
the Stage 2 best-for files classified), Audit D passed and is
signed, 009's codes are reproduced exactly from its public file, every
segment label and definition is clean against every lexicon alias (009's
v2.1, lexicon v3, 005's lexicons, keep and drop rows) and a capitalized-name
heuristic, and every public value and datasheet passes an alias scan
(aliases of at least 4 characters, case-insensitive). After writing, the
files are scanned again; a hit deletes them.

The checklists ``results/release-checklist.md`` (Stage 1, signed) and
``results/release-checklist-stage2.md`` (the Stage 2 update) are each written
once and never overwritten. Do not commit data/public/ until the stage's
checklist is signed, and do not sync the datasets to the site before that
(``sync_site_assets.py --figures-only``).

Usage: uv run python experiments/010-shortlist-stability/pipeline/25_release.py --stage 2
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
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from common import (
    DATASETS,
    EXP,
    EXPLORE_TAXONOMY_CATEGORIES,
    JUDGE_PIN,
    LEXICON_V3,
    LEXICON_V3_SHA256,
    NEW_DATASETS,
    RAW,
    REC,
    RESULTS,
    SEED,
    SPEC,
    SRC_005,
    SRC_009,
    STAGE2_NEW_WAVES,
    STAGE_WAVES,
    TAXONOMY_B2B,
    TAXONOMY_B2B_SHA256,
    TAXONOMY_EXPLORE_SHA256,
    WAVE_OFFSETS,
    Mode,
    audit_d_problems,
    bestfor_problems,
    instrument_problems,
    load_bestfor,
    load_module,
    load_stage_bestfor,
    merged_stage_taxonomy,
    read_jsonl,
    sha256_file,
)

from aeo_research import ColumnSpec, Datasheet, release_dataset

STUDY = "010-shortlist-stability"
PUBLIC = EXP / "data" / "public"
CHECKLIST_TEMPLATE = EXP.parents[1] / "templates" / "release-checklist.md"
ANSWERS_SLUG = "ai-shortlist-stability-answers"
MENTIONS_SLUG = "ai-shortlist-stability-mentions"
SEGMENTS_SLUG = "ai-shortlist-stability-segments"
SPEC_COMMIT = "6342963"
#: Answers in each stage's frame: Stage 1 = new waves 1 to 7 + holdouts; Stage
#: 2 adds 3 platforms x 40 prompts x waves 8 to 11.
N_ANSWERS = {1: 2770, 2: 3250}
STAGE1_RELEASED = "2026-10-11"
#: sha256 of the three CSVs of the signed Stage 1 release (results/
#: release-checklist.md, signed 2026-10-11; commit 4432548). The Stage 2
#: update rebuilds Stage 1 in-process, must reproduce these bytes, and must
#: start each of its files with them.
STAGE1_CSV_SHA256 = {
    "ai-shortlist-stability-answers": "829a4ca17e2d9134ba0e1a53dc7b107bd37ef0cedc4cef69d70dd7ed8b5d235c",
    "ai-shortlist-stability-mentions": "0390179f1830ac6e7b246a00cbc009a1266cd2626f968ac3b1adea8a6a083eb9",
    "ai-shortlist-stability-segments": "ac564322df9ff3e160053fa25f1e374ff6b5d18adf2c122c3ebd459fe7caed6c",
}
SCHEDULE = EXP / "collection_schedule.json"

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

#: Stage 2 descriptions of the answer columns whose meaning widened (same
#: columns, same names; the other descriptions are Stage 1's).
ANSWER_COLUMNS_STAGE2 = {
    "run_id": (
        "Id of one answer evaluated in this study; joins the mentions file. r00001 to "
        f"r{N_ANSWERS[1]:05d} are the Stage 1 release's ids, unchanged; r{N_ANSWERS[1] + 1:05d} "
        f"to r{N_ANSWERS[2]:05d} are the answers of waves 8 to 11"),
    "wave": (
        "Run number within the study: 1 to 11 for the new collection (waves 1 to 7 daily "
        "from 2026-10-03, waves 8 to 11 weekly from 2026-10-16), 1 to 3 for claude_b2b, and "
        "the source study's wave (1 to 7) for the consumer and agency answers. Rows with "
        "wave 1 to 7 are the Stage 1 release"),
}


def answer_columns(stage: int) -> list[ColumnSpec]:
    if stage == 1:
        return ANSWER_COLUMNS
    return [replace(c, description=ANSWER_COLUMNS_STAGE2.get(c.name, c.description))
            for c in ANSWER_COLUMNS]

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


def stage2_added(row: dict) -> bool:
    """A new-collection answer of waves 8 to 11 (what the Stage 2 update adds)."""
    return row["dataset"] in NEW_DATASETS and int(row["wave"]) in STAGE2_NEW_WAVES


def wave_dates(waves) -> list[str]:
    """Scheduled local date of each wave (collection_schedule.json start + offset)."""
    start = date.fromisoformat(json.loads(SCHEDULE.read_text())["start"])
    return [(start + timedelta(days=WAVE_OFFSETS[w - 1])).isoformat() for w in waves]


def csv_bytes(df: pd.DataFrame, columns: list[ColumnSpec]) -> bytes:
    """The bytes release_dataset writes for this frame (df[names].to_csv, index=False)."""
    return df[[c.name for c in columns]].to_csv(index=False).encode()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


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


def check_inputs(stage: int = 1) -> tuple[list[dict], dict]:
    mode = Mode("confirmatory", stage)
    problems = instrument_problems() + audit_d_problems(mode)
    meta_path = mode.meta_path
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if meta.get("mode") != "confirmatory" or meta.get("stage") != stage:
        problems.append(f"{mode.answers_path.name} is not the confirmatory Stage {stage} frame")
    if meta.get("lexicon_v3_sha256") != LEXICON_V3_SHA256:
        problems.append("the answer frame was built with another lexicon v3")
    if meta.get("taxonomy_b2b_sha256") != TAXONOMY_B2B_SHA256:
        problems.append("the answer frame was built with another B2B taxonomy")
    if meta.get("judge_rows_off_pin"):
        problems.append("judged rows off the judge pin")
    if meta.get("max_new_wave") != max(STAGE_WAVES[stage]):
        problems.append(f"the frame's last new-collection wave is {meta.get('max_new_wave')}, "
                        f"not {max(STAGE_WAVES[stage])}")
    if stage == 2:
        if not meta.get("stage2_inputs_complete"):
            problems.append("the Stage 2 frame was built before every wave 8 to 11 task and the "
                            "Stage 2 re-judge sample were judged OK")
        problems += bestfor_problems(mode)
    if problems:
        raise SystemExit("refusing to release:\n  - " + "\n  - ".join(problems))
    rows = read_jsonl(mode.answers_path)
    if len(rows) != N_ANSWERS[stage]:
        raise SystemExit(f"expected {N_ANSWERS[stage]} Stage {stage} answers, found {len(rows)}")
    if {r["dataset"] for r in rows} != {d.name for d in DATASETS}:
        raise SystemExit("unexpected dataset set in the frame")
    added = [r for r in rows if stage2_added(r)]
    want = 0 if stage == 1 else len(NEW_DATASETS) * 40 * len(STAGE2_NEW_WAVES)
    if len(added) != want:
        raise SystemExit(f"expected {want} waves 8 to 11 answers in the frame, found {len(added)}")
    return rows, meta


def stage_bestfor(stage: int):
    """Stage 1: bestfor_stage1 as is. Stage 2: Stage 1's classifications plus the
    Stage 2 classifications of the phrases Stage 1 did not see (deviation 10b)."""
    bf = (load_bestfor(RAW / "bestfor_stage1") if stage == 1
          else load_stage_bestfor(Mode("confirmatory", 2)))
    if bf is None or bf.taxonomy != merged_stage_taxonomy():
        raise SystemExit(f"Stage {stage} best-for files missing or not the frozen taxonomy")
    if stage == 2:
        s1 = load_bestfor(RAW / "bestfor_stage1")
        for c in s1.seg_a:
            for src, dst in ((s1.seg_a, bf.seg_a), (s1.seg_b, bf.seg_b)):
                changed = [p for p, g in src[c].items() if dst[c].get(p) != g]
                if changed:
                    raise SystemExit(f"{c}: {len(changed)} Stage 1 phrases changed segment at "
                                     "Stage 2 (deviation 10b keeps their Stage 1 classification)")
    return bf


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
    """Answer and mention frames. Rows sort by dataset, arm, study, item and
    wave; the answers a Stage 2 update adds (waves 8 to 11) sort after every
    Stage 1 row, in the same order, so Stage 1 rows keep their run ids and the
    Stage 1 file is a prefix of the updated one."""
    order = {d.name: k for k, d in enumerate(DATASETS)}

    def pub_item(r):
        return items.get((r["dataset"], r["item_id"]), r["item_id"])

    rows = sorted(rows, key=lambda r: (stage2_added(r), order[r["dataset"]], r["arm"],
                                       r["source_exp"], pub_item(r), int(r["wave"])))
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


def pct(x: float) -> str:
    return f"{round(100 * x)}%"


def stage2_audit_figures() -> dict:
    """Audit E (the Stage 2 sample) and Audit G (every phrase Stage 2 uses), from 21_audits.py."""
    d = json.loads((RESULTS / "stage2_audits.json").read_text())
    if not d["E"].get("passes") or not d["G"].get("passes"):
        raise SystemExit("Stage 2 Audit E or Audit G did not pass (results/stage2_audits.json)")
    g = d["G"]["groups"]
    return {"e": d["E"]["groups"]["Stage 2 sample (waves 8 to 11)"], "g": g["all"],
            "g_new": g["classified at Stage 2 (new phrases)"],
            "g_reused": g["classified at Stage 1 (reused)"]}


def check_stage2_models(answers: pd.DataFrame) -> None:
    """The model strings the Stage 2 datasheets describe (Audit F, deviation 9)."""
    new = answers[answers["dataset"].isin(NEW_DATASETS)]
    for (ds, w, m), n in Counter(zip(new["dataset"], new["wave"], new["model"])).items():
        ok = {"chatgpt_b2b": m == ("gpt-5-6" if w <= 5 else "gpt-6"),
              "gemini_b2b": m == "3.5 Flash-Lite" or (m == "3.6 Flash" and w == 8 and n == 1),
              "claude_api_b2b": m == "claude-opus-5-5"}[ds]
        if not ok:
            raise SystemExit(f"{ds} wave {w} reports {m!r} ({n}); the datasheet notes say otherwise")


def common_notes(meta: dict, stage: int = 1) -> list[str]:
    pin = json.loads(JUDGE_PIN.read_text())
    if stage == 1:
        deviations = (
            f"Pre-registered: spec frozen at commit {SPEC_COMMIT} (2026-10-03). Deviations 1 to 8 "
            "are listed in the spec's section 'Deviations from the frozen spec' "
            f"(experiments/{STUDY}/spec.md). Deviations 1 to 7 were made before any Stage 1 "
            "metric was computed; deviation 8 changes only the article's lead figure.")
        dates = (
            "Dates. A DataForSEO run date is the scraper's UTC timestamp, so answers submitted "
            "at 20:00 local time (US) carry the next day's date; a Claude API run date is its batch "
            "submission date. One ChatGPT task of wave 6 ran a day late and keeps its true "
            "date (deviation 2). ChatGPT reported gpt-5-6 in waves 1 to 5 and gpt-6 in waves 6 "
            "and 7.")
        audit_e = ("Judge test-retest on a seeded 10% sample (Audit E): 96% category agreement, "
                   "Cohen's kappa 0.89.")
        run_notes = []
    else:
        e = stage2_audit_figures()["e"]
        deviations = (
            f"Pre-registered: spec frozen at commit {SPEC_COMMIT} (2026-10-03). Deviations 1 to "
            "10 are listed in the spec's section 'Deviations from the frozen spec' "
            f"(experiments/{STUDY}/spec.md). Deviations 1 to 7 were made before any Stage 1 "
            "metric was computed; deviation 8 changes only the first article's lead figure; "
            "deviation 9 records the Stage 2 collection (waves 8 to 11) and deviation 10 the "
            "Stage 2 implementation choices, recorded before any Stage 2 metric was computed.")
        dates = (
            "Dates. A DataForSEO run date is the scraper's UTC timestamp, so answers submitted "
            "at 20:00 local time (US) carry the next day's date; a Claude API run date is its batch "
            "submission date. Tasks that failed and ran late keep their true dates: one ChatGPT "
            "task of wave 6 (deviation 2) and 7 Gemini tasks of wave 8, dated 2026-10-18 "
            "(deviation 9).")
        audit_e = (
            "Judge test-retest (Audit E) on seeded 10% samples: 96% category agreement, Cohen's "
            f"kappa 0.89 at Stage 1; {pct(e['agreement'])} agreement, kappa {e['kappa']:.2f} on "
            f"the {e['answers']} answers sampled from waves 8 to 11.")
        run_notes = [
            "Stage 2 run notes (deviation 9). All 40 questions were collected on every platform "
            "in every wave, with no empty answer and no refusal. Wave 9 started 1 to 2.5 hours "
            "late; no run date changed. ChatGPT reported gpt-5-6 in waves 1 to 5 and gpt-6 in "
            "waves 6 to 11, so ChatGPT comparisons across the weekly waves span that model "
            "change. Gemini reported 3.5 Flash-Lite on every answer but one, a wave 8 answer "
            "that reports 3.6 Flash. Every Claude API answer reports claude-opus-5-5."]
    return [
        deviations,
        f"Instruments: lexicon v3 sha256 {LEXICON_V3_SHA256}; B2B best-for taxonomy sha256 "
        f"{TAXONOMY_B2B_SHA256} (both pinned in harness/instrument.py, frozen 2026-10-11 "
        "before any confirmatory metric"
        + (", and used unchanged for both stages)." if stage == 2 else ")."),
        "Collection. ChatGPT and Gemini: DataForSEO's LLM scraper (US location, English; web "
        "search forced on ChatGPT, which the Gemini endpoint does not accept; Gemini as "
        "served in the Gemini app). Claude: the Anthropic Batches API, Opus 5.5 at effort "
        "medium with no system prompt and the web search tool, user location Pittsburgh, "
        "Pennsylvania (experiment 009's opus55_plain arm). claude.ai: collected by hand in "
        "experiment 009 from one fresh Pro account. The headphone and agency answers are "
        "ChatGPT answers collected through DataForSEO in July and August 2026 by "
        "experiments 002, 003 and 005.",
        dates,
        *run_notes,
        "Brands. New collection: lexicon v3, experiment 009's lexicon v2.1 plus 40 curated brands or aliases, matched after removing citation "
        "links whose text is a domain (deviation 6); Audit D on 30 answers: precision 1.00, "
        "recall 1.00. claude_b2b keeps 009's frozen lexicon v2.1 and extraction; headphone "
        "and agency answers keep experiment 005's frozen lexicons.",
        "Statuses. The Spyglasses production recommendation judge, pinned "
        f"(harness/judge_pin.json: sha256 {pin['sha256']}, Spyglasses commit "
        f"{pin['commit'][:7]}, model {pin['model']}, reasoning effort "
        f"{pin['reasoningEffort']}, MENTION_ASSESSMENT_VERSION 2). {audit_e}",
    ]


def taxonomy_notes(stage: int) -> list[str]:
    head = (
        "Use-case segments. B2B: the 20 frozen taxonomies, built by the Spyglasses utility "
        "model (gpt-5.6-luna, reasoning effort medium) from 6,014 distinct best-for phrases, 7 "
        "or 8 segments plus 'general' per category. Headphones and agencies: the exploration "
        f"taxonomies (sha256 {TAXONOMY_EXPLORE_SHA256}). Each phrase was classified twice "
        "(effort none); pass a is used in the analysis, and ")
    if stage == 1:
        return [head + "the two passes agree on 96% of distinct phrases (Audit G)."]
    a = stage2_audit_figures()
    return [
        head + f"the two passes agree on {pct(a['g']['agreement'])} of the "
        f"{a['g']['phrases']:,} distinct phrases Stage 2 uses (Audit G). The "
        f"{a['g_reused']['phrases']:,} phrases already classified at Stage 1 keep their Stage 1 "
        "classifications; "
        f"the {a['g_new']['phrases']:,} phrases first seen at Stage 2 were classified twice with "
        "the same frozen taxonomies (deviation 10), so no Stage 1 row's segment ids change."]


def changelog(rel: SimpleNamespace, s1: SimpleNamespace) -> str:
    """The Changelog section appended to each Stage 2 datasheet."""
    n1, n2 = len(s1.answers), len(rel.answers)
    m1, m2 = len(s1.mentions), len(rel.mentions)
    d = wave_dates(range(1, 12))
    items = [
        f"{STAGE1_RELEASED}, Stage 1 release: new-collection waves 1 to 7 ({d[0]} to {d[6]}) "
        f"and the holdouts; {n1:,} answers (run_id r00001 to r{n1:05d}), {m1:,} brand mentions "
        f"and {len(s1.segments)} use-case segments.",
        f"{date.today().isoformat()}, Stage 2 update: adds waves 8 to 11 of the new collection "
        f"({', '.join(d[7:10])} and {d[10]}): {n2 - n1:,} answers (run_id r{n1 + 1:05d} to "
        f"r{n2:05d}) and {m2 - m1:,} brand mentions. The holdout rows and the segments file are "
        "unchanged. Every Stage 1 row is unchanged, byte for byte, and comes first in its file, "
        "with the same run_id, brand codes and segment ids.",
        f"Stage 1 data only: keep the answers with wave 7 or less (no holdout row has a later "
        f"wave; these are run_id r00001 to r{n1:05d}) and the mentions whose run_id is among "
        "them. That gives back the Stage 1 CSV files exactly.",
    ]
    return "## Changelog\n\n" + "\n".join(f"- {i}" for i in items) + "\n"


def write_datasheets(rel: SimpleNamespace, s1: SimpleNamespace | None = None
                     ) -> dict[str, dict]:
    stage = rel.stage
    answers, mentions, segments = rel.answers, rel.mentions, rel.segments
    code_stats, log = rel.code_stats, rel.log
    notes = common_notes(rel.meta, stage)
    tax_notes = taxonomy_notes(stage)
    n_by = answers.groupby("dataset").size().to_dict()
    title = "AI shortlist stability, " + ("Stage 1" if stage == 1 else "Stages 1 and 2")
    if stage == 1:
        scope = (
            f"One row per answer evaluated in this study at Stage 1 ({len(answers):,}): "
            f"840 new answers to 40 synthetic B2B software questions, asked once a day "
            "for 7 days (2026-10-03 to 2026-10-09) on ChatGPT, Gemini and Claude "
            f"({n_by['chatgpt_b2b']} each); ")
    else:
        d = wave_dates(range(1, 12))
        n_new = sum(n_by[ds] for ds in NEW_DATASETS)
        scope = (
            f"One row per answer evaluated in this study ({len(answers):,}): {n_new:,} new "
            "answers to 40 synthetic B2B software questions on ChatGPT, Gemini and Claude "
            f"({n_by['chatgpt_b2b']} each), asked in 11 waves: daily for 7 days (waves 1 to 7, "
            f"{d[0]} to {d[6]}), then weekly (waves 8 to 11: {', '.join(d[7:10])} and {d[10]}; "
            "local submission dates); ")
    scope += (
        f"{n_by['claude_b2b']} answers from experiment "
        "009's holdout (26 questions x 3 runs x 3 arms, of which ui_default is the "
        f"tested arm); {n_by['chatgpt_consumer']:,} ChatGPT headphone answers (95 "
        f"questions, 17 runs each) and {n_by['chatgpt_agency']} brand-design agency "
        "answers (27 questions, 3 runs each) from the holdouts of experiments 002, "
        "003 and 005. "
        + ("The holdout rows are those of the Stage 1 release, unchanged. " if stage == 2 else "")
        + f"The per-brand rows are in {MENTIONS_SLUG}.csv (join on run_id).")
    paths = {}
    paths["answers"] = release_dataset(
        answers, answer_columns(stage), PUBLIC,
        Datasheet(
            title=f"{title}: answers on ChatGPT, Gemini and Claude",
            dataset_slug=ANSWERS_SLUG, study=STUDY, unit="answers",
            notes=[
                scope,
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
    code_note = (
        "Brand codes. One code is one brand everywhere in this file. A brand that "
        "experiment 009's public dataset coded keeps 009's code, so the claude_b2b "
        "rows reproduce that file's brand_codes exactly. Every other brand in the "
        f"frozen lexicons was coded from {BRAND_PREFIX}{code_stats['first_new']:04d} "
        "on, in a seeded order over the whole lexicon rather than in order of "
        "appearance. Headphone and agency brands have their "
        "own codes. No mapping to names is published.")
    if stage == 2:
        code_note += (
            " The Stage 2 update uses the same code table, so every code means the same brand "
            "as in the Stage 1 release, and adds no code: the table already covered every "
            "brand of the frozen lexicons, which stay frozen for Stage 2 (spec firewall rule 4), "
            "so a brand outside them is counted only in the answers file's n_brands_all. "
            f"{len(rel.first_seen)} codes appear for the first time in waves 8 to 11.")
    paths["mentions"] = release_dataset(
        mentions, MENTION_COLUMNS, PUBLIC,
        Datasheet(
            title=f"{title}: each lexicon brand in each answer",
            dataset_slug=MENTIONS_SLUG, study=STUDY, unit="brand mentions",
            notes=[
                f"One row per lexicon brand named in an answer evaluated in this study "
                f"({len(mentions):,} rows from {len(answers):,} answers; answers that name no "
                f"lexicon brand have no rows). Join to {ANSWERS_SLUG}.csv on run_id.",
                code_note,
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
            title=f"{title}: the B2B best-for use-case segments",
            dataset_slug=SEGMENTS_SLUG, study=STUDY, unit="use-case segments",
            notes=[
                f"The {segments['category'].nunique()} frozen B2B best-for taxonomies used in "
                f"this study ({len(segments)} segments, including one 'general' segment per "
                f"category). The mentions file's segment_ids join on category and "
                "segment_id.",
                *(["Unchanged by the Stage 2 update: the taxonomies are frozen for both "
                   "stages, and this file is byte for byte the Stage 1 release's."]
                  if stage == 2 else []),
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
    if stage == 2:
        log_text = changelog(rel, s1)
        for d in paths.values():
            md = d["datasheet"]
            md.write_text(md.read_text() + "\n" + log_text)
    return paths


# ---------------------------------------------------------------- checklist


BLANK_SIGNATURE = "- Name: ______________  Date: ______________"


def checklist_kept(path: Path) -> bool:
    """A checklist in results/ is the signed record: written once, never overwritten."""
    if not path.exists():
        return False
    signed = "Name: ______________  Date:" not in path.read_text()
    print(f"checklist kept ({'signed' if signed else 'unsigned'}): {path}")
    return True


def check_item(body: str, break_on_hyphens: bool = True) -> str:
    return textwrap.fill(body, 78, initial_indent="- [ ] ", subsequent_indent="      ",
                         break_on_hyphens=break_on_hyphens)


def fill_template(notes: dict[str, str], stage: int, decisions: str, prereq: str,
                  break_on_hyphens: bool = True) -> str:
    """The house template with the content items ticked (each with its 010 note
    under it), the decisions and prerequisites before the sign-off, and the
    sign-off lines blank for Jim."""
    text = CHECKLIST_TEMPLATE.read_text().replace("<experiment slug>", STUDY)
    text = text.replace('"citations evaluated in this study"', '"answers evaluated in this study"')
    lines = []
    for line in text.splitlines():
        if line.startswith("- Name:"):
            line = BLANK_SIGNATURE
        elif line.startswith("- Release gate run:"):
            line = (f"- Release gate run: `pipeline/25_release.py --stage {stage}` exit 0 on "
                    "______________")
        elif line.startswith("- [ ]"):
            line = "- [x]" + line[len("- [ ]"):]
        lines.append(line)
    out = "\n".join(lines) + "\n"
    for anchor, note in notes.items():
        start = out.index(anchor)
        ends = [out.find(sep, start) for sep in ("\n- [", "\n\n")]
        end = min(e for e in ends if e != -1)
        wrapped = textwrap.fill(note, 78, initial_indent="      ", subsequent_indent="      ",
                                break_on_hyphens=break_on_hyphens)
        out = out[:end] + "\n" + wrapped + out[end:]
    anchor = out.index("## Sign-off")
    return out[:anchor] + decisions + "\n\n" + prereq + out[anchor:]


def write_checklist(answers, mentions, segments, code_stats, log, tax_scan, val_scan,
                    file_hits) -> None:
    """Fill the house template once; never overwrite (the file in results/ is the signed record)."""
    path = RESULTS / "release-checklist.md"
    if checklist_kept(path):
        return
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
    item = check_item
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
    path.write_text(fill_template(notes, 1, decisions, prereq))
    print(f"checklist (unsigned): {path}")


def write_checklist_stage2(rel: SimpleNamespace, s1: SimpleNamespace, proof: dict,
                           val_scan: dict, file_hits: dict) -> None:
    """The Stage 2 update's checklist, from the house template; written once, never overwritten."""
    path = RESULTS / "release-checklist-stage2.md"
    if checklist_kept(path):
        return
    answers, mentions, segments = rel.answers, rel.mentions, rel.segments
    n1, n2 = len(s1.answers), len(answers)
    m1, m2 = len(s1.mentions), len(mentions)
    a2 = stage2_audit_figures()
    models = sorted({m for m in answers["model"] if m}, key=str.lower)
    new_models = sorted(set(models) - {m for m in s1.answers["model"] if m})
    first_seen = rel.first_seen
    fs_009 = [c for c in first_seen if int(c[1:]) < rel.code_stats["first_new"]]
    notes = {
        "Every column is a **derived feature": (
            f"(010 Stage 2: the same {len(ANSWER_COLUMNS)} answer, {len(MENTION_COLUMNS)} "
            f"mention and {len(SEGMENT_COLUMNS)} segment columns, names and order as the signed "
            "Stage 1 release, each allow-listed in `pipeline/25_release.py`. Only the "
            "descriptions of `run_id` and `wave` changed, to cover waves 8 to 11.)"),
        "No customer prompt text": (
            "(010 Stage 2: as at Stage 1, no answer text, question text, best-for phrases, "
            "judge evidence, caveat reason text, search queries or URLs. The segments file, "
            "the only model-written text, is unchanged.)"),
        "No customer, property": (
            "(010 Stage 2: no customer data was used. Brands ship as `bNNNN` codes from the "
            f"Stage 1 code table ({mentions['brand_code'].nunique()} distinct codes in the "
            f"mentions file, {s1.mentions['brand_code'].nunique()} at Stage 1). Answer ids: "
            f"Stage 1 rows keep r00001 to r{n1:05d}; the {n2 - n1} new answers are "
            f"r{n1 + 1:05d} to r{n2:05d}, sequential in the same sort (dataset, arm, study, "
            "item, wave), so they carry no information beyond those public columns.)"),
        "Free-text columns marked": (
            "(010 Stage 2: only `model` is marked public_fact. Its values, reviewed one by "
            f"one: {', '.join(models)}, or blank. New since Stage 1: "
            f"{', '.join(new_models) or 'none'} (one wave 8 Gemini answer). ChatGPT reports "
            "gpt-6 in waves 6 to 11, as Audit F found.)"),
        "The datasheet and every mention": (
            f"(010 Stage 2: {n2:,} answers evaluated in this study ({n1:,} at Stage 1, "
            f"{n2 - n1} added); the mentions file reports {m2:,} brand mentions in those "
            f"answers ({m2 - m1:,} added); the segments file {len(segments)} use-case segments, "
            "unchanged.)"),
        "Nothing in the dataset, datasheet": (
            "(010 Stage 2: as at Stage 1, the brand-code range reveals the size of the frozen "
            "lexicons, which are study instruments, not the Spyglasses database. The Audit G "
            "phrase count in the datasheets counts phrases in this study's answers.)"),
        "Could any set of rows": (
            "(010 Stage 2: no customer is involved. Waves 8 to 11 used Spyglasses' own "
            "DataForSEO and Anthropic accounts, as waves 1 to 7 did. Brand names are withheld "
            "per 009's 2026-10-02 release instruction.)"),
        "Third-party data terms": (
            "(010 Stage 2: DataForSEO and Anthropic outputs appear only as derived counts, "
            "labels and codes, not raw payloads.)"),
    }
    allowed = ", ".join(f"'{w}' ({(SCAN_ALLOW | GENERIC_WORDS)[w]})"
                        for w in sorted(set(val_scan["allowed"]) | set(file_hits["allowed"])))
    sha = ", ".join(f"`{s}.csv` {h[:12]}" for s, h in STAGE1_CSV_SHA256.items())
    d = wave_dates(range(1, 12))

    def item(body: str) -> str:  # keep file names and ids whole
        return check_item(body, break_on_hyphens=False)

    decisions = "\n\n".join([
        "## Decisions to confirm when signing (tick each)",
        item(
            "Scope: this is an update of the signed Stage 1 release (results/"
            "release-checklist.md, 2026-10-11), not a new dataset. Same three file names, same "
            "columns; the files in data/public/ are replaced. The Stage 1 version stays in git "
            "history (commit 4432548) and on the site until the datasets are synced, and each "
            "datasheet's Changelog says how to filter back to it. Alternative not taken: "
            "versioned file names (a separate `-stage1` set), which would leave two copies of "
            "the same rows on the site."),
        item(
            f"Stage 1 rows unchanged and first: the {n1:,} Stage 1 answers keep run_id r00001 "
            f"to r{n1:05d} and their position; the {n2 - n1} answers of waves 8 to 11 are "
            f"appended as r{n1 + 1:05d} to r{n2:05d}, in the same sort among themselves. So the "
            "answers file is not in one global dataset order (chatgpt_b2b rows of waves 8 to 11 "
            "come after the holdouts). Alternative not taken: re-sorting and renumbering, "
            "which would change most Stage 1 run_ids and break any join a reader built on the "
            "Stage 1 files."),
        item(
            "Proof that Stage 1 rows are unchanged, run by the gate itself: it rebuilds the "
            "Stage 1 release in-process from the Stage 1 frame and checks it against the "
            f"sha256 of the signed files ({sha}); each Stage 2 CSV must start with exactly "
            "those bytes (checked before writing and again on the written files); the rows "
            "after the prefix must be waves 8 to 11 only; the segments file must be identical. "
            f"Result: answers {proof['answers_prefix']:,} of {n2:,} rows are the Stage 1 bytes, "
            f"mentions {proof['mentions_prefix']:,} of {m2:,}, segments identical. Filtering the "
            "new files to wave 7 or less (mentions: by run_id) gives the signed files back "
            "byte for byte."),
        item(
            "Brand codes: the code table is unchanged (checked: identical to the Stage 1 "
            f"table, {rel.code_stats['reused_009']} codes from 009 and "
            f"{rel.code_stats['new']} seeded codes from {BRAND_PREFIX}"
            f"{rel.code_stats['first_new']:04d} on). No brand needed a new code: the Stage 1 "
            "table already covered every brand of the frozen lexicons, and firewall rule 4 "
            "keeps them frozen, so a brand that first appears in waves 8 to 11 outside the "
            "lexicons is counted only in `n_brands_all` (R1), never coded. The gate refuses to "
            "release if an observed brand has no code, rather than inventing one. "
            f"{len(first_seen)} codes appear for the first time in waves 8 to 11 "
            f"({len(fs_009)} of them 009 codes, {len(first_seen) - len(fs_009)} from the seeded "
            "range); the datasheet states the count, not the codes."),
        item(
            "Best-for segment ids: phrases classified at Stage 1 keep their Stage 1 "
            "classifications (deviation 10b; checked: no Stage 1 phrase changes segment in "
            f"the merged maps); the {a2['g_new']['phrases']:,} phrases first seen at Stage 2 "
            "were classified twice with the frozen taxonomies. Audit G over all "
            f"{a2['g']['phrases']:,} distinct phrases Stage 2 uses: "
            f"{pct(a2['g']['agreement'])} (pass). The datasheets give these two phrase counts; "
            "they count phrases in this study's answers, not anything in the Spyglasses "
            "database. Confirm, or drop the counts from the notes."),
        item(
            "Segments file unchanged, so the 25 segment rewrites and the definition decision "
            "signed at Stage 1 carry over as they are; nothing in REWRITES changed."),
        item(
            "Datasheets: titles now read 'Stages 1 and 2'; 'Released' is the Stage 2 date "
            f"({date.today().isoformat()}) and the Changelog keeps the Stage 1 date "
            f"({STAGE1_RELEASED}); the deviations pointer covers 1 to 10; a Stage 2 run "
            "notes item records deviation 9 (ChatGPT gpt-6 in waves 6 to 11, one Gemini "
            "answer reporting 3.6 Flash, wave 9's late start, the 7 Gemini tasks of wave 8 "
            "dated 2026-10-18); Audit E adds the Stage 2 sample "
            f"({pct(a2['e']['agreement'])}, kappa {a2['e']['kappa']:.2f}, "
            f"{a2['e']['answers']} answers). The gate's datasheet writer has no changelog "
            "field, so `25_release.py` appends the Changelog section after the gate writes "
            "each datasheet; the alias scan and an em dash check then run on the finished "
            "files. The model notes are checked against the data (the gate refuses if a "
            "wave's model differs from what the notes say)."),
        item(
            f"Wave dates: the datasheets give scheduled local dates (waves 8 to 11: "
            f"{', '.join(d[7:10])} and {d[10]}); run_date carries the true dates, through "
            f"{answers['run_date'].max()} for ChatGPT and Gemini (UTC). Late tasks keep their "
            "true dates, as at Stage 1."),
        item(
            f"Scans, all clean: the segment scan as at Stage 1 (unchanged file); every public "
            "value, column description, note and Changelog line, and the written CSV and "
            "datasheet files, against every alias of at least 4 characters, "
            f"case-insensitively; accepted: {allowed}. No other hit."),
        item(
            "Brand codes are pseudonyms, not anonymity, as signed at Stage 1. Four more runs "
            "per question add frequency information, so a reader who knows a market guesses "
            "the most frequent codes a little more easily; no name ships. Confirm this is "
            "still acceptable."),
        item(
            f"Answer-level flags: 0 refusals and 0 empty answers of {n2:,}; "
            f"`refusal_phrase` flags {int(answers['refusal_phrase'].sum())} answers "
            f"({int(s1.answers['refusal_phrase'].sum())} at Stage 1)."),
        item(
            "Not released, as at Stage 1: R1's names outside the lexicon (only the count "
            "`n_brands_all`), the Audit E second-pass labels (now including the Stage 2 "
            "sample of waves 8 to 11), and the per-answer judge metadata, which is constant "
            "and stated in the datasheets."),
        item(
            "Site: the Stage 2 figures were synced with `sync_site_assets.py --figures-only` "
            "for the article 2 draft; the datasets are not synced. After signing: commit "
            "data/public/ and this checklist, then run `uv run python scripts/"
            "sync_site_assets.py 010-shortlist-stability`."),
    ])
    prereq = "\n".join([
        "## Prerequisites",
        "",
        "- [x] Stage 1 release checklist signed by Jim Wrubel (`results/release-checklist.md`,",
        "      2026-10-11); its decisions carry over except where listed above.",
        "- [x] Audit D signed (precision 1.00, recall 1.00); Stage 2 audits pass",
        "      (`results/stage2_audits.md`): Audit A every wave 40 of 40, Audit E",
        f"      {pct(a2['e']['agreement'])} on the waves 8 to 11 sample, Audit G "
        f"{pct(a2['g']['agreement'])}.",
        "- [ ] STOP 4: Stage 2 results reviewed by Jim (`results/stage2_model.md`,",
        "      `results/stage2_robustness.md`).",
        "",
        "",
    ])
    path.write_text(fill_template(notes, 2, decisions, prereq, break_on_hyphens=False))
    print(f"checklist (unsigned): {path}")


# --------------------------------------------------------------------- main


def build_release(stage: int) -> SimpleNamespace:
    """Check the stage's inputs and build its three public frames (nothing written)."""
    tag = f"[stage {stage}]"
    rows, meta = check_inputs(stage)
    bf = stage_bestfor(stage)
    seg_map, segments, log = public_taxonomy()
    for cat, m in list(bf.seg_a.items()) + list(bf.seg_b.items()):
        bad = {g for g in m.values() if g not in NO_SEGMENT and (cat, g) not in seg_map}
        if bad:
            raise SystemExit(f"{cat}: classifier segments outside the taxonomy: {sorted(bad)}")
    tax_scan = taxonomy_scan(seg_map, segments)
    print(f"{tag} segment scan: {tax_scan['texts']} texts x {tax_scan['aliases']} aliases, "
          f"0 vendor names (generic words accepted: {tax_scan['generic_word_hits']})")

    codes, code_stats = brand_codes(rows)
    items = item_codes(rows)
    answers, mentions = build_frames(rows, codes, items, seg_map, bf)
    check_b2b_public(answers)
    n_join = check_codes_against_009(answers, mentions)
    print(f"{tag} brand codes: {code_stats}; claude_b2b rows matching 009's public codes: {n_join}")
    if len(answers) != N_ANSWERS[stage] or answers["refusal"].sum() or answers["empty"].sum():
        raise SystemExit("unexpected answer counts, refusals or empty answers")
    if stage == 2:
        check_stage2_models(answers)
    return SimpleNamespace(stage=stage, meta=meta, answers=answers, mentions=mentions,
                           segments=segments, log=log, tax_scan=tax_scan, codes=codes,
                           code_stats=code_stats, first_seen=[])


def stage1_bytes(s1: SimpleNamespace) -> dict[str, bytes]:
    """The in-process Stage 1 rebuild, which must be the signed files byte for byte."""
    out = {ANSWERS_SLUG: csv_bytes(s1.answers, answer_columns(1)),
           MENTIONS_SLUG: csv_bytes(s1.mentions, MENTION_COLUMNS),
           SEGMENTS_SLUG: csv_bytes(s1.segments, SEGMENT_COLUMNS)}
    for slug, b in out.items():
        if sha256_bytes(b) != STAGE1_CSV_SHA256[slug]:
            raise SystemExit(f"the Stage 1 rebuild of {slug}.csv is not the signed file "
                             "(STAGE1_CSV_SHA256); the Stage 1 inputs or code changed")
    return out


def check_stage1_prefix(rel: SimpleNamespace, s1: SimpleNamespace, s1b: dict[str, bytes]
                        ) -> dict:
    """Stage 2 = the signed Stage 1 bytes, then waves 8 to 11 only."""
    s2b = {ANSWERS_SLUG: csv_bytes(rel.answers, answer_columns(2)),
           MENTIONS_SLUG: csv_bytes(rel.mentions, MENTION_COLUMNS),
           SEGMENTS_SLUG: csv_bytes(rel.segments, SEGMENT_COLUMNS)}
    for slug in s2b:
        if not s2b[slug].startswith(s1b[slug]):
            raise SystemExit(f"{slug}.csv: the Stage 2 file does not start with the Stage 1 bytes")
    if s2b[SEGMENTS_SLUG] != s1b[SEGMENTS_SLUG]:
        raise SystemExit("the segments file changed at Stage 2")
    if rel.codes != s1.codes:
        raise SystemExit("the brand code table changed at Stage 2")
    n1, n2 = len(s1.answers), len(rel.answers)
    tail = rel.answers.iloc[n1:]
    if not (tail["dataset"].isin(NEW_DATASETS) & tail["wave"].isin(STAGE2_NEW_WAVES)).all():
        raise SystemExit("rows after the Stage 1 prefix are not all waves 8 to 11")
    if list(tail["run_id"]) != [f"r{i:05d}" for i in range(n1 + 1, n2 + 1)]:
        raise SystemExit("waves 8 to 11 run ids do not continue from the last Stage 1 id")
    head = rel.answers.iloc[:n1]
    if (head["dataset"].isin(NEW_DATASETS) & head["wave"].isin(STAGE2_NEW_WAVES)).any():
        raise SystemExit("a waves 8 to 11 answer sits inside the Stage 1 prefix")
    mtail = rel.mentions.iloc[len(s1.mentions):]
    if not mtail["run_id"].isin(set(tail["run_id"])).all():
        raise SystemExit("mention rows after the Stage 1 prefix belong to Stage 1 answers")
    rel.first_seen = sorted(set(rel.mentions["brand_code"]) - set(s1.mentions["brand_code"]))
    return {"answers_prefix": n1, "mentions_prefix": len(s1.mentions)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True)
    stage = ap.parse_args().stage
    if sha256_file(TAXONOMY_B2B) != TAXONOMY_B2B_SHA256:
        raise SystemExit("taxonomy changed")

    rel = build_release(stage)
    s1 = s1b = proof = None
    if stage == 2:
        s1 = build_release(1)
        s1b = stage1_bytes(s1)
        proof = check_stage1_prefix(rel, s1, s1b)
        print(f"Stage 1 prefix: answers {proof['answers_prefix']:,} of {len(rel.answers):,} rows "
              f"and mentions {proof['mentions_prefix']:,} of {len(rel.mentions):,} are the signed "
              f"Stage 1 bytes; segments identical; code table identical; "
              f"{len(rel.first_seen)} codes first seen in waves 8 to 11")
    answers, mentions, segments = rel.answers, rel.mentions, rel.segments

    columns = answer_columns(stage) + MENTION_COLUMNS + SEGMENT_COLUMNS
    texts = {"column descriptions": " ".join(c.description for c in columns),
             "notes": " ".join(common_notes(rel.meta, stage) + taxonomy_notes(stage))}
    if stage == 2:
        texts["changelog"] = changelog(rel, s1)
    val_scan = value_scan({"answers": answers, "mentions": mentions, "segments": segments}, texts)
    if val_scan["hits"]:
        raise SystemExit(f"brand alias in a public value: {val_scan['hits'][:20]}")
    print(f"value scan: 0 hits (accepted: {val_scan['allowed']})")

    outputs = [PUBLIC / f"{s}{ext}" for s in (ANSWERS_SLUG, MENTIONS_SLUG, SEGMENTS_SLUG)
               for ext in (".csv", ".datasheet.md")]
    try:
        paths = write_datasheets(rel, s1)
    except Exception:
        for p in outputs:  # never leave a partial release behind
            p.unlink(missing_ok=True)
        raise
    written = [p for d in paths.values() for p in d.values()]
    file_hits = file_scan(written)
    problems = [f"brand alias: {file_hits['hits'][:20]}"] if file_hits["hits"] else []
    problems += [f"{p.name}: em dash" for p in written if "—" in p.read_text()]
    if stage == 2:
        for slug, b in s1b.items():
            got = (PUBLIC / f"{slug}.csv").read_bytes()
            if not got.startswith(b) or (slug == SEGMENTS_SLUG and got != b):
                problems.append(f"{slug}.csv as written does not start with the Stage 1 bytes")
    if problems:
        for p in written:
            p.unlink()
        raise SystemExit(f"written files failed their checks, outputs deleted: {problems}")
    print(f"file scan: {len(written)} files, 0 hits (accepted: {file_hits['allowed']})")
    for p in written:
        print(f"released: {p}")
    print(f"rows: answers {len(answers):,}, mentions {len(mentions):,}, segments {len(segments)}")

    if stage == 1:
        write_checklist(answers, mentions, segments, rel.code_stats, rel.log, rel.tax_scan,
                        val_scan, file_hits)
    else:
        write_checklist_stage2(rel, s1, proof, val_scan, file_hits)
    print("Do not commit data/public/ or sync the datasets to the site until the release "
          f"checklist{' for the Stage 2 update' if stage == 2 else ''} is signed.")


if __name__ == "__main__":
    main()
