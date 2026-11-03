#!/usr/bin/env bash
# Spec §8 step 3 dry run. 01_features writes fake worlds to disk in the real layout and reads
# them back; 03_model must recover the planted verdicts on the first two (--expect) and stop on
# H_pos (exit 1) on the third. Everything lives under data/interim/synthetic/<world>/ and
# results/synthetic/<world>/, so the real frames are never touched.
#
# Usage: experiments/011-claude-code-fidelity/pipeline/check_synthetic.sh
# Run from anywhere; exits non-zero if any world misbehaves.
set -euo pipefail

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PIPELINE/../../.." && pwd)"
cd "$REPO"

run_world() {
  local world="$1"
  uv run python "$PIPELINE/01_features.py" --synthetic "$world" >/dev/null
  uv run python "$PIPELINE/02_audit.py" --synthetic "$world" >/dev/null
  uv run python "$PIPELINE/03_model.py" --synthetic "$world" --expect "$world" \
    | sed -n '/dry-run check/,$p'
  # sed reads all of the pipe, so a non-zero 03_model exit is caught by pipefail.
}

echo "=== planted world: cc_stock_full and opus55_plain EQUIVALENT, sched_kit and H3 REAL ==="
run_world planted

echo "=== planted_equiv world: both primary arms pass, Holm levels 95% and 90% ==="
run_world planted_equiv

echo "=== broken-join world: 03_model must stop on H_pos with exit 1 ==="
uv run python "$PIPELINE/01_features.py" --synthetic broken_join >/dev/null
set +e
uv run python "$PIPELINE/03_model.py" --synthetic broken_join | grep -A2 -E '^## H_pos|^H_pos FAILED'
status=${PIPESTATUS[0]}
set -e
if [ "$status" -ne 1 ]; then
  echo "expected exit 1 from H_pos, got $status" >&2
  exit 1
fi
echo "=== all dry-run worlds behaved as planted ==="
