# Phase 1 — causal source contract

Read first: scripts/materialize_r2b_premium_panel.py, src/binance_research/data.py, existing R2B readiness/provenance docs, and representative Binance Vision raw archives.

Change map:

- scripts/materialize_r2b_premium_panel.py: retain source_open_time, source_close_time, source_available_time; derive source_max_constituent_close_time for 1h/4h; align by availability, not open labels.
- tests/test_r2b_readiness.py: replace the incorrect 00:15 expectation and add adversarial 15m/1h/4h, exact-boundary, gap, append-invariance, and fail-closed tests.
- campaigns/r2b_restricted_derivatives_v1/R2B_ERRATUM_002.md: document the old-root availability lookahead before implementation.

Verifier: python -m pytest -q tests/test_r2b_readiness.py (collected 6 tests before edits; reads both listed changed files through the imported helper and direct assertions).

Conditional activation scenarios: an open timestamp before a boundary with close after it must yield no match; a close strictly before the boundary must match; a derived bucket is accepted only after its final constituent close; appending future rows must not alter prior values.
