# Plan — adversarial R3 evaluation V2 repair (outcome-blind)

## Scope

This plan supersedes the earlier single-horizon V2 design. It repairs the V1
statistical contract without opening any response, label, return, ranking,
performance, final-holdout, or R2B2 data. The sealed v8 collector remains
running and its immutable scientific implementation, source-tree hash, and
registry are not modified.

## Work phases

1. `wp0-firewall-audit`: reverify identities/liveness and write a defect ledger
   for every V1 H01–H06 degree of freedom.
2. `wp1-horizon-estimands`: freeze the six-horizon map and one scalar primary
   estimand per hypothesis, including non-redundant H03/H04 and oriented H06.
3. `wp2-forceorder-identity`: prove event identity, replay behavior, and
   deterministic raw/unique accounting from metadata only.
4. `wp3-inventory-accounting`: repair roster-month provenance and source-specific
   gap-to-block attrition with per-hypothesis usable block sets/minima.
5. `wp4-checker-tests`: enforce the V2 contract in a metadata-only checker and
   add the complete adversarial synthetic test matrix.
6. `wp5-qualification`: run focused tests twice, static materializer firewall,
   inventory/checker verification, and no-outcome qualification only.
7. `wp6-commit-report`: commit/push only governance/operations artifacts and
   publish an append-only final report in collection-continues state.

## Hard firewall

No historical evaluation, response materialization, return/PnL/Sharpe/hit-rate
inspection, final-holdout access, R2B2 access, threshold/horizon optimization,
or collector stop is allowed. A readiness result with unmet minima is expected
to remain `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`.

The frozen data identity is the exact append-only root
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`.
Phase 0 records its tree hash and file count twice during a read-only window,
requires equality between the two observations, and records that no root or
launch manifest was created or rewritten. The sealed launch manifest and
`SEALED` launch-seal receipt must match the frozen implementation, registry,
source-tree hash, and root. Any root identity mismatch is a hard stop.

The firewall predicates are explicit: scoped scientific status is empty;
`HEAD...origin` is `0 0`; the collector process and lock are live; exactly one
authorized writer exists; duplicate writers are zero; manifest chain
verification is true; seal verification is true; and `outcomes_accessed` is
false. A stale collector lock may be removed only after an authoritative
PID-not-found proof and only through the already-qualified resume launcher;
the restart is recorded append-only.

## Completion state

The only successful terminal state is `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`.
Any integrity or unresolved holdout-partition defect must leave the goal
blocked rather than being papered over.
