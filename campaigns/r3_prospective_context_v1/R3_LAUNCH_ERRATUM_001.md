# R3 launch erratum 001 — conformance repair required

The previous `READY_FOR_PROSPECTIVE_COLLECTION` label is superseded
operationally by `R3_LAUNCH_BLOCKED_CONFORMANCE_REPAIR`. No scientific raw
collection may start until this erratum is resolved and a new launch manifest
is frozen. Historical R2A.2/R2B conclusions and the final holdout remain
untouched.

## Pre-outcome issues

**A — rate limit.** The earlier `50 * 7 * 100 / 15 = 2333.33` smoke formula
used a Spot-style 2,400 denominator and an invented per-request reservation.
R3 must query USDⓈ-M `/fapi/v1/exchangeInfo` at launch, retain its returned
`rateLimits`, and use a verified endpoint-weight table with substantial
headroom.

**B — response telemetry.** `BinanceRestClient.get()` currently returns only
decoded JSON. It discards HTTP status, `Retry-After`, `X-MBX-USED-WEIGHT-*`,
request start, receipt time, and latency. The launch contract therefore cannot
claim rate telemetry. A metadata-returning method and deterministic 429/418
handling are required.

**C — canonical price.** The six R3 hypotheses refer to `close_t`, symbol
returns, and BTC returns, but the seven snapshot streams do not freeze a
completed-candle source. Public USDⓈ-M `/fapi/v1/klines?interval=15m` must be
the canonical closed-bar source, and forming candles must be rejected.

**D — depth continuity.** R3 currently polls `/fapi/v1/depth`; it does not
run a diff-depth WebSocket. REST depth snapshots are therefore independent
snapshots, not sequence-contiguous local-book evidence. Only a later true
diff-depth implementation may claim `U/u` synchronization.

**E — storage.** The previous 3,592-byte result used a synthetic client and is
engineering smoke only. Real pilot payloads must supply per-stream byte
quantiles and conservative 24h/7d/30d/90d projections.

This erratum is a prerequisite to any corrected launch identity.
