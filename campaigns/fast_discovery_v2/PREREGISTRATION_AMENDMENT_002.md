# Fast Discovery V2 preregistration amendment 002 — BTC and breadth context

The v2 eleven-row registry remains preserved. This amendment adds exactly two
context-only rows: `btc_regime` and `top50_breadth`. They are registered in
`FEATURE_REGISTRY_V3.csv` and are not standalone directional trade signals.

`btc_regime` uses a trailing EMA200 distance with fixed +/-0.005 context bands.
`top50_breadth` is the contemporaneous mean of selected Top50 symbols above a
trailing EMA50. Both reset or warm up causally and preserve NaN. No polarity or
threshold is selected from outcomes.

Final holdout remains `UNTOUCHED`; no R3/R2B2/live-trading access is authorized.
