#!/usr/bin/env bash
# Spec §8 step 3 dry run: 01_features plants an equivalent-and-divergent world
# and a broken-join world from fake answers; 03_model must recover the planted
# verdicts on the first (--expect planted) and stop on H_pos (exit 1) on the
# second. Both worlds live under data/interim/synthetic/<world>/ and
# results/synthetic/<world>/, so the real frames are never touched.
#
# Usage: experiments/009-claude-model-fidelity/pipeline/check_synthetic.sh
# Run from anywhere; exits non-zero if either world misbehaves.
set -euo pipefail

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PIPELINE/../../.." && pwd)"
cd "$REPO"

echo "=== planted world: equivalent arms must come out EQUIVALENT, divergent REAL ==="
uv run python "$PIPELINE/01_features.py" --synthetic planted >/dev/null
uv run python "$PIPELINE/03_model.py" --synthetic planted --expect planted \
  | sed -n '/dry-run check/,$p'
uv run python "$PIPELINE/04_figures.py" --synthetic planted

echo "=== broken-join world: 03_model must stop on H_pos with exit 1 ==="
uv run python "$PIPELINE/01_features.py" --synthetic broken_join >/dev/null
set +e
uv run python "$PIPELINE/03_model.py" --synthetic broken_join | grep -A1 '^## H_pos'
status=${PIPESTATUS[0]}
set -e
if [ "$status" -ne 1 ]; then
  echo "expected exit 1 from H_pos, got $status" >&2
  exit 1
fi
echo "=== both dry-run worlds behaved as planted ==="
