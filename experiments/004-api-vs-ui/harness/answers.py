"""Normalize the four 004 instruments' raw JSON into one answer shape (sketch, Measures).

Every arm comes out as the same dict, so UI and API answers are treated alike:

- ``answer_text``: the answer as the user would read it (markdown).
- ``model``: the model the instrument reports for this answer.
- ``cited_urls``: URLs the answer cites (DataForSEO ``sources`` / inline links;
  OpenAI ``url_citation`` annotations; Gemini chunks referenced by
  ``groundingSupports``).
- ``evaluated_urls``: URLs the instrument reports as consulted (OpenAI
  ``web_search_call`` ``action.sources``; Gemini every ``groundingChunks`` entry;
  DataForSEO ``search_results`` when present, else ``sources``).
- ``cited_domains`` / ``evaluated_domains``: registered domains. Gemini API chunk
  URIs are redirect links, so its domains come from the chunk's ``web.domain`` when
  present, else its ``web.title`` when that is a hostname (``domain_source`` says
  which); a chunk with neither has no domain here.
- ``search_queries``: the queries the instrument reports (DataForSEO
  ``fan_out_queries``; OpenAI search actions; Gemini ``webSearchQueries``).
- ``n_searches``: searches per answer, the same count as ``search_queries`` where
  the instrument reports queries (OpenAI: search actions, so a search action
  without a query still counts).

Brand extraction is not here: ``pipeline/pilot_report.py`` runs 010's
``extract_new`` (009's ``lexicon_extract`` after citation links are removed) on
``answer_text`` for every arm.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Same rules as 009's pipeline/common.py (normalize_url, registered_domain).
TRACKING_PARAMS = re.compile(r"^(utm_\w+|gclid|fbclid|msclkid|ref|ref_src|src|si|feature)$", re.I)
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}
HOSTNAME = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$", re.I)
MD_LINK = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")


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


def ordered_domains(urls_or_hosts) -> list[str]:
    seen, out = set(), []
    for u in urls_or_hosts:
        if not u:
            continue
        d = registered_domain(normalize_url(u) if "//" in u else u)
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _unique(items) -> list:
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def shape(**kw) -> dict:
    base = {"answer_text": "", "model": None, "cited_urls": [], "evaluated_urls": [],
            "cited_domains": [], "evaluated_domains": [], "search_queries": [], "n_searches": 0,
            "status": None, "domain_source": "url"}
    base.update(kw)
    return base


# ---------------------------------------------------------------- DataForSEO


def from_dataforseo(result: dict) -> dict:
    """``tasks[0].result[0]`` of a ChatGPT or Gemini LLM-scraper task_get/advanced."""
    result = result or {}
    text = result.get("markdown") or ""
    sources = [s.get("url") for s in (result.get("sources") or []) if isinstance(s, dict)]
    search = [s.get("url") for s in (result.get("search_results") or []) if isinstance(s, dict)]
    cited = _unique([*sources, *MD_LINK.findall(text)]) if sources else _unique(MD_LINK.findall(text))
    evaluated = _unique(search or sources)
    queries = [q for q in (result.get("fan_out_queries") or []) if isinstance(q, str) and q.strip()]
    return shape(answer_text=text, model=result.get("model"), cited_urls=cited,
                 evaluated_urls=evaluated, cited_domains=ordered_domains(cited),
                 evaluated_domains=ordered_domains(evaluated), search_queries=queries,
                 n_searches=len(queries), status="completed" if text.strip() else "empty")


# ---------------------------------------------------------------- OpenAI


def from_openai(resp: dict) -> dict:
    """A Responses API response (``POST /v1/responses``)."""
    resp = resp or {}
    texts, cited, evaluated, queries = [], [], [], []
    n_calls = n_search_actions = 0
    for item in resp.get("output") or []:
        kind = item.get("type")
        if kind == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    texts.append(part.get("text") or "")
                    cited += [a.get("url") for a in part.get("annotations") or []
                              if a.get("type") == "url_citation"]
        elif kind == "web_search_call":
            n_calls += 1
            action = item.get("action") or {}
            if action.get("type") == "search":
                n_search_actions += 1
                qs = action.get("queries") or ([action["query"]] if action.get("query") else [])
                queries += [q for q in qs if q]
            evaluated += [s.get("url") for s in action.get("sources") or [] if isinstance(s, dict)]
            if action.get("url"):
                evaluated.append(action["url"])
    text = "\n\n".join(t for t in texts if t)
    cited, evaluated = _unique(cited), _unique(evaluated)
    return shape(answer_text=text, model=resp.get("model"), cited_urls=cited,
                 evaluated_urls=evaluated, cited_domains=ordered_domains(cited),
                 evaluated_domains=ordered_domains(evaluated), search_queries=queries,
                 n_searches=n_search_actions, n_web_search_calls=n_calls,
                 status=resp.get("status"),
                 reasoning_effort=(resp.get("reasoning") or {}).get("effort"))


# ---------------------------------------------------------------- Gemini


def _chunk_domain(chunk: dict) -> tuple[str | None, str]:
    web = chunk.get("web") or {}
    if web.get("domain") and HOSTNAME.match(web["domain"].strip()):
        return registered_domain(web["domain"].strip()), "web.domain"
    title = (web.get("title") or "").strip()
    if HOSTNAME.match(title):
        return registered_domain(title), "web.title"
    uri = web.get("uri") or ""
    if uri and "grounding-api-redirect" not in uri:
        return registered_domain(uri), "uri"
    return None, "none"


def from_gemini(resp: dict) -> dict:
    """A ``generateContent`` response. Thought parts are not answer text."""
    resp = resp or {}
    cand = (resp.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text") or "" for p in parts if not p.get("thought"))
    gm = cand.get("groundingMetadata") or {}
    chunks = gm.get("groundingChunks") or []
    cited_idx = list(dict.fromkeys(i for s in gm.get("groundingSupports") or []
                                   for i in s.get("groundingChunkIndices") or [] if i is not None))
    doms = [_chunk_domain(c) for c in chunks]
    sources = {src for _d, src in doms if src != "none"}
    uri = lambda c: (c.get("web") or {}).get("uri")  # noqa: E731
    queries = [q for q in gm.get("webSearchQueries") or [] if q]
    return shape(
        answer_text=text, model=resp.get("modelVersion"),
        cited_urls=_unique(uri(chunks[i]) for i in cited_idx if i < len(chunks)),
        evaluated_urls=_unique(uri(c) for c in chunks),
        cited_domains=_unique(doms[i][0] for i in cited_idx if i < len(doms)),
        evaluated_domains=_unique(d for d, _s in doms),
        search_queries=queries, n_searches=len(queries), status=cand.get("finishReason"),
        domain_source="|".join(sorted(sources)) or "none",
        n_chunks=len(chunks), n_chunks_no_domain=sum(d is None for d, _s in doms),
    )


NORMALIZERS = {"dataforseo": from_dataforseo, "openai": from_openai, "gemini_api": from_gemini}


#: A UI scrape that came back with the app's error message instead of an answer
#: (seen in the smoke run: the Gemini app's "something went wrong" notice). Such a
#: task did not return an answer (G1); the driver resubmits it the same round.
ERROR_ANSWER = re.compile(
    r"^\W*(?:sorry,?\s+)?(?:something went wrong|an error occurred|there was an error|"
    r"i encountered an error|"
    r"i(?:'|’)m having a hard time fulfilling your request|network error)",
    re.I,
)
ERROR_ANSWER_MAX_CHARS = 300


def is_error_answer(text: str) -> bool:
    text = (text or "").strip()
    return not text or (len(text) <= ERROR_ANSWER_MAX_CHARS and bool(ERROR_ANSWER.search(text)))
