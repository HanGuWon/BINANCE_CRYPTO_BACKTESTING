# R3 v8 Guardian Failure Analysis — 2026-09-08 outage

## Scope

This is an outcome-blind operational incident analysis for the sealed R3 v8 prospective collector after verified Batch 001. It does not read returns, PnL, strategy outcomes, the final holdout, R2B2, or any Batch 002 material.

## Observed outage evidence

- Last completed cycle: cycle-20260908T071504498269Z, completed at 2026-09-08T07:15:36.889838Z.
- First missing executable boundary: 2026-09-08T07:30:00Z.
- Last health record: 2026-09-08T07:15:42.875471Z, collector PID 183660, restart count 57.
- At recovery census, PID 183660 and guardian PID 185608 were absent. Their numeric collector lock and tokenized guardian lock were stale and were preserved with SHA-256 before removal.
- Windows System log recorded Kernel-Power Event 41 at 2026-09-08 16:24:45 KST, Event 6008 and service-start Event 6005 at 16:24:55 KST; OS boot time was 16:24:39.5 KST. This is immediately after the last health record and before the first missing boundary.
- No matching v8 collector or guardian process remained after the reboot. The host, D-backed root, launch-control root, disk, and exact identity were reachable.
- The first recovery attempt exited fail-closed with BLOCKED_GUARDIAN_LOCK_COLLISION because the actual launch-control guardian lock still contained the stale PID/token. The lock was then copied and SHA-verified before removal.

## Competing hypotheses and falsifiers

| hypothesis | evidence | disposition | falsifier / remaining uncertainty |
| --- | --- | --- | --- |
| MACHINE_REBOOT | Kernel-Power 41, Event 6008, Event 6005, and boot time align with the outage window; both process PIDs died and both locks became stale. | PRIMARY SUPPORTED CAUSE | A clean uninterrupted boot record would falsify it; the available records show the opposite. The exact initiating power/OS fault is not known. |
| USER_LOGOFF / PARENT_SESSION_TERMINATED | No logoff/session record was available in the collected evidence. A reboot would also terminate the session. | NOT SELECTED; NOT COMPLETELY EXCLUDED | Session-security event evidence would be needed to distinguish a contributing logoff from the confirmed reboot. |
| GUARDIAN_PROCESS_CRASH / WRAPPER_EXIT | Guardian and collector were absent and stale locks remained; preserved stdout/stderr logs contained no exception. | SECONDARY/UNRESOLVED, not an independent primary cause | A crash dump or orderly-exit record is unavailable. The reboot is sufficient to explain the disappearance. |
| CONTROL_PLANE_TERMINATION | Host and D root were reachable during recovery; no control-plane termination record was found. | NOT SUPPORTED | Tunnel/service logs are incomplete, so this cannot be proved impossible; it is not needed to explain the event. |

## Classification

MACHINE_REBOOT is the evidence-backed primary classification. The record does not claim the precise underlying power or kernel fault. Other hypotheses remain explicitly marked unresolved where evidence is incomplete; elapsed time alone was not used as proof.

## Operational consequence

The historical gap is preserved. Recovery starts at future executable boundaries only. No cycle was reconstructed, no raw-v8 payload was rewritten, and no sealed identity, registry, V3 parser, Batch 001, high-water mark, outcome, or holdout was changed.

## Path correction

The authoritative guardian lock is resolved from r3_ops.V8_CONTROL_ROOT:
D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_V8_GUARDIAN.lock.
The earlier WP2 raw-root path observation is preserved as superseded evidence in the recovery receipt and was not silently rewritten.