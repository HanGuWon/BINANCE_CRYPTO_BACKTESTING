# Work phase wp4 — qualification and closeout

## Sequence

1. Run targeted ForceOrder V2 and V3 contract tests, including
   `python -m pytest -q ops/r3/tests/test_forceorder_v3_contract.py -p
   no:cacheprovider`, and all SOL repair tests.
2. Run the exact V3 verifier command:
   `python ops/r3/verify_r3_forceorder_v3_contract.py`.
   The verifier must invoke the V3 parser, collector adapter, and inventory
   path only on official-shaped in-memory fixtures and report field agreement.
3. Run these exact metadata-only verifiers as separate commands, each with
   exit code 0 and stdout captured under
   `.codexclaw/evidence/<session>/wp4-verifiers/` using the command basename:
   `python ops/r3/verify_r3_registry_contract.py`,
   `python ops/r3/verify_r3_v2_horizon_contract.py`,
   `python ops/r3/verify_r3_inventory_contract.py`, and
   `python ops/r3/verify_r3_forceorder_v3_contract.py`. Do not run
   `ops/r3/verify_ops_layer.py` in this phase because it launches a collector;
   its in-memory contract tests are already in the allowlist below.
4. Before the mandated command, run the executable static/import guard
   `python ops/r3/verify_sol_audit_qualification_allowlist.py --json
   .codexclaw/evidence/<session>/wp4-allowlist.json`. It runs
   `python -m pytest --collect-only -q tests ops/r3/tests -p no:cacheprovider`,
   records every collected nodeid, and AST-scans each test module's imports and
   call sites. The allowlist admits only `tests/` and `ops/r3/tests/` modules
   that use `tmp_path`/in-memory fixtures or repository metadata docs; it
   rejects any import/call that opens a persisted outcome/return/checkpoint
   trade/final-holdout/live-v8 raw path (`read_parquet`, `read_feather`,
   `read_pickle`, `r2a2/checkpoints`, `scientific_raw_v8`, `final_holdout`),
   and emits `skipped_nodeids` plus `skipped_count` without executing skipped
   tests. The only permitted checkpoint strings are synthetic temporary paths
   in `tests/test_r2a2_aggregation.py` and guard-rejection assertions. The
   guard itself never follows a D: root or starts a process. A zero skipped
   count is required for the current suite; any nonzero count blocks the full
   run and is recorded rather than silently ignored.
5. Run the mandated command exactly:
   `python -m pytest -q tests ops/r3/tests -p no:cacheprovider`.
   Capture complete stdout/stderr and exit code in
   `.codexclaw/evidence/<session>/wp4-full-pytest-run1.txt`; the command is
   executed only after the guard passes.
6. Repeat the read-only qualification with the same guard and full command.
   Save run two stdout/stderr at
   `.codexclaw/evidence/<session>/wp4-full-pytest-run2.txt`. Normalize each
   run with `python ops/r3/compare_sol_audit_qualification.py --run1 ...
   --run2 ... --json .codexclaw/evidence/<session>/wp4-qualification-compare.json`:
   strip pytest duration, warning-location paths, and receipt timestamps while
   retaining the final summary line, nodeid/pass/skip counts, verifier JSON,
   source-tree SHA, registry SHA, and canonical report SHA. The comparator
   requires identical normalized bytes and exit code 0 for both runs.
7. Create versioned receipts only after the commands run:
   `campaigns/r3_prospective_context_v1/operations/SOL_AUDIT_WP4_FULL_PYTEST_RECEIPT_20260905_RUN1.json`
   and `..._RUN2.json`, each with command, exit code, full final summary,
   implementation commit, scientific source-tree SHA, registry SHA, timestamp,
   scientific status, and holdout/outcome guards. Write them through the
   immutable writer; if a path exists, identical bytes are idempotent and
   different bytes fail. Add
   `SOL_AUDIT_WP4_RECEIPT_SUPERSESSION_20260905.json` naming the preserved old
   receipt SHA, both replacement receipt paths/hashes, and the reason. The old
   receipt is never edited.
8. Verify the live v8 guard without touching its process or raw root: run
   `python ops/r3/verify_sol_audit_live_guard.py --metadata-only`, which reads
   only repository-side identity metadata (implementation/source/registry,
   launch-manifest/seal SHA, status, `final_holdout_status`, and outcome status)
   from the existing WP0 evidence, never opens D-backed raw files, never checks
   checkpoint existence, and never starts/stops a process. Record its exact
   JSON and exit code in `.codexclaw/evidence/<session>/wp4-live-guard.json`.
   The static/import guard and both pytest receipts must show no outcome module
   or checkpoint reader was invoked; final holdout must remain `UNTOUCHED`.

## Receipt contract

Write a versioned receipt under `campaigns/r3_prospective_context_v1/` only
after the command actually runs. It must include command, exit code, full final
pytest summary, timestamp, implementation commit, scientific source-tree SHA,
  registry SHA, scientific status, and holdout/outcome guards. The old receipt is
  preserved byte-for-byte. A new supersession index names its path/hash, the
  replacement receipt path/hash, and the reason; no immutable receipt is
  numerically edited.

## Final report and stop condition

Write `reports/SOL_AUDIT_REPAIR_FINAL.md` with branch/HEAD, bug disposition,
raw counts, schema evidence, V2/V3 decision, each repair and classification,
the exact allowlist/skip evidence, verifier receipts, both full-pytest receipts,
the normalized comparison, live-guard receipt, and explicit no-outcome
attestation. End exactly in
`SOL_AUDIT_REPAIR_BRANCH_VERIFIED_READY_FOR_MIGRATION_REVIEW` only if every
criterion passes; otherwise name `SOL_AUDIT_REPAIR_BLOCKED_*`. Never run R3
evaluation, R2B outcomes, V9 migration, or final-holdout access as part of this
phase.
