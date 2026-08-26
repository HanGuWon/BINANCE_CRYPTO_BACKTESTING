# R2A.2 directional repair and verified campaign

## Objective and constraints

Repair the P0 directional gate, preserve frozen SIGNAL_SEMANTICS, archive all interrupted/invalid checkpoints with hashes, qualify optimized execution against an explicit-sign reference, then run and aggregate the 756-trial x 8-fold campaign. No R2B or final holdout access; raw/processed data remain immutable.

## Work-phase map

- Phase 1 (`010`): archive interrupted outputs, finalize directional/segment-safe executor and regression qualification.
- Phase 2 (`020`): run the corrected pre-holdout outcome campaign into a fresh D-backed root.
- Phase 3 (`030`): aggregate, verify, document historical disposition, and publish source plus small reproducibility artifacts.

## Acceptance evidence

Fresh targeted and full pytest receipts; qualification receipt with field-by-field equality; implementation and registry SHAs; complete checkpoint manifest with zero failures; holdout guard proof; aggregate diagnostics and verification report; git status and push receipt.
