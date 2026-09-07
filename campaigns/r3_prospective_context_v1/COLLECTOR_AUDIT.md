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

Binance's USDⓈ-M `exchangeInfo` response is the launch authority for the
`REQUEST_WEIGHT` limit and must be retained with its response metadata. The
2026-08-28 verification returned 2,400 weight/minute. The rejected historical
smoke formula `50 × 7 × 100 / 15 = 2,333.3` is not a valid budget: it combines
an invented per-request weight with a mistaken cadence denominator and must not
be used for scheduling or a readiness claim. Launch scheduling instead sums the
verified endpoint weights for each request, uses the observed
`X-MBX-USED-WEIGHT-*` headers, and maintains substantial headroom. REST depth
snapshots are independent observations; only a true diff-depth WebSocket may
claim Binance `U`/`u` sequence continuity.

The collector writes one envelope per response. Storage is therefore bounded
by `symbols × public_streams × snapshots × measured_envelope_bytes`; the
launch smoke records actual bytes per stream before any outcome analysis.

Sources: Binance [general REST limits](https://developers.binance.com/en/docs/products/spot/rest-api),
[USDⓈ-M derivatives API](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction),
and [WebSocket depth sequence semantics](https://developers.binance.com/zh-CN/docs/products/spot/testnet/web-socket-streams).
