# 040 — Phase 4 (reconcile-stale-r3-worktree-v8)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- MODIFY only operations evidence if a fresh receipt is due:
  `campaigns/r3_prospective_context_v1/operations/R3_V8_DAILY_OPERATIONS_RECEIPTS.jsonl`
  (append one UTC record, never rewrite prior lines).
- Reuse existing `ops/r3/launch_r3_v8_resume.ps1`, `watch_r3_v8.ps1`, service
  qualification, and runbook; do not create v9 or alter `scripts/src/tests/configs`.
- DELETE: none; leave raw records, manifests, seals, and old launch evidence intact.

## TESTS

- `python -m pytest -q ops/r3/tests/test_operations_layer.py` and
  `python ops/r3/verify_ops_layer.py`.
- Read-only watchdog/final-audit checks for one writer, fresh cycles, chain/seal,
  roster binding, gaps, D free space, session independence, and forbidden-field
  exclusion.

## Verification (C)

- Require `authorized_writer_count == 1`, chain PASS, seal SEALED, current root and
  roster exact, and no outcome access. A live restart is skipped if evidence risk is
  non-trivial and documented as `SAFE_SKIP_LIVE_RESTART`.
- Verify launcher uses absolute paths, fail-closed v8 resume, lock collision exit
  73, and native Startup/Task Scheduler status without credentials.
