# R2B semantics-design exclusion list

This list is a pre-outcome provenance boundary. The following repository
artifacts must not be inspected, parsed, searched for numeric outcomes, or used
to select premium polarity, thresholds, transformations, horizons, or variants:

- `artifacts/holdout-proof-base/`
- `artifacts/holdout-proof-sentinel/`
- Any inherited predictive-horizon, validation, or holdout performance artifact
  containing `premium_zscore90` or another R2A/R2A.2 performance-like output.

R2B semantics may use only the mathematical/source definition of Binance
Premium Index, official documentation, the frozen source implementation, and
independent economic reasoning or literature available before R2B outcomes.
No performance result or repository return artifact has been consulted for the
blocked amendment 001.
