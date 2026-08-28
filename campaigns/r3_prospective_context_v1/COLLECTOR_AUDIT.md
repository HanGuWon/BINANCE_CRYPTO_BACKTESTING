# R3 v1 forward collector audit

The existing collector already preserves raw Binance responses in an
append-only JSONL store and exposes public UM snapshots for open interest,
premium, book ticker, depth, aggregate trades, open-interest history, and
taker long/short ratio. The two top-trader ratio endpoints remain explicitly
excluded from R3 v1 because this code marks them API-key dependent. No account,
balance, position, or order method is present in the R3 path.

## Provenance envelope

Schema version 2 records `exchange_event_time` when supplied by the payload,
`collector_receipt_time` separately, `source_time_available`, symbol, market,
stream, endpoint, request parameters, source kind (REST snapshot or WebSocket
event), sequence/update identifier, continuity state, and the untouched raw
payload. A missing exchange timestamp is represented as
`SOURCE_TIME_UNAVAILABLE`; receipt time is never substituted as event time.

## Continuity and failure states

The accepted states are `COMPLETE`, `RESTART_GAP`, `POLL_GAP`,
`SOURCE_TIME_UNAVAILABLE`, `SEQUENCE_GAP`, `SCHEMA_ERROR`, and
`RATE_LIMIT_GAP`. Sequence tracking rejects non-contiguous updates. WebSocket
reconnects emit a restart-gap control record. REST failures emit poll- or
rate-limit-gap records; no gap is silently bridged.

## Cadence and rate budget

Binance documents a 2,400 request-weight/minute IP limit and requires backoff
after HTTP 429 responses. The R3 public snapshot set has seven endpoints per
symbol. For the conservative, source-independent upper bound of 100 weight
per request, 50 symbols polled every 15 minutes consume
`50 × 7 × 100 / 15 = 2,333.3 weight/minute`, below the 2,400 limit. This is a
worst-case budget, not a performance-tuned cadence; endpoint-specific weights
and response headers must be logged at launch. WebSocket depth continuity is
checked using Binance's documented `U`/`u` sequence rule.

The collector writes one envelope per response. Storage is therefore bounded
by `symbols × public_streams × snapshots × measured_envelope_bytes`; the
launch smoke records actual bytes per stream before any outcome analysis.

Sources: Binance [general REST limits](https://developers.binance.com/en/docs/products/spot/rest-api),
[USDⓈ-M derivatives API](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction),
and [WebSocket depth sequence semantics](https://developers.binance.com/zh-CN/docs/products/spot/testnet/web-socket-streams).
