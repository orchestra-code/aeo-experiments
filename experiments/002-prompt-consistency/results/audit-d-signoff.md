# Audit D — manual spot-check sign-off

- **Sample:** 30 randomly sampled wave-1 headphone responses
  (`data/interim/spotcheck_sample.md`, seed 20260716).
- **Reviewer:** Jim Wrubel, 2026-07-16.
- **Result:** confirmed — extracted brand lists match the answers at the
  pre-registered thresholds (precision ≥ 0.95, recall ≥ 0.90). Lexicons in
  `pipeline/brands.py` are now FROZEN for analysis; any further change must
  be logged under "Deviations from the frozen spec".
- Supporting automated cross-check (results/audit.txt): extractor recovered
  100% of DataForSEO's own brand/product entity annotations on the 59/143
  responses that carried them.
