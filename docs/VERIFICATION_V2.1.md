# V2.1 Verification Report

## Environment

- Python 3.11.15

## Test contract

- `python -m compileall -q src tests`: passed
- 39 tests collected
- 39 tests passed

## CLI and build

The following entrypoints were verified:

- `binance-research`
- `python -m binance_research`
- `python -m binance_research.cli`

The fresh wheel build produced `binance_indicator_research-0.1.0-py3-none-any.whl`.

## Synthetic smoke

The V2.1 smoke run wrote `artifacts/synthetic-smoke-v21` and completed with:

- final holdout `UNTOUCHED`;
- no embargo-derived `MISSING_INTERVAL`;
- zero Spot short trades;
- development-only walk-forward;
- experiment evidence `INSUFFICIENT EVIDENCE`.

## Holdout sentinel

Only outer final-test rows were changed to extreme values. Ordinary validation,
predictive, parameter, and walk-forward outputs remained byte-identical. UUIDs,
timestamps, and registry/report metadata were not used for the comparison.

## Official Binance smoke

- Spot BTCUSDT, 1h, January 2024
- 744 rows
- start `2024-01-01 00:00 UTC`
- end `2024-01-31 23:00 UTC`
- published/computed SHA-256 matched:
  `cf873a185bd5b24b8e00034e49583fcb49928e0c3a45c6fc27a632a683655417`
- integrity clean
- final holdout untouched

## Live liquidation smoke

- Endpoint: `wss://fstream.binance.com/market/ws/!forceOrder@arr`
- bounded 30-second handshake succeeded
- 7 events were received and parsed
- no private/account endpoint was used

The event count is a verification observation, not an expected event rate.

## Scientific status

**Experiment Evidence: INSUFFICIENT EVIDENCE**

No profitability claim is made.
