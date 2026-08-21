# R1.6 timeframe source policy

15m is the canonical source. Native 1h and 4h archives are compared against
complete 15m aggregation on BTCUSDT and ETHUSDT for clean months and known
gap months. The frozen choice is based only on integrity, coverage, semantic
consistency, and causal availability; no return or performance statistic enters
the decision.

The comparison manifest records field-level matches for OHLC, volume,
quote-volume, trade count, and taker fields. Any native source with missing or
conflicting fields remains RESAMPLED_FROM_15M_GAP_SAFE until independently
verified. The BTCUSDT/ETHUSDT Spot/UM January–February 2024 comparison matched
all checked fields within the declared numerical tolerance, so the current
policy is native 15m, native 1h, and native 4h for the selected-cohort stage;
known 15m gaps remain first-class segment boundaries in the 15m source.
