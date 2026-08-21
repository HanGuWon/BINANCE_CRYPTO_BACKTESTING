# R1 verification report

## Scope and scientific status

This is a causal historical-data-panel verification, not a strategy test. No
returns, correlations, Sharpe ratios, indicator rankings, or profitability
claims were computed. The V2.1 baseline remains untouched on `main`.

## Evidence collected

- Published baseline at freeze: `4d7377214ad0fd272911f6247eb612b10ed882b4`, tag `research-harness-v2.1`.
- Official Binance archives: Spot and USD-M BTCUSDT/ETHUSDT, January 2024,
  canonical 15-minute klines. Published and computed SHA-256 values match.
- Anchor panel: 4 raw objects, 11,904 canonical 15-minute rows, plus complete
  1-hour (2,976 rows) and 4-hour (744 rows) derived rows across both markets
  and anchors. No internal grid gaps or partial buckets were retained.
- Binance connector evidence: current Spot metadata identifies BTCUSDT and
  ETHUSDT as USDT symbols; current UM metadata identifies both as USDT
  perpetuals and reports onboard timestamps. These are schema checks only and
  are not used as historical membership.
- Alpaca connector evidence: BTC/USD and ETH/USD are available through a
  separate crypto asset/bar schema. Alpaca observations were not merged into
  this Binance panel.

## Adversarial checks

The R1 tests cover future as-of observations, future symbol existence,
future-month liquidity changes, delisted-symbol retention in earlier observed
cohorts, incomplete 15m-to-1h/4h resampling, and the complete 22-feature
availability classification. Existing V2.1 tests cover checksum mismatch,
raw immutability, retention fail-closed behavior, funding fail-closed behavior,
and final-holdout sentinels.

## Size estimate before expansion

The four measured 15-minute January anchor archives average about 152 KiB
compressed. A Top-50 Spot+UM campaign over roughly 120 completed months would
be approximately 12,000 monthly objects and about 1.8 GiB compressed at that
observed average, before funding/trades/aggTrades. Derived 1-hour/4-hour
Parquet is expected to add roughly 0.3–1.0 GiB depending on provenance columns.
This is an order-of-magnitude estimate, not a download authorization; the full
universe expansion is intentionally not run in this branch.

## Missing-data classes and blockers

`AVAILABLE` means an integrity-verified archive or complete derived bucket;
`STALE` and `NO_PRIOR_OBSERVATION` are reserved for causal as-of joins;
`HISTORICAL_UNAVAILABLE` is used for short-retention open-interest history and
forward-only depth features. No unavailable history is replaced with zero,
interpolation, another venue, or future data.

The remaining blockers are (1) full completed-history anchor discovery and
download to the frozen cutoff, (2) lifecycle-aware liquid-universe expansion
through Top-50 with delisted cohorts, and (3) archive-backed funding/premium
coverage manifests. COIN-M is deferred until Spot+UM verification is complete.

`final_holdout_status=UNTOUCHED`.

## Verdict

PARTIALLY VERIFIED — DATA PANEL BLOCKERS REMAIN
