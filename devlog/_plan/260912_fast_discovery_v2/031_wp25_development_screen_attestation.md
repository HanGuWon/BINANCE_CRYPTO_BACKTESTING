# WP25 — Development screen execution and attestation

After the causal Top50 membership fix was committed, the authorized UM development screen ran on two symbols (`1000BONKUSDT`, `1000FLOKIUSDT`) for 1h, 4h, and the preregistered 15m lane over 2024-02 through 2024-04. Each run used actual Binance OHLCV archives and actual temporal/calendar folds; non-Top50 rows were excluded and counted. New versioned roots `development_screen_um_{1h,4h,15m}_2024q1_v3` preserve the prior `_v2` roots.

A hash-pinned `DEVELOPMENT_SCREEN_ATTESTATION.json` is generated per root, binding implementation commit, source-tree SHA, receipt/result/rejection SHAs, row counts, and the holdout/trade firewall. No final-holdout rows or R2B/R3 outcome runs were accessed.
