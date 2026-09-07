# R2B evidence grading contract 001

`TEMPORAL_REPLICATION` requires all of: at least four valid pseudo-OOS folds;
aggregate effect direction consistent in at least 75% of valid folds; BH-FDR
q ≤ 0.05 across all 72 hypotheses; aggregate HAC |t| ≥ 3.0; top-symbol share
of aggregate net PnL ≤ 0.50; and no catastrophic reversal.

Catastrophic reversal is
`worst_fold_aggregate_mean < -2 × best_fold_aggregate_mean`. Otherwise the
grade is `NO_REPLICATION` or `INSUFFICIENT_FOLDS` as applicable. No weaker
success label may be invented after outcomes.
