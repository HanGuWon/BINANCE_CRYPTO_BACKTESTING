# R3 data contract

Raw records are immutable JSONL envelopes (`schema_version=2`) containing
market, symbol, stream, endpoint, source kind, exchange event time (nullable),
collector receipt time, request parameters, sequence/update identifier,
continuity state, and the untouched payload. Derived records are separate and
must retain source identity, event/receipt/availability/decision timestamps,
feature value, and continuity segment.

Required fail-closed states are `COMPLETE`, `RESTART_GAP`, `POLL_GAP`,
`SOURCE_TIME_UNAVAILABLE`, `SEQUENCE_GAP`, `SCHEMA_ERROR`, and
`RATE_LIMIT_GAP`. No cross-venue substitution, historical top-book synthesis,
daily OI substitution, or liquidation reconstruction is allowed.
