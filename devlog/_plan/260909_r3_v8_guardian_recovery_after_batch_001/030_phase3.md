# 030 — Phase 3: guardian-first recovery and future-only resume

## Scope

WP6–WP9. Use the standing recovery architecture to start exactly one canonical persistent guardian first. The guardian, not a manual collector command, must mint and consume one child authorization and launch exactly one collector writer. Missed intervals remain gaps and are never reconstructed.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_GUARDIAN_RECOVERY_20260908.json`, recording the preflight, stale-lock disposition, guardian PID/parent/start command, guardian-lock path and hash, child authorization path/SHA, authorization consumption, collector PID/lock, and outcome firewall.
- MODIFY: none unless an existing operations contract fails a synthetic gate; any such repair is a separate atomic change to `ops/r3/r3_v8_guardian.py`, `ops/r3/run_r3_v8_guardian.ps1`, or `ops/r3/launch_r3_v8_resume.ps1` with a red test first and a local commit.
- DELETE: none.

## Recovery sequence and activation conditions

1. Confirm WP2 exact identity, no live guardian, no live collector, no unknown lock owner, and a valid non-expired standing policy.
2. If the guardian lock is stale, preserve its original bytes and metadata and archive/copy it only through an explicitly authorized, hash-recorded disposition. If it is active, malformed, or uncertain, stop; do not launch a second guardian.
3. Launch exactly one canonical process: `& .\ops\r3\run_r3_v8_guardian.ps1 -Persistent -PollSeconds 300`. Do not call the collector directly.
4. Verify guardian count is exactly one and its lock is alive. When its snapshot has `authorized_writer_count == 0`, the guardian should run `detect -> verify -> preflight -> child authorization -> consume -> authorized launcher -> verify`.
5. Verify one child authorization is consumed exactly once, preflight passes, and one collector writer owns `scientific_raw_v8\control\collector.lock`. A race, duplicate, identity drift, or preflight failure must fail closed.
6. Resume only at the next valid future boundary; append restart/gap evidence and never backfill missed cycles.

## Verification

- Fresh process census: guardian `1`, collector writer `1`, duplicate lists empty, both locks alive.
- Guardian receipt verifier: `python ops\r3\verify_r3_v8_guardian_receipt.py ...` (exact arguments are recorded in the receipt) exit `0`.
- `python ops\r3\r3_ops.py watch --exact-v8`: identity/chain/seal must remain exact; historical gaps may keep the state YELLOW.
- Synthetic fail-closed tests remain green before any production launch: `pytest -q ops/r3/tests/test_guardian.py ops/r3/tests/test_operations_layer.py`.

## Acceptance

The phase is PASS only with one guardian, one authorized writer, one consumed child lease, and preserved gap accounting. Any manual collector launch, duplicate process, or changed high-water is a hard failure.

