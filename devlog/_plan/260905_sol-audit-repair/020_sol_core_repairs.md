# Work phase wp2 — SOL core correctness repairs

All changes are generic-harness repairs in the isolated branch. No dedicated
R3 scientific executor, frozen result, historical conclusion, or outcome file is
rewritten.

## A02 readiness

Modify `ops/r3/build_r3_evidence_inventory.py` and
`ops/r3/check_r3_evaluation_readiness.py` so missing cycle/gap/metadata fields
are explicit failure states, not numeric zero defaults. Validate types,
freshness, identity, complete accounting, and cross-file consistency. Add
tests for absent, stale, mismatched, incomplete, and explicit-gap receipts;
preserve a fail-closed readiness decision.

## A04 embargo/index alignment

Modify `src/binance_research/splits.py` and its direct CLI callers to carry
timestamp labels and a timeframe step through development/validation splitting
and embargo. Remove accidental
`reset_index`/label-to-position conflation; map a decision to the next
executable open using the configured interval (15m, 1h, 4h), reject equality,
and test exact boundary, non-default index, and future-observation cases.

## A05 accounting

Correct `src/binance_research/backtest.py` short-direction equity/timeline
accounting so per-bar short returns compound consistently with fixed-entry gross
return, costs, and funding sign. Add zero-cost, intermediate-price, positive-
and negative-funding fixtures; assert trade/equity fields independently.

## A06 Deflated Sharpe

Make observation frequency/unit and annualization explicit between
`src/binance_research/cli.py` and `src/binance_research/statistics.py`; pass
periodic Sharpe or convert exactly once. Validate skewness/excess-kurtosis
inputs and small-sample behavior with an independent reference calculation.
Tests must catch annualized-vs-bar scale mismatch and default-moment ambiguity.

## A07 and A12

Use the information set available at decision time for regime attribution in
`src/binance_research/cli.py` (never the future entry bar). Update
`src/binance_research/features.py` gap-safe grouping to use labels/positions
explicitly and support arbitrary DataFrame indices. Add fixtures for a decision
before regime change, index `[10,20,...]`, missing bars, and gap reset.

## Required verification

Add focused tests under `tests/` and run them before commit. Confirm no test
imports returns/checkpoints or accesses final holdout. Record a clean scientific
scope status and commit SHA before wp2 handoff.
