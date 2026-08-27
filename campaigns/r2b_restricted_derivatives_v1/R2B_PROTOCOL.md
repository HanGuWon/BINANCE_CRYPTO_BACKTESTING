# R2B Restricted Derivatives — Pre-outcome protocol (frozen)

Status: `R2B_BLOCKED_IMPLEMENTATION` (semantics frozen; qualification pending)

This campaign is a provenance-repaired, pre-outcome protocol for the two
restricted UM context features `derivatives.premium` and
`derivatives.premium_zscore`. It is not an outcome run and contains no
performance claim.

## Frozen data and causal rules

- Source: Binance Vision UM `premiumIndexKlines`, 15-minute close.
- Archive cutoff: `2024-01`; the `2024-02` validation/holdout month is not
  acquired or materialized.
- Study timeframes: 15m, 1h, and 4h. The latter are derived only from complete
  contiguous 15m buckets; incomplete buckets and gaps are quarantined.
- The point-in-time rule is exact: `source_available_time < next_executable_open_time`, where `next_executable_open_time` is `decision_timestamp + timeframe_step`.
  For native 15m rows, `source_available_time` is the native premium-kline close time. For derived 1h/4h rows, it is the maximum constituent 15m close time from a complete contiguous bucket.
  Equality at the executable boundary and any later source observation are rejected (`source_available_time >= next_executable_open_time`). Source open, close, and maximum constituent close times are retained.
  No forward fill, interpolation, or cross-venue substitution is permitted.
- Universe membership is the causal UM Top-50 selection from
  `universe_monthly.csv`, with membership effective only in the selected
  universe month.
- Any future implementation must retain the existing next-open execution,
  per-symbol non-overlap, segment-safe warmups, actual funding-event cashflow,
  and final-holdout guard used by R2A.2.

## Frozen signal semantics

Amendment 002 freezes `PRESSURE_CONTINUATION` and `CROWDING_REVERSION` as
separate variants for raw `premium` and `premium_zscore90`. Both use a strict
zero-centered sign rule; LONG requires `+1`, SHORT requires `-1`, and zero,
missing, or NaN never enter. Exact equations, warmup, gap reset, and
next-open behavior are defined in `R2B_SIGNAL_SEMANTICS_AMENDMENT_002.md`.

No R2B executor, qualification result, outcome checkpoint, final-holdout read,
or R2B performance verdict may be produced while this blocker remains.

The prior repaired root is preserved as `INVALID/SUPERSEDED` under
`root_history.md`; its tree SHA256 is recorded in `R2B_ERRATUM_002.md`. The
candidate causal root is separate and must pass
`python scripts/verify_r2b_causal_root.py --root <root> --out <proof>` before
any semantics or qualification gate can advance.

## Intended preregistered dimensions

The registry contains 72 UM Top-50 rows: two features × two variants × three
timeframes × two sides × the fixed horizon set for each timeframe. Rows are
preregistered metadata only; this is not evidence that any historical trial ran.
The qualification contract is UM-only; Spot is an engine control only.
