# WP6 roadmap — close R3 v8 recovery accounting and self-healing guardian

Status: docs-only roadmap, 2026-09-07 KST.  This work remains operations-only
and outcome-blind.  The sealed `scientific_raw_v8` collector must remain running
throughout; no historical backfill, restart, migration, R2B2, returns, or
holdout access is authorized.

Roadmap gate: the live census observed one v8 collector (PID 180656) and no
guardian process; the collector is not to be stopped, and exactly one canonical
guardian will be started only after the guarded implementation is installed.

## Invariants to preserve

- Existing v8 identity, launch manifest/seal, roster, registry, and source-tree
  identity remain byte-for-byte and hash-for-hash unchanged.
- Exactly one authorized collector writer may exist.  The guardian is a separate
  single-authority operations process and may only invoke the existing v8 resume
  launcher after all fail-closed gates pass.
- The outcome firewall remains `outcomes_accessed=false`, `final_holdout=UNTOUCHED`,
  `r2b2=NOT_ACCESSED`, and `forceorder_v3_migration=NOT_STARTED`.
- Existing receipts and the current V2 outage accounting/firewall artifacts are
  immutable historical evidence.  Corrections append V3/V7 artifacts and record
  explicit supersession; no prior JSON is edited in place.

## Work packages and proof

1. **Accounting closure (WP6-A).**  Create
   `campaigns/r3_prospective_context_v1/operations/R3_V8_OUTAGE_AND_RECOVERY_20260907_V3.json`
   from the V2 evidence, with explicit formulas `284-197=87`,
   `262-87=175`, `87+175=262`, and `466-204=262`, plus the UTC 44-hour /
   176-step / 175-gap temporal proof.  Preserve the nonqualifying
   `cycle-20260907T033004700902Z` disposition.  Extend the WP5 firewall verifier
   with a V7 append-only receipt that binds the V3 body/file hashes and checks
   the same decomposition.  Add operations tests and immutable V2→V3/V6→V7
   supersession evidence.

2. **Standing policy and per-attempt authorization (WP6-B).**  Add an
   operations-only standing policy with expiry no later than
   `2026-10-01T00:00:00Z`, exact implementation/source/registry/root/manifest/
   seal/roster identity pins, existing-v8-only action, and no credentials.
   Implement detect→verify→immutable preflight→standing-policy verify→atomic
   short-lived single-use child authorization.  Reuse the canonical launcher and
   `r3_ops.verify_resume_authorization` schema; bind child metadata to parent
   policy SHA, identity, preflight receipt SHA, issue/expiry, and a unique UUID.
   Replay, expiry, wrong-parent, wrong-identity, malformed, and non-v8 attempts
   fail closed without launching.

3. **Guardian self-healing and foreground semantics (WP6-C).**  Make the
   persistent guardian mint a child lease only for `RESUME_ELIGIBLE`, retain the
   strict guardian lock, and return to its polling loop after a launcher/collector
   child exits.  Persist a bounded state-transition/heartbeat receipt so a
   persistent healthy state cannot flood the receipt sink.  Keep Startup aimed
   at the guardian and leave Task Scheduler unregistered when unavailable.  Add
   synthetic tests for one guardian, policy/child auth, replay/expiry/wrong
   parent, launcher re-entry, foreground process ownership, state transitions,
   and every required firewall gate.  The destructive live-crash test is recorded
   as a safe skip; it is not simulated by stopping the real collector.

4. **Closeout (WP6-D).**  Re-read the live census without stopping it, verify
   one writer/one guardian/locks, chain PASS, seal SEALED, exact identity, and
   continuing cycles.  Run focused and broader operations tests, verify V3 and
   V7 receipts, and write
   `R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION_20260907_V2.json` with state
   `FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED_AND_OPERATIONS_CLOSED`.
   Commit only intentional operations/governance files, keep scientific source
   status clean, and push the branch normally (never force-push) only after the
   evidence is complete.

## Required final evidence

Record current collector/guardian PID and parent/start/command/lock details;
pre-existing/outage/total missing counts and formulas; V2/V3 and V6/V7
body/file hashes; standing-policy path/SHA/expiry/identity; child authorization
and preflight/replay proofs; the complete synthetic matrix; focused/broader test
counts; chain/seal/identity and continuing-cycle checks; scientific-scope Git
status; and all outcome/holdout/R2B2/ForceOrder firewall fields.  The final
state is `R3_V8_RECOVERY_ACCOUNTING_CORRECTED_GUARDIAN_SELF_HEALING_VERIFIED`
with the ForceOrder V3 migration prerequisite restored, while migration itself
remains not started.
