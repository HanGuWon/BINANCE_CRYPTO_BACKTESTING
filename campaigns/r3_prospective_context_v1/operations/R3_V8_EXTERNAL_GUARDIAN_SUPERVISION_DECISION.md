# R3 v8 External Guardian Supervision Decision — 2026-09-08 outage

## Decision

Select the existing per-user Startup shortcut as the single external guardian supervisor for the sealed-v8 collection. Do not register or enable Task Scheduler, a service, a second Startup loop, or a recursive watchdog.

Selected shortcut:

- path: C:\Users\user\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\R3-Prospective-Scientific-v8.lnk
- validation command: ops\r3\install_r3_v8_startup.ps1 -ValidateOnly
- validation result: exit 0, Valid=True
- target: canonical powershell.exe
- arguments: canonical ops\r3\run_r3_v8_guardian.ps1 -Persistent -PollSeconds 300
- working directory: repository root
- authority: relaunches the guardian only; it cannot mint collector child leases

## Alternatives and non-competition

Get-ScheduledTask -TaskName R3-Prospective-Scientific-v8 returned no registered task. ops\r3\register_r3_v8_task.ps1 -ValidateOnly returned exit 0, but that command only validates a prospective task definition and did not register one. Task Scheduler is therefore absent and non-competing. No service registration was found. The selected Startup shortcut is the only active external launch mechanism observed.

## Qualification

- R3_V8_GUARDIAN_SYNTHETIC_QUALIFICATION_20260909.json: 17/17 synthetic cases PASS, including duplicate/stale/active lock, identity, chain, seal, disk, roster, child parent/issuer/expiry, persistent re-entry, and receipt throttling.
- Standing policy expiry boundary using policy SHA 6a23cf36e00b15ed5e5a46f1273052e946699a8e21a32b56588c4ae4f82e1e7c: valid before 2026-10-01T00:00:00Z (exit 0); rejected at the exact boundary (exit 1); rejected after the boundary (exit 1).
- The service qualifier observed the task as unregistered (Get-ScheduledTask exit 1) and the Startup shortcut as valid; it did not mutate registration.

## Fail-closed expiry and limitations

After policy expiry, the guardian's standing-policy gate refuses child authorization and the existing Startup action can launch only that guardian. The supervisor does not extend the policy or launch a collector directly. The shortcut covers logon recovery but cannot detect a guardian death during an already-active user session. Therefore the operational disposition is:

R3_V8_COLLECTION_RECOVERED_GUARDIAN_SUPERVISION_HARDENING_PENDING

The current guardian and authorized collector remain alive. No registration change, expiry extension, duplicate supervisor, direct collector launch, backfill, Batch 002, outcome, R2B2, or final-holdout access is authorized in this recovery.