# Experiment 011: data-quality audits

Generated 2026-11-09 by `pipeline/02_audit.py` (600 answers). Aggregates only: no brand, domain, prompt, answer or query text.

## Audit A: degenerate responses

Ledgers, local and API arms (`attempts` = finished attempts including reruns; `failed_runs` = the run itself failed; `audit_failures` = the instrument check in `collect_cc.audit` failed; `not_counted` = answers whose last ledger record is not a success, dropped before the model):

| arm | wave | attempts | failed_runs | audit_failures | not_counted |
|---|---|---|---|---|---|
| cc_stock_full | 1 | 40 | 0 | 0 | 0 |
| cc_stock_full | 2 | 40 | 0 | 0 | 0 |
| cc_stock_full | 3 | 40 | 0 | 0 | 0 |
| cc_none_search | 1 | 40 | 0 | 0 | 0 |
| cc_none_search | 2 | 40 | 0 | 0 | 0 |
| cc_none_search | 3 | 40 | 0 | 0 | 0 |
| opus55_plain | 1 | 40 | 0 | 0 | 0 |
| opus55_plain | 2 | 40 | 0 | 0 | 0 |
| opus55_plain | 3 | 40 | 0 | 0 | 0 |

Counted answers per arm x wave: all complete.

Per arm x wave counts (`no_search` for `sched_kit` is the record's `searched` flag; `asks_back` = no brands and the reply ends on a question; `coding_flag` = offers or claims file or code work, to be read by a person; `clarifying` = claude.ai asked clarifying questions, first reply scored; `notes` = collector note, excluded in R6; `warned` = the parser or ingest recorded a warning):

| arm | wave | answers | empty | no_search | zero_links | zero_brands | asks_back | coding_flag | clarifying | notes | warned |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ui_default | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 |
| ui_default | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| ui_default | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| cc_stock_full | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| cc_stock_full | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| cc_stock_full | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sched_kit | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| sched_kit | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sched_kit | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| cc_none_search | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| cc_none_search | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| cc_none_search | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| opus55_plain | 1 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| opus55_plain | 2 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| opus55_plain | 3 | 40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

No-search rule, pooled over waves (more than 30% makes the arm's domain claims INCONCLUSIVE):

| arm | answers | no_search | no_search_rate | domain_claims |
|---|---|---|---|---|
| ui_default | 120 | 0 | 0.000 | eligible |
| cc_stock_full | 120 | 0 | 0.000 | eligible |
| sched_kit | 120 | 0 | 0.000 | eligible |
| cc_none_search | 120 | 0 | 0.000 | eligible |
| opus55_plain | 120 | 0 | 0.000 | eligible |

Empty-vs-empty pairs (Jaccard NaN, pair excluded), share of the condition's pairs. Evaluated URLs are not observed on `sched_kit`:

| condition | pairs | brands | cited | evaluated |
|---|---|---|---|---|
| cross:cc_none_search|ui_default | 120 | 0.000 | 0.000 | 0.000 |
| cross:cc_stock_full|sched_kit | 120 | 0.000 | 0.000 | n/a |
| cross:cc_stock_full|ui_default | 120 | 0.000 | 0.000 | 0.000 |
| cross:opus55_plain|ui_default | 120 | 0.000 | 0.000 | 0.000 |
| cross:sched_kit|ui_default | 120 | 0.000 | 0.000 | n/a |
| within:cc_stock_full | 120 | 0.000 | 0.000 | 0.000 |
| within:sched_kit | 120 | 0.000 | 0.000 | n/a |
| within:ui_default | 120 | 0.000 | 0.000 | 0.000 |

`sched_kit` per wave, from each transcript. `no_join` = a printed answer with no subagent result to join to, counted as not searched; `exact_instruction` = the subagent received the frozen instruction; `exact_copies` = the printed answer equals the subagent's report. The transcript records whether a subagent searched and its total tool count, not the number of searches, so search depth is reported as a tool count. The cloud's Claude Code version cannot be read:

| wave | answers | searched | no_join | fetched | exact_instruction | copies_checked | exact_copies | report_match_rate | resolved_model | tool_uses_per_answer |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 40 | 40 | 0 | 3 | 40 | 40 | 40 | 1.000 | claude-opus-5-5 | 6.975 |
| 2 | 40 | 40 | 0 | 4 | 40 | 40 | 40 | 1.000 | claude-opus-5-5 | 7.150 |
| 3 | 40 | 40 | 0 | 4 | 40 | 40 | 40 | 1.000 | claude-opus-5-5 | 7.025 |

Instruction mismatches or missing joins: 0. Copies that differ from the report: 0.

Model strings per arm: {'cc_none_search': ['claude-opus-5-5'], 'cc_stock_full': ['claude-opus-5-5'], 'opus55_plain': ['claude-opus-5-5'], 'sched_kit': ['nan'], 'ui_default': ['nan']}
Claude Code version per arm x wave: {'cc_none_search w1': ['2.1.316'], 'cc_none_search w2': ['2.1.316'], 'cc_none_search w3': ['2.1.316'], 'cc_stock_full w1': ['2.1.316'], 'cc_stock_full w2': ['2.1.316'], 'cc_stock_full w3': ['2.1.316']}
Run dates per wave x surface: {'w1 api': ['2026-11-03'], 'w1 claude.ai': ['2026-11-03'], 'w1 local': ['2026-11-03'], 'w1 scheduled': [], 'w2 api': ['2026-11-05'], 'w2 claude.ai': ['2026-11-05'], 'w2 local': ['2026-11-05'], 'w2 scheduled': [], 'w3 api': ['2026-11-09'], 'w3 claude.ai': ['2026-11-09'], 'w3 local': ['2026-11-09'], 'w3 scheduled': []}

## Audit B: what the labels mean (quoted from code)

- **brand named** = a keep-row alias of the frozen lexicon (sha256 `8e063e09873f8fb3d0d748c371c2c90904c6c039b80314d3debfacec6bd948ed`) matched in the answer text for the prompt's category, after labelled sources blocks, link targets, bare URLs and markup are stripped; longest alias first, word boundaries, matched spans consumed, first-mention order.

`experiments/011-claude-code-fidelity/pipeline/brands.py::strip_sources` (lines 69-82)

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

`experiments/011-claude-code-fidelity/pipeline/brands.py::lexicon_extract` (lines 85-96)

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

`experiments/011-claude-code-fidelity/pipeline/brands.py::load_lexicon` (lines 39-56)

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

- **link in answer** (Claude Code) = a URL in the answer text. Claude Code has no citation objects, so this differs from `citations[]` on claude.ai and the API, and domain results are descriptive. **evaluated** = a link in a `WebSearch` result, local arms; a subagent's searches are not in the pulled transcript, so `sched_kit` has none.

`src/aeo_research/claude_answers.py::_links_in_text` (lines 332-334)

```python
def _links_in_text(text: str) -> list[str]:
    """URLs in answer text, markdown links first-seen with bare URLs, unique."""
    return _unique(u.rstrip(".,;:") for u in _BARE_URL_RE.findall(text or ""))
```

`src/aeo_research/claude_answers.py::from_claude_code_stream` (lines 337-442)

```python
    - ``evaluated_urls``: the ``url`` of each link in a ``WebSearch`` tool
    - ``search_queries`` / ``n_searches``: ``WebSearch`` calls by the main model.
                if block.get("name") == "WebSearch":
                    queries.append(tool_input.get("query") or "")
                                evaluated.append(link.get("url"))
        "cited_urls": _links_in_text(answer_text),
        "n_searches": len(queries),
        "n_backend_searches": sum(
```

- **cited** (claude.ai, API) = citation objects in the answer's text blocks.

`src/aeo_research/claude_answers.py::_export_citation_url` (lines 194-205)

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

`src/aeo_research/claude_answers.py::from_api_message` (lines 81-172)

```python
            for citation in block.get("citations") or []:
                    cited.append(citation["url"])
```

`experiments/011-claude-code-fidelity/pipeline/common.py::normalize_url` (lines 170-174)

```python
def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    netloc = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), query, ""))
```

`experiments/011-claude-code-fidelity/pipeline/common.py::registered_domain` (lines 177-185)

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

`experiments/011-claude-code-fidelity/pipeline/common.py::ordered_domains` (lines 188-198)

```python
def ordered_domains(urls: list[str]) -> list[str]:
    """Registered domains in first-seen order."""
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

- Pair metrics (stage 03): Jaccard with empty-vs-empty = NaN (`aeo_research.overlap.jaccard`), truncated normalized RBO at p = 0.9 (`aeo_research.overlap.rbo`).

## Audit C: independence

40 prompts in 20 categories (prompts per category: [(2, 20)]); intents ['evaluate', 'shortlist']; waves [1, 2, 3]; 5 arms; 600 answers.

Same-prompt pair counts per condition (within = different waves, cross = same wave):

| condition | pairs | prompts |
|---|---|---|
| cross:cc_none_search|ui_default | 120 | 40 |
| cross:cc_stock_full|sched_kit | 120 | 40 |
| cross:cc_stock_full|ui_default | 120 | 40 |
| cross:opus55_plain|ui_default | 120 | 40 |
| cross:sched_kit|ui_default | 120 | 40 |
| within:cc_none_search | 120 | 40 |
| within:cc_stock_full | 120 | 40 |
| within:opus55_plain | 120 | 40 |
| within:sched_kit | 120 | 40 |
| within:ui_default | 120 | 40 |

Every answer joins several pairs, so pairs are not independent. All inference is a prompt-level cluster bootstrap (`aeo_research.overlap.cluster_boot` weights), with no pair-level standard errors. The two prompts of a category share vendors, so category is a coarser cluster: R5 resamples categories instead.

## Audit D: extraction validity

Arm-blind spot check, 30 answers stratified across the 5 arms, drawn with seed 20261103, shuffled into A01-A30. The reviewer edits `audit_d_sheet.csv` and reads `audit_d_answers.md`; neither names the arm, prompt or wave. `audit_d_key.csv` maps audit_id to arm, item and wave for the scorer. All three are gitignored. `missed_brands` = in-category brands the answer presents that extraction missed; `wrong_brands` = extracted brands that are not real in-category mentions in that answer (names separated by `; `).

Not scored yet. After review: `02_audit.py --score-audit-d --signed-by "<name>"`. 03_model refuses to run on real data until the score passes and is signed.

Haiku candidate cache coverage (R4 needs every answer; `harness/lexicon_candidates.py --wave N`):

| wave | answers | with_candidates | coverage |
|---|---|---|---|
| 1 | 200 | 200 | 1.000 |
| 2 | 200 | 200 | 1.000 |
| 3 | 200 | 200 | 1.000 |

Names the lexicon cannot place, per answer (R4 adds these to both sides):

| arm | answers | unplaced_per_answer |
|---|---|---|
| ui_default | 120 | 0.000 |
| cc_stock_full | 120 | 0.000 |
| sched_kit | 120 | 0.025 |
| cc_none_search | 120 | 0.017 |
| opus55_plain | 120 | 0.008 |
