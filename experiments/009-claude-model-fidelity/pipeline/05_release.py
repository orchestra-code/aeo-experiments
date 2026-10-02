"""Stage 05: gate-checked public datasets -> data/public/.

Two files, joined by ``item_id``:

- ``claude-api-vs-claude-ai-answers.csv``: one row per answer (prompt x arm x
  wave), derived features only.
- ``claude-api-vs-claude-ai-prompts.csv``: the 40 verbatim synthetic prompts,
  released under the data policy's "Synthetic study prompts" exemption
  (study-generated over software categories, no brand anchors at all; the
  harness rejected any draft naming a vendor, and this stage scans the text
  against every keep alias of the frozen lexicon again before release).

What ships and what does not (spec §3, docs/data-policy.md, and the release
instruction of 2026-10-02 that no brand name from the answers appears in any
public output):

- SHIPS: item, category, intent, arm, surface, wave, run date, model string,
  counts (brands, searches, cited and evaluated URLs and domains, answer
  length), protocol flags, the ORDERED brand list as per-release
  pseudonymous codes, and the cited / evaluated registered-domain lists with
  their source class. Every Jaccard and RBO statistic in the study can be
  recomputed from the codes, because a code stands for one brand everywhere
  in the file.
- PSEUDONYMIZED: brand names (spec §3 marks canonical vendor names
  publishable, but the release instruction is stricter, so they ship only as
  ``b0001`` style codes (short, so a 23-brand list stays under the
  gate's free-text limit) with no published mapping), and any domain
  whose source class is ``vendor`` or that the frozen domain map does not
  classify (a vendor's own site names the vendor). Those ship as
  ``site_0001`` codes, one code space shared by the cited and evaluated
  lists. Codes are assigned in a seeded random order, so a code says nothing
  about when or where the brand first appeared.
- NEVER SHIPS: answer text, its hash, search-query text and query tokens,
  full URLs, the leaked or production system prompts, collector notes and
  chat names (only 0/1 flags), per-answer usage and cost (spec §3: cost is
  published as per-arm aggregates, which go in the datasheet notes).

The technical gate (``aeo_research.release_dataset``) enforces the
allow-list, the forbidden-name patterns and the free-text scans; the human
checklist written next to the results enforces the judgment calls. Do not
commit data/public/ until that checklist is signed.

Usage: uv run python experiments/009-claude-model-fidelity/pipeline/05_release.py
"""

from __future__ import annotations

from pathlib import Path

import hashlib

import json

import csv
import re
import textwrap

import numpy as np
import pandas as pd
from common import (
    ALL_ARMS,
    DOMAIN_MAP,
    EXP,
    PROMPTS_CSV,
    RAW,
    RESULTS,
    SEED,
    load_features,
)

from aeo_research import ColumnSpec, Datasheet, release_dataset
from aeo_research.anonymize import CUID_PATTERN

SLUG = "claude-api-vs-claude-ai-answers"
PROMPTS_SLUG = "claude-api-vs-claude-ai-prompts"
STUDY = "009-claude-model-fidelity"
PUBLIC = EXP / "data" / "public"
LEXICON = RAW / "lexicon_v2_1.csv"
CHECKLIST_TEMPLATE = EXP.parents[1] / "templates" / "release-checklist.md"
LEAK_DIR = RAW / "system_prompts"
LEAK_TRIMMED = "claude-opus-5.5.trimmed.template.md"
LEAK_RELEASE = "claude-opus-5.5-trimmed-system-prompt.md"

#: Domains of these classes name a vendor, so they ship as codes.
PSEUDONYMIZED_CLASSES = {"vendor"}

ARM_DESCRIPTION = {
    "ui_default": "claude.ai, Opus 5.5, Medium reasoning (the default); the reference",
    "ui_think": "claude.ai, Opus 5.5, High reasoning",
    "opus55_plain": "API, Opus 5.5, effort medium, no system prompt",
    "opus55_leak": "API, Opus 5.5, effort medium, trimmed leaked claude.ai system prompt",
    "sonnet5_plain": "API, Sonnet 5, adaptive thinking, no system prompt",
    "sonnet5_leak_think": "API, Sonnet 5, adaptive thinking, trimmed leaked prompt",
    "sonnet5_leak_low": "API, Sonnet 5, adaptive thinking at effort low, trimmed leaked prompt",
    "sonnet5_prod": "API, Sonnet 5, Spyglasses' production request at the time of the study",
    "haiku45_leak": "API, Haiku 4.5, no thinking, trimmed leaked prompt",
}

COLUMNS = [
    ColumnSpec("item_id", "Study prompt id, b2b_01 to b2b_40; joins the prompts file"),
    ColumnSpec("category", "Software category the prompt is about (20 categories, 2 prompts each)"),
    ColumnSpec(
        "intent",
        "shortlist (a buyer with a concrete company profile asks for options) "
        "or evaluate (a buyer describes a use case and asks how the top "
        "options compare)",
    ),
    ColumnSpec(
        "arm",
        "Configuration that produced the answer; see the datasheet notes for "
        "the nine arms",
    ),
    ColumnSpec("surface", "claude.ai (collected by hand) or api (Anthropic Batches API)"),
    ColumnSpec("wave", "Collection day, 1 to 3 (2026-09-27, 2026-09-29, 2026-10-01)"),
    ColumnSpec("run_date", "Collection date of the wave"),
    ColumnSpec(
        "model_version",
        "Model string the API reported, or 'claude.ai' for the hand-collected arms",
        public_fact=True,
    ),
    ColumnSpec(
        "n_brands",
        "Count of distinct in-category brands the answer named (frozen lexicon v2.1)",
    ),
    ColumnSpec(
        "brand_codes",
        "Pipe-joined pseudonymous brand codes in first-mention order. One code "
        "is one brand everywhere in this file; the mapping to names is not "
        "published",
    ),
    ColumnSpec("n_searches", "Count of web searches the answer ran"),
    ColumnSpec("no_search", "1 if the answer ran no web search"),
    ColumnSpec("n_cited_urls", "Count of cited URLs (structured citations)"),
    ColumnSpec("n_cited_domains", "Count of distinct registered domains cited"),
    ColumnSpec(
        "cited_domains",
        "Pipe-joined registered domains cited, first-seen order. Publisher, "
        "review-marketplace, analyst and other sources appear as domains "
        "(public web facts); vendor sites appear as site_NNNN codes",
        public_fact=True,
    ),
    ColumnSpec(
        "cited_domain_classes",
        "Pipe-joined source class of each cited domain, aligned with "
        "cited_domains (frozen domain map v1)",
        public_fact=True,
    ),
    ColumnSpec("n_evaluated_urls", "Count of search-result URLs the answer's searches returned"),
    ColumnSpec("n_evaluated_domains", "Count of distinct registered domains in those search results"),
    ColumnSpec(
        "evaluated_domains",
        "Pipe-joined registered domains in the search results. Domains the "
        "frozen map classes as non-vendor appear as domains; vendor and "
        "unclassified domains appear as site_NNNN codes (same code space as "
        "cited_domains)",
        public_fact=True,
    ),
    ColumnSpec("chars", "Length of the scored answer text in characters"),
    ColumnSpec(
        "clarifying_questions",
        "1 if claude.ai asked clarifying questions first; only its first reply "
        "is scored (spec deviation 1)",
    ),
    ColumnSpec(
        "collector_note",
        "1 if the hand collector left a note on the chat (the R7 robustness "
        "check drops these); the note itself is not released",
    ),
    ColumnSpec("other_tools", "1 if the claude.ai chat used a tool other than web search"),
]

PROMPT_COLUMNS = [
    ColumnSpec("item_id", "Study prompt id; joins the answers file"),
    ColumnSpec("category", "Software category"),
    ColumnSpec("intent", "shortlist or evaluate"),
    ColumnSpec("n_words", "Word count of the prompt"),
    ColumnSpec(
        "prompt_text",
        "Verbatim study-generated synthetic prompt (data policy: Synthetic study prompts)",
        synthetic_study_text=True,
    ),
]


def code_map(values: set[str], prefix: str, rng: np.random.Generator) -> dict[str, str]:
    """Per-release codes in a seeded random order (no first-appearance signal)."""
    ordered = sorted(values)
    perm = rng.permutation(len(ordered))
    return {ordered[k]: f"{prefix}{i + 1:04d}" for i, k in enumerate(perm)}


def load_classes() -> dict[str, str]:
    out = {}
    with DOMAIN_MAP.open(newline="") as f:
        for r in csv.DictReader(f):
            cls = (r.get("reviewer_class") or "").strip() or (r.get("suggested_class") or "").strip()
            out[r["registered_domain"]] = cls or "other"
    return out


def leak_scan(prompts: pd.DataFrame) -> None:
    """Refuse to release a prompt that names any brand the lexicon keeps."""
    aliases = set()
    with LEXICON.open(newline="") as f:
        for r in csv.DictReader(f):
            if r["decision"] != "keep":
                continue
            for a in r["aliases"].split("|"):
                if a.strip():
                    aliases.add((a.strip(), r["match"] == "cs"))
    leaks = [
        (p.item_id, a)
        for p in prompts.itertuples()
        for a, cs in aliases
        if re.search(rf"(?<![\w&]){re.escape(a)}(?![\w&])", p.text, 0 if cs else re.I)
    ]
    if leaks:
        raise SystemExit(f"brand alias found in prompt text: {leaks}")
    print(f"prompt leak scan: {len(aliases)} keep aliases x {len(prompts)} prompts, 0 hits")


def write_checklist(n_answers: int, n_prompts: int, n_brand_codes: int, n_site_codes: int) -> None:
    """Write the house checklist next to the results, filled except the sign-off.

    Never overwrites: the file in results/ is the human's signed record. If it
    exists it is left alone, signed or not.
    """
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "release-checklist.md"
    if path.exists():
        signed = "Name: ______________  Date:" not in path.read_text()
        print(f"checklist kept ({'signed' if signed else 'unsigned'}): {path}")
        return
    text = CHECKLIST_TEMPLATE.read_text().replace("<experiment slug>", STUDY)
    text = text.replace(
        '"citations evaluated in this study"', '"answers evaluated in this study"')
    notes = {
        "Every column is a **derived feature": (
            f"(009: {len(COLUMNS)} answer columns and {len(PROMPT_COLUMNS)} prompt "
            "columns, each allow-listed with a description in `pipeline/05_release.py`.)"),
        "No customer prompt text": (
            "(009: no answer text, answer hash, search-query text or tokens, full "
            "URLs, system prompt text, collector notes or chat names. Prompt text "
            "is the study's own synthetic panel, see the exemption item below.)"),
        "No customer, property": (
            "(009: no customer data was used. Brands ship as "
            f"{n_brand_codes} `bNNNN` codes and vendor or unclassified "
            f"domains as {n_site_codes} `site_NNNN` codes, assigned in a seeded "
            "random order; no mapping is published.)"),
        "Free-text columns marked": (
            "(009: `model_version` holds four model strings; `cited_domains`, "
            "`evaluated_domains` and `cited_domain_classes` hold only "
            "registered domains, `site_NNNN` codes and the six source-class "
            "labels. They are marked public_fact because the pipe-joined lists "
            "exceed the gate's 200-character free-text limit.)"),
        "The datasheet and every mention": (
            f"(009: {n_answers:,} answers and {n_prompts} prompts evaluated in "
            "this study.)"),
        "Could any set of rows": (
            "(009: no customer is involved; the account is a fresh claude.ai Pro "
            "account owned by Spyglasses. Brand names are withheld per the "
            "2026-10-02 release instruction.)"),
    }
    lines = []
    for line in text.splitlines():
        if line.startswith("- Name:"):
            line = "- Name: ______________  Date: ______________"
        elif line.startswith("- Release gate run:"):
            line = "- Release gate run: `pipeline/05_release.py` exit 0 on ______________"
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
    exemption = (
        "\n- [ ] Synthetic prompt text ships only under the data policy's "
        "\"Synthetic study\n      prompts\" exemption, all three conditions: "
        "(1) study-generated by\n      `harness/make_prompts.py` over 20 software "
        "categories, no brand anchors,\n      never seeded from customer prompts "
        f"(leak scan: 0 hits over {n_prompts} prompts);\n      (3) column flagged "
        "`synthetic_study_text=True`. Condition (2), that the\n      generation "
        "styles (shortlist and evaluate buyer prompts) are publicly\n      "
        "reproducible with the free spyglasses.io prompt generator, needs "
        "Jim's\n      confirmation; tick this box only then.\n"
    )
    anchor = out.index("## Phrasing")
    out = out[:anchor].rstrip("\n") + "\n" + exemption + "\n" + out[anchor:]
    prereq = (
        "## Prerequisite\n\n- [x] Audit D spot check signed (`results/audit_d_score.json`, "
        "Jim Wrubel,\n      2026-10-02: precision 1.00, recall 0.99 against gates "
        "0.95 / 0.90).\n\n"
    )
    anchor = out.index("## Sign-off")
    out = out[:anchor] + prereq + out[anchor:]
    path.write_text(out)
    print(f"checklist (unsigned): {path}")


def release_trimmed_prompt() -> Path:
    """Copy the trimmed leaked prompt (as sent, with its slots) under a source header.

    Released by Jim's decision of 2026-10-02 (spec deviation 11). The file is
    verified against the manifest written when the leak was fetched, so the
    released text is byte for byte the template the API arms used.
    """
    manifest = json.loads((LEAK_DIR / "manifest.json").read_text())
    src = LEAK_DIR / LEAK_TRIMMED
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    if digest != manifest["files"][LEAK_TRIMMED]["sha256"]:
        raise SystemExit(f"{LEAK_TRIMMED} does not match its manifest sha256")
    removed = "\n".join(f"- `{r['section']}`" for r in manifest["removed"])
    header = (
        "<!--\n"
        "Trimmed claude.ai system prompt used by the leaked-prompt arms of\n"
        "Spyglasses Research experiment 009 (Claude API vs claude.ai).\n\n"
        f"Source: https://github.com/{manifest['repo']} (open source), file\n"
        f"{manifest['path']} at commit {manifest['sha']}, fetched\n"
        f"{manifest['fetched_at'][:10]}. Neither Spyglasses nor the source repository\n"
        "can verify that this is claude.ai's actual or current system prompt.\n"
        "The text is Anthropic's, as circulated by that repository; Spyglasses\n"
        "claims no rights in it and adds only the trimming. For the full,\n"
        "untrimmed version, see the source repository at that commit.\n\n"
        "Trimming rules: experiments/009-claude-model-fidelity/harness/leak_trim_rules.md.\n"
        f"Template sha256 (this text, without this header): {digest}\n\n"
        "Slots filled per call: {{RUN_DATE}} = the collection date (YYYY-MM-DD),\n"
        "{{RUN_DATE_LONG}} = the same date written out, {{USER_LOCATION}} =\n"
        "Pittsburgh, Pennsylvania, US.\n\n"
        "Sections removed by the trimming:\n"
        f"{removed}\n"
        "-->\n\n"
    )
    out = PUBLIC / LEAK_RELEASE
    out.write_text(header + src.read_text())
    return out


def main() -> None:
    df = load_features()
    if int(df["synthetic"].max()) == 1:
        raise SystemExit("refusing to release a SYNTHETIC frame")
    if set(df["arm"]) != set(ALL_ARMS):
        raise SystemExit(f"unexpected arms: {sorted(set(df['arm']))}")

    rng = np.random.default_rng(SEED)
    brand_codes = code_map({b for bs in df["brands"] for b in bs}, "b", rng)

    classes = load_classes()
    all_domains = {d for col in ("cited_domains", "evaluated_domains") for ds in df[col] for d in ds}
    # A domain whose label looks like a Prisma cuid (one 25-character label
    # starting with "c") trips the gate's identifier scan; it ships as a code
    # too rather than weakening the gate.
    hidden = {d for d in all_domains if classes.get(d, "unclassified") in PSEUDONYMIZED_CLASSES
              or d not in classes or CUID_PATTERN.search(d)}
    site_codes = code_map(hidden, "site_", rng)

    def show(domains: list[str]) -> str:
        return "|".join(site_codes.get(d, d) for d in domains)

    out = pd.DataFrame(
        {
            "item_id": df["item_id"],
            "category": df["category"],
            "intent": df["intent"],
            "arm": df["arm"],
            "surface": df["surface"].map({"ui": "claude.ai", "api": "api"}),
            "wave": df["wave"],
            "run_date": df["run_date"],
            "model_version": df["model"],
            "n_brands": df["n_brands"],
            "brand_codes": df["brands"].map(lambda bs: "|".join(brand_codes[b] for b in bs)),
            "n_searches": df["n_searches"],
            "no_search": (df["n_searches"] == 0).astype(int),
            "n_cited_urls": df["n_cited"],
            "n_cited_domains": df["n_cited_domains"],
            "cited_domains": df["cited_domains"].map(show),
            "cited_domain_classes": df["cited_domains"].map(
                lambda ds: "|".join(classes.get(d, "other") for d in ds)),
            "n_evaluated_urls": df["n_evaluated"],
            "n_evaluated_domains": df["evaluated_domains"].map(len),
            "evaluated_domains": df["evaluated_domains"].map(show),
            "chars": df["chars"],
            "clarifying_questions": df["clarifying_questions"].astype(int),
            "collector_note": df["collector_notes"].astype(int),
            "other_tools": df["other_tools"].astype(int),
        }
    )
    if out["surface"].isna().any():
        raise SystemExit("unknown surface value")
    # Belt and braces: no pseudonymized value may appear in the clear.
    for col, withheld in (("brand_codes", set(brand_codes)),
                          ("cited_domains", hidden | set(brand_codes)),
                          ("evaluated_domains", hidden | set(brand_codes))):
        tokens = {t for v in out[col] for t in v.split("|") if t}
        if tokens & withheld:
            raise SystemExit(f"{col}: a withheld name appears in the clear")

    cost = (df[df["surface"] == "api"].groupby("arm")["cost_usd"].mean().round(3))
    arm_notes = [f"`{a}`: {ARM_DESCRIPTION[a]}" for a in ALL_ARMS]
    paths = release_dataset(
        out,
        COLUMNS,
        PUBLIC,
        Datasheet(
            title="Claude API vs claude.ai: brands named and domains cited, "
                  "40 B2B software prompts, 9 configurations, 3 days",
            dataset_slug=SLUG,
            study=STUDY,
            unit="answers",
            notes=[
                "One row per answer evaluated in this study: 40 synthetic B2B "
                "software prompts x 9 configurations (arms) x 3 waves. The "
                "prompt text is in claude-api-vs-claude-ai-prompts.csv; "
                "item_id joins the two files.",
                "The arms are: " + "; ".join(arm_notes) + ".",
                "The claude.ai arms come from one fresh Pro account with "
                "memory, chat search, preferences, styles, projects and "
                "connectors off, signed in from Pittsburgh, Pennsylvania. API "
                "arms used the web_search tool with the same city as "
                "user_location (except sonnet5_prod, which reproduces the "
                "production request: no location, at most 5 searches).",
                "The leaked system prompt is a publicly circulated copy of "
                "claude.ai's system prompt from the open-source repository "
                "asgeirtj/system_prompts_leaks, whose provenance and accuracy "
                "cannot be verified, trimmed by the rules in "
                "harness/leak_trim_rules.md. The trimmed version used in the "
                f"study is released as {LEAK_RELEASE} (spec deviation 11). The "
                "production prompt's text is not released.",
                "Brands are the in-category brands an answer names, matched "
                "with the frozen lexicon v2.1 (Audit D: precision 1.00, "
                "recall 0.99 on 30 answers). They ship as bNNNN codes. "
                "Vendor sites and domains the frozen source-class map does "
                "not cover ship as site_NNNN codes. Codes are per release and "
                "no mapping is published.",
                "For the 9 claude.ai chats that asked clarifying questions, "
                "only the first reply is scored (spec deviation 1).",
                "Mean measured cost per API call, batch pricing, 1-hour cache "
                "writes included (USD): "
                + ", ".join(f"{a} {cost[a]:.3f}" for a in cost.index)
                + ". claude.ai reports subscription usage only as a share of "
                "plan limits, so there is no per-chat cost for its arms.",
                "Answer text, search-query text, full URLs, collector notes "
                "and per-answer cost are not released.",
            ],
        ),
    )
    print(f"released: {paths['csv']}\n          {paths['datasheet']}")

    prompts = pd.read_csv(PROMPTS_CSV)
    leak_scan(prompts)
    pout = pd.DataFrame(
        {
            "item_id": prompts["item_id"],
            "category": prompts["category"],
            "intent": prompts["intent"],
            "n_words": prompts["text"].str.split().map(len),
            "prompt_text": prompts["text"],
        }
    )
    ppaths = release_dataset(
        pout,
        PROMPT_COLUMNS,
        PUBLIC,
        Datasheet(
            title="Claude API vs claude.ai: the 40 synthetic B2B software prompts",
            dataset_slug=PROMPTS_SLUG,
            study=STUDY,
            unit="prompts",
            notes=[
                "Rows are the synthetic prompts evaluated in this study; each "
                "ran in all 9 arms on 3 days (see the answers file; item_id "
                "joins the two).",
                "Generated once by claude-haiku-4-5 (harness/make_prompts.py): "
                "20 software categories x 2 intents, first-person buyer "
                "phrasing, 15 to 45 words, no vendor or product names, no "
                "location, no year; checked by rule, regenerated on failure, "
                "reviewed by a person and frozen with the spec.",
                "Released under the research data policy's 'Synthetic study "
                "prompts' exemption: study-generated, no brand anchors, never "
                "seeded from customer prompts.",
                "Text is verbatim as generated.",
            ],
        ),
    )
    print(f"released: {ppaths['csv']}\n          {ppaths['datasheet']}")

    print(f"released: {release_trimmed_prompt()}")

    write_checklist(len(out), len(pout), len(brand_codes), len(site_codes))
    print("Do not commit data/public/ until the release checklist is signed.")


if __name__ == "__main__":
    main()
