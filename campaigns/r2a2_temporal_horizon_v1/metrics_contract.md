# R2A.2 Metrics Contract

Per trial x horizon x fold:
- n_trades, symbols_traded, mean/median per-trade net return (descriptive)
- aggregate decision-time portfolio series length and sum
- HAC t-statistic on the AGGREGATE series (primary), per-trade HAC descriptive
- worst-fold aggregate mean, median fold effect
Per trial x horizon (across folds):
- valid_fold_count, positive_fold_fraction, fold-by-fold means and HAC stats,
  calendar-year behavior, Top20/Top50/Top100 sharpe, Spot-UM consistency note,
  UM LONG-vs-SHORT asymmetry, horizon-decay table position.
15m path diagnostics (causal post-entry): MFE/MAE/time-to-MFE/time-to-MAE.
Missing metrics are NaN with reason; never silently dropped.
