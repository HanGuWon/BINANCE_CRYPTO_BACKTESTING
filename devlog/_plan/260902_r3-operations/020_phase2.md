# 020 — Phase 2: operations layer implementation

## MODIFY / NEW / DELETE

- NEW `ops/r3/launch_r3_v8_resume.ps1`: absolute-path launcher; verifies the sealed v8 manifest through the existing collector entrypoint and starts only the exact v8 command. It relies on the existing scientific PID lock as the sole writer lock; no second mutex is used.
- NEW `ops/r3/watch_r3_v8.ps1` (or `.py` only if required by existing runtime): reads process/cycle/health/chain/seal/disk/gap evidence and emits GREEN/YELLOW/RED without raw payload or returns. Staleness uses `eligible_next_execution_time` and a fixed 120-second grace in calibrated UTC: one missed boundary is YELLOW; two consecutive missed boundaries or a dead lock owner is RED.
- NEW `ops/r3/write_r3_daily_receipt.ps1` (or `.py`): append-only daily operational receipt outside `raw_v1`, guarded by a separate operations lock and atomic append/flush; duplicate day records are rejected rather than overwritten.
- NEW `campaigns/r3_prospective_context_v1/operations/R3_PROSPECTIVE_OPERATIONS_RUNBOOK_V1.md`: service, failure, gap, disk, receipt, duplicate-writer, restart, and October procedures.
- NEW `campaigns/r3_prospective_context_v1/operations/` small receipts/config only; no raw archives or Parquet. Task Scheduler XML is a sanitized template/receipt without user security descriptors or credentials.
- MODIFY/DELETE: none in scientific source and no existing raw/manifests.

## Activation scenarios

- Launcher lock trigger: invoke the launcher twice; second invocation must return a collision status and must not start another collector.
- Chain/seal guard trigger: point the launcher at a copied or mismatched manifest; it must refuse before process creation.
- Watchdog red trigger: use an isolated temporary fixture with a dead PID or broken chain; output RED and never delete/rewrite evidence.
- Staleness trigger: fixture with one missing 15-minute interval -> YELLOW; two consecutive missing intervals or dead process -> RED.
- Single-instance trigger: invoke the launcher while the v8 lock owner is alive; it must return a documented collision code and must not create a second writer.

## Acceptance

All new files use absolute paths, no secrets, v8-only identity, append-only receipts, and explicit prohibited-outcome checks. The runbook states that September roster expires at `2026-10-01T00:00:00Z` and collection suspends with `UNIVERSE_ROLLOVER_GAP` until a separately built October roster is sealed. Every receipt repeats the v8 manifest/seal hashes and `outcomes_accessed=false`.
