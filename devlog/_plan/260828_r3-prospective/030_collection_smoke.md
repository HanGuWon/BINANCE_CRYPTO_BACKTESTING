# Collection-only smoke and launch boundary

`scripts/r3_collection_smoke.py` exercises all seven R3 public UM snapshot
streams against deterministic fake responses. It records stream count, bytes,
source-time availability, continuity states, API-key stream exclusion, and a
conservative request-weight upper bound. It intentionally emits no return,
PnL, Sharpe, hit-rate, or candidate-ranking field. Continuous collection is
not launched in this goal; the resulting state is
`READY_FOR_PROSPECTIVE_COLLECTION` once the full verification suite passes.
