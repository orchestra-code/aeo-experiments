#!/usr/bin/env bash
# Spec §8 item 2 dry run. synthetic.py collects three fake waves per world through the real
# wave driver (harness/run_wave.py) with fake transports, so nothing is sent anywhere; 01_frame
# reads them back from disk; 03_model must recover the planted verdicts (--expect) on the first
# two worlds and stop on H_pos (exit 1) on the third. Then the pilot check: the same gap code on
# the feasibility run's frame must reproduce results/pilot_report.md's gaps (exit 0).
# Synthetic outputs live under data/interim/synthetic/<world>/ and results/synthetic/<world>/
# (gitignored), and the pilot frame under data/interim/pilot/ of this checkout (gitignored).
#
# Usage: experiments/004-api-vs-ui/pipeline/check_synthetic.sh
# Run from anywhere; exits non-zero if any world misbehaves.
set -euo pipefail

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PIPELINE/../../.." && pwd)"
cd "$REPO"

run_world() {
  local world="$1"
  uv run python "$PIPELINE/synthetic.py" --world "$world"
  uv run python "$PIPELINE/01_frame.py" --synthetic "$world" >/dev/null
  uv run python "$PIPELINE/02_audit.py" --synthetic "$world" >/dev/null
}

echo "=== planted: cg_api_low and gm_api_plain EQUIVALENT, cg_api_plain and H2 REAL ==="
run_world planted
uv run python "$PIPELINE/03_model.py" --synthetic planted --expect planted | sed -n '/dry-run check/,$p'

echo "=== planted_flip: both ChatGPT arms pass (Holm 95% and 90%), gm_api_plain REAL ==="
run_world planted_flip
uv run python "$PIPELINE/03_model.py" --synthetic planted_flip --expect planted_flip \
  | sed -n '/dry-run check/,$p'
# sed reads all of the pipe, so a non-zero 03_model exit is caught by pipefail.

echo "=== broken_join: 03_model must stop on H_pos with exit 1 ==="
run_world broken_join
set +e
uv run python "$PIPELINE/03_model.py" --synthetic broken_join | grep -E '^- (ChatGPT|Gemini)|^H_pos FAILED'
status=${PIPESTATUS[0]}
set -e
if [ "$status" -ne 1 ]; then
  echo "expected exit 1 from H_pos, got $status" >&2
  exit 1
fi

echo "=== pilot: the gap code reproduces results/pilot_report.md ==="
uv run python "$PIPELINE/01_frame.py" --pilot >/dev/null
uv run python "$PIPELINE/03_model.py" --pilot

echo "=== all dry-run worlds behaved as planted, and the pilot gaps reproduce ==="
