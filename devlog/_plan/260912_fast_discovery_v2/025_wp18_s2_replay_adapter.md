# WP18 — Finalist-only S2 replay adapter

Added `src/binance_research/fast_discovery_replay.py` as a narrow handoff layer. It requires an explicit finalist contract (`candidate_id`, `feature_id`, `variant`, `side`, `horizon_bars`), refuses final-holdout rows, and delegates each gap segment to the caller-supplied corrected executor. It never discovers candidates, broadens the registry, or runs a historical outcome by itself. Executor output is checked for the required trade fields before aggregation.

Synthetic tests cover explicit-finalist-only handoff, empty finalist no-op, holdout refusal, and incomplete-contract failure. Verification: 12 focused S0/S1/replay tests passed. No historical R2B/R3 outcomes or holdout observations were accessed.
