#!/usr/bin/env bash
# Spec §8 dry run for the Stage 1 pipeline (pipeline/20_ to 24_, --stage 1).
#
# planted: 20_answers writes fake tasks and judge output for all six datasets
#   (new-collection waves 1 to 11, so the Stage 1 firewall must drop waves 8
#   to 11) with known structure, builds them with the real code, and
#   22_model must recover the planted verdicts (--expect planted): the
#   shortlist beats exact position everywhere except the fixed-order agency
#   set; on Gemini the top pick never changes, so H2 and H3 fail there.
# broken_join: the same world with every new-collection answer filed under a
#   random prompt of its wave; 22_model must stop on H_pos with exit 1.
#
# Everything lands under data/interim/synthetic/<world>/ and
# results/synthetic/<world>/ (gitignored); real data are never touched.
# Usage: experiments/010-shortlist-stability/pipeline/check_synthetic_stage1.sh
set -euo pipefail

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PIPELINE/../../.." && pwd)"
cd "$REPO"
run() { uv run python "$PIPELINE/$1" --stage 1 "${@:2}"; }

echo "=== planted world: the planted verdicts must come back ==="
run 20_answers.py --synthetic planted | grep -E "firewall|flagged"
run 21_audits.py --synthetic planted > /dev/null
run 22_model.py --synthetic planted --expect planted | sed -n '/dry-run check/,$p'
run 23_robustness.py --synthetic planted > /dev/null
run 24_figures.py --synthetic planted

echo "=== broken-join world: 22_model must stop on H_pos with exit 1 ==="
run 20_answers.py --synthetic broken_join > /dev/null
set +e
out="$(mktemp)"
run 22_model.py --synthetic broken_join > "$out"
status=$?
set -e
grep "FAIL: STOP" "$out" || true
rm -f "$out"
if [ "$status" -ne 1 ]; then
  echo "expected exit 1 from H_pos, got $status" >&2
  exit 1
fi
set +e
run 23_robustness.py --synthetic broken_join > /dev/null 2>&1
rstatus=$?
set -e
if [ "$rstatus" -eq 0 ]; then
  echo "23_robustness.py ran after a failed H_pos" >&2
  exit 1
fi
echo "=== both dry-run worlds behaved as planted ==="
