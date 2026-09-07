# Phase 2 — forceOrder identity and replay-safe accounting

## Scope and firewall

This unit freezes the metadata-only identity contract for Binance UM
`forceOrder` envelopes. It may inspect field names and synthetic fixtures, but
must not parse or report historical event values, response values, returns,
performance, holdout, or R2B2 data. The live collector remains running and its
D-backed root is not rewritten.

## Canonical candidate identity

The collector stores the decoded event under `payload` and records the market,
symbol, exchange event time, sequence metadata, and receipt metadata in the
envelope. The endpoint-specific forceOrder schema requires payload `e` to be
exactly `forceOrder`, payload `E` to be a non-negative integer number of
milliseconds, and nested order `T` to be the non-negative integer order/event
time in milliseconds. Lowercase `t` is an optional trade/order identifier; it
is never a timestamp alias or a fallback for missing `T`. If a payload omits
`T`, it is invalid; a legacy payload presenting only `t` is not silently
accepted.

The canonical identity tuple, in this exact order, is:

`market_type, symbol, E_ms, T_ms, t_trade_id, S, o, f, q, p, ap, X, l, z, ps, st`.

`S` is the forced side; `o` order type; `f` time-in-force; `q` original
quantity; `p` order price; `ap` average fill price; `X` order status; `l` last
filled quantity; `z` accumulated filled quantity; `ps` position side; and `st`
the UM/CM subtype. `t_trade_id` and the other optional fields use explicit
`null` placeholders when absent. Missing identity-critical fields
(`market_type`, envelope `symbol`, nested `o.s`, `e`, `E`, `T`, or `S`) are
invalid and cannot be repaired with requested symbol, receipt time, or
sequence id. Envelope and nested symbols must match after uppercase/outer-
whitespace normalization.

Canonicalization is deterministic. Envelope `market_type` accepts a string
only; after outer-whitespace removal and ASCII case-folding it must be `um`,
whose canonical value is lowercase `"um"`. Numeric `1`, booleans, CM, and
unknown values are invalid. Symbols are trimmed and uppercased. Enum strings
are trimmed and uppercased (`e` remains the exact `forceOrder` token). The
optional UM subtype `st` accepts only `1`, `"1"`, `"UM"`, `"USD-M"`, or
`"USDⓈ-M"` (canonical `"UM"`); absent/null is canonical `null`, and CM or
unknown subtype values are invalid. Lowercase `t` is an optional trade/order
identifier: a non-negative integer or base-10 integer string is accepted,
booleans/fractions/exponents/signs/NaN/infinity are rejected, and its
canonical value is a decimal string with leading zeroes removed (`"0"` for
zero), or JSON `null` when absent.

`E` and `T` are required non-negative base-10 integer milliseconds (not
booleans, fractions, exponent notation, NaN/infinity, negatives, or overflow).
`q/p/ap/l/z` and the allowed `b/a` fields use `Decimal` from trimmed text,
reject booleans, NaN, infinity, and negative values, and normalize exponents,
trailing zeroes, and negative zero to fixed plain-decimal strings. The
canonical payload schema is explicit: top-level keys are exactly `e`, `E`,
`o`, with optional `st`; order keys are exactly from
`s,S,o,f,q,p,ap,X,l,z,T,t,ps,st,b,a,m,wt,ot`; required order keys are
`s,S,o,f,q,p,ap,X,l,z,T`; optional order keys are `t,ps,st,b,a,m,wt,ot` and
missing optionals become `null`. Unknown keys are invalid. `m` is a JSON
boolean; `s` is a symbol; and `S`, order `o`, `f`, `X`, `ps`, `wt`, and `ot`
must use the enumerated sets below. The normalized object includes every
allowed key (including null optionals), is serialized as UTF-8 JSON with
sorted keys, compact separators, and `ensure_ascii=False`; raw key order is
irrelevant. The enum allowlists are `S ∈ {BUY,SELL}`, `o,ot ∈
{LIMIT,MARKET,STOP,TAKE_PROFIT,STOP_MARKET,TAKE_PROFIT_MARKET,TRAILING_STOP_MARKET,LIQUIDATION}`, `f ∈ {GTC,IOC,FOK,GTX}`, `X ∈
{NEW,PARTIALLY_FILLED,FILLED,CANCELED,EXPIRED,EXPIRED_IN_MATCH}`, `ps ∈
{BOTH,LONG,SHORT}`, and `wt ∈ {MARK_PRICE,CONTRACT_PRICE}`. Unknown enum
values are invalid. If both top-level and nested `st` are present, their
canonical values must agree.

The replay-safe key is

`forceorder:v2:<lowercase SHA256(canonical_json(identity_tuple))>`.

Collector receipt time, corrected receipt time, websocket sequence id, raw
JSON key order, and transport wrapper fields are excluded from the key so a
replay after restart maps to the same identity. A canonical payload hash is
also retained for collision checking. The payload hash is computed separately
from raw-payload provenance: it hashes the fully normalized schema object above
and excludes only transport wrappers (`stream`, `endpoint`, receipt/sequence
metadata). The raw provenance hash hashes the original payload bytes/JSON
independently.
The canonical tuple and canonical payload JSON are retained alongside the
SHA-256 values, so a digest collision cannot silently merge records.

## Duplicate and collision semantics

The input count is `raw_envelope_count` and the categories are disjoint:

`raw = unique + duplicate + collision + invalid`.

Envelopes with the same identity key and identical canonical identity tuple
JSON and canonical payload hash are replay duplicates and count once in
`unique_event_count`. A key group is a
`FORCEORDER_IDENTITY_COLLISION` when either its canonical identity-tuple JSON
set has cardinality greater than one or its canonical payload-hash set has
cardinality greater than one. This remains a collision even if payload hashes
happen to match but tuple JSON differs. Every member of that group is counted
as collision (the provisional unique is reclassified), the key is excluded
from all H03/H04 minima, and no collision is silently merged.
Missing/invalid identity or timestamp fields are
`FORCEORDER_IDENTITY_INVALID`, not unique events. The invariant is checked on
every result.

For a duplicate group, representative selection is independent of arrival
order: first prefer a finite `COMPLETE` record, then sort by earliest valid
`source_available_time`, `collector_receipt_time`, canonical payload hash, and
raw provenance hash. If no `COMPLETE` record exists, select the earliest valid
gap record and mark the event ineligible. A malformed corrected receipt is an
invalid record, not a silent fallback. This makes replay eligibility and
continuity handling deterministic.

The H03/H04 candidate universe is the set of unique, collision-free,
identity-valid events. For each H-specific endpoint predicate, every
transport-valid record is first classified as `endpoint_eligible`,
`endpoint_invalid`, or `not_in_endpoint_universe`. `raw_endpoint_count_H`
counts eligible and endpoint-invalid records before deduplication, including
replay duplicates. The disjoint H-specific invariant is

`raw_endpoint_count_H = unique_endpoint_count_H + duplicate_endpoint_count_H + collision_endpoint_count_H + invalid_endpoint_count_H`.

`unique_endpoint_count_H` and all evidence minima use one representative only
from collision-free valid identities. Transport-invalid records remain in the
global invalid count and never enter an H endpoint universe. H03 applies its
+15m response predicate; H04 independently requires +15m and +60m.

## Source timing and market safety

`source_available_time` for a forceOrder candidate is
`corrected_response_receipt_time` when present, otherwise
`collector_receipt_time`; an invalid corrected timestamp is an invalid record.
Let `G = {1970-01-01T00:00Z + 15m*k | k ∈ Z}`. `T_exec` is the smallest
`g ∈ G` satisfying `g > exchange_event_time` and `g >
source_available_time`; equality is rejected by construction. H03 requires a
closed COMPLETE 15-minute bar `[T_exec, T_exec+15m]`, with open at `T_exec`
and close at `T_exec+15m`. H04 is an independent incremental closed-bar
window `[T_exec+15m, T_exec+60m]` and requires every intervening 15-minute
bar to be COMPLETE; its response endpoint is
`close(T_exec+60m) / close(T_exec+15m) - 1`. It is not `-H03`, and an event
may qualify for both. Missing/restart/rollover/exact-boundary bars make only
that H endpoint ineligible; no zero is imputed. UM-only validation requires
envelope `market_type=um`, `stream=liquidation`, and an endpoint accepted by
the exact parsed allowlist `wss://fstream.binance.com/market/ws/<stream>`
where `<stream>` is `!forceOrder@arr` or `[a-z0-9_]+@forceOrder` after
case-folding, with no port/userinfo/query/fragment. CM/unknown host/path,
non-forceOrder events, and endpoint/market/symbol mismatches are invalid. A
no-event interval is
`NO_FORCEORDER_EVENT_OBSERVED`, never a synthetic zero event.

## Required synthetic checks

The B implementation and C qualification must prove: exact key stability
under JSON reordering and receipt changes; exact Decimal/integer
canonicalization; T-versus-t handling; explicit null placeholders; exact
duplicate collapse and earliest-valid representative selection; changed
payload collision rejection; missing/invalid-critical-field rejection;
UM/CM/unknown/event-type/endpoint/symbol mismatch rejection; separate
H03/H04 endpoint counts; event/open exact-boundary rejection; and preservation
of the raw/unique/duplicate/collision/invalid invariant. Tests must use
constructed payloads only and must not read the live root.

## Exit evidence

Exit requires a committed helper and synthetic tests, a deterministic receipt
with raw/unique/duplicate/collision/invalid accounting, and a static check
that no response or outcome field is imported. The next phase may then repair
inventory accounting using this key.
