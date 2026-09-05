# 030 — Phase 3: service qualification and restart safety

## MODIFY / NEW / DELETE

- NEW `ops/r3/register_r3_v8_task.ps1` and sanitized Task Scheduler XML template (or an existing approved local mechanism if already present). Registration uses an at-logon trigger, restart-on-failure settings, and `MultipleInstancesPolicy=IgnoreNew`; credentials and security descriptors are never committed.
- NEW operational qualification receipt under `campaigns/r3_prospective_context_v1/operations/`.
- MODIFY/DELETE: none in scientific source, roster, manifest, seal, or raw records.

## Activation scenarios

- Task start trigger: run the exported task command in a controlled shell; it must resolve the same v8 root/manifest/seal and leave the existing writer untouched.
- Restart trigger: production-v8 is never stopped by default. First run a no-stop preflight and qualify launcher collision/resume on an isolated fixture. Only if evidence protection is proven may an operator perform a graceful stop, verify absence, invoke the same v8 resume launcher, and require a `RESTART_GAP` plus no duplicate cycle ID. If risk remains, record `SAFE_SKIP_LIVE_RESTART` and leave the collector running.
- Disk threshold trigger: derive bytes/cycle from the latest nine completed manifest deltas (median, inclusive p95, max; fewer than three observations are marked provisional), read D: free bytes from `Get-PSDrive D`, and classify GREEN (>=30 projected days), YELLOW (7–30), RED (<7).

## Acceptance

The task is restart-on-failure/startup-recovery capable, single-instance protected, and cannot create a fresh scientific root automatically. Qualification receipt includes command, exit code, process identity, gap disposition, and chain/seal status.
