# R3 p2 — key-safe causal materialization and UM roster rollover

Scope: materialize each `(market, symbol, stream)` independently so BTC/ETH or
different streams can never overwrite one another. Preserve continuity and
availability fields while selecting latest eligible observations per key.
Freeze a deterministic August 2026 USD-M Top50 roster from prior-ranking
evidence with source and roster SHA256, effective bounds, and exactly 50 unique
symbols. A missing September roster enters `UNIVERSE_ROLLOVER_GAP` and
suspends collection; only an immutable matching roster permits LEAVE/REENTER.

Out of scope: historical outcomes, final holdout, R2B2, live collection, and
return/PnL analysis.

Verification: `python -m pytest -q tests/test_r3_materializer.py
tests/test_r3_universe.py`.
