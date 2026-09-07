# Phase 2 — Repair the Metadata-Only Readiness Checker

## Scope

Modify the existing operations-only checker and its tests. Do not import or touch
the collector, materializer, response store, outcome evaluator, final holdout, or
R2B2 code.

## Exact implementation delta

1. Add a typed metadata representation for a gap interval (`start`, optional
   `end`, `category`, `stream`) and a deterministic `utc_6h_block_ids_for_gap`
   helper next to the current checker owner. The helper normalizes aware UTC
   timestamps, treats a closed/open interval conservatively, and returns a sorted
   set of every UTC 6h block intersected by the interval. A point gap belongs to
   its containing block; a boundary-spanning interval belongs to both blocks.
2. Add `derive_gap_accounting(inventory)` that consumes only explicit metadata
   gap records, health/cycle timestamps, source-unavailable ranges, and continuity
   segments. It rejects missing category/timestamps, duplicate cycle IDs, malformed
   intervals, and strict-boundary violations. It returns raw gap count, unique
   excluded block IDs with reason categories, and a stable block-to-reason map.
3. Replace `_effective_counts` aggregate subtraction with actual eligibility:
   raw counts remain unchanged; primary block count subtracts the unique excluded
   block set; each H01/H02/H05/H06 observation and H03/H04 event is counted only
   when its timestamp and required stream metadata are present and its block is
   eligible. Never subtract `gap_count` from a hypothesis integer.
4. Add verified roster accounting. The CLI receives the immutable roster artifact
   path (default September artifact), validates replay/hash fields and roster
   identity, derives `YYYY-MM` from verified metadata, deduplicates by identity,
   and returns the sorted verified month set. No filename-only accreditation.
5. Update `evaluate_readiness` to require V2 contract/horizon identity, remove the
   lifetime missing-cycle gate, require all gaps to be accounted for, and return
   `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES` when the contract is frozen
   but calendar/block/roster/hypothesis minima remain unmet. Preserve
   `R3_EVALUATION_PREREGISTRATION_BLOCKED` only for contract/integrity errors.
   `human_authorized` remains false unless a future evaluation receipt explicitly
   supplies it; a 15m horizon authorization must not flip it.
6. Keep `_reject_forbidden` broad and fail-closed before any counting. Add explicit
   horizon firewall checks so the artifact cannot contain response values or
   response-field paths.

## Tests / activation scenarios

- Gap cases: zero; two same-block gaps; separate blocks; a gap crossing a 6h
  boundary; explicit missing cycle; restart gap; source-unavailable only; malformed
  interval; duplicate cycle; strict-boundary equality.
- Roster cases: none; verified September; September+October; duplicate September;
  invalid hash/replay.
- Contract cases: one horizon; two horizons; no horizon; injected future/return,
  holdout, PnL, or R2B2 key/path; assert no materializer import and no response
  values in returned receipts.
- State cases: valid frozen contract with low counts gives collection-continues;
  invalid contract/integrity gives preregistration-blocked; all minima plus no
  human evaluation authorization gives eligible-not-started but never auto-starts.

## Verification

Run `python -m pytest -q ops/r3/tests/test_evaluation_readiness.py` and inspect full
output/exit code. The test file directly imports the changed checker and exercises
every new branch, satisfying the target-read verifier requirement.
