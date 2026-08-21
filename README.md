# BINANCE_CRYPTO_BACKTESTING

A research-only Binance indicator and causal backtesting harness.

This project uses public Binance market data for research and backtesting only.
It does not provide live trading, order submission, autonomous execution, or a
profitability guarantee.

## Research state

Harness engineering status: `VERIFIED — READY FOR REAL DATA CAMPAIGN`

Strategy/indicator evidence: `INSUFFICIENT EVIDENCE`

These statuses are intentionally separate. No strategy has been shown to be
profitable.

The repository began empty. The implementation is therefore isolated as a Python
package under `src/binance_research`; there is no production bot behavior to
change or preserve.

## Quick start

```powershell
python -m pip install -e ".[dev]"
python -m compileall -q src tests
python -m pytest -q
binance-research --help
python -m binance_research --help
binance-research download --market spot --dataset klines --symbol BTCUSDT --interval 1h --year 2024 --month 1 --processed-output data/processed/BTCUSDT-1h-2024-01.parquet
binance-research download --market spot --dataset klines --symbol BTCUSDT --interval 1h --year 2024 --month 1 --cadence daily --day 15 --processed-output data/processed/BTCUSDT-1h-2024-01-15.parquet
binance-research run --input data/processed/BTCUSDT-1h-2024-01.parquet --output artifacts/example --market spot --timeframe 1h
binance-research collect --symbol BTCUSDT --output data/raw/forward
```

For a network-free smoke run (not market evidence):

```powershell
binance-research generate-synthetic --rows 1000 --timeframe 1h --output data/processed/synthetic-1h.csv
binance-research run --input data/processed/synthetic-1h.csv --output artifacts/synthetic-smoke --market spot --timeframe 1h
```

Use `--final-holdout` only after the candidate set and parameters are frozen.
Ordinary runs write validation results and leave the final test untouched.
The same CLI is available as `python -m binance_research` and
`python -m binance_research.cli`.
The versioned `artifacts/synthetic-smoke-v21` and `artifacts/official-smoke-v21`
outputs supersede older V2 smoke directories; older artifacts are retained as
historical, stale verification records.

## Research contract

- UTC internally; timestamp units are detected and normalized.
- Raw archives are immutable and official SHA-256 sidecars are verified.
- Completed bar `t` creates the signal; the earliest entry is the next executable
  observation (normally next-bar open).
- Rolling transforms use trailing observations only. OOS quantile boundaries are
  fitted on training data and then frozen.
- Fees, spread, slippage, latency, and funding are explicit configuration inputs.
- Chronological train/validation/test splits and expanding walk-forward are used;
  observations are never shuffled.
- Every experiment has an append-only registry record with code and dataset hashes.
- Short-retention endpoints are marked `HISTORICAL_UNAVAILABLE` outside their
  actual coverage and are collected forward without fabricated history.

See [the methodology](docs/research_methodology.md), [data availability](docs/data_availability.md),
and [implementation plan](docs/implementation_plan.md).

## Scope status

The first implementation covers the preregistered core 22 features, predictive
horizon studies, canonical rule backtests, execution costs, regimes, chronological
splits/walk-forward, redundancy diagnostics, bootstrap/Deflated-Sharpe diagnostics,
forward snapshots, append-only artifacts, and integrity/causality tests. Exhaustive
catalog expansion, CPCV/PBO, model combinations, and production-language signal
ports remain deliberately gated until standalone OOS evidence exists.
