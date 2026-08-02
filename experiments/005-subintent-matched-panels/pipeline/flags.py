"""The 15 phrasing-flag regexes — the frozen sub-intent instrument.

Verbatim from experiment 002's exploratory coding, unchanged through 003
(90_coverage_flags.py). In 005 they are PART OF THE DESIGN, not just the
descriptive layer: the mat panel is stratified on the joint distribution of
STRATIFY_FLAGS over 003's human panel, and the harness validates every
generated prompt against these exact patterns. Any change after the freeze
is a protocol violation.
"""

from __future__ import annotations

FLAGS = {
    "f_budget_specific": r"[\$€£]\s?\d|\d+\s?(dollars|bucks|euros?|pounds)|under \d|less than \d|budget of",
    "f_value_language": r"best value|good value|affordable|cheap|budget[- ]friendly|not too expensive|reasonabl|won'?t break the bank|bang for",
    "f_recipient_named": r"\b(sister|brother|wife|husband|mom|mother|dad|father|daughter|son|aunt|uncle|niece|nephew|girlfriend|boyfriend|partner|friend|cousin|grandm|grandf|in[- ]law)\b",
    "f_age_mentioned": r"\b\d{2}[s\-]?\s?(year|yr|s\b)|(early|mid|late)\s\d{2}s|\bage[ds]?\b",
    "f_noise_cancel": r"noise[- ]?cancel|\banc\b|noise[- ]reduc",
    "f_form_factor": r"over[- ]?(the[- ])?ear|on[- ]ear|in[- ]ear|earbud|ear[- ]bud",
    "f_wireless": r"wireless|bluetooth|cordless",
    "f_battery": r"battery|charge|charging",
    "f_comfort": r"comfort|comfy|long flight|hours",
    "f_output_count": r"\b(top|best|give me|list|recommend)\s?(the\s)?\d\b|\d\s(options|choices|recommendations|suggestions|picks|models|brands)",
    "f_output_format": r"\btable\b|\bformat\b|bullet|column|rank(ed|ing)?\b|compare.*side",
    "f_reviews_stars": r"\bstar\b|\bstars\b|rated|rating|review",
    "f_usage_movies": r"movie|video|film|netflix|show",
    "f_usage_music": r"music|listen|song|audio ?book|podcast",
    "f_travel_context": r"travel|flight|plane|airplane|trip|commut|airport",
}

#: The six flags the mat panel stratifies on: the human panel's most
#: prevalent frames (travel, music) plus the four "valued attribute" levers
#: 002/003 showed steer brand mix (budget, recipient, form factor, wireless).
STRATIFY_FLAGS = [
    "f_travel_context",
    "f_usage_music",
    "f_budget_specific",
    "f_recipient_named",
    "f_form_factor",
    "f_wireless",
]

#: Plain-language generation requirements per stratified flag. "must" text is
#: injected when the target cell has the flag ON; "must_not" when OFF.
FLAG_REQUIREMENTS = {
    "f_travel_context": {
        "must": "mention travel (flights, trips, commuting, or airports)",
        "must_not": "mention travel, flights, planes, trips, commuting, or airports",
    },
    "f_usage_music": {
        "must": "mention listening to music, podcasts, or audiobooks",
        "must_not": "mention music, songs, listening, podcasts, or audiobooks",
    },
    "f_budget_specific": {
        "must": "state a specific numeric budget (e.g. a dollar amount or 'under $150')",
        "must_not": "state any specific price, dollar amount, or numeric budget",
    },
    "f_recipient_named": {
        "must": "name a specific family member or friend the purchase is for (e.g. dad, sister, husband, friend)",
        "must_not": "name any family member, partner, or friend",
    },
    "f_form_factor": {
        "must": "mention a headphone form factor (over-ear, on-ear, in-ear, or earbuds)",
        "must_not": "mention over-ear, on-ear, in-ear, or earbuds",
    },
    "f_wireless": {
        "must": "mention wireless, Bluetooth, or cordless connectivity",
        "must_not": "mention wireless, Bluetooth, or cordless",
    },
}
