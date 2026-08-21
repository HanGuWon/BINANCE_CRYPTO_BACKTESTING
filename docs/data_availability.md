# Binance Data Availability Contract

Verified against the current Binance connector schemas and official documentation
on 2026-08-20. Coverage is discovered at acquisition time and written into every
dataset manifest; these labels are not permission to assume that an object exists.

| Dataset | Historical source | Coverage contract |
|---|---|---|
| Spot klines, trades, aggTrades | Official public daily/monthly archive; REST tail | Long archive; Spot archive timestamps from 2025-01-01 are microseconds |
| USD-M/COIN-M klines, aggTrades | Official public daily/monthly archive; REST tail | Long archive, symbol-dependent |
| Mark/index/premium-index klines | Official futures archive and REST | Long archive, symbol-dependent |
| Funding rate | Official futures archive and paginated REST | Long history where objects/records exist |
| Open-interest statistics | REST plus any explicitly discovered archive objects | REST latest one month only; earlier missing data is `HISTORICAL_UNAVAILABLE` |
| Taker buy/sell volume | REST plus any explicitly discovered archive objects | REST latest 30 days only |
| Top-trader account/position ratios | REST forward collection | REST latest 30 days only; `MARKET_DATA` may require optional API key |
| Best bid/ask, depth, microprice | REST/WebSocket forward collection | Point-in-time/forward only unless raw events were already collected |
| Liquidations | Futures liquidation WebSocket forward collection | Forward only; no fabricated backfill |

Current public futures liquidation streams use `!forceOrder@arr` (or
`<symbol>@forceOrder`) at `wss://fstream.binance.com/market/ws/{stream}`.
After the CM migration Binance documents merged UM/CM payloads with `st=1`
for UM and `st=2` for CM. Raw event symbols are retained and unknown
discriminators are not guessed.

Official archive ZIPs have `.CHECKSUM` sidecars. The downloader refuses a mismatch
and records both the published and computed hash. Archive validity does not imply
economic correctness: continuity and OHLC validation still run after extraction.

Ordinary public depth excludes Retail Price Improvement (RPI) orders and displayed
depth is not guaranteed executable liquidity. Order book reconstruction requires a
REST snapshot plus correctly sequenced depth updates; raw and derived data stay
separate.

The Alpaca connector was used during the implementation audit as an independent
cross-venue schema sanity check. Alpaca observations are not ingested by this
harness, used to fill missing Binance observations, or used to construct
Binance-native features.

Primary references:

- https://github.com/binance/binance-public-data
- https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market
- https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public
