#!/usr/bin/env bash
# Spec §8 dry run for the Stage 2 pipeline (pipeline/20_ to 24_, --stage 2).
#
# Each world is written by 20_answers (new-collection waves 1 to 11 with the
# real collection's quirks: one ChatGPT task of wave 6 and seven Gemini tasks
# of wave 8 a day late, one wave 8 Gemini answer from another model, and a
# Gemini wave with 35 of 40 answers, which Audit A takes out of H5's lag
# bins), then pushed through the same steps as real data: build the frame,
# gather the Stage 2 best-for phrases, classify them (a stand-in for
# bestfor_segments.mts), audits, model, robustness, figures.
#
# planted_stable: no drift; H5 must come out practically equivalent (null or
#   negligible) on all three platforms, and on the consumer holdout lags.
# planted_drift: one core vendor per prompt replaced over time on Claude API
#   (about 0.10 lower shortlist retention in far pairs); H5 must come out
#   "real change" there and null or negligible on ChatGPT and Gemini.
# broken_join: every new-collection answer filed under a random prompt of its
#   wave; 22_model must stop on H_pos with exit 1 and 23 must refuse.
#
# Everything lands under data/interim/synthetic/<world>/ and
# results/synthetic/<world>/ (gitignored); real data are never touched.
# Usage: experiments/010-shortlist-stability/pipeline/check_synthetic_stage2.sh
set -euo pipefail

PIPELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PIPELINE/../../.." && pwd)"
cd "$REPO"
run() { uv run python "$PIPELINE/$1" --stage 2 "${@:2}"; }
prepare() {
  run 20_answers.py --synthetic "$1" | grep -E "firewall \(stage 2, waves 1 to 11\): kept 1320|flagged"
  run 20_answers.py --synthetic "$1" --gather-bestfor | grep -E "distinct phrases"
  run 20_answers.py --synthetic "$1" --synthetic-classify
}

for world in planted_stable planted_drift; do
  echo "=== $world: the planted H5 verdicts must come back ==="
  prepare "$world"
  run 21_audits.py --synthetic "$world" > /dev/null
  run 22_model.py --synthetic "$world" --expect planted | sed -n '/dry-run check/,$p'
  run 23_robustness.py --synthetic "$world" > /dev/null
  run 24_figures.py --synthetic "$world"
done

echo "=== broken-join world: 22_model must stop on H_pos with exit 1 ==="
prepare broken_join > /dev/null
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
echo "=== all three Stage 2 dry-run worlds behaved as planted ==="
