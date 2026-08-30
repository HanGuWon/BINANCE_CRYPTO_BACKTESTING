# R3 prospective context v1 protocol

R3 asks whether historically unavailable market-state observations add causal
context or gates to simple price-direction observations. It is a prospective
data-collection and later evaluation protocol, not a retrospective search for
profitability. No outcome analysis, return ranking, threshold tuning, or
final-holdout access is permitted before a separately approved evaluation
phase.

The authoritative primary Binance UM streams are closed 15-minute klines,
premium-index klines, premium index, open interest, book-ticker, and continuous
liquidation force-order events. Depth, aggregate trades, open-interest history,
and taker ratio are diagnostic-only. Liquidation force-order events are
collected through the public market stream.
Top-trader ratio endpoints, private APIs, balances, positions, and orders are
excluded from R3 v1.

The frozen primary family has six structural hypotheses: execution-quality
context, price×OI quadrant, liquidation continuation, liquidation reversal,
crowding×stress modifier, and BTC/breadth concordance. There are no parameter
grids. The 72-row R2B registry is not reused as an R3 registry.

All observations are retained raw and append-only. Derived materialization is
separate and uses `source_available_time < decision_or_executable_boundary`.
Continuity gaps reset state and are never silently bridged. A minimum evidence
window will be fixed from event counts, dependence blocks, and confidence
precision before prospective outcome analysis; returns cannot choose its end.
