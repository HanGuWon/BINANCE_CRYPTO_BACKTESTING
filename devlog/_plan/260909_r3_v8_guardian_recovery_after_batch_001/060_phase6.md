# 060 — Phase 6: Batch 001 supersession and firewall closeout

## Scope

WP18–WP20. Close the liveness incident without rewriting the original blocked closeout, and prove the scientific firewall remains closed.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/operations/R3_FORCEORDER_V3_INCREMENTAL_BATCH_000001_FINAL_SUPERSESSION_20260908.json`, explicitly stating Batch 001 scientific verification stayed valid, the block was live postcheck only, missing intervals were preserved, high-water was unchanged, and the final disposition conditional on WP4.
- MODIFY: none of the prior blocked closeout, Batch 001 manifest, lineage, raw-v8 bytes, or high-water files.
- DELETE: none.

## Firewall and closeout checks

- Verify `outcomes_accessed=false`, `historical_performance_accessed=false`, `final_holdout=UNTOUCHED`, `r2b2=NOT_ACCESSED`, `pnl=NOT_COMPUTED`, `live_transition=NOT_EXECUTED`, `october_roster=NOT_CREATED`, and `batch_002=NOT_STARTED`.
- Compare Batch 001 manifest/high-water/tree hashes before and after all recovery work; any change is a hard stop and invalidates only the attempted recovery, not silently the prior evidence.
- If WP4 passes, record `R3_FORCEORDER_V3_FIRST_REAL_INCREMENTAL_BATCH_VERIFIED` and `R3_FORCEORDER_V3_INCREMENTAL_LINEAGE_OPERATIONAL`; if not, retain `R3_V3_INCREMENTAL_BATCH_BLOCKED_POSTCHECK` and state the exact blocker.

## Verification

- Run the existing outcome firewall and the exact-v8 watchdog; retain command, exit code, and receipts.
- Run the relevant synthetic operations tests; do not run Batch 001, Batch 002, outcomes, returns, or final-holdout reads.
- Verify Git scientific scope (`scripts`, `src`, `tests`, `configs`) is clean and that no data/cache/raw/Parquet/`.codexclaw` files are staged.

## Acceptance

Only an evidence-backed recovered or pending-hardening state is allowed. The original blocked closeout remains immutable and is linked as superseded, never overwritten.

