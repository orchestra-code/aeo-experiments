"""Ship-of-Theseus audit: are qualifying Reddit posts usable AS PROMPTS, verbatim?

A post that must be edited to work as a directly-submitted prompt is no
longer a human artifact — it is a synthetic derivative of one, which
defeats the entire reason for sourcing from human conversations.

Runs over the qualifying posts in every saved sample and characterises the
edits each would need. No API calls. Post text stays local; only
characteristics and short fragments are printed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
sys.path.insert(0, str(EXP.parent / "005-subintent-matched-panels" / "pipeline"))
from brands import HEADPHONE_LEXICON  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from syften_probe import qualifies  # noqa: E402

ALIASES = sorted(
    {a.lower() for canon, al in HEADPHONE_LEXICON.items() for a in [canon, *al]},
    key=len, reverse=True,
)

#: Artifacts that make a post something other than a submittable prompt.
ARTIFACTS = {
    "reddit_address": re.compile(r"\br/\w+|\bsubreddit\b|\bredditors?\b", re.I),
    "thread_edit": re.compile(r"^\s*(edit|update)\s*\d*\s*[:.]", re.I | re.M),
    "tldr": re.compile(r"\bt(l;?|/)dr\b", re.I),
    "thanks_signoff": re.compile(r"\b(thanks in advance|any (help|advice) (is |would be )?appreciated|"
                                 r"thank you (all|in advance)|cheers)\b", re.I),
    "markdown_link": re.compile(r"\[[^\]]+\]\([^)]+\)|https?://\S+"),
    "markdown_fmt": re.compile(r"\*\*|^\s*[-*]\s+|^\s*#{1,6}\s", re.M),
    "crosspost_ref": re.compile(r"\b(as i (said|mentioned)|my (other|previous) post|see my)\b", re.I),
    "flair_or_tag": re.compile(r"^\s*\[[^\]]{1,25}\]", re.M),
    "html_markup": re.compile(r"</?(p|br|a|em|strong|ul|ol|li|blockquote)\b|&#?\w+;", re.I),
    "greeting": re.compile(r"^\s*(?:<p>)?\s*(hello|hi|hey|good (morning|evening))\b", re.I),
    "flair_prefix": re.compile(r"^\s*flair:\s*\w+", re.I),
}

#: Strip everything that varies between copies of the same cross-posted item
#: so duplicates actually collapse. The frozen hash-dedup missed these
#: because a "Flair: Question" prefix changes the hash.
def canonical(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text)
    t = re.sub(r"&#?\w+;", " ", t)
    t = re.sub(r"^\s*flair:\s*\w+", " ", t, flags=re.I)
    return re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"\s+", " ", t.lower())).strip()


def brands_in(text: str) -> list[str]:
    low = text.lower()
    hits = []
    for a in ALIASES:
        if re.search(rf"(?<![\w&]){re.escape(a)}(?![\w&])", low):
            hits.append(a)
    return hits


def main() -> None:
    rows = []
    for path in sorted(RAW.glob("sample_*.json")):
        for it in json.loads(path.read_text()):
            inner = it.get("item", it)
            ok, _ = qualifies(inner)
            if not ok:
                continue
            text = (inner.get("text") or "").strip()
            found = {k: bool(p.search(text)) for k, p in ARTIFACTS.items()}
            b = brands_in(text)
            rows.append(dict(
                source=path.stem.replace("sample_", ""),
                sub=inner.get("backend_sub"),
                words=len(text.split()),
                questions=text.count("?"),
                brands=b,
                artifacts=[k for k, v in found.items() if v],
                text=text,
            ))

    if not rows:
        print("no qualifying posts in the saved samples")
        return

    print(f"qualifying posts across saved samples: {len(rows)}\n")
    print(f"{'src':<18} {'subreddit':<22} {'words':>5} {'?':>2} {'brands':>6}  artifacts")
    print("-" * 100)
    for r in rows:
        print(f"{r['source']:<18} {str(r['sub'] or '?'):<22} {r['words']:>5} "
              f"{r['questions']:>2} {len(r['brands']):>6}  {','.join(r['artifacts']) or '-'}")

    n = len(rows)

    # Cross-post collapse: the same human question posted to several subs is
    # ONE data point, not several. The frozen hash-dedup missed these.
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(canonical(r["text"])[:400], []).append(r)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    unique_n = len(groups)
    print(f"\n--- cross-post duplication (frozen dedup missed these) ---")
    print(f"  qualifying rows      : {n}")
    print(f"  unique questions     : {unique_n}")
    print(f"  inflation            : {(n - unique_n) / n:.0%} of the count")
    for v in dupes.values():
        print(f"    same post in: {', '.join(str(x['sub']) for x in v)}")

    uniq = [v[0] for v in groups.values()]
    m = len(uniq)
    clean = [r for r in uniq if not r["artifacts"] and not r["brands"]]
    no_brand = [r for r in uniq if not r["brands"]]
    single_q = [r for r in uniq if r["questions"] <= 1]

    print(f"\n--- usable VERBATIM as a prompt (unique questions only, n={m}) ---")
    print(f"  no artifacts and no brand names : {len(clean)}/{m} ({len(clean)/m:.0%})")
    print(f"  no brand names (redaction free) : {len(no_brand)}/{m} ({len(no_brand)/m:.0%})")
    print(f"  at most one question            : {len(single_q)}/{m} ({len(single_q)/m:.0%})")

    from collections import Counter
    art = Counter(a for r in rows for a in r["artifacts"])
    print("\n--- artifact prevalence ---")
    for a, c in art.most_common():
        print(f"  {a:<18} {c}/{n} ({c/n:.0%})")

    ws = sorted(r["words"] for r in rows)
    med = ws[len(ws) // 2]
    print(f"\n--- length vs the human survey panel ---")
    print(f"  reddit candidates: median {med} words (range {ws[0]}-{ws[-1]})")
    print(f"  005 human panel  : median 30 words (range 3-274)")
    print(f"  over 100 words   : {sum(1 for w in ws if w > 100)}/{n}")

    bc = Counter(b for r in rows for b in r["brands"])
    if bc:
        print("\n--- brands named in candidate posts (each one needs redacting) ---")
        for b, c in bc.most_common(12):
            print(f"  {b:<18} {c}")

    print("\n--- first 200 chars of each candidate (local only, never published) ---")
    for i, r in enumerate(rows, 1):
        frag = re.sub(r"\s+", " ", r["text"])[:200]
        print(f"\n{i:2d}. [{r['sub']}] {frag}...")


if __name__ == "__main__":
    main()
