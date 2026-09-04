# Phase 3 — roster-use and source-specific gap/block accounting

## Scope and firewall

This unit changes only outcome-blind governance inventory/readiness logic and
synthetic tests. It may inspect roster identities, timestamps, continuity
states, block ids, and artifact hashes. It must not read response values,
returns, performance, holdout contents, R2B2 artifacts, or run any historical
evaluation. The scientific collector remains running and the D-backed root is
not rewritten.

## Files and exact changes

### MODIFY `ops/r3/build_r3_evidence_inventory.py`

The following names and output shapes are part of the implementation contract
(the current functions are unchanged until the B phase applies this diff):

```python
HYPOTHESIS_SCOPES = {
    "book_ticker": ("R3_H01",),
    "klines_15m": ("R3_H02", "R3_H06"),
    "open_interest": ("R3_H02",),
    "premium": ("R3_H05",),
    "premium_klines_15m": ("R3_H05",),
    "liquidation": ("R3_H03", "R3_H04"),
}

def _gap_scopes(stream: str, state: str) -> tuple[str, ...]: ...
def _scoped_gap_blocks(records: Iterable[dict[str, Any]]) -> dict[str, set[str]]: ...
def _used_roster_identities(
    cycles: Sequence[dict[str, Any]],
    verified_rosters: Sequence[dict[str, Any]],
    complete_rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...
```

`_gap_scopes` returns the stream mapping above and adds `GLOBAL` only for a
`RESTART_GAP`, a canonical `ROLLOVER_GAP`, or a `collector_status` incident.
The legacy spelling `UNIVERSE_ROLLOVER_GAP` is rejected (never normalized).
Each record passed to `_scoped_gap_blocks` carries `start_time`, optional
`end_time`, and a de-duplicated `scopes` list. The function expands inclusive
UTC-6h block ids from start through end and unions them per scope; a repeated
incident touching a block appears once. Duplicate ids inside one incident
are invalid, while overlap across distinct incidents is unioned once.

`_used_roster_identities` matches cycle timestamp to exactly one verified
artifact whose `[effective_start,effective_end)` contains it. If a cycle
contains `roster_sha256`, it must equal that artifact SHA; otherwise the
interval match is the compatibility rule for legacy cycle metadata. A match
is used only when `complete_rows[roster_sha]` contains at least one
symbol-qualified complete observation in the same interval. Each complete-row
mapping is exactly `{symbol, timestamp}`; the symbol must belong to the matched
verified roster membership and the timestamp must be inside its interval.
Same-month artifacts with the same SHA are deduplicated. Overlapping intervals
with different SHAs fail closed; a cycle carrying a SHA must match it exactly.
It returns (i) used identity objects
`{effective_month, roster_sha256, membership, cycle_ids, complete_rows}`, where
`membership` contains the sorted symbol list and its deterministic membership
SHA and `complete_rows` is a symbol-to-count map, and (ii)
rejected/unmatched cycle diagnostics. The month set is derived from the first
result, so duplicate September artifacts/cycles cannot inflate the count.

1. Import `deduplicate_forceorders` and `ValidatedForceOrder` from
   `ops.r3.r3_forceorder_identity`. Convert each raw liquidation envelope to
   the strict UM forceOrder helper input without copying payload values. Emit
   `forceorder_accounting` with the helper's global and H03/H04 raw/unique/
   duplicate/collision/invalid counts, identity key version, and per-block
   unique representative counts. Do not use the previous raw-row hash or
   `observed_forceorder_pressure` for primary counts.
2. Track each cycle's verified roster identity (month, roster SHA, cycle IDs,
   membership) from cycle metadata. A roster month is `used` only when at least
   one eligible primary cycle references that exact verified roster SHA and
   contributes a complete source observation. Emit `verified_roster_months`
   from this used set, retain all verified artifacts separately, and count
   September exactly once. Unused verified artifacts are reported but never
   satisfy the roster-month gate. The raw cycle/roster envelope mapping is
   exact: use `cycle_id`, `cycle_time`, `roster_sha256` (when present), and
   the verified artifact's `[effective_start,effective_end)` interval; require
   complete source rows to carry `(symbol,timestamp)` and prove symbol
   membership; never fall back to a requested-symbol list.
3. Replace the single aggregate `gap_blocks` subtraction with
   `gap_blocks_by_scope`: each explicit timestamped gap maps to every touched
   UTC 6-hour block, deduplicated by `(scope, block_id)`. Scope is the affected
   source/hypothesis (`R3_H01`…`R3_H06`) plus `GLOBAL` when the incident is a
   collector-wide restart. Preserve spanning intervals and never infer gaps
   from an aggregate counter.
4. Emit `usable_blocks_by_hypothesis`, `usable_days_by_hypothesis`, and
   `roster_contribution_by_hypothesis` from source-specific raw block maps after
   removing only that hypothesis' excluded blocks. A block excluded for one
   source remains usable for another source unless its scope is `GLOBAL`.
   Duplicate exclusions are one set operation per scope/block, not one count
   per record. The JSON shapes are exact and deterministic:
   `gap_blocks_by_scope: {scope: [utc_6h_block_id, ...]}`;
   `usable_blocks_by_hypothesis: {H: [block_id, ...]}`;
   `usable_days_by_hypothesis: {H: [YYYY-MM-DD, ...]}`; and
   `roster_contribution_by_hypothesis: {H: {roster_sha: {effective_month,
   complete_count}}}`. Sets never appear in emitted JSON. The contribution
   calculator consumes the symbol-qualified rows and rejects any row outside
   the matched membership before counting it.
5. Keep `calendar.independent_utc_days` and
   `calendar.independent_utc_6h_blocks` as global complete source-calendar
   counts, and add explicit global gates metadata targets (30 complete UTC days,
   120 complete UTC 6-hour blocks). Do not subtract gap counts from global
   totals; emit raw and usable maps separately. The per-hypothesis temporal
   floors are fixed before implementation and are not optimization knobs: every
   H01–H06 must have at least 30 usable UTC-6h blocks, 30 usable UTC days, and
   one complete source record from every used roster SHA. These floors are
   separate from (and in addition to) the global complete-calendar gates.

### MODIFY `ops/r3/check_r3_evaluation_readiness.py`

The checker additions have these exact interfaces:

```python
def validate_scoped_gap_blocks(
    inventory: Mapping[str, Any],
) -> dict[str, Any]: ...

def validate_per_hypothesis_gates(
    inventory: Mapping[str, Any],
    used_roster_identities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]: ...
```

`validate_scoped_gap_blocks` recomputes every interval's inclusive UTC-6h
ids, requires the supplied `utc_6h_block_ids` set to be exactly equal, rejects
duplicate ids and unknown scopes, and returns
`excluded_block_ids_by_hypothesis` as the union of that H's scopes plus
`GLOBAL`. It does not subtract any aggregate counter. The function rejects an
inventory that has positive health/stream gap counters but no explicit
timestamped records.

`validate_per_hypothesis_gates` requires each H entry to contain maps
`usable_blocks`, `usable_days`, and `roster_contribution` keyed by the exact
H names. It checks each map's counts against the declared `MINIMA` block/day
thresholds and requires every used roster SHA to have a positive contribution
for that H. It also checks `calendar.independent_utc_days >= 30` and
`calendar.independent_utc_6h_blocks >= 120` directly. Missing, duplicate, or
non-integer keys fail closed.

1. Require `verified_roster_months` to be the used-month set (or an explicit
   `used_roster_months` field), reject caller-supplied months that are not
   backed by a verified roster identity, and count unique month strings only.
2. Validate `gap_blocks_by_scope` and derive `excluded_block_ids_by_hypothesis`
   by set union, rejecting duplicate or unknown block ids, intervals whose
   block list omits a touched block, and aggregate-only gap claims.
3. Read exact per-H usable block/day/roster maps; require every hypothesis to
   satisfy its declared block/day minima and a positive contribution from each
   used roster month. Require global complete-day >=30 and complete-block >=120.
   Never infer eligibility by subtracting an aggregate gap counter.
4. Continue to enforce the metadata-only firewall, final holdout `UNTOUCHED`,
   R2B2 `NOT_STARTED`, no outcome values, and no materializer import.

### ADD `ops/r3/tests/test_inventory_accounting_v2.py`

Construct fixtures only (no D-root access) covering: one September roster
counted once; an unused verified roster not counted; two overlapping gaps
touching one block; a gap spanning multiple UTC 6-hour blocks; source-scoped
exclusion that leaves another hypothesis usable; global restart exclusion;
per-H day/block/roster minima; and fail-closed missing/duplicate block maps.
Include forceOrder accounting fixtures asserting global/H03/H04 raw, unique,
duplicate, collision, and invalid counts, with the representative bucket based
on normalized exchange event time `E` (never receipt time, availability, or
`T_exec`). The tests must assert no response/outcome field is read and must not
import a materializer or executor.

### ADD governance receipt/report

`ops/r3/verify_r3_inventory_contract.py` will validate the new schema against
synthetic metadata and hash the superseding matrix. It emits no market values
and refuses any output path containing outcome/holdout tokens.

## Exit evidence

Exit requires a committed implementation, synthetic inventory/readiness tests,
and a cxc receipt. The receipt must show exact per-H usable block/day/roster
maps, global 30-day/120-block gate handling, used-roster-month accounting, and
scope-aware gap set unions. No live root or outcome field may be accessed.
