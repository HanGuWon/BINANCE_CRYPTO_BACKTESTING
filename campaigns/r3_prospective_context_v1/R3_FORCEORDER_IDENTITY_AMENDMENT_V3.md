# R3 ForceOrder identity amendment v3

**Status:** `R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`  
**Scope:** metadata-only parser, routing, inventory, and replay accounting

The V2 ForceOrder amendment remains immutable. The current Binance all-market
payload uses `ps` as the contract pair symbol and `st` as the market subtype
(`1=UM`, `2=CM`). The old V2 contract interpreted those fields as a position
side and UM-only discriminator, so it cannot be silently reused for the
current raw shape. This amendment introduces a new identity; it does not
rewrite the active v8 collector or reinterpret any historical evidence.

## Canonical fields

The parser requires `e=forceOrder`, non-negative integer `E`, an event symbol
`o.s`, and a pair symbol from top-level `ps` or legacy nested `o.ps`. The event
symbol must equal the pair or the pair followed by an underscore-delimited
contract suffix. Subtype `st` is required at top level for the official shape;
`o.st` is a legacy fallback only. When both locations exist they must agree.
Only subtype `1` (UM) and `2` (CM) are accepted. Unknown keys, missing fields,
contradictions, invalid enums, and symbol/pair mismatches fail closed.

The canonical identity tuple is:

```text
(market_type, event_type, event_symbol, pair_symbol, event_time_ms,
 order_trade_time_ms, trade_id, side, order_type, time_in_force, quantity,
 price, average_price, order_status, last_filled_quantity,
 cumulative_filled_qty, subtype)
```

All decimal fields use finite non-negative canonical decimal strings; `q` is
strictly positive. Optional order fields are emitted as `null` when absent,
and `o.t` is never inferred from a timestamp. The replay key is
`forceorder:v3:<sha256(canonical identity tuple JSON)>`, using compact sorted
UTF-8 JSON. Duplicate/replay payloads collapse; a same-key/different-canonical
payload is a collision and fails closed.

## Versioned API and wiring

`ops/r3/r3_forceorder_identity.py` and all V2 signatures remain unchanged.
`ops/r3/r3_forceorder_identity_v3.py` exposes explicit V3 normalizer,
validator, identity-key, and deduplicator functions. The collector adds
`route_liquidation_event_v3` and `observed_forceorder_pressure_v3`; the old
collector functions remain V2-default. The inventory helper accepts
`identity_version="v2"` by default and rejects unknown selectors. Only the
fixture-only V3 verifier selects `identity_version="v3"`.

The verifier compares parser, collector, and inventory fields on official UM,
official CM, legacy nested, contradiction, symbol mismatch, replay, and
collision fixtures. It never reads the active v8 root, a checkpoint, a return,
or a final-holdout row.

## Supersession

This amendment supersedes `R3_SOURCE_DEPENDENCY_MATRIX_V2_FORCEORDER.json`
only for a future V3 identity. The V2 matrix, amendment, tests, and receipts
remain historical records with their original hashes and are not rewritten.
Any future scientific use of V3 requires a new implementation identity,
registry, and qualification receipt.

## Frozen timing, pressure, and continuity equations

For an envelope with corrected response receipt `c` and collector receipt `r`,
the parser sets `source_available_time = c` when `c` is present, otherwise
`source_available_time = r`; it never substitutes the exchange event time for
an unavailable receipt. Let `event_time = E_ms` and let `G15` be the UTC
15-minute grid. The next executable open is the first `G15` boundary strictly
after `max(event_time, source_available_time)`. A source is eligible exactly
when:

```text
source_available_time < next_executable_open_time
```

Equality, a missing timestamp, and any non-`COMPLETE` continuity state are
ineligible (`endpoint_invalid`). The gap states are
`RESTART_GAP`, `POLL_GAP`, `SOURCE_TIME_UNAVAILABLE`, `SEQUENCE_GAP`,
`SCHEMA_ERROR`, `RATE_LIMIT_GAP`, and `CLOCK_UNCERTAINTY_GAP`; a gap is retained
as metadata and never repaired or forward-filled. V3 pressure is

```text
signed_observed_notional = +Decimal(l) * Decimal(ap or p), if S == SELL
                           -Decimal(l) * Decimal(ap or p), if S == BUY
                           undefined, otherwise
```

The public observable sign is therefore `+1` for forced SELL pressure and
`-1` for forced BUY pressure; it is not a trading-side recommendation.
Non-finite numbers, negative decimals, missing required values, and unsupported
enums fail closed rather than becoming zero or `NaN`. Optional fields are
canonical `null`, and `o.t` is never inferred. Duplicate identities collapse
to the deterministic representative; a same-key/different-identity or
canonical-payload collision invalidates every member of the collision group.

