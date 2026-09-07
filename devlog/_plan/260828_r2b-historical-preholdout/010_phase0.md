# Phase 0 — reality sync and qualification hash provenance

## MODIFY / NEW map

- MODIFY `scripts/r2b_qualification.py` to emit separately named payload and
  result identities; serialized file identity is measured externally.
- MODIFY `tests/test_r2b_qualification.py` with a regression that recomputes
  payload and file hashes and proves they are not conflated.
- MODIFY `campaigns/r2b_restricted_derivatives_v1/qualification_receipt.json`,
  `reproducibility_manifest.json`, and the freeze report after the fresh
  qualification receipt is generated.

## Verification

- Confirm branch/HEAD, registry/causal/source hashes, scoped Git cleanliness,
  qualification result identity, and exact final-holdout status.
- No historical panel, return, checkpoint, or holdout read in this phase.
