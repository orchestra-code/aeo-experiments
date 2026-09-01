"""Experiment 008 brand panel — THE instrument. **STATUS: DRAFT.**

Freezes WITH the spec (after pilot wave 0). Until then every factual claim in
here — canonical domain, old domains, migration facts, entity-ambiguity notes
— is a candidate, to be verified at freeze per spec Audit D (true_domain
resolves and is confirmed from the brand's own site; every old_domains entry
gets a documented migration date + source). Nothing in this file may change
after wave 1 submits; deviations go in the spec's Deviations section.

Tiers (12 each, 48 total):
  A  guessable      — canonical domain IS brandname.com (control)
  B  non-obvious    — canonical domain is not brandname.com (.app/.ai/.do,
                      prefixed, or a different name entirely)
  C  migrated       — brand moved domains; old_domains records the prior one
  D  obscure        — real but low-prominence brands (the pure-guess
                      condition); domain_guessable annotates whether the
                      naive guess happens to be right

`expected_guess` is the frozen morphological-guess token set for error-kind
scoring (spec §2 Audit B): a consulted domain in this set counts as
`morphological_guess`. `ambiguity` notes a name collision with a bigger or
unrelated entity — those brands' prompt templates carry the category anchor,
and several morphological guesses are REAL sites owned by others (bear.com,
motion.com), which is exactly the trap the error-content contrast needs.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrandEntry:
    canonical: str
    tier: str  # "A" | "B" | "C" | "D"
    true_domain: str
    category: str  # prompt-template anchor ("project management software", …)
    aliases: tuple[str, ...] = ()
    old_domains: tuple[str, ...] = ()  # tier C: prior canonical domains
    expected_guess: tuple[str, ...] = ()  # morphological-guess domains
    domain_guessable: bool = False  # true when a naive guess lands right
    ambiguity: str = ""  # entity-collision note; anchors matter here


DRAFT_PANEL: tuple[BrandEntry, ...] = (
    # ---- Tier A — guessable (brandname.com), high prominence ----
    BrandEntry("Sony", "A", "sony.com", "consumer electronics", domain_guessable=True),
    BrandEntry("Bose", "A", "bose.com", "audio equipment", domain_guessable=True),
    BrandEntry("Asana", "A", "asana.com", "project management software", domain_guessable=True,
               ambiguity="yoga asana — anchor needed in category prompts"),
    BrandEntry("Shopify", "A", "shopify.com", "e-commerce platform", domain_guessable=True),
    BrandEntry("Stripe", "A", "stripe.com", "payments platform", domain_guessable=True),
    BrandEntry("Figma", "A", "figma.com", "design software", domain_guessable=True),
    BrandEntry("Slack", "A", "slack.com", "team messaging software", domain_guessable=True),
    BrandEntry("Dropbox", "A", "dropbox.com", "cloud storage", domain_guessable=True),
    BrandEntry("Airbnb", "A", "airbnb.com", "vacation rental platform", domain_guessable=True),
    BrandEntry("Spotify", "A", "spotify.com", "music streaming service", domain_guessable=True),
    BrandEntry("Duolingo", "A", "duolingo.com", "language learning app", domain_guessable=True),
    BrandEntry("Canva", "A", "canva.com", "graphic design tool", domain_guessable=True),

    # ---- Tier B — non-obvious canonical domain ----
    BrandEntry("Linear", "B", "linear.app", "issue tracking software",
               expected_guess=("linear.com",),
               ambiguity="common English word — anchor needed"),
    BrandEntry("Bear", "B", "bear.app", "note-taking app",
               expected_guess=("bear.com",),
               ambiguity="bear.com is an unrelated mattress company; the animal"),
    BrandEntry("Craft", "B", "craft.do", "document editor",
               expected_guess=("craft.com", "craft.io"),
               ambiguity="common English word; craft.co is a company-data firm"),
    BrandEntry("Things", "B", "culturedcode.com", "to-do list app",
               aliases=("Things 3", "Cultured Code"),
               expected_guess=("things.com", "things.app"),
               ambiguity="maximally generic name — strong anchor needed"),
    BrandEntry("Motion", "B", "usemotion.com", "AI calendar and scheduling app",
               expected_guess=("motion.com", "motion.app", "motion.ai"),
               ambiguity="motion.com is Motion Industries (industrial supply)"),
    BrandEntry("Clockwise", "B", "getclockwise.com", "calendar optimization software",
               expected_guess=("clockwise.com",)),
    BrandEntry("Otter", "B", "otter.ai", "AI meeting transcription",
               aliases=("Otter.ai",),
               expected_guess=("otter.com",),
               ambiguity="the animal; anchor needed"),
    BrandEntry("Fireflies", "B", "fireflies.ai", "AI meeting notetaker",
               aliases=("Fireflies.ai",),
               expected_guess=("fireflies.com",)),
    BrandEntry("Gamma", "B", "gamma.app", "AI presentation software",
               expected_guess=("gamma.com", "gamma.io"),
               ambiguity="greek letter; multiple gamma-named companies"),
    BrandEntry("Tome", "B", "tome.app", "AI presentation software",
               expected_guess=("tome.com",),
               ambiguity="common English word"),
    BrandEntry("Height", "B", "height.app", "project management software",
               expected_guess=("height.com",),
               ambiguity="common English word — strong anchor needed"),
    BrandEntry("Mural", "B", "mural.co", "online whiteboard software",
               expected_guess=("mural.com",),
               ambiguity="common English word"),

    # ---- Tier C — migrated / rebranded domains ----
    BrandEntry("Notion", "C", "notion.com", "workspace and notes software",
               old_domains=("notion.so",),
               expected_guess=("notion.com",), domain_guessable=True,
               ambiguity="notion.so was canonical until ~2023 and still redirects"),
    BrandEntry("X", "C", "x.com", "social media platform",
               aliases=("Twitter", "X (formerly Twitter)"),
               old_domains=("twitter.com",),
               expected_guess=("x.com", "twitter.com"),
               ambiguity="single letter; the Twitter alias is load-bearing"),
    BrandEntry("Zoom", "C", "zoom.com", "video conferencing software",
               old_domains=("zoom.us",),
               expected_guess=("zoom.com", "zoom.us"), domain_guessable=True,
               ambiguity="verify which of zoom.com/zoom.us is canonical at freeze"),
    BrandEntry("Front", "C", "front.com", "shared inbox software",
               aliases=("Front App",),
               old_domains=("frontapp.com",),
               expected_guess=("front.com", "frontapp.com"), domain_guessable=True,
               ambiguity="common English word — anchor needed"),
    BrandEntry("GoTo", "C", "goto.com", "IT management and remote work software",
               aliases=("GoTo (formerly LogMeIn)", "LogMeIn"),
               old_domains=("logmein.com",),
               expected_guess=("goto.com",), domain_guessable=True),
    BrandEntry("Sketch", "C", "sketch.com", "design software for Mac",
               old_domains=("sketchapp.com",),
               expected_guess=("sketch.com", "sketchapp.com"), domain_guessable=True,
               ambiguity="common English word"),
    BrandEntry("Freshworks", "C", "freshworks.com", "customer service software",
               aliases=("Freshdesk",),
               old_domains=("freshdesk.com",),
               expected_guess=("freshworks.com",), domain_guessable=True,
               ambiguity="freshdesk.com still live as a product domain — verify treatment at freeze"),
    BrandEntry("Limitless", "C", "limitless.ai", "AI wearable and meeting memory",
               aliases=("Rewind", "Rewind AI"),
               old_domains=("rewind.ai",),
               expected_guess=("limitless.com", "limitless.ai"),
               ambiguity="common English word; the Rewind alias is load-bearing"),
    BrandEntry("Meta", "C", "meta.com", "social media company",
               aliases=("Facebook", "Meta Platforms"),
               old_domains=("facebook.com", "about.fb.com"),
               expected_guess=("meta.com", "facebook.com"), domain_guessable=True,
               ambiguity="corporate vs product domains — score corporate asks only"),
    BrandEntry("Shortcut", "C", "shortcut.com", "project management for software teams",
               aliases=("Clubhouse (project management)",),
               old_domains=("clubhouse.io",),
               expected_guess=("shortcut.com",), domain_guessable=True,
               ambiguity="Clubhouse collides with the audio app clubhouse.com"),
    BrandEntry("Bitly", "C", "bitly.com", "link shortening service",
               aliases=("bit.ly",),
               old_domains=("bit.ly",),
               expected_guess=("bitly.com", "bit.ly"), domain_guessable=True,
               ambiguity="bit.ly is still the live short domain — verify canonical-site treatment"),
    BrandEntry("Alphabet", "C", "abc.xyz", "holding company of Google",
               aliases=("Alphabet Inc.",),
               old_domains=(),
               expected_guess=("alphabet.com",),
               ambiguity="alphabet.com belongs to BMW's fleet-management brand — a real other_real trap"),

    # ---- Tier D — obscure long-tail (pure-guess condition) ----
    BrandEntry("Bonsai", "D", "hellobonsai.com", "freelancer business software",
               aliases=("Hello Bonsai",),
               expected_guess=("bonsai.com", "bonsai.io"),
               ambiguity="the tree; bonsai.io is an unrelated search-hosting firm"),
    BrandEntry("HoneyBook", "D", "honeybook.com", "client management for creatives",
               domain_guessable=True),
    BrandEntry("Dubsado", "D", "dubsado.com", "business management for creatives",
               domain_guessable=True),
    BrandEntry("17hats", "D", "17hats.com", "small business management software",
               domain_guessable=True),
    BrandEntry("Plutio", "D", "plutio.com", "all-in-one business management app",
               domain_guessable=True),
    BrandEntry("SuiteDash", "D", "suitedash.com", "client portal software",
               domain_guessable=True),
    BrandEntry("Accelo", "D", "accelo.com", "professional services automation",
               domain_guessable=True),
    BrandEntry("Scoro", "D", "scoro.com", "work management software",
               domain_guessable=True),
    BrandEntry("Avaza", "D", "avaza.com", "project management and invoicing",
               domain_guessable=True),
    BrandEntry("Paymo", "D", "paymo.com", "time tracking and invoicing software",
               expected_guess=("paymo.com", "paymo.biz"),
               ambiguity="verify canonical at freeze — paymo.biz was long the primary"),
    BrandEntry("Moxo", "D", "moxo.com", "client interaction platform",
               aliases=("Moxtra",),
               old_domains=("moxtra.com",),
               domain_guessable=True,
               ambiguity="rebranded from Moxtra — arguably C; kept D for prominence, noted"),
    BrandEntry("Nutshell", "D", "nutshell.com", "CRM for small businesses",
               domain_guessable=True,
               ambiguity="common English word — anchor needed"),
)

# Draft prompt templates for pilot wave 0 (wording freezes with the spec; the
# {category} anchor is mandatory for every brand with an ambiguity note).
DRAFT_TEMPLATES: dict[str, str] = {
    # p1 — brand-identity style: the shape production sees consult the brand
    # site by default.
    "p1": "What is {brand}, the {category}? What does it offer and how is it priced?",
    # p2 — brand-named category question: the older named-consultation shape.
    "p2": "Is {brand} a good {category} for a small team? What do reviews say?",
}


def by_tier(tier: str) -> tuple[BrandEntry, ...]:
    return tuple(b for b in DRAFT_PANEL if b.tier == tier)


assert len(DRAFT_PANEL) == 48, len(DRAFT_PANEL)
assert all(len(by_tier(t)) == 12 for t in "ABCD"), {
    t: len(by_tier(t)) for t in "ABCD"
}
