"""Stage 02 — data-quality audits A-E (spec §2) -> results/audit.txt.

A  emission conditioning: ledger status by wave x intent (the pre-freeze
   pilot reported separately), completeness against prompts.csv, and the
   funnel all calls -> calls with a search action -> calls with a site:
   query, by tier x template.
B  outcome label: the scoring code quoted verbatim, the label counts it
   produces, and the resolution check that turns unreachable error domains
   into `nonexistent` (--resolve; cached in interim/resolution.json with its
   check date, reassignments written to interim/error_kind_resolved.csv).
C  independence: brands with >= 2 wrong observations (the effective sample
   for H2), the within-day replicate structure, and the clustering rule.
D  panel validity: the frozen panel, the freeze-time resolution check, and
   the human REVIEW TABLE of every stale and name-bearing-other domain per
   brand — entity attribution is a judgment call and is signed off by hand.
E  model drift: `model` by wave; any second model is flagged, never averaged.

Plus an exploratory table (clearly labelled): the third-party domains the
comparison template makes the model consult, which replicates 007's
comparison-trigger finding on this instrument.

Usage:
  uv run python experiments/008-brand-domain-knowledge/pipeline/02_audit.py [--resolve]
"""

from __future__ import annotations

import argparse
import inspect
import json
import socket
import sys
import urllib.error
import urllib.request
from datetime import date

import annotations
import pandas as pd
import scoring
from common import (
    LEDGER,
    MAX_WAVE,
    PANEL,
    PROMPTS_CSV,
    RESOLUTION_JSON,
    RESOLVED_CSV,
    RESOLVED_ERROR_KINDS,
    STUDY_INTENTS,
    SYNTHETIC_WORLDS,
    interim_dir,
    load_observations,
    load_responses,
    results_dir,
)

from aeo_research.dataforseo import Ledger

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
)
TIMEOUT_S = 8


def h(out: list[str], title: str) -> None:
    out.append(f"\n{title}\n{'-' * len(title)}")


# ------------------------------------------------------------------ A


def audit_a(calls: pd.DataFrame, out: list[str]) -> None:
    h(out, "## Audit A — emission conditioning and collection completeness")
    if LEDGER.exists():
        ledger = pd.DataFrame(Ledger(LEDGER).records())
        ledger = ledger.drop_duplicates(subset=["intent", "item_id", "wave"], keep="last")
        pilot = ledger[~ledger["intent"].isin(STUDY_INTENTS)]
        study = ledger[ledger["intent"].isin(STUDY_INTENTS)]
        out.append("Ledger status by wave x intent (study waves only):")
        out.append(study.groupby(["wave", "intent", "status"]).size().to_string())
        out.append(
            f"\nPre-freeze pilot (wave 0, intent 'pilot'): {len(pilot)} calls, "
            f"status {pilot['status'].value_counts().to_dict()} — reported here "
            "only; excluded from every study frame (spec §8b/§8c)."
        )
        failed = study[study["status"] != "collected"]
        out.append(f"Non-collected study rows: {len(failed)}"
                   + (f" ({failed['item_id'].tolist()})" if len(failed) else ""))
    else:
        out.append("(no ledger — synthetic frame)")

    prompts = pd.read_csv(PROMPTS_CSV)
    expected = prompts.groupby("intent").size().to_dict()
    out.append(f"\nprompts.csv items per intent: {expected}")
    got = calls.groupby(["intent", "wave"]).size().unstack(fill_value=0)
    out.append("Collected calls per intent x wave (expect 96 per cell that ran):")
    out.append(got.to_string())
    waves = sorted(calls["wave"].unique())
    missing = [
        f"core wave {w}" for w in range(1, MAX_WAVE + 1)
        if w not in waves
    ]
    out.append(
        f"Waves present: {waves}. "
        + (f"Not yet collected: {missing} (re-run after they land)."
           if missing else "All 10 waves present.")
    )
    for intent, items in expected.items():
        for wave in waves:
            n = int(((calls["intent"] == intent) & (calls["wave"] == wave)).sum())
            if n and n != items:
                out.append(f"  ** incomplete: {intent} wave {wave} has {n}/{items} **")

    out.append("\nEmission funnel by tier x template (all calls -> >=1 search "
               "action -> >=1 site: query -> >=1 BRAND-ATTRIBUTABLE site: query):")
    funnel = calls.assign(searched=(calls["n_search_actions"] > 0).astype(int)).groupby(
        ["tier", "template"]
    ).agg(calls=("item_id", "size"), with_search=("searched", "sum"),
          with_site=("emitted_site_query", "sum"),
          with_brand_site=("emitted_brand_site_query", "sum"))
    funnel["site_rate"] = (funnel["with_site"] / funnel["calls"]).round(4)
    funnel["brand_site_rate"] = (funnel["with_brand_site"] / funnel["calls"]).round(4)
    out.append(funnel.to_string())
    out.append(
        "\nThe analysis set conditions on emission (spec §1): every claim reads "
        "'when the model consulted a site directly', never 'the model believes'."
        " The fourth stage conditions further on the consultation being ABOUT "
        "the asked brand — a comparison prompt that only ever opens "
        "competitors' sites made no claim about the brand's domain."
    )
    only_third = calls[(calls["emitted_site_query"] == 1)
                       & (calls["emitted_brand_site_query"] == 0)]
    out.append(
        f"\nCalls whose site: searches named ONLY third-party sites "
        f"({len(only_third)}) — non-emitting for the primary outcome:"
    )
    out.append(
        only_third[["item_id", "tier", "template", "wave", "intent",
                    "first_search_domain_any"]].to_string(index=False)
        if len(only_third) else "(none)"
    )
    no_site = calls[calls["emitted_site_query"] == 0]
    if len(no_site):
        out.append(f"\nCalls with no site: query ({len(no_site)}):")
        out.append(no_site[["item_id", "tier", "template", "wave", "intent"]].to_string(index=False))
    malformed = int(calls["n_malformed_site_tokens"].sum())
    out.append(
        f"\nMalformed site: tokens (operator typed with no host, e.g. "
        f"'site:productguide?'): {malformed} — dropped before scoring."
    )


# ------------------------------------------------------------------ B


def _reach(host: str) -> tuple[bool, str]:
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return False, f"dns: {e.strerror or e}"
    last = "no response"
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(
            f"https://{host}/", headers={"User-Agent": UA}, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return True, f"http {resp.status}"
        except urllib.error.HTTPError as e:
            # A 403/404/500 is still a live host — the domain exists.
            return True, f"http {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = str(e)[:120]
    return False, f"connect: {last}"


def resolve_domain(domain: str, observed_host: str = "") -> dict:
    """DNS + HTTPS reachability for one registered domain.

    An apex that does not resolve is not automatically a dead domain: Meta
    consults investor.atmeta.com while atmeta.com itself has no A record. So
    when the apex fails, the most-consulted observed HOST is checked too, and
    `nonexistent` is assigned only when both fail.
    """
    checked = date.today().isoformat()
    ok, detail = _reach(domain)
    host_checked = domain
    if not ok and observed_host and observed_host != domain:
        ok_host, detail_host = _reach(observed_host)
        if ok_host:
            ok, detail, host_checked = True, f"apex {detail}; {detail_host}", observed_host
        else:
            detail = f"apex {detail}; {observed_host} {detail_host}"
    return {"resolves": ok, "detail": detail, "host_checked": host_checked,
            "checked_on": checked}


def audit_b(obs: pd.DataFrame, out: list[str], do_resolve: bool) -> None:
    h(out, "## Audit B — outcome label (the scoring code, quoted)")
    out.append(inspect.getdoc(scoring) or "")
    for fn in (scoring.BrandScorer.label, scoring.BrandScorer.error_kind,
               scoring.scorer_for, scoring.search_queries, scoring.site_hosts):
        out.append("\n" + inspect.getsource(fn).rstrip())

    out.append("\nLabel counts (all site: observations):")
    out.append(pd.crosstab(obs["tier"], obs["label"]).to_string())
    out.append("\nError kinds by tier:")
    out.append(pd.crosstab(obs["tier"], obs["error_kind"]).to_string())
    out.append("\nError kinds by template:")
    out.append(pd.crosstab(obs["template"], obs["error_kind"]).to_string())

    candidates = sorted(
        obs.loc[obs["error_kind"].isin(RESOLVED_ERROR_KINDS), "registered_domain"].unique()
    )
    cache = json.loads(RESOLUTION_JSON.read_text()) if RESOLUTION_JSON.exists() else {}
    if do_resolve:
        for domain in candidates:
            if domain not in cache:
                hosts = obs.loc[obs["registered_domain"] == domain, "host"]
                cache[domain] = resolve_domain(domain, str(hosts.mode().iat[0]))
                print(f"  resolved {domain}: {cache[domain]['detail']}")
        RESOLUTION_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESOLUTION_JSON.write_text(json.dumps(cache, indent=1, sort_keys=True))

    rows = []
    for domain in candidates:
        hit = cache.get(domain)
        counts = obs[obs["registered_domain"] == domain]
        rows.append({
            "registered_domain": domain,
            "observed_error_kind": counts["error_kind"].mode().iat[0],
            "n_observations": len(counts),
            "brands": "|".join(sorted(counts["brand"].unique())),
            "checked_on": hit["checked_on"] if hit else "",
            "host_checked": hit.get("host_checked", "") if hit else "",
            "check_detail": hit["detail"] if hit else "unchecked",
            "resolved_error_kind": (
                "nonexistent" if hit and not hit["resolves"]
                else counts["error_kind"].mode().iat[0]
            ),
        })
    table = pd.DataFrame(rows)
    if not table.empty:
        RESOLVED_CSV.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(RESOLVED_CSV, index=False)
    out.append(
        f"\nResolution check ({'live' if do_resolve else 'cache only — re-run with --resolve'}), "
        f"{len(candidates)} distinct stale / guess / name-bearing domains. "
        "Unreachable domains are reassigned to `nonexistent` by 03_model via "
        f"{RESOLVED_CSV.name}; the interim frames are never rewritten."
    )
    out.append(table.to_string(index=False) if not table.empty else "(no error domains)")


# ------------------------------------------------------------------ C


def audit_c(calls: pd.DataFrame, obs: pd.DataFrame, out: list[str]) -> None:
    h(out, "## Audit C — independence, clustering, and the effective sample")
    own = obs[(obs["label"] != "correct") & (obs["error_kind"] != "third_party")]
    per_brand = own.groupby(["brand", "tier"]).size().sort_values(ascending=False)
    out.append("Own-domain wrong observations per brand (observation level):")
    out.append(per_brand[per_brand > 0].to_string() if len(per_brand) else "(none)")
    out.append(
        f"\nBrands with >= 2 wrong observations (observation level): "
        f"{int((per_brand >= 2).sum())} of {calls['brand'].nunique()}"
    )
    first = calls[(calls["first_site_own_error"] == 1)]
    per_brand_call = first.groupby("brand").size()
    out.append(
        f"Brands with >= 2 wrong observations (call level, first site: query): "
        f"{int((per_brand_call >= 2).sum())}"
    )
    out.append(
        "\nThis count IS the effective sample for H2 (spec §2 Audit C). Below 3 "
        "brands the repeat-structure test is reported INCONCLUSIVE rather than "
        "given a verdict."
    )
    wave1 = calls[calls["wave"] == 1]
    pairs = (
        wave1.groupby(["brand", "template"])["replicate"].nunique().map(lambda n: n * (n - 1) // 2)
    )
    out.append(
        f"\nWithin-day replicate structure (wave 1, spec §7): "
        f"{int(pairs.sum())} within-day pairs over {len(pairs)} brand x template items "
        f"({wave1['replicate'].nunique()} slots per item)."
    )
    out.append(
        f"Day-over-day chains: {calls['wave'].nunique()} waves x "
        f"{calls['brand'].nunique()} brands x 2 templates on the core series."
    )
    out.append(
        "\nEvery rate in stage 03 that pools calls clusters on brand (brands are "
        "the independent units; replicates and waves within a brand are "
        "correlated by design)."
    )


# ------------------------------------------------------------------ D


def audit_d(obs: pd.DataFrame, out: list[str]) -> None:
    h(out, "## Audit D — panel validity (frozen instrument)")
    out.append(
        "The panel resolved and was corrected at freeze by "
        "`harness/verify_panel.py` (spec §8c): two dead tier-B brands replaced "
        "(Tome -> Granola, Height -> Amie), Paymo's canonical corrected to "
        "paymoapp.com (paymo.biz redirects there, paymo.com is dead — a natural "
        "morphological-guess trap), and Gamma/GoTo/Meta's scripted-fetch 403/400 "
        "responses recorded as WAF behaviour with the domains verified by hand. "
        "Nothing in brands.py has changed since; it is part of the frozen "
        "instrument."
    )
    panel = pd.DataFrame([
        {"brand": b.canonical, "tier": b.tier, "true_domain": b.true_domain,
         "old_domains": "|".join(b.old_domains), "expected_guess": "|".join(b.expected_guess),
         "domain_guessable": b.domain_guessable, "ambiguity": b.ambiguity[:70]}
        for b in PANEL
    ])
    out.append("\n" + panel.to_string(index=False))

    out.append(
        "\nREVIEW TABLE — entity attribution, for human sign-off. Every stale, "
        "name-bearing-other and morphological-guess domain the model consulted, "
        "per brand, with counts and the template that produced it. These are judgment calls the "
        "pipeline must NOT make on its own (atmeta.com is Meta's own investor "
        "domain; playstation.com is Sony's own product domain; both are scored "
        "name_bearing_other, which is not the same as an error about the brand's "
        "canonical domain). Annotate by hand before the write-up."
    )
    review = obs[obs["error_kind"].isin(RESOLVED_ERROR_KINDS)]
    if review.empty:
        out.append("(no stale, name-bearing or guess observations)")
        return
    table = (
        review.groupby(["brand", "tier", "error_kind", "registered_domain", "template"])
        .size()
        .rename("n")
        .reset_index()
        .sort_values(["tier", "brand", "n"], ascending=[True, True, False])
    )
    out.append(table.to_string(index=False))

    out.append(
        f"\nSIGNED ATTRIBUTION — {annotations.SIGNED_BY}, {annotations.SIGNED_ON} "
        f"({annotations.SIGNOFF_DOC}). A domain carrying the brand's name may be "
        "the brand's OWN property (a product, regional, developer or investor "
        "site) or a different company that shares the name; the pipeline cannot "
        "tell which, so a person ruled on each and the rulings are frozen in "
        "pipeline/annotations.py. The primary outcome is NOT changed by them — "
        "they enter as the H3 split, robustness (f), and the genuinely-wrong "
        "counts."
    )
    signed = pd.DataFrame(annotations.signed_rows())
    counts = (
        obs[obs["error_kind"] == "name_bearing_other"]
        .groupby(["brand", "registered_domain"]).size().rename("n")
    )
    signed["n_observations"] = [
        int(counts.get((r.brand, r.registered_domain), 0)) for r in signed.itertuples()
    ]
    out.append(signed.to_string(index=False))
    unseen = signed[signed["n_observations"] == 0]
    if not unseen.empty:
        out.append(
            "  note: signed rows with no observations in this frame "
            f"({', '.join(unseen['registered_domain'])}) — the sign-off predates "
            "a re-scoring, or those domains stopped appearing."
        )

    name_bearing = obs[obs["error_kind"] == "name_bearing_other"]
    unreviewed = (
        name_bearing[name_bearing["attribution"] == annotations.UNREVIEWED]
        .groupby(["brand", "registered_domain", "tier"]).size().rename("n").reset_index()
    )
    if unreviewed.empty:
        out.append(
            "\n  ACTION ITEMS: none — every name-bearing domain in this frame "
            "carries a signed attribution."
        )
    else:
        out.append(
            f"\n  ** {len(unreviewed)} UNREVIEWED NAME-BEARING DOMAIN(S) — AUDIT D "
            "IS REOPENED. These reached the data after the sign-off. They count "
            "as GENUINELY WRONG everywhere until a reviewer rules on them; add "
            "each to AUDIT_D_ATTRIBUTION in pipeline/annotations.py, extend "
            f"{annotations.SIGNOFF_DOC}, and re-date the signature. **"
        )
        out.append(unreviewed.to_string(index=False).upper())


# ------------------------------------------------------------------ E


def audit_e(calls: pd.DataFrame, out: list[str]) -> None:
    h(out, "## Audit E — model drift")
    table = calls.groupby(["wave", "model"]).size().unstack(fill_value=0)
    out.append(table.to_string())
    models = sorted(calls["model"].dropna().unique())
    if len(models) > 1:
        out.append(
            f"\n** {len(models)} models in the study frame: {models}. A swap is a "
            "documented natural experiment (spec §2 Audit E) — stage 03 must "
            "report per-model strata, never average over the swap. **"
        )
    else:
        out.append(f"\nSingle model across every wave: {models[0] if models else 'n/a'}.")


# --------------------------------------------------------- exploratory


def exploratory(obs: pd.DataFrame, out: list[str]) -> None:
    h(out, "## EXPLORATORY (not pre-registered) — third-party consultations on p2")
    out.append(
        "The comparison template makes the model consult other companies' sites "
        "by design; these are not errors about the asked brand. Reported because "
        "it replicates experiment 007's comparison-trigger finding on a second "
        "instrument. Top 5 third-party domains per brand, comparison prompts only."
    )
    third = obs[(obs["error_kind"] == "third_party") & (obs["template"] == "p2")]
    if third.empty:
        out.append("(none)")
        return
    counts = third.groupby(["tier", "brand", "registered_domain"]).size().rename("n")
    top = (
        counts.reset_index()
        .sort_values(["tier", "brand", "n"], ascending=[True, True, False])
        .groupby("brand", sort=False)
        .head(5)
    )
    out.append(top.to_string(index=False))
    p2 = obs[obs["template"] == "p2"]
    share = (
        p2.assign(tp=(p2["error_kind"] == "third_party").astype(int))
        .groupby("tier")["tp"].mean().round(3).to_dict()
    )
    out.append(f"\nShare of p2 site: observations that are third-party, by tier: {share}")


# --------------------------------------------------------- deviations


def deviations(out: list[str]) -> None:
    h(out, "## Deviations / analysis-time definitions")
    out.append(
        "The frozen spec fixes the hypotheses and decision rules; these are the "
        "definitions it left open, resolved at analysis time and recorded here.\n"
        "\n"
        "1. `other_real` is split into `name_bearing_other` and `third_party`.\n"
        "   Spec §2 Audit B names four error kinds. In the data the 'other real "
        "domain' bucket holds two very different things: domains that carry the "
        "brand's own name (atmeta.com, gotomypc.com, boseprofessional.com — the "
        "brand's own orbit) and domains that do not (clickup.com consulted while "
        "answering about Asana — a competitor the comparison template invites). "
        "Only the first is a claim about the asked brand's domain, so H2/H3 "
        "analyse own-domain errors and exclude third_party. The frozen four-way "
        "labels stay derivable: name_bearing_other + third_party = other_real.\n"
        "\n"
        "2. The primary call-level outcome is the first BRAND-ATTRIBUTABLE site: "
        "query. Spec §5 defines it as 'the domain of a site: fan-out naming the "
        "brand's prompt-run', and a third-party site: query does not name the "
        "asked brand at all: the comparison template makes the model open on a "
        "competitor by design (adyen.com while answering about Stripe, "
        "vrbo.com about Airbnb), which would otherwise be scored as a wrong "
        "domain and would make the template, not the model's belief, the thing "
        "being measured. So the outcome is the first site: query whose target "
        "is about this brand (correct / stale / morphological_guess / "
        "name_bearing_other); calls with only third-party site: queries get "
        "first_site_label = 'none' and are NON-EMITTING for this outcome — "
        "reported as the fourth stage of the H1 funnel, by tier x template. "
        "The raw first site: query of any kind survives as "
        "first_search_domain_any (released) and as robustness (e); "
        "`any_wrong_incl_stale` — any non-correct, non-third-party site: query "
        "anywhere in the call — remains robustness (a).\n"
        "\n"
        "3. H2 IS NOT IDENTIFIABLE AS PRE-REGISTERED, and no verdict is reported "
        "for it. Spec §4 asks whether the observed same-wrong-domain agreement "
        "exceeds 'the independence baseline ... expected agreement Sigma p^2'. "
        "Under any model where a call's wrong domain is drawn independently "
        "from the brand's own distribution — which is precisely what per-run "
        "guessing means — the observed pairwise agreement IS an unbiased "
        "estimator of Sigma p^2, and the plug-in Sigma p_hat^2 is its biased "
        "twin, always >= it. The contrast therefore has expectation zero under "
        "the guessing hypothesis and is bounded above by zero in the plug-in "
        "form: it cannot separate the mechanisms on any data. Stage 03 prints "
        "the observed agreement and the plug-in for transparency, states NOT "
        "IDENTIFIABLE, and rests the mechanism claim on the pre-registered H3 "
        "(error content) and H4 (temporal structure). Two supporting analyses "
        "are reported and labelled: an EXPLORATORY permutation of wrong-domain "
        "labels across brands (which tests brand-specificity — near-tautological, "
        "since a per-run guesser generating from the brand's own name is also "
        "brand-specific), and a POST-HOC sensitivity whose baseline is EXTERNAL "
        "to the observations: uniform choice over the brand's frozen candidate "
        "set (old_domains + expected_guess minus the truth, K domains), which "
        "predicts agreement 1/K under guessing and 1 under a stored "
        "association. That one is identifying, but only where K >= 2; the "
        "frozen panel gives most tier-C brands K = 1 (GoTo's only candidate is "
        "logmein.com), where the two mechanisms make the SAME prediction and "
        "the brand is reported as not separable by design. The 0.25 / 0.05 "
        "bands are unchanged and were never widened.\n"
        "\n"
        "4. H4 gains an identifying companion (still temporal, still "
        "pre-registered in substance): the agreement of the WRONG DOMAIN "
        "within a day (wave-1 replicate pairs) versus across days (consecutive "
        "core waves), over pairs where BOTH calls were wrong. A stored "
        "association predicts both near 1 and equal; a per-run guess predicts "
        "both near 1/K. Reported pooled and restricted to K >= 2 brands, with "
        "brand-clustered CIs and pair counts.\n"
        "\n"
        "5. H4's transition test is reported twice: pooled over all brands, and restricted to "
        "brands that erred at least once (composition-matched). Pooling all "
        "brands puts the never-erring brands entirely into the "
        "P(correct | correct) arm, which inflates the gap for reasons that have "
        "nothing to do with self-correction; the matched version is the one to "
        "read.\n"
        "\n"
        "6. `nonexistent` is assigned only by this stage's resolution check, "
        "with its date, and only to stale / morphological-guess / name-bearing "
        "domains. It is written to interim/error_kind_resolved.csv and merged by "
        "stage 03 rather than rewritten into the interim frames, so the scored "
        "frames stay reproducible from the raw responses alone.\n"
        "\n"
        "7. Name-bearing matching uses name tokens of 3+ characters, so tier-C "
        "brand 'X' contributes only its 'Twitter' alias — a one-character token "
        "would make every domain containing an x name-bearing.\n"
        "\n"
        "8. Audit D's entity attribution is applied as a LABELLED ROBUSTNESS "
        "LAYER, never to the primary. A consulted domain that carries the "
        "brand's name may be the brand's own property (atmeta.com is Meta's "
        "investor site, sony.co.jp Sony's Japanese site) or a different "
        "company that shares the name (amieapp.com is not Amie). No rule the "
        "pipeline could apply separates those, so a person ruled on each of "
        "the 8 name-bearing domains in waves 1-9 and the rulings are frozen, "
        f"dated and signed in pipeline/annotations.py ({annotations.SIGNED_BY}, "
        f"{annotations.SIGNED_ON}; prose record in {annotations.SIGNOFF_DOC}). "
        "They surface as the `attribution` column, the H3 error-kind split, "
        "robustness (f) (own-property first commitments recounted as correct; "
        "Amie stays wrong) and the genuinely-wrong counts. first_site_label is "
        "untouched: a name-bearing consultation is still not the canonical "
        "domain. A name-bearing domain with no signed ruling attributes as "
        "`unreviewed`, counts as genuinely wrong, and is printed in capitals "
        "as an Audit D action item — so a wave-10 domain reopens the review "
        "rather than silently passing.\n"
        "\n"
        "9. Release column names avoid the substrings the release gate forbids "
        "(`emitted_site_search`, not `emitted_site_query`); see 05_release.py. "
        "`Datasheet` grew a `unit` field (default 'citations', unchanged for "
        "every other study) so this dataset's row count reads 'calls evaluated "
        "in this study' — the only edit outside this experiment."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", choices=SYNTHETIC_WORLDS, default=None)
    ap.add_argument("--resolve", action="store_true",
                    help="do live HTTPS reachability checks (cached with their date)")
    a = ap.parse_args()

    calls = load_responses(synthetic=a.synthetic)
    obs = load_observations(synthetic=a.synthetic)
    if int(calls.get("synthetic", pd.Series([0])).max()) == 1:
        print(f"NOTE: auditing a SYNTHETIC frame ({a.synthetic})")

    out = [
        f"# Experiment 008 — data-quality audits{f' (SYNTHETIC/{a.synthetic})' if a.synthetic else ''}",
        f"generated {date.today().isoformat()}; {len(calls)} study calls, "
        f"{len(obs)} site: observations, waves {calls['wave'].min()}-{calls['wave'].max()}",
    ]
    audit_a(calls, out)
    audit_b(obs, out, a.resolve)
    audit_c(calls, obs, out)
    audit_d(obs, out)
    audit_e(calls, out)
    exploratory(obs, out)
    deviations(out)

    results = results_dir(a.synthetic)
    results.mkdir(parents=True, exist_ok=True)
    path = results / "audit.txt"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path}")
    if not a.synthetic:
        print(f"interim: {interim_dir(None)}")


if __name__ == "__main__":
    sys.exit(main())
