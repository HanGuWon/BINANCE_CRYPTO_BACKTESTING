# R3 collection contract

Only Binance public market data is collected. The authoritative primary source
matrix is closed 15-minute UM klines, premium-index klines, premium index,
open interest, book ticker, and continuous `@forceOrder` events. Depth,
aggregate trades, OI history, and taker ratio are diagnostic-only; top-trader
ratio endpoints are excluded when credentials would be required. A force-order event is an event-time
liquidation observation, not a periodic sample; absent events are recorded as
no observation rather than zero.

Every request/response is recorded with raw payload, endpoint, receipt time,
source time availability, and gap status. REST cycles are scheduled on an
absolute UTC 15-minute epoch grid, not by sleeping after work. The collector
calibrates local time against Binance server time with a request midpoint and
retains offset and round-trip evidence.

The authoritative primary set is `klines_15m`, `premium_klines_15m`, `premium`,
`open_interest`, `book_ticker`, and forceOrder. Shadow and scientific modes use
the same primary set and normalizers. Kline availability is
`max(native_close_time, corrected_response_receipt_time)` and eligibility is
the strict rule `source_available_time < next_executable_open_time`.

The collector is append-only, fsyncs each envelope, emits explicit restart,
poll, rate-limit, sequence, schema, and source-time gaps, and never bridges a
gap. A restart requires a fresh warmup. Derived features cannot overwrite raw
records.
