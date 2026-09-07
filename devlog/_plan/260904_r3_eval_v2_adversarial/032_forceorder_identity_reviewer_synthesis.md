# Phase 2 reviewer synthesis — remaining forceOrder blockers

The second independent review found six executable-contract gaps. This note
records the accept decisions before the next re-review; it is not an outcome
artifact and it does not inspect the live D-backed root.

## Accept decisions

1. **Market and trade-id canonical forms.** Envelope `market_type` accepts a
   string only; after outer whitespace removal and ASCII case-folding it must
   equal `um`, and its canonical representation is lowercase `"um"`. Numeric
   `1`, booleans, `cm`, and unknown values are rejected at this layer. The
   optional nested/top-level `st` discriminator has a separate allowlist:
   `1`, `"1"`, `"UM"`, `"USD-M"`, and `"USDⓈ-M"` canonicalize to `"UM"`;
   `2`, CM spellings, and unknown tokens are invalid. Lowercase `t` is an
   optional non-negative integer trade/order id. Integer values and base-10
   integer strings are accepted, booleans/fractions/exponents/signs/NaN/
   infinity are rejected, and the canonical value is a decimal string with
   leading zeroes removed (`"0"` for zero), or JSON `null` when absent.

2. **Enumerated payload schema.** A forceOrder payload has exactly top-level
   keys `e`, `E`, `o`, and optional `st`; unknown top-level keys are invalid.
   The order object has the allowed set
   `s,S,o,f,q,p,ap,X,l,z,T,t,ps,st,b,a,m,wt,ot`; unknown nested keys are
   invalid. Required order keys are `s,S,o,f,q,p,ap,X,l,z,T`; optional keys
   are `t,ps,st,b,a,m,wt,ot`. The canonical payload hash is built from a
   normalized object containing every allowed key (missing optionals become
   `null`) and therefore has no implementation-dependent omission policy.
   `E/T/t` use integer rules; `q,p,ap,l,z,b,a` use non-negative Decimal
   rules; `m` is a JSON boolean; `s` is a symbol; and `S,o,f,X,ps,wt,ot`
   use the explicit enum sets in 030. `st` is the UM discriminator above.

3. **Digest collision guard.** A key group is a collision if either its
   canonical identity-tuple JSON set has cardinality >1 *or* its canonical
   payload-hash set has cardinality >1. This remains a collision even when
   payload hashes happen to match but tuple JSON differs. Every member is
   classified as collision and excluded from unique/H03/H04 minima. Retained
   tuple JSON and canonical payload JSON make the comparison explicit.

4. **Exact endpoint allowlist.** Parse the endpoint with a URL parser. Accept
   only `wss`, host `fstream.binance.com` (no port/userinfo/query/fragment),
   path `/market/ws/<stream>`, and a final stream token matching either
   `!forceOrder@arr` or `[a-z0-9_]+@forceOrder` after case-folding. The
   envelope stream must be exactly `liquidation` after trim/case-folding. No
   substring, CM host, unknown path, or transport-wrapper fallback is valid.
   Side, order-type, time-in-force, status, position-side, and `wt/ot` enum
   values are checked against the sets in 030; unknown values are invalid.

5. **Per-hypothesis raw/unique counts.** For each H03/H04 endpoint predicate,
   first classify every transport-valid input record into exactly one of
   `endpoint_invalid`, `endpoint_eligible`, or `not_in_endpoint_universe`.
   `raw_endpoint_count_H` counts both eligible and endpoint-invalid records
   in that H-specific universe, before deduplication and including replay
   duplicates. After identity grouping, the disjoint accounting is
   `raw_endpoint_count_H = unique_endpoint_count_H + duplicate_endpoint_count_H + collision_endpoint_count_H + invalid_endpoint_count_H`.
   `unique_endpoint_count_H` and all minima use one representative only from
   collision-free valid identities. Transport-invalid records are counted in
   the global invalid total and never enter an H endpoint universe.

6. **Closed endpoint equations and gap handling.** Let
   `G = {1970-01-01T00:00Z + 15m*k | k ∈ Z}` and
   `T_exec = min {g ∈ G : g > exchange_event_time and g > source_available_time}`.
   Equality is rejected by the strict inequalities. H03 requires the closed
   15-minute bar `[T_exec, T_exec+15m]`, with open at `T_exec`, close at
   `T_exec+15m`, and COMPLETE continuity. H04 is an independent incremental
   response `[T_exec+15m, T_exec+60m]`, using
   `close(T_exec+60m) / close(T_exec+15m) - 1`, requiring every intervening
   15-minute bar to be closed and COMPLETE. H04 is not `-H03`; the shared
   +15m boundary may qualify the same event for both hypotheses. Any missing,
   restart, rollover, or exact-boundary bar makes only that H endpoint
   ineligible and never creates a zero observation. Raw/unique endpoint counts
   apply the predicates before/after the identity partition exactly as in item
   5.

The 030 plan and its closure 031 are patched to these decisions before the
same reviewer is asked for a final PASS/remaining-blocker verdict.

