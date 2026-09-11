# Phase 1 — Predictability engine

## Files

- NEW `src/binance_research/predictability.py`
- MODIFY `src/binance_research/__init__.py`
- NEW `tests/test_predictability.py`

## Behavior

- Build next-executable-open to future-close labels for four horizons.
- Fit a deterministic L2 logistic model using NumPy/SciPy only.
- Provide constant and lagged-price baselines, probability metrics, and block
  bootstrap confidence intervals.
- Provide a walk-forward evaluator that returns one row per fold/model/horizon.

## Acceptance

- Future mutation cannot change earlier labels or features.
- Missing input and incomplete future windows are excluded explicitly.
- Perfect, constant, and inverted predictions receive distinguishable scores.
