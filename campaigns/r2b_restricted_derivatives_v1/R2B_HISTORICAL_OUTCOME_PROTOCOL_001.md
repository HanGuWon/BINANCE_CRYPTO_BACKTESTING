# R2B historical pre-holdout outcome protocol 001

Status: `FROZEN BEFORE HISTORICAL OUTCOME ACCESS`  
Campaign: `r2b_restricted_derivatives_v1`

This protocol authorizes only the pre-holdout study on the canonical causal
root. It does not authorize final-holdout access, January 2024 evaluation,
R2B2, post-outcome tuning, new features, new horizons, threshold searches,
polarity changes, strategy combinations, or model search.

## Scientific family

Exactly 72 UM hypotheses are evaluated: `derivatives.premium` and
`derivatives.premium_zscore`; `PRESSURE_CONTINUATION` and
`CROWDING_REVERSION`; 15m/1h/4h; LONG/SHORT; and the already frozen horizon
sets (15m: 4/16/48/96, 1h: 4/12/24, 4h: 3/6). Top-50 monthly membership is
the primary cohort. No selection is performed from any fold's returns.

## Exact folds and embargo

`fold_registry.csv` is generated deterministically by
`scripts/generate_r2b_fold_registry.py` and contains exact UTC intervals for
every fold/timeframe/horizon. Validation is `[validation_start_utc,
validation_end_exclusive_utc)`. The one-bar operational embargo is included in
`validation_start_utc`; horizon-aware purge uses `purge_bars = horizon_bars` and
`history_end_exclusive_utc = validation_start_utc - purge_bars × timeframe_step`.
The eight blocks end at 2024-01-01T00:00:00Z; January 2024 is unused.

## Causal execution contract

Signals use completed causal bars only. Entry is exactly the next executable
open; same-close fills are forbidden. A source is eligible only when
`source_available_time < next_executable_open_time`; equality is rejected.
Native 15m availability is the premium-kline close; derived 1h/4h availability
is the maximum constituent 15m close. Gaps reset state and no state crosses a
segment. Positions are non-overlapping per symbol. Funding events crossed by a
holding interval are `(entry_time, exit_time]` and
`funding_cashflow = -side_direction × sum(crossed funding rates)`.

## Unit validity and sealing

Every 72 × 8 = 576 trial-fold units receives a terminal status. A unit with at
least 30 executed trades is `VALID`; fewer is explicitly
`INSUFFICIENT_TRADES` and remains sealed, never deleted. Checkpoints are atomic,
resume-safe, and pinned to implementation, registry, source-tree, causal-root,
protocol, and cost hashes.

## Inference and grading

Primary inference is the time-indexed aggregate decision-time portfolio series,
equal-weighting simultaneous active signals. Per-trade statistics are
descriptive. HAC, bootstrap, BH-FDR, and deterministic grading are frozen in
the companion contracts committed with this protocol.

## Holdout guard

The canonical causal root is pre-holdout only. The final holdout remains
`UNTOUCHED`; any holdout row or January 2024 evaluation row is a hard failure.
