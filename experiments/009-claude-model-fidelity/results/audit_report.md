# Experiment 009: data-quality audits

Generated 2026-10-01 by `pipeline/02_audit.py` from `data/interim/features.jsonl` (1080 answers). Aggregates only: no brand, domain, prompt, answer or query text.

## Audit A: degenerate responses

Batch ledger, last status per task (API arms):

| arm | wave | collected |
|---|---|---|
| opus55_plain | 1 | 40 |
| opus55_plain | 2 | 40 |
| opus55_plain | 3 | 40 |
| opus55_leak | 1 | 40 |
| opus55_leak | 2 | 40 |
| opus55_leak | 3 | 40 |
| sonnet5_plain | 1 | 40 |
| sonnet5_plain | 2 | 40 |
| sonnet5_plain | 3 | 40 |
| sonnet5_leak_think | 1 | 40 |
| sonnet5_leak_think | 2 | 40 |
| sonnet5_leak_think | 3 | 40 |
| sonnet5_leak_low | 1 | 40 |
| sonnet5_leak_low | 2 | 40 |
| sonnet5_leak_low | 3 | 40 |
| sonnet5_prod | 1 | 40 |
| sonnet5_prod | 2 | 40 |
| sonnet5_prod | 3 | 40 |
| haiku45_leak | 1 | 40 |
| haiku45_leak | 2 | 40 |
| haiku45_leak | 3 | 40 |

Failed, errored or expired batch requests: 0.
Answers present per arm x wave: all complete.

Per arm x wave counts (answers; `paused` = a `pause_turn` continuation in the ledger; `refusal` = heuristic pattern near the start of the answer or a `refusal` stop reason; `clarifying` = claude.ai asked clarifying questions, first reply scored (deviation 1); `notes` = collector note on the sheet row (R7); `other_tools` = the chat used a claude.ai tool other than search):

| arm | wave | answers | empty | paused | zero_search | zero_cited | zero_brands | refusal | clarifying | notes | other_tools |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ui_default | 1 | 40 | 0 | 0 | 6 | 8 | 0 | 0 | 1 | 1 | 2 |
| ui_default | 2 | 40 | 0 | 0 | 8 | 9 | 0 | 0 | 2 | 2 | 3 |
| ui_default | 3 | 40 | 0 | 0 | 7 | 7 | 0 | 0 | 1 | 1 | 2 |
| ui_think | 1 | 40 | 0 | 0 | 1 | 1 | 0 | 0 | 2 | 2 | 2 |
| ui_think | 2 | 40 | 0 | 0 | 1 | 2 | 0 | 0 | 2 | 2 | 3 |
| ui_think | 3 | 40 | 0 | 0 | 1 | 2 | 0 | 0 | 1 | 2 | 5 |
| opus55_plain | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| opus55_plain | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| opus55_plain | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| opus55_leak | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| opus55_leak | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| opus55_leak | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_plain | 1 | 40 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_plain | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_plain | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_leak_think | 1 | 40 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_leak_think | 2 | 40 | 0 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_leak_think | 3 | 40 | 0 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_leak_low | 1 | 40 | 0 | 0 | 6 | 9 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_leak_low | 2 | 40 | 0 | 0 | 10 | 11 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_leak_low | 3 | 40 | 0 | 0 | 5 | 12 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_prod | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_prod | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sonnet5_prod | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| haiku45_leak | 1 | 40 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| haiku45_leak | 2 | 40 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| haiku45_leak | 3 | 40 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |

No-search rule (pooled over waves; more than 30% no-search answers makes the arm's domain claims INCONCLUSIVE whatever the CI):

| arm | answers | no_search | no_search_rate | domain_claims |
|---|---|---|---|---|
| ui_default | 120 | 21 | 0.175 | eligible |
| ui_think | 120 | 3 | 0.025 | eligible |
| opus55_plain | 120 | 0 | 0.000 | eligible |
| opus55_leak | 120 | 0 | 0.000 | eligible |
| sonnet5_plain | 120 | 1 | 0.008 | eligible |
| sonnet5_leak_think | 120 | 1 | 0.008 | eligible |
| sonnet5_leak_low | 120 | 21 | 0.175 | eligible |
| sonnet5_prod | 120 | 0 | 0.000 | eligible |
| haiku45_leak | 120 | 5 | 0.042 | eligible |

Empty-vs-empty pairs (both sets empty, so Jaccard is NaN and the pair is excluded), as a share of the condition's pairs:

| condition | pairs | brands | cited | evaluated |
|---|---|---|---|---|
| cross:haiku45_leak|ui_default | 120 | 0.000 | 0.017 | 0.017 |
| cross:opus55_leak|ui_default | 120 | 0.000 | 0.000 | 0.000 |
| cross:opus55_plain|ui_default | 120 | 0.000 | 0.000 | 0.000 |
| cross:sonnet5_leak_low|sonnet5_leak_think | 120 | 0.000 | 0.033 | 0.008 |
| cross:sonnet5_leak_low|ui_default | 120 | 0.000 | 0.067 | 0.067 |
| cross:sonnet5_leak_think|ui_default | 120 | 0.000 | 0.008 | 0.000 |
| cross:sonnet5_plain|ui_default | 120 | 0.000 | 0.008 | 0.008 |
| cross:sonnet5_prod|ui_default | 120 | 0.000 | 0.000 | 0.000 |
| cross:ui_default|ui_think | 120 | 0.000 | 0.033 | 0.025 |
| within:sonnet5_leak_low | 120 | 0.000 | 0.108 | 0.083 |
| within:sonnet5_leak_think | 120 | 0.000 | 0.008 | 0.000 |
| within:ui_default | 120 | 0.000 | 0.108 | 0.108 |
| within:ui_think | 120 | 0.000 | 0.008 | 0.008 |

claude.ai ingest, re-derived read-only from each wave's export (`other_ignored` = chats outside the protocol names, including voided chats):

| wave | conversations_in_export | expected | matched | matched_by_prompt_text | duplicated | ambiguous | other_ignored |
|---|---|---|---|---|---|---|---|
| 1 | 81 | 80 | 80 | 0 | 0 | 0 | 1 |
| 2 | 80 | 80 | 80 | 0 | 0 | 0 | 0 |
| 3 | 80 | 80 | 80 | 0 | 0 | 0 | 0 |

UI chats run with the wrong model or reasoning setting (collector notes): none. Every wave's notes record Opus 5.5 with Medium reasoning (default) and no wrong-setting chat (common.UI_WRONG_SETTING).
UI chats with a collector note (excluded in R7): 10 ({'ui_default': 4, 'ui_think': 6}). Chats where claude.ai asked clarifying questions: 9.

Model strings per arm: {'haiku45_leak': ['claude-haiku-4-5-20251001'], 'opus55_leak': ['claude-opus-5-5'], 'opus55_plain': ['claude-opus-5-5'], 'sonnet5_leak_low': ['claude-sonnet-5'], 'sonnet5_leak_think': ['claude-sonnet-5'], 'sonnet5_plain': ['claude-sonnet-5'], 'sonnet5_prod': ['claude-sonnet-5'], 'ui_default': ['claude.ai'], 'ui_think': ['claude.ai']}
Run dates per wave x surface: {(1, 'api'): ['2026-09-27'], (1, 'ui'): ['2026-09-27'], (2, 'api'): ['2026-09-29'], (2, 'ui'): ['2026-09-29'], (3, 'api'): ['2026-10-01'], (3, 'ui'): ['2026-10-01']}

## Audit B: what the labels mean (quoted from code)

- **brand named** = a keep-row alias of the frozen lexicon v2 (sha256 `a2745081980cb819b7de7e0dc698d0fecb001fc7a677259e68d57bf5c744e1eb`) matched in the answer text for the prompt's category, after the sources block, link targets, bare URLs and markup are stripped; longest alias first, word boundaries, matched spans consumed, first-mention order. For a claude.ai chat that asked clarifying questions the answer text is the first reply only (deviation 1).

`experiments/009-claude-model-fidelity/pipeline/brands.py::strip_sources` (lines 94-107)

```python
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
```

`experiments/009-claude-model-fidelity/pipeline/brands.py::lexicon_extract` (lines 110-121)

```python
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
```

`experiments/009-claude-model-fidelity/pipeline/brands.py::load_lexicon` (lines 63-80)

```python
def load_lexicon(path: Path) -> dict[str, list[tuple[re.Pattern, str, bool]]]:
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
```

- **domain cited** = registered domain of a normalized URL in a text block's `citations[]` (API) or `citations[].details.url` (claude.ai export); **domain evaluated** = registered domain of a `web_search_tool_result` item (API) or a search `tool_result` item (export).

`src/aeo_research/claude_answers.py::from_api_message` (lines 81-172)

```python
            for citation in block.get("citations") or []:
                    cited.append(citation["url"])
                    queries.append(query)
        elif kind == "web_search_tool_result":
                # web_search_tool_result_error (max_uses_exceeded, too_many_requests, ...)
                    and item.get("type") == "web_search_result"
                    evaluated.append(item["url"])
```

`src/aeo_research/claude_answers.py::_export_citation_url` (lines 192-203)

```python
def _export_citation_url(citation) -> str | None:
    if not isinstance(citation, Mapping):
        return None
    for holder in (citation, citation.get("details") or {}, citation.get("source") or {}):
        if isinstance(holder, Mapping) and isinstance(holder.get("url"), str):
            return holder["url"]
    sources = citation.get("sources")
    if isinstance(sources, list):
        for src in sources:
            if isinstance(src, Mapping) and isinstance(src.get("url"), str):
                return src["url"]
    return None
```

`src/aeo_research/claude_answers.py::_export_result_urls` (lines 206-216)

```python
def _export_result_urls(content) -> list[str]:
    urls: list[str] = []
    if not isinstance(content, list):
        return urls
    for item in content:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url") or (item.get("metadata") or {}).get("url")
        if isinstance(url, str) and url.startswith("http"):
            urls.append(url)
    return urls
```

`src/aeo_research/claude_answers.py::from_claude_export` (lines 237-322)

```python
                if "citations" in block:
                for citation in block.get("citations") or []:
                    url = _export_citation_url(citation)
                if name in EXPORT_SEARCH_TOOLS:
                        queries.append(query)
                if block.get("name") in EXPORT_SEARCH_TOOLS:
                    evaluated.extend(_export_result_urls(block.get("content")))
    cited_source = "citations"
        md_links = _MD_LINK_RE.findall(answer_text)
        if md_links:
            cited = md_links
            cited_source = "markdown_links"
            warnings.append("no structured citations; cited_urls taken from markdown links")
            warnings.append("no citations field on any text block")
        "cited_urls_source": cited_source,
```

`experiments/009-claude-model-fidelity/pipeline/common.py::normalize_url` (lines 156-160)

```python
def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    netloc = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), query, ""))
```

`experiments/009-claude-model-fidelity/pipeline/common.py::registered_domain` (lines 163-171)

```python
def registered_domain(url_or_host: str) -> str:
    host = url_or_host
    if "//" in host:
        host = urlsplit(host).netloc
    host = host.lower().removeprefix("www.").split(":")[0]
    labels = [p for p in host.split(".") if p]
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host
```

`experiments/009-claude-model-fidelity/pipeline/common.py::ordered_domains` (lines 178-188)

```python
def ordered_domains(urls: list[str]) -> list[str]:
    """Registered domains in first-seen order (the set is ``domains``)."""
    seen, out = set(), []
    for u in urls:
        if not u:
            continue
        d = registered_domain(normalize_url(u))
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out
```

- **grounding tokens** = stopword-filtered tokens of the search queries.

`src/aeo_research/overlap.py::token_set` (lines 81-86)

```python
def token_set(queries: Iterable[str], stopwords: frozenset[str] = QUERY_STOPWORDS) -> set[str]:
    """Union of normalized tokens across a response's queries."""
    out: set[str] = set()
    for q in queries:
        out.update(t for t in _TOKEN_RE.findall(q.lower()) if t not in stopwords)
    return out
```

- Pair metrics (stage 03): Jaccard with empty-vs-empty = NaN (`aeo_research.overlap.jaccard`), truncated normalized RBO at p = 0.9 (`aeo_research.overlap.rbo`).

## Audit C: independence

40 prompts in 20 categories (prompts per category: [(2, 20)]); intents ['evaluate', 'shortlist']; waves [1, 2, 3]; 9 arms; 1080 answers.

Same-prompt pair counts per condition (within = different waves, cross = same wave):

| condition | pairs | prompts |
|---|---|---|
| cross:haiku45_leak|ui_default | 120 | 40 |
| cross:opus55_leak|ui_default | 120 | 40 |
| cross:opus55_plain|ui_default | 120 | 40 |
| cross:sonnet5_leak_low|sonnet5_leak_think | 120 | 40 |
| cross:sonnet5_leak_low|ui_default | 120 | 40 |
| cross:sonnet5_leak_think|ui_default | 120 | 40 |
| cross:sonnet5_plain|ui_default | 120 | 40 |
| cross:sonnet5_prod|ui_default | 120 | 40 |
| cross:ui_default|ui_think | 120 | 40 |
| within:haiku45_leak | 120 | 40 |
| within:opus55_leak | 120 | 40 |
| within:opus55_plain | 120 | 40 |
| within:sonnet5_leak_low | 120 | 40 |
| within:sonnet5_leak_think | 120 | 40 |
| within:sonnet5_plain | 120 | 40 |
| within:sonnet5_prod | 120 | 40 |
| within:ui_default | 120 | 40 |
| within:ui_think | 120 | 40 |

Every answer joins several pairs, so pairs are not independent. All inference is a prompt-level cluster bootstrap (`aeo_research.overlap.cluster_boot` weights, resampling the 40 prompts); no pair-level standard errors. The two prompts of a category share vendors, so category is a coarser cluster: R6 resamples the 20 categories instead. Panel shares (`pipeline/shares.py`) resample categories, then prompts within each drawn category.

## Audit D: extraction validity

Arm-blind spot check, 30 answers stratified across the 9 arms, drawn with seed 20260926, shuffled into A01-A30. The reviewer edits `data/raw/audit_d_sheet.csv` (audit_id, category, extracted brands, reviewer columns) and reads `data/raw/audit_d_answers.md` (each answer as extraction reads it, sources block stripped); neither names the arm, prompt or wave. `data/raw/audit_d_key.csv` maps audit_id to arm, item and wave for the scorer. All three are gitignored. `missed_brands` = in-category brands the answer presents that extraction missed; `wrong_brands` = extracted brands that are not real in-category mentions in that answer (names separated by `; `).

Not scored yet. After review: `02_audit.py --score-audit-d --signed-by "<name>"`. 03_model refuses to run on real data until the score passes and is signed.

Haiku candidate cache coverage (R4 needs every wave; the extraction for waves 2 and 3 is `harness/lexicon_candidates.py --wave N`):

| wave | answers | with_candidates | coverage |
|---|---|---|---|
| 1 | 360 | 360 | 1.000 |
| 2 | 360 | 360 | 1.000 |
| 3 | 360 | 360 | 1.000 |

Agreement, lexicon extraction vs Haiku candidates mapped through the frozen lexicon (same answer; per-answer Jaccard, NaN when both are empty). The lexicon was curated from the wave 1 candidates, so wave 1 agreement is in-sample:

| arm | answers | mean_jaccard | identical | lexicon_brands | haiku_brands | both_empty |
|---|---|---|---|---|---|---|
| ui_default | 120 | 0.964 | 0.775 | 8.425 | 8.083 | 0 |
| ui_think | 120 | 0.965 | 0.758 | 8.225 | 7.933 | 0 |
| opus55_plain | 120 | 0.947 | 0.650 | 9.617 | 9.092 | 0 |
| opus55_leak | 120 | 0.953 | 0.692 | 8.692 | 8.300 | 0 |
| sonnet5_plain | 120 | 0.947 | 0.708 | 8.000 | 7.508 | 0 |
| sonnet5_leak_think | 120 | 0.953 | 0.725 | 7.633 | 7.225 | 0 |
| sonnet5_leak_low | 120 | 0.960 | 0.792 | 6.933 | 6.617 | 0 |
| sonnet5_prod | 120 | 0.910 | 0.525 | 9.475 | 8.550 | 0 |
| haiku45_leak | 120 | 0.941 | 0.725 | 5.625 | 5.275 | 0 |
| all | 1080 | 0.949 | 0.706 | 8.069 | 7.620 | 0 |
