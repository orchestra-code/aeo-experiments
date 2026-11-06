"""Stage 02: data-quality audits (spec §2) -> results/audit_report.md and results/audit.json.

A  degenerate responses, per arm x wave: missing answers, UI resubmissions, failed tasks
   and the app's error messages, failed API attempts, empty answers, answers with no
   search, no citations or no extracted brands, replies that only ask a question back, API
   answers whose model is not the pin, UI answers whose model label is not the expected
   one (R8), and Gemini app markup (present, and any left after stripping). The no-search
   rule: more than 30% of an arm's answers with no search makes its domain results
   INCONCLUSIVE. ``gm_ui`` search depth is not observable; "searched" there means sources
   were reported. Flagged answers are listed by (arm, item, wave) on stdout only, for a
   person to read, as in 011.
   Lexicon coverage (spec §5): per arm x wave, the share of Haiku names the lexicon's own
   matcher cannot place, against the 2% limit; "not run" until ``01_frame.py --haiku``.
B  what the labels mean, with the code that defines each one.
C  independence: prompts, categories, waves and the pair counts per condition.
D  extraction validity is scored separately (a 30-answer arm-blind sheet, signed by Jim
   Wrubel); 03_model's gate reads ``results/audit_d_score.json``.

Nothing here computes a hypothesis metric. Outputs hold aggregates only: no brand, domain,
prompt, answer or query text.

Usage (repo root):
  uv run python experiments/004-api-vs-ui/pipeline/02_audit.py
  uv run python .../02_audit.py --synthetic planted
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

import common
import pandas as pd
from common import API_ARMS, NO_SEARCH_MAX, PLATFORMS, UI_ARMS, Mode, m011, md_table

COVERAGE_MAX_UNPLACED = 0.02  # spec §5 lexicon protocol


def audit_a(df: pd.DataFrame, meta: dict) -> tuple[pd.DataFrame, list[str]]:
    tallies = pd.DataFrame(meta.get("tallies", []))
    missing = Counter((m["arm"], int(m["wave"])) for m in meta.get("missing", []))
    rows, flagged = [], []
    for arm in common.ALL_ARMS:
        for wave in meta["waves"]:
            g = df[(df["arm"] == arm) & (df["wave"] == wave)]
            t = tallies[(tallies["arm"] == arm) & (tallies["wave"] == wave)] if len(tallies) else tallies
            is_ui = arm in UI_ARMS
            row = {"arm": arm, "wave": int(wave), "answers": len(g), "missing": missing[(arm, wave)]}
            if is_ui:
                subs = int(t["submissions"].sum()) if len(t) else 0
                row |= {"submissions": subs, "resubmissions": subs - int((t["submissions"] > 0).sum())
                        if len(t) else 0,
                        "failed": int(t["failed"].sum()) if len(t) else 0,
                        "error_answers": int(t["error_answers"].sum()) if len(t) else 0,
                        "off_model": int((~g["model_ok"].astype(bool)).sum())}
            else:
                row |= {"submissions": int(t["attempts"].sum()) if len(t) else 0,
                        "resubmissions": int(t["attempts"].sum() - len(t)) if len(t) else 0,
                        "failed": int(t["failed"].sum()) if len(t) else 0,
                        "error_answers": int(t["empty_answers"].sum()) if len(t) else 0,
                        "off_model": int((~g["model_ok"].astype(bool)).sum())}
            row |= {"empty": int(g["empty"].sum()), "no_search": int((~g["searched"].astype(bool)).sum()),
                    "no_citations": int((g["n_cited"] == 0).sum()), "no_brands": int((g["n_brands"] == 0).sum()),
                    "question_only": int(g["question_only"].astype(bool).sum()),
                    "markup": int((g["markup_tags"] > 0).sum()), "markup_left": int((g["markup_left"] > 0).sum())}
            rows.append(row)
            for r in g.itertuples():
                why = [w for w, hit in (("empty", r.empty), ("no brands", r.n_brands == 0),
                                        ("question only", r.question_only),
                                        ("model not the pin", r.arm in API_ARMS and not r.model_ok),
                                        ("app markup left after stripping", r.markup_left > 0)) if hit]
                if why:
                    flagged.append(f"{r.arm} {r.item_id} w{r.wave}: {', '.join(why)}")
    return pd.DataFrame(rows), flagged


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (arm, wave), g in df.groupby(["arm", "wave"], sort=False):
        have = g["n_haiku_names"].notna()
        names = int(g.loc[have, "n_haiku_names"].sum())
        unplaced = int(g.loc[have, "n_unplaced"].sum())
        rows.append({"arm": arm, "wave": int(wave), "answers_with_names": int(have.sum()),
                     "answers": len(g), "haiku_names": names, "unplaced": unplaced,
                     "unplaced_share": unplaced / names if names else float("nan"),
                     "over_limit": bool(names and unplaced / names > COVERAGE_MAX_UNPLACED)})
    return common.arm_order(pd.DataFrame(rows))


AUDIT_B = """\
- **Brand named**: a lexicon alias match for the prompt's category in the answer text, with
  labelled source blocks, link targets and links whose text is a domain removed, in
  first-mention order (`common.extract`: 010's `extract_new` over 009's `lexicon_extract`).
  For `gm_ui` the Gemini app's follow-up, chip and media components are stripped first
  (`harness/answers.py`, `strip_app_markup`); R6 keeps them (`brands_markup`).
- **Cited**: DataForSEO `sources` plus inline links (UI), `url_citation` annotations
  (OpenAI), grounding chunks referenced by a support (Gemini API; the domain comes from the
  chunk's `web.domain` or `web.title`, since its URIs are redirect links).
- **Evaluated**: DataForSEO `search_results` (ChatGPT UI; `sources` where it has none),
  `web_search_call` sources and opened pages (OpenAI), every grounding chunk (Gemini API).
- **Searched**: API, at least one search call or query; UI, fan-out queries or sources
  reported (the Gemini app reports no queries).
- **An answer**: per (arm, prompt, wave), the UI task collected last whose text is not the
  app's error message (`answers.is_error_answer`), or the API attempt collected with the
  pinned model and a non-empty text (`exp004.api_attempt`, strict).
- **Question only**: no lexicon brand, at most 1,200 characters, and a question mark
  (`pilot_report.question_only`).

The instruments expose different fields, so domain results are descriptive."""


def audit_c(df: pd.DataFrame) -> list[str]:
    per_cat = df.groupby("category")["item_id"].nunique()
    lines = [f"{df['item_id'].nunique()} prompts in {df['category'].nunique()} categories "
             f"({dict(Counter(per_cat.tolist()))} prompts per category), waves "
             f"{sorted(int(w) for w in df['wave'].unique())}. Inference resamples prompts (the "
             "cluster); R5 resamples categories.", ""]
    rows = []
    for p, spec in PLATFORMS.items():
        sub = df[df["platform"] == p].reset_index(drop=True)
        pairs = m011.build_pairs(sub)
        counts = pairs["condition"].value_counts()
        for cond in [m011.within(spec.ref)] + [m011.cross(a, spec.ref) for a in spec.primary]:
            n = int(counts.get(cond, 0))
            per = pairs[pairs["condition"] == cond].groupby("cluster_i").size()
            rows.append({"platform": spec.label, "condition": cond, "pairs": n,
                         "prompts": int(per.size), "pairs_per_prompt_min": int(per.min()) if n else 0,
                         "pairs_per_prompt_max": int(per.max()) if n else 0})
    lines.append(md_table(pd.DataFrame(rows)))
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_mode_args(ap)
    a = ap.parse_args()
    mode: Mode = common.mode_from(a)
    df, meta = common.load_frame(mode)
    table, flagged = audit_a(df, meta)
    pooled = df.groupby("arm")["searched"].apply(lambda s: float((~s.astype(bool)).mean())).to_dict()
    inconclusive = sorted(arm for arm, rate in pooled.items() if rate > NO_SEARCH_MAX)
    cov = coverage(df)
    tag = f" (SYNTHETIC/{a.synthetic})" if a.synthetic else (" (PILOT)" if mode.pilot else "")
    out = [f"# Experiment 004: data-quality audits{tag}", "",
           f"{len(df)} answers in the frame; lexicon `{meta['lexicon']}` sha256 "
           f"`{meta['lexicon_sha256'][:12]}`. Aggregates only.", "",
           "## Audit A: degenerate responses, per arm x wave", "",
           "UI: `submissions` counts DataForSEO tasks, `failed` tasks DataForSEO failed and "
           "`error_answers` the app's error messages (both resubmitted the same day, at most 3 "
           "submissions). API: `submissions` counts attempts, `failed` failed calls and "
           "`error_answers` empty answers (both retried, at most 3 attempts). `off_model`: API "
           "answers not on the pin (none can count), UI answers whose label is not "
           f"{common.UI_MODEL_EXPECTED} (kept; R8 drops them).", "",
           md_table(table), "",
           "Pooled no-search rate per arm: "
           + ", ".join(f"`{k}` {v:.3f}" for k, v in sorted(pooled.items())) + ". Over the "
           f"{NO_SEARCH_MAX:.0%} limit (domain results INCONCLUSIVE): "
           + (", ".join(f"`{x}`" for x in inconclusive) or "none") + ".", "",
           f"Answers flagged for a person to read: {len(flagged)} (listed on stdout only).", "",
           "### Lexicon coverage (spec §5: no arm over 2% unplaced Haiku names)", ""]
    if cov["answers_with_names"].sum() == 0:
        out.append("Not run: no Haiku names cached yet (`01_frame.py --haiku`).")
    else:
        out += [md_table(cov), "", "Arms over the limit: "
                + (", ".join(f"`{r.arm}` w{r.wave}" for r in cov.itertuples() if r.over_limit) or "none")]
    out += ["", "## Audit B: what the labels mean", "", AUDIT_B, "",
            "## Audit C: independence", "", *audit_c(df), "",
            "## Audit D: extraction validity", "",
            "Scored separately: a 30-answer random spot check, arm-blind, stratified across the "
            "five arms, read by hand (precision at least 0.95, recall at least 0.90), signed by "
            "Jim Wrubel. 03_model refuses the real data until `results/audit_d_score.json` "
            "records a pass against the pinned lexicon."]
    res = mode.results
    res.mkdir(parents=True, exist_ok=True)
    (res / "audit_report.md").write_text("\n".join(out) + "\n")
    (res / "audit.json").write_text(json.dumps(common.jsonable({
        "audit_a": table.to_dict("records"), "no_search_rate": pooled,
        "domain_inconclusive": inconclusive, "flagged": len(flagged),
        "coverage": cov.to_dict("records")}), indent=1) + "\n")
    print("\n".join(out))
    print(f"\nwrote {res / 'audit_report.md'}")
    print(f"\nFlagged answers for a person to read (arm item wave), not in the report: {len(flagged)}")
    for f in flagged:
        print(f"  {f}")


if __name__ == "__main__":
    main()
