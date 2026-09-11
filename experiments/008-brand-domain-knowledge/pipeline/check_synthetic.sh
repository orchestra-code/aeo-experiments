#!/usr/bin/env bash
# Spec §5 dry run: 01_features plants a pure-lookup world and a pure-guess
# world, 03_model must return the matching H2 verdict and H4 gap on each.
# Both worlds live under data/interim/synthetic/<world>/ and
# results/synthetic/<world>/, so the real frames are never touched.
#
# Usage: experiments/008-brand-domain-knowledge/pipeline/check_synthetic.sh
# Run from the repo root; exits non-zero if either world misses its verdict.
set -euo pipefail

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PIPELINE/../../.." && pwd)"
cd "$REPO"

for world in lookup guess; do
  echo "=== planting the pure-$world world ==="
  uv run python "$PIPELINE/01_features.py" --synthetic "$world" >/dev/null
  uv run python "$PIPELINE/03_model.py" --synthetic "$world" --expect "$world" \
    | grep -A 8 'dry-run check'
done
echo "=== both dry-run worlds returned the expected verdicts ==="
