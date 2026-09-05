# Phase 3 reviewer synthesis — contract-level closure

The second A review required seven deterministic clarifications. The
decisions below are binding for the B implementation and are reflected in
040.

1. **Temporal floors are preregistered.** Each H01–H06 requires at least 30
   usable UTC-6h blocks, 30 usable UTC calendar days, and at least one complete
   source contribution from every used roster SHA. These fixed structural
   floors are independent of observed counts and are separate from the existing
   per-H observation-count floors. Global complete-calendar gates remain 30
   days and 120 blocks.
2. **Gap duplicates.** Duplicate block IDs *inside one record* are invalid;
   identical blocks across different valid records are unioned once per
   `(scope, block_id)`. Thus overlap is deduplicated, not rejected globally.
3. **Category spelling.** `ROLLOVER_GAP` is the sole canonical rollover
   category in builder, checker, and output. Legacy `UNIVERSE_ROLLOVER_GAP`
   is rejected rather than silently translated.
4. **JSON ordering and shapes.** Sets are serialized as sorted arrays. The
   inventory shape is
   `gap_blocks_by_scope: {scope: [utc_6h_block_id...]}`;
   `usable_blocks_by_hypothesis: {H: [block_id...]}`;
   `usable_days_by_hypothesis: {H: [YYYY-MM-DD...]}`; and
   `roster_contribution_by_hypothesis: {H: {roster_sha: {effective_month, complete_count}}}`.
   Counts are recomputed from these arrays/maps; no implicit set coercion is
   allowed in the checker.
5. **Roster overlap.** Artifacts with the same effective month and the same
   roster SHA are one identity and are deduplicated. Two overlapping intervals
   with different SHAs are an ambiguous roster match and fail closed. A cycle
   with a declared SHA must match it exactly; legacy cycles without SHA use the
   unique interval match only.
6. **Raw forceOrder conversion and bucket basis.** The builder passes exactly
   `market_type`, `symbol`, `stream`, `endpoint`, `payload`,
   `collector_receipt_time`, `corrected_response_receipt_time`, and
   `continuity_state` from each raw envelope to
   `validate_forceorder_envelope`; no requested-symbol or payload-value
   fallback is permitted. Per-block forceOrder representative counts are
   bucketed by the normalized exchange event time `E`, not receipt time,
   availability time, or executable open; source availability is used only for
   strict endpoint eligibility.
7. **Proof coverage.** The synthetic suite must assert forceOrder global and
   H03/H04 raw/unique/duplicate/collision/invalid accounting, including a
   duplicate, collision, invalid record, and no payload-value emission, in
   addition to roster/gap/minima cases.

These decisions close the plan-level blockers. Implementation remains deferred
to the B phase and is still confined to metadata-only governance code.

