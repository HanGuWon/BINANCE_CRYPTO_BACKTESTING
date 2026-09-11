# Fast Discovery development run

Run one bounded, development-only invocation on a single repaired causal premium parquet under the D-backed root. Pass the concrete development split manifest and never access final holdout. Because the causal premium parquet lacks OHLC labels, the expected result is fail-closed `HISTORICAL_UNAVAILABLE` and zero survivors; this is an execution-contract result, not a performance conclusion.

Files: `campaigns/fast_discovery_v1/run_1000BONKUSDT_1h/` compact CSV/JSON/MD manifests, benchmark, and final report. No parquet/raw/cache committed. Verifier reads the generated reports, checks zero trade rows, source/provenance hash, and holdout untouched.


## Fail-closed run binding
- Input: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\processed\r2b_restricted_derivatives_v1_repaired_v2_causal3\market=um\symbol=1000BONKUSDT\timeframe=15m\year=2024\part-000.parquet`; SHA256 `6a9923908087fa67a027087699b0e6a8b8a246c931a59a8d182b99eeb753d462`.
- Split manifest: `campaigns/predictability_v1/DEVELOPMENT_FINAL_HOLDOUT_MANIFEST.json`; SHA256 `75db5609e5c5d99c888972c46941f698c965d36b6d373b97b4326abca2a45df5`; dataset root SHA `6eef4e59225cb45c2833452a883249b11f03469298c1ecfb3837c5f4aaa27a7d`; final holdout starts `2026-09-01T00:00:00Z` and remains `UNTOUCHED`.
- Exact command: `python scripts/run_fast_discovery.py --input <above parquet> --output campaigns/fast_discovery_v1/run_1000BONKUSDT_15m --timeframe 15m --market um --dataset-root D:\BINANCE_CRYPTO_BACKTESTING_DATA\processed\r2b_restricted_derivatives_v1_repaired_v2_causal3 --split-manifest campaigns/predictability_v1/DEVELOPMENT_FINAL_HOLDOUT_MANIFEST.json`.
- Output root is fresh and development-only. Verifier must check input/tree/manifest hashes, `HISTORICAL_UNAVAILABLE` for all primitives, zero S0/S1/S2 survivors and `trade_rows=0`, provenance agreement, no holdout timestamps, and no forbidden outcome-path references. Missing either required CLI binding is a nonzero failure.
