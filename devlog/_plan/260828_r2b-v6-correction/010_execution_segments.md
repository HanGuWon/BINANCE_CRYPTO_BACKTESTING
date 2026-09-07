# Execution-segment implementation unit

Scope: `scripts/r2b_historical_runner.py` and focused regression tests only.

Derive `execution_segment_id` after sorting each symbol/timeframe frame. Start a
new segment when the original causal `segment_id` changes, when the timestamp
delta differs from the exact timeframe step, or when the execution price needed
for the sequence is unavailable/nonfinite. Execute only within one derived
segment so entry is exactly one step after decision and exit is exactly
`horizon_bars` steps after entry. Preserve all frozen signal, cost, funding,
fold, and registry rules. The immutable causal root is read-only.

Verification: synthetic October-selected/November-absent/December-selected
fixture; original segment-boundary fixture; missing-price fail-closed fixture;
targeted runner tests and `python -m pytest -q` after the unit is complete.
