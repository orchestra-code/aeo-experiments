# Audit D — manual spot-check sign-off

- **Sample:** 30 randomly sampled headphone-panel responses across all arms
  and waves (`data/interim/spotcheck_sample.md`, regenerated 2026-08-02 by
  `02_audit.py`, seed 20260729).
- **Reviewer:** Jim Wrubel, 2026-08-02.
- **Result:** confirmed — extracted brand lists match the answers at the
  pre-registered thresholds (precision ≥ 0.95, recall ≥ 0.90). The
  002-seeded lexicon in `pipeline/brands.py` entered analysis unchanged
  (wave-1 mining found no new candidates) and remains frozen; any further
  change must be logged under "Deviations from the frozen spec".
- Supporting automated cross-check (`results/audit.txt`): the extractor
  recovered 100% of DataForSEO's own brand/product entity annotations on
  the 180/1,285 responses that carried them.
