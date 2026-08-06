"""Shortest vs longest clean window — give the clipping counterclaim its best shot.

The first pass took the SHORTEST clean sentence window containing the ask,
which is the least charitable reading of the counterclaim: it strips
maximum context and therefore maximises apparent sub-intent loss.

This re-runs the saved sample under the most charitable rule — the LONGEST
clean window inside the word budget — so the objection is tested at its
strongest. Re-analysis only; no API calls.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(EXP.parent / "005-subintent-matched-panels" / "pipeline"))

from audit_candidates import brands_in, canonical  # noqa: E402
from confirm_viability import (ASK, CLIP_MAX_WORDS, DANGLING, GREETING,  # noqa: E402
                               flags_of, sentences, strip_markup)
from flags import FLAGS  # noqa: E402
from syften_probe import qualifies  # noqa: E402

STRATIFY = ["f_travel_context", "f_usage_music", "f_budget_specific",
            "f_recipient_named", "f_form_factor", "f_wireless"]


def clip(text: str, longest: bool, budget: int = CLIP_MAX_WORDS) -> str | None:
    body = GREETING.sub("", strip_markup(text)).strip()
    sents = sentences(body)
    best = None
    for i in range(len(sents)):
        for j in range(i + 1, len(sents) + 1):
            w = " ".join(sents[i:j])
            n = len(w.split())
            if n > budget:
                break
            if not ASK.search(w) or brands_in(w) or DANGLING.match(w):
                continue
            if best is None:
                best = w
            elif longest and n > len(best.split()):
                best = w
            elif not longest and n < len(best.split()):
                best = w
    return best


def main() -> None:
    items = json.loads((EXP / "data/raw/confirm_sample.json").read_text())
    groups: dict[str, str] = {}
    for it in items:
        inner = it.get("item", it)
        ok, _ = qualifies(inner)
        if ok:
            groups.setdefault(canonical(inner.get("text") or "")[:400],
                              inner.get("text") or "")
    posts = list(groups.values())
    print(f"unique qualifying posts: {len(posts)}\n")

    for label, longest, budget in [("shortest window", False, CLIP_MAX_WORDS),
                                   ("longest window (charitable)", True, CLIP_MAX_WORDS),
                                   ("longest window, 150-word budget", True, 150)]:
        clips, loss, kept_all = [], {}, 0
        strat_loss = 0
        for text in posts:
            c = clip(text, longest, budget)
            if not c:
                continue
            clips.append(c)
            full_f = flags_of(strip_markup(text))
            lost = full_f - flags_of(c)
            if not lost:
                kept_all += 1
            if any(f in lost for f in STRATIFY):
                strat_loss += 1
            for f in lost:
                loss[f] = loss.get(f, 0) + 1
        n = len(clips)
        wc = sorted(len(c.split()) for c in clips) or [0]
        print(f"=== {label} ===")
        print(f"  clip-usable        : {n}/{len(posts)} ({n/len(posts):.0%})")
        print(f"  median clip length : {wc[len(wc)//2]} words (human panel: 30)")
        print(f"  clips losing NO sub-intent flag      : {kept_all}/{n} ({kept_all/max(n,1):.0%})")
        print(f"  clips losing >=1 STRATIFIED flag     : {strat_loss}/{n} ({strat_loss/max(n,1):.0%})")
        top = sorted(loss.items(), key=lambda kv: -kv[1])[:5]
        print(f"  most-lost flags    : " +
              ", ".join(f"{f.replace('f_','')} {c}/{n}" for f, c in top))
        print()


if __name__ == "__main__":
    main()
