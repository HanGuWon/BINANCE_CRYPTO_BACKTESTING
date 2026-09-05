# Work phase wp1 — versioned ForceOrder V3 schema and provenance chain

## Scientific boundary

The V2 amendment and matrix remain immutable historical records. Binance's
current all-market ForceOrder payload uses `ps` as pair symbol and `st` as the
market subtype (`1=UM`, `2=CM`); the observed raw census contains this shape.
That is a material V2 validator/normalizer defect, not a reason to reinterpret
old V2 evidence. A corrected parser/matrix therefore requires a new scientific
identity: `R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`. The active v8 collector is
not stopped, rewritten, or re-sealed in this work phase.

## Versioned artifacts (new, never overwrite V2)

- `campaigns/r3_prospective_context_v1/R3_SOURCE_DEPENDENCY_MATRIX_V3_FORCEORDER.json`
- `campaigns/r3_prospective_context_v1/R3_FORCEORDER_IDENTITY_AMENDMENT_V3.md`
- `ops/r3/r3_forceorder_identity_v3.py` (the V2 module/API is preserved
  unchanged)
- `ops/r3/verify_r3_forceorder_v3_contract.py`
- `ops/r3/tests/test_forceorder_v3_contract.py`

The new matrix/amendment records the V2 hashes, new hashes, reason for
supersession, accepted UM/CM scope, and exact official-shaped fixture hashes.
V2 files and their receipts remain `SUPERSEDED`/`INVALID` as appropriate.

## Exact parser and field chain

The implementation must exercise one explicit chain:

`raw official payload → collector route/store → parser normalizer → canonical
identity serialization/deduplication → inventory/verifier`.

The parser accepts the documented top-level `e,E,ps,st,o` shape and the
repository's historical nested `o.ps/o.st` shape only when normalization is
unambiguous. The V3 matrix must define each field's source key, type,
required/optional status, and rejection rule before implementation:

| canonical field | source key(s) | type/status | rule |
| --- | --- | --- | --- |
| event_type | top-level `e` | non-empty string, required | must equal `forceOrder` |
| event_time_ms | top-level `E` | integer ms, required | non-negative; event-time identity |
| pair_symbol | top-level `ps` or nested `o.ps` | string, required | top-level/nested must agree; pair, never position-side |
| subtype | top-level `st` required for official shape; nested `o.st` optional mirror and required only for legacy fallback | enum 1/2 | top-level wins; if both exist they must agree; no default when neither exists |
| event_symbol | nested `o.s` | string, required | symbol suffix/pair relation must be valid for subtype |
| side | nested `o.S` | `BUY`/`SELL`, required | exact Binance order-side enum |
| order_type | nested `o.o` | string, required | exact documented order-type enum; never treated as a timestamp |
| time_in_force | nested `o.f` | string, required | exact documented enum |
| quantity | nested `o.q` | decimal string, required | finite, positive |
| price | nested `o.p` | decimal string, required | finite, non-negative |
| average_price | nested `o.ap` | decimal string, required | finite, non-negative |
| order_status | nested `o.X` | string, required | exact documented order-status enum; never treated as execution type |
| last_filled_quantity | nested `o.l` | decimal string, required | finite, non-negative |
| cumulative_filled_qty | nested `o.z` | decimal string, required | finite, non-negative |
| order_trade_time_ms | nested `o.T` | integer ms, required | non-negative; this is the order-trade timestamp |
| trade_id | nested `o.t` | integer/string, optional | canonical null when absent; absence is not inferred from another id |

`ps` is always a pair symbol string; it is never a position-side enum. For
subtype, official payloads require top-level `st`; the legacy nested shape may
provide `o.st` only when top-level `st` is absent, and a payload containing both
must have equal values. `st=1` routes UM and `st=2` routes CM. A contradictory
top-level versus nested pair/subtype, unknown subtype, missing required field,
or symbol/pair conflict fails closed. CM may be routed for metadata census but
is rejected from the UM-only scientific scope with an explicit reason, never
silently counted as UM.

For UM scientific identity, canonical fields are ordered and typed as (the
source-key names above are normative; no field is inferred from a different
timestamp or enum):

`("um", event_type, event_symbol, pair_symbol, event_time_ms,
order_trade_time_ms, trade_id, side, order_type, time_in_force, quantity,
price, average_price, order_status, last_filled_quantity,
cumulative_filled_qty, subtype)`.

The identity key is `forceorder:v3:<sha256(canonical JSON)>`; serialization is
UTF-8 JSON with sorted keys/separators and integer/string canonicalization
specified in the V3 matrix. All fields in the table are either present or have
the specified canonical null; `X` and status-related fields are not omitted.
Duplicate payloads/reconnect replays collapse; same-key different canonical
payloads are collisions and fail closed.

## Exact callable API and default wiring

The historical V2 module and its public call signatures are immutable. The
following V2 functions remain available with their current behavior and are
the default for every existing caller:

```python
def validate_forceorder_envelope(
    envelope: Mapping[str, Any], *,
    complete_bar_opens: Iterable[datetime] = (),
) -> ValidatedForceOrder

def forceorder_identity_key(envelope: Mapping[str, Any]) -> str

def deduplicate_forceorders(
    envelopes: Iterable[Mapping[str, Any]], *,
    complete_bar_opens: Iterable[datetime] = (),
) -> DeduplicationReceipt
```

The corrected adapter is a separate module with an explicit V3 API; it does
not monkey-patch or delegate the V2 functions:

```python
def normalize_forceorder_payload_v3(
    payload: Mapping[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]

def validate_forceorder_envelope_v3(
    envelope: Mapping[str, Any], *,
    complete_bar_opens: Iterable[datetime] = (),
) -> ValidatedForceOrderV3

def forceorder_identity_key_v3(envelope: Mapping[str, Any]) -> str

def deduplicate_forceorders_v3(
    envelopes: Iterable[Mapping[str, Any]], *,
    complete_bar_opens: Iterable[datetime] = (),
) -> DeduplicationReceiptV3
```

The V3 result types mirror the V2 metadata-only receipt fields and add the
canonical market, pair symbol, and subtype. `Mapping`, `Iterable`,
`datetime`, and `Literal` are the normative typing vocabulary; an unknown
identity version or malformed payload fails closed.

Collector adapters are versioned in the same way. These existing functions
remain unchanged and continue to use V2 by default:

```python
def route_liquidation_event(
    payload: dict[str, Any], requested_symbol: str = "ALL", *,
    endpoint: str | None = None,
) -> tuple[str, str]

def observed_forceorder_pressure(
    payload: dict[str, Any], *, endpoint: str | None = None,
) -> dict[str, Any]
```

Only the following new functions select V3, and they do so explicitly:

```python
def route_liquidation_event_v3(
    payload: dict[str, Any], requested_symbol: str = "ALL", *,
    endpoint: str | None = None,
) -> tuple[str, str]

def observed_forceorder_pressure_v3(
    payload: dict[str, Any], *, endpoint: str | None = None,
) -> dict[str, Any]
```

The inventory seam also defaults to V2 and rejects an unknown selector:

```python
def build_forceorder_metadata(
    envelopes: Iterable[Mapping[str, Any]], *,
    identity_version: Literal["v2", "v3"] = "v2",
    complete_bar_opens: Iterable[datetime] = (),
) -> dict[str, Any]
```

`build_inventory(root=DEFAULT_ROOT)` and all existing production callers retain
their V2 behavior. The dedicated V3 verifier is the sole caller that passes
`identity_version="v3"`, and it uses synthetic official-shaped fixtures only;
it never opens or writes the active v8 root. The verifier imports the V3
normalizer, validator, deduplicator, both V3 collector adapters, and this
explicit inventory selector, then asserts field-for-field agreement across
the complete parser → collector → inventory chain. V2 tests continue to import
the original module unchanged.

## Required verification

The V3 verifier must read the new matrix and invoke the same normalizer used by
the collector on official-shaped UM and CM fixtures, including top-level `ps`,
nested legacy `ps`, `st=1`, `st=2`, contradictory fields, symbol/pair mismatch,
duplicate/replay, and collision cases. It must report census counts and
non-silent rejection reasons. Tests must prove parser → collector → inventory
agreement rather than merely hashing a matrix.

The phase also repairs
`scripts/audit_r2b_premium_coverage.py`: supplied manifests must be
`premiumIndexKlines`, expected market/interval, checksum PASS, root-consistent,
and not the historical BTC/ETH-only R1 anchor. The authoritative R2B manifest
path is explicit in the CLI and in tests; before any panel scan, the script must
verify the exact authoritative path, every referenced archive exists, every
archive's byte checksum matches, and the manifest's declared root identity/hash
matches the causal root. Fixed output names become immutable/collision-checked;
invalid or conflicting inputs fail closed before any scan.

V2 files are not edited. A new supersession index/receipt records V2 hashes,
V3 hashes, and the reason for replacement; it never rewrites immutable V2
bytes.

No historical R2B/R3 performance, checkpoint trades, returns, or final-holdout
rows may be read.
