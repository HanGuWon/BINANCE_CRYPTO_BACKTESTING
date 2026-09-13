# Fast Discovery V2 — V3 development status

Scope: UM development-only, two symbols (`1000BONKUSDT`, `1000FLOKIUSDT`), causal monthly Top50 membership, Binance OHLCV archives, 2024-02 through 2024-04. Final holdout is `UNTOUCHED`; R2B/R3 historical outcomes are `NOT_RUN`/`NOT_ACCESSED`.

| timeframe | rows after cohort filter | non-Top50 rows excluded | complete result rows | S0 survivors | S1/S2 |
|---|---:|---:|---:|---:|---|
| 1h | 2,880 | 1,440 | 27 | 0 | not entered |
| 4h | 720 | 360 | 18 | 0 | not entered |
| 15m | 11,520 | 5,760 | 27 | 11 | not entered |

`HISTORICAL_UNAVAILABLE` means the feature could not be evaluated; `S0_REJECTED` means it was evaluated and failed frozen S0 gates; `S0_SURVIVOR` is only a predictive-screen status. No trade rows were materialized, and no status is prospective evidence.
