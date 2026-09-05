# R2A.2 Protocol — Temporal Replication & Horizon Decay (Pre-Holdout)

## Status and purpose

R2A.2 is a NEW post-R2A exploratory/pre-holdout campaign on the corrected R2A.1
engine. It is NOT independent final confirmation and does not spend the final
holdout. Two questions:

1. Do standalone indicators replicate across MULTIPLE historical pseudo-OOS periods?
2. Is information concentrated at shorter horizons, obscured by the 24h-only R2A test?

## Frozen design (identical to R2A where applicable)

- Spot LONG only; UM LONG + SHORT. Native 15m/1h/4h only.
- Causal monthly Top50 primary cohort; Top20/Top100 diagnostics.
- Completed-bar decision; entry = exactly next executable open (decision+1);
  no same-close fill; correct funding cashflow sign (+funding_cashflow).
- Non-overlapping position per symbol. Frozen costs (Spot 10bps+5bps slip/side;
  UM 5bps+5bps) plus actual crossed funding events for UM.

## Horizons (each a separate preregistered hypothesis)

- 15m decisions: 4 / 16 / 48 / 96 bars (=1h/4h/12h/24h)
- 1h decisions: 4 / 12 / 24 bars (=4h/12h/24h)
- 4h decisions: 3 / 6 bars (=12h/24h)

## Temporal replication folds (deterministic)

Fixed six-month calendar validation blocks using ONLY pre-holdout history:
2020-H1, 2020-H2, 2021-H1, 2021-H2, 2022-H1, 2022-H2, 2023-H1, 2023-H2.
A fold is VALID for a trial if the trial has >=30 executed trades inside it.
Training expands from data start to the fold start minus horizon-specific purge;
the frozen one-bar operational embargo applies at split boundaries only. No
future fold influences an earlier fold. TEMPORAL_REPLICATION requires >=4 valid
folds with consistent direction in >=75% of valid folds.

## Statistical unit

Thousands of simultaneous cross-symbol trades are NOT independent observations.
Primary inference uses a time-indexed aggregate series (equal-weight active-signal
decision-time portfolio return per bar). Per-trade statistics are descriptive only.
HAC/Newey-West on the aggregate series; calendar-block bootstrap preserving all
symbols together; BH-FDR across the frozen expanded family; Bonferroni descriptive.

## Evidence grading (frozen before outcomes)

TEMPORAL_REPLICATION requires ALL of:
- >=4 valid pseudo-OOS folds;
- effect direction consistent in >=75% of valid folds (aggregate series);
- BH-FDR q <= 0.05 within the preregistered family;
- aggregate HAC |t| >= 3 on the decision-time portfolio series;
- top-symbol share of aggregate net PnL <= 0.5 (not dominated by one symbol);
- no catastrophic reversal (worst-fold aggregate mean < -2x best-fold mean is a fail).
Otherwise NO_REPLICATION (or INSUFFICIENT_FOLDS if fewer than 4 valid folds).
Diagnostic-only grade DIAGNOSTIC_SHORT_HORIZON may be attached when a shorter
horizon shows positive fold-consistent effects that fail the above, without any
confirmatory claim.

## Holdout

Absolutely excluded. No row at/after the per-timeframe final-holdout boundary may
reach signals, execution, MFE/MAE, statistics, bootstrap, selection or grading.
