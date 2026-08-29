# R3 collection contract

Only Binance public market data is collected. The primary source matrix is
closed 15-minute UM klines, premium index, open interest, book ticker, depth,
aggregate trades, and continuous `@forceOrder` events. OI history and taker
ratio are diagnostic context only; top-trader ratio endpoints are excluded
when credentials would be required. A force-order event is an event-time
liquidation observation, not a periodic sample; absent events are recorded as
no observation rather than zero.

Every request/response is recorded with raw payload, endpoint, receipt time,
source time availability, and gap status. REST cycles are scheduled on an
absolute UTC 15-minute epoch grid, not by sleeping after work. The collector
calibrates local time against Binance server time with a request midpoint and
retains offset and round-trip evidence.

The collector is append-only, fsyncs each envelope, emits explicit restart,
poll, rate-limit, sequence, schema, and source-time gaps, and never bridges a
gap. A restart requires a fresh warmup. Derived features cannot overwrite raw
records.
