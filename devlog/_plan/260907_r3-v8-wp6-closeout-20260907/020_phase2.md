# 020 — Phase 2 (r3-v8-wp6-closeout-20260907)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION_20260907_V2.json`.
  It supersedes the prior continuation by explicit path/SHA, records the
  restored safety prerequisite, the live guardian evidence path, and keeps
  `forceorder_v3_migration=NOT_STARTED`, `outcomes_accessed=false`,
  `final_holdout=UNTOUCHED`, and `r2b2=NOT_ACCESSED`.
- MODIFY: no prior continuation, V2/V3 outage, or V6/V7 firewall artifact is
  overwritten.  A small operations-only verifier/test may be added to validate
  V2 body/file hashes, V3 formulas, V7 supersession, and V2 continuation body
  hash.
- DELETE: none.

## TESTS

- Verify V3 formulas `284-197=87`, `262-87=175`, `87+175=262`,
  `466-204=262`, 44-hour/176-step/175-gap temporal proof, and preserved
  nonqualifying cycle.
- Verify immutable V2/V6/V7 hashes and continuation V2 canonical body hash.

## Verification (C)

- `python -m ops.r3.verify_r3_v8_wp5_firewall_v7`: exit 0, V7 PASS.
- Direct SHA/body-hash verification of the new continuation: exit 0.
- No command may read returns, outcomes, R2B2 artifacts, or final-holdout data.
