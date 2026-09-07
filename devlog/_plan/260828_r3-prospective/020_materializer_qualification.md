# Causal materializer and replay qualification

`src/binance_research/r3_materializer.py` converts immutable schema-v2 raw
envelopes into a separate derived table. Availability is the receipt time and
must be strictly before a decision. Duplicate identities are dropped
deterministically; out-of-order or explicit gap states create a new continuity
segment and cannot provide a valid feature value. Missing event time and
nonfinite values are retained as fail-closed data-quality states.

Synthetic tests cover polling and restart gaps, sequence gaps, duplicate and
out-of-order events, missing event time, missing OI/liquidation observations,
and nonfinite quantities. No return or performance field is constructed.
