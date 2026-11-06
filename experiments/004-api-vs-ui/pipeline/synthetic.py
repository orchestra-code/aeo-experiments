"""Synthetic worlds for the dry run (spec §8 item 2), collected by the real wave driver.

Each world runs ``harness/run_wave.py`` for waves 1 to 3 with fake transports in place
of DataForSEO, OpenAI and Gemini: the driver's orders, ledgers, retries, resubmissions,
response files and cost guard all run as they would on a collection day, and nothing is
sent anywhere. The fake answers name made-up brands (``Zq<category><letter>``) from a fake
lexicon over 20 fake categories and 40 fake prompts, include a text marker, and are written
to ``data/interim/synthetic/<world>/raw/`` (gitignored).

Answer model. Each (platform, prompt) has a core shortlist of 7 brands from its
category's pool of 16. An answer keeps each core brand with probability 0.85 and adds up
to two others from the pool, so two answers from one process overlap at about 0.7. An
arm planted EQUIVALENT draws from the UI's core; one planted DIVERGENT draws from a core
that swaps 4 of the 7, so its true gap is about +0.3.

Worlds:

- ``planted``: ``cg_api_low`` and ``gm_api_plain`` equivalent, ``cg_api_plain`` divergent.
- ``planted_flip``: both ChatGPT arms equivalent, ``gm_api_plain`` divergent.
- ``broken_join``: as ``planted``, but every API answer is drawn for a prompt 10 places
  away (another category), so the prompt join is broken and H_pos must fail.

Planted bookkeeping, every world: a Gemini app error answer (resubmitted), a failed
ChatGPT UI task (resubmitted), an OpenAI HTTP 500 (retried), a Gemini API prompt that
fails all 3 attempts (missing), a question-only API answer, one UI answer per platform
with an unexpected model label (R8), Gemini app follow-up chips naming an extra brand on
most ``gm_ui`` answers (R6), and no grounding on 45% of ``gm_api_plain`` answers (over
Audit A's no-search limit).

Usage (repo root):
    uv run python experiments/004-api-vs-ui/pipeline/synthetic.py --world planted
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import threading
from pathlib import Path

import common
import numpy as np
from common import SYNTH_ANSWER_MARK, SYNTH_BRAND_PREFIX, SYNTH_QUERY_MARK, Mode

sys.path.insert(0, str(common.HARNESS))
import collect_gemini  # noqa: E402
import collect_openai  # noqa: E402
import exp004  # noqa: E402
import run_wave  # noqa: E402
import ui  # noqa: E402

from aeo_research.dataforseo import Submitted, TaskOutcome  # noqa: E402

N_CATS, POOL, CORE, SWAP = 20, 16, 7, 4
KEEP_P, EXTRA_DRAWS, EXTRA_P = 0.85, 2, 0.5
ITEMS = [f"b2b_{k:02d}" for k in range(1, 41)]
CATEGORY = {item: f"cat{(k - 1) // 2 + 1:02d}" for k, item in enumerate(ITEMS, start=1)}
DIVERGENT = {"planted": {"cg_api_plain"}, "planted_flip": {"gm_api_plain"},
             "broken_join": {"cg_api_plain"}}
PLATFORM_OF_ARM = {a: exp004.ARMS[a].platform for a in exp004.STUDY_ARMS}

#: Planted bookkeeping: (arm, item, wave).
ERROR_ANSWER = ("gm_ui", "b2b_05", 1)       # first submission is the app's error message
FAILED_TASK = ("cg_ui", "b2b_11", 2)        # first submission fails at DataForSEO
HTTP_500 = ("cg_api_plain", "b2b_20", 3)    # first attempt is a server error
ALWAYS_FAILS = ("gm_api_plain", "b2b_33", 2)  # every attempt fails: one answer missing
QUESTION_BACK = ("cg_api_low", "b2b_02", 1)
ODD_MODEL = {("cg_ui", "b2b_07", 3): "gpt-6-thinking", ("gm_ui", "b2b_09", 2): "3.6 Flash"}
NO_GROUNDING_SHARE = 0.45


def rng_for(*key) -> np.random.Generator:
    digest = hashlib.sha256("|".join(map(str, key)).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def pool(cat: str) -> list[str]:
    return [f"{SYNTH_BRAND_PREFIX}{cat}{chr(97 + i)}" for i in range(POOL)]


def core(world: str, platform: str, item: str, divergent: bool) -> list[str]:
    names = pool(CATEGORY[item])
    base = list(rng_for(world, platform, item, "core").choice(names, CORE, replace=False))
    if not divergent:
        return base
    rest = [n for n in names if n not in base]
    rng = rng_for(world, platform, item, "swap")
    out = list(base)
    for pos, new in zip(rng.choice(CORE, SWAP, replace=False), rng.choice(rest, SWAP, replace=False),
                        strict=True):
        out[pos] = new
    return out


def answer_brands(world: str, arm: str, item: str, wave: int) -> list[str]:
    platform = PLATFORM_OF_ARM[arm]
    source = item
    if world == "broken_join" and arm in exp004.STUDY_API_ARMS:
        source = ITEMS[(ITEMS.index(item) + 10) % len(ITEMS)]  # another category
    base = core(world, platform, source, arm in DIVERGENT[world])
    rng = rng_for(world, arm, item, wave, "answer")
    kept = [b for b in base if rng.random() < KEEP_P]
    others = [n for n in pool(CATEGORY[source]) if n not in base]
    for _ in range(EXTRA_DRAWS):
        if rng.random() < EXTRA_P:
            kept.insert(int(rng.integers(0, len(kept) + 1)), str(rng.choice(others)))
    return list(dict.fromkeys(kept))


def answer_text(brands: list[str], cat: str) -> str:
    lines = [f"{SYNTH_ANSWER_MARK} Here is a shortlist for {cat} tools.", ""]
    for n, b in enumerate(brands, start=1):
        lines.append(f"{n}. **{b}**: suits small teams ([{b.lower()}.example](https://{b.lower()}.example/p)).")
    lines += ["", "Pick the one that fits your budget."]
    return "\n".join(lines)


def chips(world: str, item: str, wave: int, brands: list[str]) -> str:
    """Gemini app follow-up markup naming a brand the answer does not (R6 sees it)."""
    rng = rng_for(world, "chips", item, wave)
    if rng.random() < 0.25:
        return ""
    extra = next((n for n in pool(CATEGORY[item]) if n not in brands), brands[0])
    if rng.random() < 0.5:
        return (f'\n\n<ElicitationsGroup message="Want more?">\n<Elicitation label="Compare {extra}" '
                f'query="{extra} pricing {SYNTH_QUERY_MARK}"/>\n<Elicitation label="Alternatives" '
                f'query="alternatives {SYNTH_QUERY_MARK}"/>\n</ElicitationsGroup>')
    return f'\n\n<FollowUp label="Tell me about {extra}" query="{extra} {SYNTH_QUERY_MARK}"/>'


def urls(brands: list[str]) -> list[str]:
    return [f"https://{b.lower()}.example/p" for b in brands] + ["https://reviews.example.org/list"]


# ---------------------------------------------------------------- fake transports


class World:
    def __init__(self, name: str):
        self.name = name
        self.wave = 0
        self.lock = threading.Lock()
        self.tasks: dict[str, tuple[str, str, int, int]] = {}
        self.submits: dict[tuple, int] = {}
        self.calls: dict[tuple, int] = {}

    # --- DataForSEO
    def post_tasks(self, _key, specs, *, platform="chatgpt", opener=None):
        out = []
        for spec in specs:
            item = re.search(r"b2b_\d\d", spec.keyword).group(0)
            wave = int(re.search(r"-w(\d+)$", spec.tag).group(1))
            with self.lock:
                k = (platform, item, wave)
                self.submits[k] = self.submits.get(k, 0) + 1
                task_id = f"synthetic-{platform}-{item}-w{wave}-{self.submits[k]}"
                self.tasks[task_id] = (platform, item, wave, self.submits[k])
            out.append(Submitted(task_id, spec.keyword, spec.tag, 0.0024, 20100))
        return out

    def get_task(self, _key, task_id, *, platform="chatgpt", opener=None):
        platform, item, wave, nth = self.tasks[task_id]
        arm = exp004.UI_ARM[platform]
        if (arm, item, wave) == FAILED_TASK and nth == 1:
            return TaskOutcome(task_id, "failed", 40501, "synthetic failure")
        if (arm, item, wave) == ERROR_ANSWER and nth == 1:
            return TaskOutcome(task_id, "done", 20000, "", {"model": "3.5 Flash-Lite",
                                                            "markdown": "Something went wrong."})
        brands = answer_brands(self.name, arm, item, wave)
        text = answer_text(brands, CATEGORY[item])
        model = ODD_MODEL.get((arm, item, wave), exp004.UI_MODEL_EXPECTED[arm])
        if platform == "gemini":
            text += chips(self.name, item, wave, brands)
            searched = rng_for(self.name, "gm_ui_search", item, wave).random() > 0.07
            result = {"model": model, "markdown": text,
                      "sources": [{"url": u} for u in urls(brands)] if searched else []}
        else:
            result = {"model": model, "markdown": text, "sources": [{"url": u} for u in urls(brands)],
                      "search_results": [{"url": u} for u in urls(brands)],
                      "fan_out_queries": [f"{SYNTH_QUERY_MARK} {CATEGORY[item]} tools", "pricing"]}
        return TaskOutcome(task_id, "done", 20000, "", result)

    # --- API
    def _attempt(self, arm: str, item: str) -> int:
        with self.lock:
            k = (arm, item, self.wave)
            self.calls[k] = self.calls.get(k, 0) + 1
            return self.calls[k]

    def openai_send(self, body: dict) -> exp004.HttpResult:
        arm = "cg_api_low" if "reasoning" in body else "cg_api_plain"
        item = re.search(r"b2b_\d\d", body["input"]).group(0)
        n = self._attempt(arm, item)
        if (arm, item, self.wave) == HTTP_500 and n == 1:
            return exp004.HttpResult(500, None, "HTTP 500: synthetic", 4)
        brands = answer_brands(self.name, arm, item, self.wave)
        text = answer_text(brands, CATEGORY[item])
        if (arm, item, self.wave) == QUESTION_BACK:
            text = f"{SYNTH_ANSWER_MARK} How large is your team, and what is your budget?"
            brands = []
        found = urls(brands)
        output = [{"type": "web_search_call",
                   "action": {"type": "search", "query": f"{SYNTH_QUERY_MARK} {CATEGORY[item]}",
                              "sources": [{"url": u} for u in found]}},
                  {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": [
                      {"type": "url_citation", "url": u} for u in found[:3]]}]}]
        effort = body.get("reasoning", {}).get("effort", "medium")
        return exp004.HttpResult(200, {"model": "gpt-6-luna-2026-10-07", "status": "completed",
                                       "reasoning": {"effort": effort}, "output": output,
                                       "usage": {"input_tokens": 20000, "output_tokens": 1500,
                                                 "input_tokens_details": {"cached_tokens": 0}}}, None, 1)

    def gemini_send(self, body: dict) -> exp004.HttpResult:
        arm = "gm_api_plain"
        item = re.search(r"b2b_\d\d", body["contents"][0]["parts"][0]["text"]).group(0)
        self._attempt(arm, item)
        if (arm, item, self.wave) == ALWAYS_FAILS:
            return exp004.HttpResult(503, None, "HTTP 503: synthetic", 4)
        brands = answer_brands(self.name, arm, item, self.wave)
        cand = {"content": {"parts": [{"text": answer_text(brands, CATEGORY[item])}]},
                "finishReason": "STOP"}
        if rng_for(self.name, "grounding", item, self.wave).random() >= NO_GROUNDING_SHARE:
            cand["groundingMetadata"] = {
                "webSearchQueries": [f"{SYNTH_QUERY_MARK} {CATEGORY[item]}"],
                "groundingChunks": [{"web": {"uri": "https://vertexaisearch.cloud.google.com/"
                                                    f"grounding-api-redirect/{i}",
                                             "title": u.split("/")[2]}}
                                    for i, u in enumerate(urls(brands))],
                "groundingSupports": [{"groundingChunkIndices": [0, 1]}]}
        return exp004.HttpResult(200, {"modelVersion": exp004.GEMINI_MODEL, "candidates": [cand],
                                       "usageMetadata": {"promptTokenCount": 100,
                                                         "candidatesTokenCount": 1200}}, None, 1)


# ---------------------------------------------------------------- build


def write_inputs(raw: Path) -> Path:
    raw.mkdir(parents=True, exist_ok=True)
    prompts = raw / "prompts.csv"
    with prompts.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "intent", "text", "category", "prompt_intent"])
        for item in ITEMS:
            w.writerow([item, "b2b", f"Synthetic buyer prompt {item} about {CATEGORY[item]} tools.",
                        CATEGORY[item], "shortlist"])
    with (raw / "lexicon.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical", "aliases", "category", "decision", "match"])
        for k in range(1, N_CATS + 1):
            for name in pool(f"cat{k:02d}"):
                w.writerow([name, name, f"cat{k:02d}", "keep", "ci"])
    (raw / "low_effort_probe.json").write_text(json.dumps({"accepted": "none", "cost_usd": 0.0}))
    return prompts


def build_world(name: str, quiet: bool = True) -> Path:
    mode = Mode(synthetic=name)
    if mode.interim.exists():
        shutil.rmtree(mode.interim)
    raw = mode.raw
    prompts = write_inputs(raw)
    world = World(name)
    original_load = exp004.load_prompts
    exp004.RAW = raw
    exp004.load_prompts = lambda path=None: original_load(prompts)
    collect_openai.PROBE_PATH = raw / "low_effort_probe.json"
    collect_openai.send = world.openai_send
    collect_gemini.send = world.gemini_send
    ui._key = lambda: "synthetic"
    ui.post_tasks = world.post_tasks
    ui.get_task = world.get_task
    ui.POLL_SLEEP_S = 0
    if quiet:
        run_wave.print = lambda *a, **k: None  # the log file still gets every line
    for wave in exp004.STUDY_WAVES:
        world.wave = wave
        run_wave.run_wave(wave, any_time=True, any_day=True, ui_wait_s=0, ui_max_wait_s=0)
    exp004.load_prompts = original_load
    return raw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--world", choices=common.SYNTHETIC_WORLDS, required=True)
    a = ap.parse_args()
    raw = build_world(a.world)
    state = json.loads((raw / "main_state.json").read_text())
    done = {w: info.get("complete") for w, info in state["waves"].items()}
    print(f"synthetic world {a.world}: waves collected by run_wave.py {done}; main spend "
          f"${exp004.main_spend():.4f}; raw files under {raw}")


if __name__ == "__main__":
    main()
