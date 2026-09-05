# Work phase wp4 — qualification and closeout

## Sequence

1. Run targeted ForceOrder V2 and V3 contract tests, including
   `python -m pytest -q ops/r3/tests/test_forceorder_v3_contract.py -p
   no:cacheprovider`, and all SOL repair tests.
2. Run the exact V3 verifier command:
   `python ops/r3/verify_r3_forceorder_v3_contract.py`.
   The verifier must invoke the V3 parser, the collector adapter, and the
   inventory path on official-shaped fixtures and report their field-by-field
   agreement.
3. Run registry, horizon, inventory, and operations verifiers, saving complete
   output and exit codes.
4. Run the mandated command exactly:
   `python -m pytest -q tests ops/r3/tests -p no:cacheprovider`.
   Before execution, run the explicit collection allowlist/guard that skips any
   test opening persisted outcomes, returns, checkpoint trades, final-holdout
   rows, or live v8 raw data; record skipped nodeids and count. Synthetic
   metadata-only checkpoint construction is allowed.
5. Repeat the read-only qualification twice; compare normalized test summaries,
   verifier outputs, source-tree hash, registry hash, and canonical report hash
   byte-for-byte. Volatile receipt/report timestamps are recorded separately
   and excluded from the canonical identity hash.
6. Verify the live v8 metadata guard (without touching its process/root), assert
   through the recorded execution/import allowlist that no outcome module or
   checkpoint reader was invoked, and confirm final holdout remains
   `UNTOUCHED`. Do not inspect checkpoint-path existence or checkpoint contents;
   the audit boundary is enforced by static/import guards and the test receipt.

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
test/verification receipts, reproducibility comparison, live collector state,
and explicit no-outcome attestation. End exactly in
`SOL_AUDIT_REPAIR_BRANCH_VERIFIED_READY_FOR_MIGRATION_REVIEW` only if every
criterion passes; otherwise name `SOL_AUDIT_REPAIR_BLOCKED_*`. Never run R3
evaluation, R2B outcomes, V9 migration, or final-holdout access as part of this
phase.
