# Fast Discovery V2 preregistration amendment 001 — causal relative strength

Status: FROZEN BEFORE CONTEXT SCREENING

The original nine-row `FEATURE_REGISTRY.csv` remains immutable historical
provenance. This amendment adds exactly two theory-defined, continuous context
hypotheses: `relative_strength_24h` and `relative_strength_rank`. The amended
canonical registry is `FEATURE_REGISTRY_V2.csv`; its SHA is recorded in
`REGISTRY_MANIFEST_V2.json`.

`relative_strength_24h` is symbol trailing return over the fixed lookback minus
BTC trailing return over the same lookback. `relative_strength_rank` is the
contemporaneous percentile rank among rows marked `selected_top50` within the
same market and timestamp. Both are continuous, have no binary threshold or
post-outcome polarity, reset at segment boundaries, and preserve NaN warmup.

This amendment does not authorize final-holdout, R3, R2B2, or live-trading access.
