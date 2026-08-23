# R2A Protocol - Standalone Indicator Evidence (Pre-Holdout)

## Objective

Determine which individual indicators contain reproducible pre-holdout
predictive information and which survive causal next-open execution costs.

## Frozen design decisions

- Feature universe: exact R2A_PRIMARY feature IDs from the corrected
  feature_availability_final.csv (19 spot; 19 um including funding and
  funding_zscore). Premium/premium_zscore are R2B_RESTRICTED and are NOT
  part of R2A.
- Markets: Spot LONG-only; UM LONG and SHORT.
- Timeframes: native 15m/1h/4h only.
- Cohort: causal monthly Top50 primary cohort (from universe_monthly.csv);
  Top20/Top100 diagnostic only.
- Decisions on completed bars only; no same-close fill; entry at next
  executable open after decision timestamp.
- Pre-holdout boundaries from corrected split_metadata_final.csv:
  train through last_train_timestamp, validation through
  last_validation_timestamp. Final holdout fully excluded from R2A.
- Purge: 24h label horizon (96/24/6 bars) plus one-bar operational embargo.
- Horizons: forward-return horizon equal to each timeframe purge equivalent;
  no overlapping-label reuse inside validation scoring.
- Parameter variants: frozen coarse grid in campaign_spec.toml only; no
  tuning after observing validation results.
- Costs: frozen cost_model.md; UM trades include actual crossed funding
  events as trading cost.
- Statistics: dependence-aware HAC/Newey-West t-stats; time-block bootstrap
  preserving cross-sectional dependence (block length = one calendar month).
- Multiple testing: BH-FDR across the full preregistered trial registry,
  family = all trials within market x timeframe cell (see
  multiple_testing_plan.md).
- Diagnostics: walk-forward stability folds; yearly, timeframe, horizon and
  symbol-concentration robustness cuts.
- Promotion: see promotion_policy.md. No profitability claims; evidence
  grades only.

## Explicit exclusions

- No indicator combinations, no ML models, no post-validation threshold
  changes, no final holdout access of any kind.

## Execution order

1. Freeze trial registry (trial_registry.csv committed BEFORE any run).
2. Run trials exactly once over train+validation partitions.
3. Score with metrics_contract.md metrics; apply multiple_testing_plan.md.
4. Emit evidence grades via promotion_policy.md.
5. STOP. Holdout evaluation is a separate future campaign.
