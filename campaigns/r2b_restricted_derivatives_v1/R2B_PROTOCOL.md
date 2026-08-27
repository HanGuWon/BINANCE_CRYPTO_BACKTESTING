# R2B Restricted Derivatives — Pre-outcome protocol (blocked)

Status: `R2B_BLOCKED_IMPLEMENTATION`

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
- The feature is backward-as-of joined to the completed-bar decision time.
  No forward fill, interpolation, or cross-venue substitution is permitted.
- Universe membership is the causal UM Top-50 selection from
  `universe_monthly.csv`, with membership effective only in the selected
  universe month.
- Any future implementation must retain the existing next-open execution,
  per-symbol non-overlap, segment-safe warmups, actual funding-event cashflow,
  and final-holdout guard used by R2A.2.

## Why execution is blocked

The repository has no frozen directional signal semantics for either premium
feature. `src/binance_research/features.py` exposes
`premium_zscore90` as a value feature but does not define `sig_premium` or
`sig_premium_zscore`; `derivatives_semantics.md` defines the source and
90-event/bar z-score only. A sign, threshold, or contrarian interpretation
would therefore be a new scientific rule, not a repair. The registry records
the intended dimensions with `UNDEFINED_SIGNAL_SEMANTICS` and must remain
blocked until an explicit, reviewed semantics amendment is added.

No R2B executor, qualification result, outcome checkpoint, final-holdout read,
or R2B performance verdict may be produced while this blocker remains.

## Intended preregistered dimensions

The registry contains 36 UM Top-50 rows: two features × three timeframes × two
sides × the R2A.2 horizon set for each timeframe. Rows are metadata only and
are marked `BLOCKED_IMPLEMENTATION`; this is not evidence that 36 trials ran.

