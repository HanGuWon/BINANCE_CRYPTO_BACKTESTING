# Phase 2 review closure — forceOrder identity contract

This closure records the disposition of the independent A-review of
`030_forceorder_identity.md`. The live scientific collector and D-backed
context root remain out of scope. No response, return, performance, holdout,
or R2B2 field may be read by this unit.

## Accepted blockers and exact decisions

### 1. Accounting partition

The receipt must enforce the disjoint identity

`raw_envelope_count = unique_event_count + duplicate_envelope_count + collision_envelope_count + invalid_envelope_count`.

Classification is performed after validation and grouping. A key group with
more than one canonical payload hash has *all* of its members classified as
collision; a provisional first member is never left in `unique`. Collision
groups are excluded from H03/H04 eligibility and minima. Invalid records are
not repaired or counted as unique.

### 2. Timestamp and trade-id semantics

`E` and nested order `T` are required, non-negative, base-10 integer
milliseconds. `T` is never replaced by lowercase `t`. Lowercase `t` is an
optional trade/order identifier and is retained in the tuple as `null` when
absent. Booleans, fractions, exponent notation, NaN, infinity, negative
values, and overflow are invalid for `E`/`T`.

### 3. Canonicalization

Envelope `market_type` accepts only a string whose trimmed ASCII case-fold is
`um`, canonicalized as lowercase `"um"`; numeric `1`, booleans, CM, and
unknown values are rejected. Symbols and enum strings are trimmed and
uppercased; event type remains exact `forceOrder`. The optional `st`
discriminator accepts only `1`, `"1"`, `"UM"`, `"USD-M"`, or `"USDⓈ-M"`,
canonicalized as `"UM"`; absent/null is `null`, and CM/unknown values are
invalid. Optional `t` is a non-negative integer/trusted decimal string,
canonicalized to a base-10 decimal string without leading zeroes (`"0"` for
zero), or `null`; booleans, fractions, exponents, signs, NaN, and infinity
are rejected. `E` and `T` are required non-negative base-10 integer
milliseconds with the same rejection rules. Known quantity/price fields
`q,p,ap,l,z,b,a` are non-negative Decimal values normalized from exponent,
trailing zeroes, and negative zero to fixed plain-decimal strings. The
payload top-level schema is exactly `e,E,o` plus optional `st`; nested `o`
keys are exactly `s,S,o,f,q,p,ap,X,l,z,T,t,ps,st,b,a,m,wt,ot`, with required
`s,S,o,f,q,p,ap,X,l,z,T` and optional `t,ps,st,b,a,m,wt,ot`; unknown keys are
invalid and absent optionals become null. `m` is boolean and all listed enums
use their explicit allowlists. The canonical tuple and fully normalized
payload object are UTF-8 compact JSON with sorted keys and
`ensure_ascii=False`; both JSON values and hashes are retained. The enum
allowlists are `S ∈ {BUY,SELL}`, `o,ot ∈
{LIMIT,MARKET,STOP,TAKE_PROFIT,STOP_MARKET,TAKE_PROFIT_MARKET,TRAILING_STOP_MARKET,LIQUIDATION}`, `f ∈ {GTC,IOC,FOK,GTX}`, `X ∈
{NEW,PARTIALLY_FILLED,FILLED,CANCELED,EXPIRED,EXPIRED_IN_MATCH}`, `ps ∈
{BOTH,LONG,SHORT}`, and `wt ∈ {MARK_PRICE,CONTRACT_PRICE}`. Unknown enum
values are invalid; if top-level and nested `st` are both present, their
canonical values must agree.

### 4. Market and transport firewall

Only an unambiguous Binance UM liquidation stream is admissible: envelope
`market_type=um`, `stream=liquidation`, and an endpoint parsed as
`wss://fstream.binance.com/market/ws/<stream>` with no port/userinfo/query/
fragment. `<stream>` must be exactly `!forceOrder@arr` or
`[a-z0-9_]+@forceOrder` after case-folding; substring matches, CM hosts, and
other paths are invalid. Payload `e` must equal exact `forceOrder`; CM,
unknown, endpoint/stream mismatch, non-forceOrder events, and envelope/nested
symbol mismatch are invalid. Side (`BUY|SELL`), order type (the standard
USD-M set), time-in-force (`GTC|IOC|FOK|GTX`), status
(`NEW|PARTIALLY_FILLED|FILLED|CANCELED|EXPIRED|EXPIRED_IN_MATCH`), position
side (`BOTH|LONG|SHORT`), and `wt/ot` enum values are checked and unknown
values rejected. There is no requested-symbol or transport-wrapper fallback.
Stream/endpoint text is excluded from the replay key only after this allowlist
succeeds.

### 5. Replay and provenance

The replay key is

`forceorder:v2:<lowercase SHA256(canonical_json(identity_tuple))>`.

Collector receipt, corrected receipt, sequence metadata, raw key ordering, and
transport wrappers are excluded from the key. A separate canonical payload
hash (and a raw provenance hash) is retained. Corrected receipt timestamps are
used for availability when valid; if a corrected receipt is present but
malformed, that envelope is invalid rather than silently falling back to the
collector receipt. The canonical payload hash is the deterministic tie-break
before raw provenance hash. A group is a collision if its tuple JSON set or
canonical payload-hash set has more than one member, even if one hash happens
to match; all members are collision and excluded.

### 6. Representative and continuity rules

For a duplicate group, representative selection is arrival-order independent:
finite `COMPLETE` first, then earliest valid `source_available_time`,
collector receipt, canonical payload hash, and raw provenance hash. If no
`COMPLETE` record exists, the earliest valid gap record is selected and marked
ineligible. A corrected receipt and continuity/gap status therefore affect
eligibility, not identity.

### 7. H03/H04 endpoint accounting

Let `G = {1970-01-01T00:00Z + 15m*k | k ∈ Z}` and
`T_exec = min {g ∈ G : g > exchange_event_time and g >
source_available_time}`. Equality is rejected. H03 requires a closed COMPLETE
bar `[T_exec, T_exec+15m]` (open at `T_exec`, close at `T_exec+15m`). H04 is
independent and incremental: `[T_exec+15m, T_exec+60m]`, every intervening
15-minute bar closed/COMPLETE, response
`close(T_exec+60m)/close(T_exec+15m)-1`; it is not `-H03`, and the same event
may enter both. Missing/restart/rollover/exact-boundary bars make only that H
ineligible and are never zero-imputed.

For each H, every transport-valid record is classified as
`endpoint_eligible`, `endpoint_invalid`, or outside the endpoint universe.
`raw_endpoint_count_H` includes eligible and endpoint-invalid records before
deduplication (duplicates included), with the disjoint invariant
`raw_endpoint_count_H = unique_endpoint_count_H + duplicate_endpoint_count_H + collision_endpoint_count_H + invalid_endpoint_count_H`.
Only one collision-free valid representative contributes to unique counts and
minima; transport-invalid records stay in the global invalid total.

### 8. Implementation and dependency wiring

The next B phase replaces the current non-replay-safe `_identity` path in
`src/binance_research/r3_materializer.py` only through a governance helper
API, `ops/r3/r3_forceorder_identity.py`, and proves the inventory caller uses
that API. The helper is metadata-only and may not import response or outcome
fields. The existing source dependency matrix is superseded by a versioned
forceOrder identity matrix that pins the exact tuple, canonicalization, and
firewall; the old matrix remains immutable for provenance.

## Required re-review evidence

The same independent reviewer must re-read the updated 030/031 documents and
return `PASS` or a new blocker list. Implementation is not permitted until the
reviewer confirms that the count partition, timestamp distinction,
canonicalization edge cases, UM firewall, representative selection, H03/H04
timing, and replacement API are executable and complete.
