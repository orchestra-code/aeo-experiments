"""YouTube URL and description parsing.

Spyglasses' URL normalization keeps non-tracking query params, so
``watch?v=X`` and ``watch?v=X&t=138`` are distinct CitedPage rows — analysis
must dedup/cluster on the parsed ``video_id``, never on the URL. Fragments
are stripped from the normalized key but survive in the raw citation URL,
so ``#t=`` is parsed here too.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

_TIMESTAMP = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")

#: A chapter line: optional list marker, then m:ss or h:mm:ss at line start.
_CHAPTER_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\[)?(\d{1,2}):(\d{2})(?::(\d{2}))?\b", re.MULTILINE
)

_LINK = re.compile(r"https?://\S+")


def parse_video_id(url: str | None) -> str | None:
    """Extract the 11-char video id from any YouTube URL form, else None."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path or ""

    candidate: str | None = None
    if host == "youtu.be":
        candidate = path.lstrip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            m = re.match(r"^/(?:shorts|embed|live|v)/([^/?#]+)", path)
            if m:
                candidate = m.group(1)
    if candidate and VIDEO_ID.match(candidate):
        return candidate
    return None


def parse_timestamp(url: str | None) -> int | None:
    """Seconds from a ``t=`` query param or ``#t=`` fragment, else None.

    Accepts ``138``, ``138s``, ``2m18s``, ``1h2m3s``. A timestamp is evidence
    the assistant had *some* temporal anchor for the video — not proof it read
    the transcript (chapters and SERP "key moments" are alternative sources).
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    raw: str | None = (parse_qs(parsed.query).get("t") or [None])[0]
    if raw is None and parsed.fragment:
        frag = parsed.fragment
        if frag.startswith("t="):
            raw = frag[2:]
        elif re.fullmatch(r"\d+[hms]?.*", frag) and _TIMESTAMP.match(frag):
            raw = frag
    if raw is None:
        return None

    m = _TIMESTAMP.match(raw)
    if not m or not any(m.groups()):
        return None
    h, mnt, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mnt * 60 + s


def extract_chapter_timestamps(description: str | None) -> list[int]:
    """Seconds for each chapter-style timestamp line in a video description."""
    if not description:
        return []
    out = []
    for m in _CHAPTER_LINE.finditer(description):
        a, b, c = m.groups()
        if c is not None:  # h:mm:ss
            out.append(int(a) * 3600 + int(b) * 60 + int(c))
        else:  # m:ss
            out.append(int(a) * 60 + int(b))
    return out


def timestamp_matches_chapter(ts: int, chapters: list[int], tol: int = 5) -> bool:
    """Whether a cited timestamp coincides with a description chapter marker."""
    return any(abs(ts - c) <= tol for c in chapters)


def description_features(description: str | None) -> dict:
    """Derived, releasable features of a video description.

    The description text itself is page content and is never released;
    only these scalars are.
    """
    if not description:
        return {
            "desc_word_count": 0,
            "desc_link_count": 0,
            "chapter_count": 0,
            "has_chapters": False,
        }
    chapters = extract_chapter_timestamps(description)
    # YouTube requires >=3 markers starting at 0:00 for real chapter segments;
    # we use the same threshold so has_chapters means "creator built chapters".
    has_chapters = len(chapters) >= 3 and 0 in chapters
    return {
        "desc_word_count": len(description.split()),
        "desc_link_count": len(_LINK.findall(description)),
        "chapter_count": len(chapters),
        "has_chapters": has_chapters,
    }
