# Metrics Contract

Every trial reports ALL of the following; none is optional:

- n_signals, n_trades (after next-open execution and cost model)
- hit_rate, mean_trade_return_bps (net of costs)
- annualized_sharpe (per market x timeframe cell), sortino
- max_drawdown, calmar
- turnover_per_bar, avg_holding_bars
- HAC t-statistic (Newey-West automatic lag) on mean net return
- time-block bootstrap CI95 for mean net return (1000 resamples, fixed seed 1729)
- FDR q-value within market x timeframe family
- walk-forward fold count and per-fold Sharpe sign consistency

Definitions are frozen before any run; a metric that cannot be computed
(insufficient trades) is reported as NaN with reason, never silently dropped.
