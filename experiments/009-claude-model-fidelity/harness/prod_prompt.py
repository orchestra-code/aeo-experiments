"""The production discovery prompt for the ``sonnet5_prod`` arm, kept out of git.

The Spyglasses discovery prompt is product IP, so this public repo never
holds its text. ``extract()`` reads it from a local spyglasses checkout
(``buildDiscoveryPrompts`` in
``packages/background-jobs/src/utils/discovery-query-execution.ts``) and
writes ``data/raw/system_prompts/spyglasses_prod.json`` (gitignored) with the
system prompt, the user-prompt suffix, the source path, the spyglasses commit
and sha256 hashes. ``load()`` reads that file for ``arms.build_params``.

Usage (repo root; idempotent):
    uv run python experiments/009-claude-model-fidelity/harness/prod_prompt.py \
        [--spyglasses /Users/jcw/projects/spyglasses]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
OUT = EXP / "data" / "raw" / "system_prompts" / "spyglasses_prod.json"
DEFAULT_SPYGLASSES = Path("/Users/jcw/projects/spyglasses")
SOURCE_REL = "packages/background-jobs/src/utils/discovery-query-execution.ts"
QUERY_PLACEHOLDER = "${query}"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse_source(ts: str) -> tuple[str, str]:
    """(system prompt, user suffix) from the TypeScript source text.

    The system prompt is the ``const systemPrompt`` template literal inside
    ``buildDiscoveryPrompts``. The user prompt literal is ``${query}`` plus a
    suffix; JS ``\\n`` escapes become newlines. The location line that
    production appends only for located properties is not part of it (study
    prompts have no location).
    """
    seg = ts[ts.index("export function buildDiscoveryPrompts"):]
    system = re.search(r"const systemPrompt = `(.*?)`;", seg, re.S)
    user = re.search(r"let userPrompt = `(.*?)`;", seg, re.S)
    if not system or not user:
        raise SystemExit("buildDiscoveryPrompts literals not found; the source changed")
    user_text = user.group(1).replace("\\n", "\n")
    if not user_text.startswith(QUERY_PLACEHOLDER) or "${" in user_text[len(QUERY_PLACEHOLDER):]:
        raise SystemExit("user prompt template is no longer '${query}' + a fixed suffix")
    if "${" in system.group(1) or "\\" in system.group(1):
        raise SystemExit("system prompt now has interpolation or escapes; review the parser")
    return system.group(1), user_text[len(QUERY_PLACEHOLDER):]


def _commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%H", "--", SOURCE_REL],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def extract(spyglasses: Path = DEFAULT_SPYGLASSES, out: Path = OUT) -> dict:
    """Parse the source and write the JSON; returns the record."""
    source = spyglasses / SOURCE_REL
    system, suffix = parse_source(source.read_text())
    record = {
        "system": system,
        "user_suffix": suffix,
        "source_path": SOURCE_REL,
        "spyglasses_commit": _commit(spyglasses),
        "sha256": {"system": sha256(system), "user_suffix": sha256(suffix)},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    return record


def load(path: Path = OUT) -> dict:
    """The extracted record; a clear error when the extractor has not run."""
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. The sonnet5_prod arm needs the Spyglasses production "
            "prompt, which is not in this repo. Run:\n"
            "  uv run python experiments/009-claude-model-fidelity/harness/prod_prompt.py "
            "--spyglasses <path to a spyglasses checkout>"
        )
    record = json.loads(path.read_text())
    for key in ("system", "user_suffix"):
        if sha256(record[key]) != record["sha256"][key]:
            raise SystemExit(f"{path}: sha256 mismatch on {key}; re-run the extractor")
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spyglasses", default=str(DEFAULT_SPYGLASSES))
    a = ap.parse_args()
    rec = extract(Path(a.spyglasses))
    print(f"wrote {OUT} (spyglasses commit {rec['spyglasses_commit']}, "
          f"system sha256 {rec['sha256']['system'][:12]}, "
          f"suffix sha256 {rec['sha256']['user_suffix'][:12]})")


if __name__ == "__main__":
    main()
