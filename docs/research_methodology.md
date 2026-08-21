# Research Methodology

## Preregistered first pass

The feature catalog contains 22 candidates and small conventional parameter choices.
Each candidate is evaluated standalone before any combination. Every evaluated
variant is counted in the experiment registry; the final holdout remains untouched
until selection is frozen.

Predictive studies measure returns from the next executable open to a later close,
plus IC/rank-IC, quantile distributions, MFE/MAE, and directional asymmetry.
Quantile edges are learned from training observations only. Rule studies use
non-overlapping conventional positions with explicit costs and report gross and net.

## Causality

A feature row is timestamped at the source bar close. Rolling windows are trailing,
Donchian bounds exclude the decision bar, and external context must be aligned by
the latest timestamp known at decision time. No centered window, future pivot, or
full-sample scaler is accepted. Appending arbitrary future observations must not
alter previously computed feature values.

## Validation

Data is divided chronologically into train, validation, and untouched test. Expanding
walk-forward is supported with an optional embargo. Results are sliced by symbol,
year/month, timeframe, BTC trend, volatility, liquidity, breadth, and direction.
Risk metrics use the complete bar-level open-to-open return timeline, including
inactive bars. Sharpe/Sortino use `365*24*60/interval_minutes`, while MDD and
Calmar use the full equity path. Deflated Sharpe uses the same bar observations,
not trade count. Parameter robustness is grouped by named rule families; these
are diagnostics, not proof of causality or future performance.

External sources use backward as-of joins with source timestamp, age, and
coverage provenance. Missing prior observations are `NO_PRIOR_OBSERVATION`;
explicitly unavailable history is `HISTORICAL_UNAVAILABLE`; stale values are
marked `STALE` and nulled.

UM/CM funding is mandatory and missing values crossed by a position fail closed.
The charged value is aligned per crossed bar, an explicitly documented
approximation to event-time funding. Ordinary runs use only development
train/validation data; each walk-forward fold selects on validation and tests
on the following fold. The outer final holdout is excluded unless
`--final-holdout` is explicitly supplied.

## Decision language

Without sufficient OOS observations and robustness slices, the only valid conclusion
is `INSUFFICIENT EVIDENCE`. Candidates may advance to forward shadow/paper validation;
they are never promoted directly to live autonomous trading by this repository.
