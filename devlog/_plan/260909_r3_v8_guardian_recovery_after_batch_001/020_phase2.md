# 020 — Phase 2: sealed evidence, outage episode, and lock classification

## Scope

WP2–WP5. Verify the sealed identity and standing policy before any launch, record this outage separately from earlier Sep-05→Sep-07 accounting, and classify collector and guardian locks without destroying evidence.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_OUTAGE_EPISODE_20260908.json`, with last valid cycle, first missing 15m boundary, recovery boundary, additional missing count, process census reference, and `preserved_gap: true`.
- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_GUARDIAN_LOCK_DISPOSITION_20260908.json`, with guardian-lock path, original content/PID/timestamp (if present), liveness result, and disposition; a missing lock is recorded as absent, not synthesized.
- MODIFY: none; prior outage receipts and the blocked Batch 001 closeout remain immutable.
- DELETE: none. No stale lock is deleted. If an explicitly authorized archival step is needed later, it copies the bytes first and records both paths and hashes.

## Evidence gates

- `& .\ops\r3\launch_r3_v8_resume.ps1 -PreflightOnly` must exit `0` and report exact implementation/source-tree/registry, chain PASS, seal SEALED, valid September roster, and non-RED disk.
- Read the standing policy and verify expiry `2026-10-01T00:00:00Z`; expired/malformed/mismatched policy stops as `R3_V8_RECOVERY_BLOCKED_IDENTITY_OR_EVIDENCE_FAILURE`.
- Reconcile the fresh census with `collector.lock` and `R3_V8_GUARDIAN.lock`: live owner, stale owner, malformed content, and absent lock are separate dispositions. Never infer liveness from PID text.

## Verification

- `python ops\r3\r3_ops.py watch --exact-v8` and the exact preflight output are copied into the new outage/lock receipts with exit codes.
- Manifest-chain and launch-seal hashes are recomputed from the declared files; identity must equal the frozen v8 values in `000_plan.md`.
- The receipt explicitly asserts `outcomes_accessed: false`, `final_holdout: UNTOUCHED`, `r2b2: NOT_ACCESSED`, and `batch_002: NOT_STARTED`.

## Acceptance

No recovery action is permitted until evidence is exact and locks are classified. A live or unknown writer/guardian, duplicate, identity mismatch, or RED disk is a hard block.

