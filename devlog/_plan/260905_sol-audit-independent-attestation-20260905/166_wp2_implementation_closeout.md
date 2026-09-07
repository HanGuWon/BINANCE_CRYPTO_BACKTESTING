# WP2 — Sealed-v8 resume authorization implementation closeout

Date: 2026-09-07 KST  
Implementation commit: `ae69efa` (`ops: gate sealed v8 resume with single-use authorization`)

## Scope

This change is operations-only. It does not alter the sealed scientific
collector, raw history, roster, launch manifest, launch seal, or any outcome
code. The scientific source identity remains the v8 identity pinned by
`verify_identity`.

## Implemented gate

`ops/r3/r3_ops.py` now supports a strict structured preflight receipt and the
`verify-resume-authorization` command. A resume lease is accepted only when:

- the authorization JSON has the exact schema, UUID, existing-v8 scientific
  mode, bounded validity window, and exact v8 identity hashes;
- the referenced preflight receipt is an absolute path, has the exact schema,
  matching SHA256, a successful no-launch assertion, an untouched final
  holdout, no R2B2 or ForceOrder V3 access, and zero writers;
- the current writer census is zero, with no active collector lock or duplicate
  authorized writer.

`--consume` takes a dedicated `single_instance_lock`, re-reads and re-validates
the authorization under that lock, then writes `consumed_at_utc` through an
fsync'd same-directory temporary file and `os.replace`. A second consumer or
any failed validation cannot launch the collector.

The PowerShell resume wrapper now requires `-AuthorizationReceipt` for a real
resume and enforces:

`preflight → consume authorization → immediate preflight → collector once`.

`-PreflightOnly` remains read-only and does not require a lease. Missing,
malformed, expired, mismatched, or failed leases fail closed before any
collector call.

## Qualification evidence

`pytest -q ops/r3/tests/test_operations_layer.py` — **12 passed**.

The tests cover atomic single-use consumption, missing/mismatched preflight,
identity drift, active-writer rejection, immutable receipt creation, and an
actual PowerShell subprocess proving missing-auth, verifier-failure, and
success ordering with exactly one collector call.

No collector was resumed in WP2. The existing v8 dead-state and 87-cycle gap
are unchanged.
