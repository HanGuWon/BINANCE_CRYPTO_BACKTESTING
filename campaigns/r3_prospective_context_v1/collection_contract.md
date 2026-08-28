# R3 collection contract

Only Binance public market data is collected. Public REST snapshots use the
seven streams enumerated in `COLLECTOR_AUDIT.md`; continuous liquidation events
use the public UM market stream. Top-trader ratio endpoints are excluded when
credentials would be required. Every request/response is recorded with raw
payload, endpoint, receipt time, source time availability, and gap status.

The collector is append-only, fsyncs each envelope, emits explicit restart,
poll, rate-limit, sequence, schema, and source-time gaps, and never bridges a
gap. A restart requires a fresh warmup. Derived features cannot overwrite raw
records.
