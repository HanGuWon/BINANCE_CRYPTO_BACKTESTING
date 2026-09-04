# Phase 3 — Build V2 Outcome-Blind Inventory and Receipts

## Scope

Extend the existing metadata inventory owner and create new timestamped outputs.
Read only D-backed v8 raw envelope schema/timestamps, health/cycle metadata,
continuity, availability flags, source keys, and verified roster metadata.

## Exact implementation delta

1. Extend `build_r3_evidence_inventory.py` to retain explicit compact gap records
   (category, stream, start/end, source metadata only), cycle IDs/timestamps, and
   verified roster identities/months. Keep raw payload values discarded and retain
   the existing forbidden-token firewall.
2. Add `gap_block_accounting` with exact UTC 6h block IDs and reason categories;
   map multiple gaps in one block once and a boundary-spanning range to both
   blocks. Add raw and primary-eligible H01–H06 counts; do not infer eligibility
   by subtracting aggregate health counters.
3. Refuse overwriting any prior inventory. Write a new
   `R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2_<UTC timestamp>.json`, a matching
   `R3_EVALUATION_READINESS_V2_<UTC timestamp>.json`, and
   `reports/R3_EVIDENCE_ACCRUAL_V2.md`. Include current cycle/calendar/block/gap
   metadata, excluded block IDs, roster-month count, raw/eligible counts, and
   state. Do not include response, return, PnL, ranking, or holdout values.
4. Update current-state index/report with paths and current metadata only; prior
   V1 receipts remain immutable and are referenced as superseded where applicable.

## Activation scenario

Run the builder against the sealed D-backed v8 root after the checker change. The
current live root has explicit restart/source gaps; the generated receipt must show
their exact blocks excluded, preserve descriptive counts, show September as one
verified roster month, and report collection continues with the 30-day/120-block/
two-roster minima unmet.

## Verification

Run the inventory builder with a new output path, then run the V2 checker against
that output/spec/horizon. Parse both receipts and assert `outcomes_accessed=false`,
`final_holdout=UNTOUCHED`, `r2b2=NOT_STARTED`, and no forbidden keys/paths.
