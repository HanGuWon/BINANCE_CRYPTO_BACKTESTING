# 040 — Phase 4 (reconcile-stale-r3-worktree-v8)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- MODIFY only operations evidence if a fresh receipt is due:
  `campaigns/r3_prospective_context_v1/operations/R3_V8_DAILY_OPERATIONS_RECEIPTS.jsonl`
  (append one UTC record, never rewrite prior lines).
- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_RECONCILIATION_AUDIT_20260903.json`,
  an immutable, timestamped outcome-blind snapshot of the live watch, identity,
  service, and negative-access checks. It must be written once for this phase;
  a rerun uses a new timestamped filename and never overwrites this file or
  `R3_V8_FINAL_OPERATIONS_AUDIT_20260902.json` (the fixed-path legacy writer is
  not invoked).
- Reuse existing `ops/r3/launch_r3_v8_resume.ps1`, `watch_r3_v8.ps1`, service
  qualification, and runbook; do not create v9 or alter `scripts/src/tests/configs`.
- DELETE: none; leave raw records, manifests, seals, and old launch evidence intact.

## TESTS

- `python -m pytest -q ops/r3/tests/test_operations_layer.py` and
  `python ops/r3/verify_ops_layer.py`.
- Read-only watchdog/final-audit checks for one writer, fresh cycles, chain/seal,
  roster binding, gaps, D free space, session independence, and forbidden-field
  exclusion; the new reconciliation audit must reference the captured command
  outputs and include `recorded_at_utc`, `current_head`, `origin_head`,
  `writer_count`, `cycle_count`, `health_count`, `manifest_entry_count`,
  `chain_pass`, `seal_status`, `root`, `roster_sha256`, `watchdog_state`,
  `disk_state`, `restart_disposition`, and explicit negative-access flags.

## Verification (C)

- Require `authorized_writer_count == 1`, chain PASS, seal SEALED, current root and
  roster exact, and no outcome access. A live restart is skipped if evidence risk is
  non-trivial and documented as `SAFE_SKIP_LIVE_RESTART`.
- Verify launcher uses absolute paths, fail-closed v8 resume, lock collision exit
  73, and native Startup/Task Scheduler status without credentials.
- Verify the audit is a new path with no prior bytes changed: `git diff --check`,
  the old final-audit SHA remains unchanged, and the new timestamped receipt is
  the only final-audit artifact referenced by the phase evidence.
