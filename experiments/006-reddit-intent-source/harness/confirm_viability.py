"""Confirmation sample + the sentence-clipping counterclaim test.

Two jobs:

1. **Firm up the viability rate.** The first estimate rested on 15 unique
   qualifying posts. This draws a date-sliced sample across the whole
   window (the archive returns newest-first, so slicing also removes the
   recency bias of taking the first N).

2. **Test the strongest objection to the finding.** The counterclaim: you
   need not *rewrite* a Reddit post to use it, only clip it at sentence
   boundaries, which preserves the human's own words. If a contiguous run
   of a post's own sentences forms a viable brand-free prompt, the
   "editing makes it synthetic" argument weakens considerably.

   The clip rule is MECHANICAL — which sentences to keep cannot be a
   per-post judgment call, or the researcher is writing the panel.

Also measures what clipping costs: sub-intent flags present in the full
post but absent from the clipped prompt. 005 established that sub-intent
drives the answers, so a clip that strips sub-intent is not a free edit.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
RESULTS = EXP / "results"
HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(EXP.parent / "005-subintent-matched-panels" / "pipeline"))

from audit_candidates import ARTIFACTS, brands_in, canonical  # noqa: E402
from flags import FLAGS  # noqa: E402
from syften_probe import PACE_SECONDS, load_key, qualifies, search  # noqa: E402

QUERY = "headphones travel site:reddit.com type:post"
#: Date slices across the frozen window. Newest-first ordering means an
#: unsliced pull only ever sees the last week.
SLICES = [
    ("2026-01-01T00:00:00Z", "2026-02-15T00:00:00Z"),
    ("2026-02-15T00:00:00Z", "2026-04-01T00:00:00Z"),
    ("2026-04-01T00:00:00Z", "2026-05-15T00:00:00Z"),
    ("2026-05-15T00:00:00Z", "2026-07-01T00:00:00Z"),
    ("2026-07-01T00:00:00Z", "2026-08-07T00:00:00Z"),
]
PER_SLICE = 100

#: A prompt-shaped clip: at most this many words, matching the human panel's
#: distribution (005 median 30, max 274) rather than a forum post's.
CLIP_MAX_WORDS = 80
GREETING = re.compile(r"^\s*(hello|hi|hey|good (morning|evening|afternoon))\b[^.!?]*[.!?]\s*", re.I)
ASK = re.compile(
    r"\b(looking for|recommend|recommendation|suggest|advice|which|what should|"
    r"any (ideas|suggestions)|help me|worth (it|buying)|best)\b", re.I)
DANGLING = re.compile(r"^\s*(so|also|but|and|then|plus|however|that said|as i said|"
                      r"as mentioned|it|they|these|those|this)\b", re.I)


def strip_markup(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text)
    t = (t.replace("&#39;", "'").replace("&quot;", '"').replace("&amp;", "&")
         .replace("&nbsp;", " ").replace("&gt;", ">").replace("&lt;", "<"))
    return re.sub(r"\s+", " ", t).strip()


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def clip(text: str) -> tuple[str | None, str]:
    """Mechanical sentence-boundary clip. Returns (clip, reason_if_none).

    Rule, applied identically to every post: strip markup, drop a leading
    greeting, then take the SHORTEST contiguous sentence window that
    contains the ask, is brand-free, is within the word budget, and does
    not open with a dangling connective.
    """
    body = GREETING.sub("", strip_markup(text)).strip()
    sents = sentences(body)
    if not sents:
        return None, "no_sentences"
    best: str | None = None
    for i in range(len(sents)):
        for j in range(i + 1, len(sents) + 1):
            window = " ".join(sents[i:j])
            if len(window.split()) > CLIP_MAX_WORDS:
                break
            if not ASK.search(window):
                continue
            if brands_in(window):
                continue
            if DANGLING.match(window):
                continue
            if best is None or len(window.split()) < len(best.split()):
                best = window
    return (best, "") if best else (None, "no_clean_window")


def flags_of(text: str) -> set[str]:
    low = text.lower()
    return {f for f, pat in FLAGS.items() if re.search(pat, low)}


def main() -> None:
    key = load_key()
    RAW.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    all_items = []
    for i, (after, before) in enumerate(SLICES):
        if i:
            time.sleep(PACE_SECONDS)
        r = search(key, QUERY, PER_SLICE, after=after, before=before)
        items = r.get("items", [])
        print(f"  slice {after[:10]}..{before[:10]}: {len(items)} of {r.get('total')}")
        all_items.extend(items)
        quota = r.get("quota")
    (RAW / "confirm_sample.json").write_text(json.dumps(all_items, indent=2))

    qual = []
    for it in all_items:
        inner = it.get("item", it)
        ok, _ = qualifies(inner)
        if ok:
            qual.append(inner)

    groups: dict[str, dict] = {}
    for inner in qual:
        groups.setdefault(canonical(inner.get("text") or "")[:400], inner)
    uniq = list(groups.values())

    verbatim, clipped, failed = [], [], []
    flag_loss: dict[str, int] = {}
    for inner in uniq:
        text = inner.get("text") or ""
        arts = [k for k, p in ARTIFACTS.items() if p.search(text)]
        if not arts and not brands_in(text):
            verbatim.append(inner)
        c, why = clip(text)
        if c:
            clipped.append((inner, c))
            lost = flags_of(strip_markup(text)) - flags_of(c)
            for f in lost:
                flag_loss[f] = flag_loss.get(f, 0) + 1
        else:
            failed.append((inner, why))

    n_fetched, n_q, n_u = len(all_items), len(qual), len(uniq)
    out = [
        "# 006 — viability confirmation and the sentence-clipping test", "",
        f"Date-sliced sample across the frozen window ({len(SLICES)} slices x "
        f"{PER_SLICE}), which also removes the newest-first bias of the earlier pulls.", "",
        "## Funnel", "",
        "| Stage | Count |", "|---|---|",
        f"| Posts fetched | {n_fetched} |",
        f"| Pass frozen criteria | {n_q} ({n_q/max(n_fetched,1):.1%}) |",
        f"| Unique after cross-post collapse | {n_u} |",
        f"| **Usable verbatim** | **{len(verbatim)} ({len(verbatim)/max(n_u,1):.0%} of unique)** |",
        f"| **Usable via mechanical sentence clip** | **{len(clipped)} ({len(clipped)/max(n_u,1):.0%} of unique)** |",
        f"| Not usable even clipped | {len(failed)} |", "",
        "## The clipping counterclaim", "",
        "The objection: clipping a post at sentence boundaries preserves the",
        "author's own words, so it should not count as making the prompt",
        "synthetic. The clip rule here is mechanical and identical for every",
        "post: strip markup, drop a leading greeting, then take the shortest",
        "contiguous sentence window containing the ask that is brand-free,",
        f"under {CLIP_MAX_WORDS} words, and does not open with a dangling connective.", "",
    ]
    if clipped:
        wc = sorted(len(c.split()) for _, c in clipped)
        out.append(f"Clipped prompts: median {wc[len(wc)//2]} words "
                   f"(range {wc[0]}-{wc[-1]}); the 005 human panel is median 30.")
    out += ["", "### What clipping costs", "",
            "005 established that sub-intent drives the answers, so a clip that",
            "strips sub-intent is not a free edit. Flags present in the full post",
            "but absent from the clipped prompt:", "",
            "| Sub-intent flag | Posts losing it |", "|---|---|"]
    for f, c in sorted(flag_loss.items(), key=lambda kv: -kv[1]):
        out.append(f"| {f} | {c} |")
    if not flag_loss:
        out.append("| (none) | 0 |")
    out += ["", f"Quota after this run: `{quota}`", ""]

    (RESULTS / "viability-confirmation.md").write_text("\n".join(out) + "\n")
    print(f"\nfetched {n_fetched} | qualify {n_q} | unique {n_u} | "
          f"verbatim {len(verbatim)} | clip-usable {len(clipped)}")
    print(f"flag loss from clipping: {flag_loss}")
    print(f"quota: {quota}")


if __name__ == "__main__":
    main()
