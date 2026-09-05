# 040 — Phase 4: implementation and regression tests

## MODIFY / NEW / DELETE map

- MODIFY `scripts/r2a_engine.py`: expose the frozen R2B premium and
  premium-z-score sign equations through the existing signal owner, preserving
  NaN/warmup values and strict side gates used by the corrected executor.
- MODIFY `scripts/run_r2a2_v2.py`: retain segment-local cache/next-open execution
  and make the directional gate reusable by the synthetic qualification harness.
- MODIFY `scripts/r2b_qualification.py`: replace the historical blocked stub with
  synthetic-only optimized/reference helpers (UM scientific matrix; Spot control
  is explicitly excluded from the family).
- MODIFY `tests/test_r2b_qualification.py` and NEW
  `tests/test_r2b_signal_semantics.py`: deterministic fixtures for both variants,
  raw versus z-score separation, NaN/zero/warmup, gap reset, append invariance,
  side polarity, funding signs, and exact field-level qualification.
- MODIFY campaign receipt/provenance metadata only after gates pass; do not touch
  historical outcome or holdout artifacts.

## TESTS

- `python -m pytest -q tests/test_r2b_signal_semantics.py tests/test_r2b_qualification.py`
- All fixtures are in-memory and contain no repaired historical-root reads.

## Verification (C)

- `python -m pytest -q` after implementation; implementation commit SHA and
  scoped scientific git status clean; qualification remains synthetic/reference-
  only and no R2B outcome checkpoint is created.
