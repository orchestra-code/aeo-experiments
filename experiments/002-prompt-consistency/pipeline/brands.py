"""Brand lexicon + deterministic extraction from answer markdown.

Method (spec §3): canonical brand -> alias list (model names map to the
parent brand); extraction is a longest-alias-first, word-boundary regex over
cleaned lowercase markdown (URLs stripped so citation links don't count as
recommendations). Ordered by first mention.

The lexicon below is seeded from widely-known headphone brands and is CURATED
after wave 1 via mine_candidates() + human review (extraction code, not a
hypothesis — refinements are allowed post-freeze and logged in spec
"Deviations"). Audit D validates precision/recall on a 30-response manual
spot-check before the lexicon is frozen for analysis.
"""

from __future__ import annotations

import re
from collections import Counter

#: canonical -> aliases (all matched case-insensitively on word boundaries).
HEADPHONE_LEXICON: dict[str, list[str]] = {
    "sony": ["sony", "wh-1000xm4", "wh-1000xm5", "wh-1000xm6", "wf-1000xm4",
             "wf-1000xm5", "linkbuds", "ult wear"],
    "bose": ["bose", "quietcomfort", "qc35", "qc45", "qc ultra", "qc-ultra"],
    "apple": ["apple", "airpods", "airpods pro", "airpods max", "beats"],
    "sennheiser": ["sennheiser", "momentum 4", "momentum wireless", "accentum",
                   "hd 450bt", "hd 560s", "hd 660"],
    "anker": ["anker", "soundcore", "space one", "space q45", "life q30", "life q35"],
    "jbl": ["jbl", "tour one", "live 660nc", "live 770nc", "tune 760nc"],
    "jabra": ["jabra", "elite 85h", "elite 10"],
    "audio-technica": ["audio-technica", "audio technica", "ath-m50x", "ath-m50xbt"],
    "bowers & wilkins": ["bowers & wilkins", "bowers and wilkins", "b&w", "px7", "px8"],
    "bang & olufsen": ["bang & olufsen", "bang and olufsen", "beoplay"],
    "marshall": ["marshall", "monitor ii", "major iv", "major v"],
    "skullcandy": ["skullcandy", "crusher anc", "hesh anc"],
    "1more": ["1more", "sonoflow"],
    "shure": ["shure", "aonic 40", "aonic 50"],
    "philips": ["philips", "fidelio"],
    "beyerdynamic": ["beyerdynamic", "dt 770", "amiron"],
    "focal": ["focal", "bathys"],
    "shokz": ["shokz", "openrun", "aftershokz"],
    "earfun": ["earfun", "wave pro"],
    "edifier": ["edifier", "w820nb", "stax spirit"],
    "technics": ["technics", "eah-az80", "eah-az100"],
    "samsung": ["samsung", "galaxy buds"],
    "google": ["google", "pixel buds"],
    "nothing": ["nothing ear"],
    "denon": ["denon", "perl pro"],
    "master & dynamic": ["master & dynamic", "master and dynamic", "mw75", "mh40"],
    "puro": ["puro", "puro sound labs", "bt2200"],
    "dyson": ["dyson", "ontrac", "zone"],
    "sonos": ["sonos ace"],
}

#: Coffee-shop / brand-design-agency arm. Curated 2026-07-16 from wave-1
#: candidate mining (mine_candidates over 143 answers) per spec §2 Audit D;
#: single-word aliases (clay, motto, koto, ember, ...) are deliberate — these
#: answers are agency listicles — and validated by the Audit D spot-check.
COFFEE_LEXICON: dict[str, list[str]] = {
    "pentagram": ["pentagram"],
    "landor": ["landor"],
    "wolff olins": ["wolff olins"],
    "interbrand": ["interbrand"],
    "collins": ["collins"],
    "designstudio": ["designstudio"],
    "ramotion": ["ramotion"],
    "clay": ["clay"],
    "duck.design": ["duck.design", "duck design"],
    "99designs": ["99designs"],
    "fiverr": ["fiverr"],
    "upwork": ["upwork"],
    "canva": ["canva"],
    "looka": ["looka"],
    "tailor brands": ["tailor brands"],
    "smith & diction": ["smith & diction", "smith and diction"],
    "motto": ["motto"],
    "red antler": ["red antler"],
    "all good nyc": ["all good nyc", "all good"],
    "bureau of small projects": ["bureau of small projects"],
    "crate47": ["crate47", "crate 47"],
    "murmur creative": ["murmur creative", "murmur"],
    "matchstic": ["matchstic"],
    "ulysses design co": ["ulysses design co", "ulysses design"],
    "studio mpls": ["studio mpls"],
    "holman design": ["holman design"],
    "gretel": ["gretel"],
    "crown creative": ["crown creative"],
    "zut alors": ["zut alors"],
    "freshsparks": ["freshsparks"],
    "splurge media": ["splurge media"],
    "mucho": ["mucho"],
    "pearlfisher": ["pearlfisher"],
    "jones knowles ritchie": ["jones knowles ritchie", "jkr"],
    "anchour": ["anchour"],
    "koto": ["koto"],
    "lippincott": ["lippincott"],
    "nice branding": ["nice branding"],
    "mixed media collective": ["mixed media collective"],
    "ragged edge": ["ragged edge"],
    "helms workshop": ["helms workshop"],
    "supervox": ["supervox"],
    "atlas branding": ["atlas branding"],
    "vorena studio": ["vorena studio", "vorena"],
    "manypixels": ["manypixels"],
    "mucca": ["mucca"],
    "upstart food brands": ["upstart food brands"],
    "focus lab": ["focus lab"],
    "&walsh": ["&walsh", "and walsh"],
    "siegel+gale": ["siegel+gale", "siegel gale"],
    "studio tyrsa": ["studio tyrsa"],
    "born & bred": ["born & bred", "born and bred"],
    "south square creative": ["south square creative"],
    "huckleberry branding": ["huckleberry branding", "huckleberry"],
    "design ranch": ["design ranch"],
    "basecoat": ["by basecoat", "basecoat"],
    "outcrowd": ["outcrowd"],
    "vigor branding": ["vigor branding", "vigor"],
    "saint urbain": ["saint urbain"],
    "knapsack creative": ["knapsack creative", "knapsack"],
    "brigade": ["brigade"],
    "black anchor design": ["black anchor design", "black anchor"],
    "chermayeff & geismar & haviv": ["chermayeff & geismar & haviv", "chermayeff"],
    "ember": ["ember"],
    "the working assembly": ["the working assembly", "working assembly"],
    "design womb": ["design womb"],
    "blindtiger design": ["blindtiger design", "blindtiger"],
    "ludlow kingsley": ["ludlow kingsley"],
    "the cooper studio": ["the cooper studio", "cooper studio"],
    "stuck with pins": ["stuck with pins"],
    "cactus country": ["cactus country"],
    "richard manville studio": ["richard manville studio", "richard manville"],
    "florence studios": ["florence studios"],
    "curbside agency": ["curbside agency", "curbside"],
    "element 47": ["element 47"],
    "la caballa agency": ["la caballa agency", "la caballa"],
    "louise fili": ["louise fili"],
    "stellen design": ["stellen design"],
    "moving brands": ["moving brands"],
    "how&how": ["how&how", "how & how"],
}

LEXICONS = {"headphones": HEADPHONE_LEXICON, "coffee": COFFEE_LEXICON}

_MD_URL = re.compile(r"\((?:https?|www)[^)]*\)|https?://\S+")
_MD_MARKUP = re.compile(r"[*_#>`]")


def clean_markdown(markdown: str) -> str:
    """Lowercase; strip link targets/bare URLs and markdown markup, keep link text."""
    text = _MD_URL.sub(" ", markdown)
    text = _MD_MARKUP.sub(" ", text)
    return text.lower()


_COMPILED: dict[str, list[tuple[re.Pattern, str]]] = {}


def _compile(intent: str) -> list[tuple[re.Pattern, str]]:
    if intent not in _COMPILED:
        lexicon = LEXICONS[intent]
        pairs = [(alias, canon) for canon, aliases in lexicon.items() for alias in aliases]
        pairs.sort(key=lambda p: len(p[0]), reverse=True)  # longest alias first
        _COMPILED[intent] = [
            (re.compile(rf"(?<![\w&]){re.escape(alias)}(?![\w&])"), canon)
            for alias, canon in pairs
        ]
    return _COMPILED[intent]


def extract_brands(markdown: str, intent: str) -> list[str]:
    """Canonical brands ordered by first mention in the answer."""
    text = clean_markdown(markdown)
    first_pos: dict[str, int] = {}
    for pattern, canon in _compile(intent):
        m = pattern.search(text)
        if m and (canon not in first_pos or m.start() < first_pos[canon]):
            first_pos[canon] = m.start()
    return sorted(first_pos, key=first_pos.get)


#: Candidate mining for lexicon curation (run over wave-1 markdown, then a
#: human folds real brands/aliases into the lexicon above).
_CANDIDATE = re.compile(
    r"\*\*([^*\n]{2,60})\*\*"           # bold spans
    r"|^\s*(?:[-*]|\d+\.)\s+([^\n:–—]{2,60})"  # list-item lead text
    r"|\|\s*([^|\n]{2,60})\s*\|",       # first table cells
    re.M,
)


def mine_candidates(markdowns: list[str]) -> Counter:
    counts: Counter = Counter()
    for md in markdowns:
        text = _MD_URL.sub(" ", md)
        for m in _CANDIDATE.finditer(text):
            phrase = next(g for g in m.groups() if g)
            phrase = re.sub(r"\s+", " ", phrase).strip(" .,:;()[]")
            if phrase and not phrase.isdigit():
                counts[phrase] += 1
    return counts
