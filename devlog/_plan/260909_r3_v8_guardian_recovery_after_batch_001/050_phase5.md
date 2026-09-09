# 050 — Phase 5: guardian failure analysis and one external supervisor

## Scope

WP12–WP17. Determine why the guardian disappeared without guessing, then select and qualify one external guardian-of-guardian mechanism. The external mechanism may relaunch only the guardian and must fail closed after the standing-policy expiry.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_GUARDIAN_FAILURE_ANALYSIS_20260908.md`, with evidence-backed classification, three considered hypotheses/falsifiers, rejected hypotheses, and UNKNOWN when evidence is insufficient.
- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_EXTERNAL_GUARDIAN_SUPERVISION_DECISION.md`, selecting exactly one authority, documenting disabled/non-competing alternatives, fail-closed conditions, expiry, and qualification result.
- MODIFY: only the selected existing operations entrypoint (`ops/r3/register_r3_v8_task.ps1`, `ops/r3/install_r3_v8_startup.ps1`, or an already-present OS-level launcher) if an actual permission check shows it is needed. Any code/config change must have a focused synthetic test and local commit; no scientific file changes are allowed.
- DELETE: none. Do not remove the existing Startup or Task Scheduler mechanism until the replacement authority is validated and the old one is explicitly documented as disabled/non-competing.

## Failure-analysis hypotheses and falsifiers

- H1 `MACHINE_REBOOT`: falsified by a clean boot/shutdown event log with no reboot in the outage window.
- H2 `USER_LOGOFF` or `PARENT_SESSION_TERMINATED`: falsified by accessible logon/session/process-ancestry evidence showing the parent session survived.
- H3 `GUARDIAN_PROCESS_CRASH` or `WRAPPER_EXIT`: falsified by intact stdout/stderr and an orderly wrapper exit without an exception.
- H4 `CONTROL_PLANE_TERMINATION`: falsified by continuous host/tunnel reachability and no control-plane termination record.
- If records are unavailable or contradictory, classify `UNKNOWN`; never infer a specific cause from elapsed time alone.

## Supervisor decision order and activation

1. Probe per-user Task Scheduler registration/inspection. If permitted, choose one task with `MultipleInstancesPolicy=IgnoreNew`, guardian-only action, canonical identity/policy checks, and expiry guard.
2. If Scheduler is unavailable, validate the existing per-user Startup shortcut as the sole fallback and state explicitly that it covers logon recovery but not mid-session guardian death; this yields `R3_V8_COLLECTION_RECOVERED_GUARDIAN_SUPERVISION_HARDENING_PENDING` unless another allowed external supervisor exists.
3. Never enable Startup plus Scheduler plus service as independent launch loops. The supervisor may not mint collector child authorizations.

## Verification

- `python ops\r3\qualify_r3_v8_service.py` and `pytest -q ops/r3/tests/test_guardian.py ops/r3/tests/test_operations_layer.py` run on synthetic fixtures only; cover zero/multiple guardian, stale/active lock, identity mismatch, expiry, race, and guardian-only relaunch.
- Validate the selected supervisor with `-ValidateOnly`/inspection before registration; record exit code, task/shortcut identity, action, trigger, and no-duplicate proof.
- Test the expiry boundary at `2026-10-01T00:00:00Z`; after expiry the supervisor must refuse relaunch.

## Acceptance

One supervisor authority is selected and qualified, or the exact pending-hardening state is recorded. No recursive watchdog, direct collector launch, or silent expiry extension is allowed.

