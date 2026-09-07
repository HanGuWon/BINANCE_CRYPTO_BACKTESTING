# 040 — Phase 4: final live verification and report

## MODIFY / NEW / DELETE

- NEW final operations receipt and evidence summary under `campaigns/r3_prospective_context_v1/operations/`.
- MODIFY: none in scientific source or raw evidence.
- DELETE: none.

## Verification

Repeat identity, origin sync, source-tree/registry hashes, one-writer lock-owner process tree, current cycle/health/gap counts, manifest-chain verifier, launch-seal verifier, D: capacity, watchdog state, and Task Scheduler task state. Verify the task with `Get-ScheduledTask -TaskName 'R3-Prospective-Scientific-v8'` and `Get-ScheduledTaskInfo -TaskName 'R3-Prospective-Scientific-v8'`; expected `State=Ready`, `LastTaskResult=0`, and settings `MultipleInstancesPolicy=IgnoreNew` from the sanitized task receipt. Run targeted operations smoke checks and `python -m pytest -q` only if `scripts src tests configs` remains clean. Do not stop the live process during final verification.

## Acceptance

Leave the collector running. Report exact PID tree, authorized writer count, cycle/health/gap/reconnect counts, bytes/cycle statistics, free capacity and projections, launcher command, restart result or safe-skip, runbook/receipt paths, `outcomes_accessed=false`, evaluation amendment `NOT_YET_AUTHORIZED`, outcomes `NOT_STARTED`, final holdout `UNTOUCHED`, and R2B2 `NOT_STARTED`.
