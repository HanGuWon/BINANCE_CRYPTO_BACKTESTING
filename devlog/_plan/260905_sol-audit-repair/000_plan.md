# SOL audit repair — docs-first execution plan

This plan is the diff-level contract for the isolated `codex/sol-audit-repair-v1`
branch. The canonical `research/r2b-restricted-derivatives-v1` checkout and the
live R3 v8 collector remain read-only. No historical outcomes, returns,
performance artifacts, or final-holdout rows may be opened.

## Baseline and gates

- Baseline: canonical `HEAD 9e532aeea014547283776b1728b2222ae1622fad`.
- V2 scientific identity is inspected, not rewritten, until the raw ForceOrder
  schema audit proves a material preregistration defect. The active v8 process,
  PID/lock, raw files, launch manifest, and sealed receipts are never stopped or
  edited.
- Every mutation is confined to this worktree and is committed before the next
  phase. No merge, push, V3 launch, R3 evaluation, R2B outcome run, or holdout
  access is in scope.
- Scientific-source cleanliness is checked with `git status --porcelain --
  scripts src tests configs campaigns/r3_prospective_context_v1`; unrelated
  pre-existing worktree dirt is preserved and excluded from that proof.

## Planned diffs by work phase

| phase | files | exact change and verifier |
| --- | --- | --- |
| wp0 | `devlog/_plan/260905_sol-audit-repair/{000_plan,010_forceorder_provenance,015_forceorder_v3_schema,020_sol_core_repairs,030_sol_provenance_ops,040_qualification_closeout}.md`; a new audit report under `reports/` | Record current V2 contract, horizon-map/registry hashes, six-primary-test matrix, H03/H04 nonredundancy, H01/H05 determinism, H06 orientation, roster/gap/missing-metadata/no-auto-evaluation/no-outcome gates; append the raw ForceOrder census, official Binance schema citations, live lock/process evidence, and exact V2/V3 decision. Read-only commands include `git show`, `python -m pytest ... --collect-only`, registry/horizon/inventory verifiers, `scripts/audit_r2b_premium_coverage.py` input validation, and a concise D-backed metadata census. |
| wp1 | `015_forceorder_v3_schema.md`; preserve `ops/r3/r3_forceorder_identity.py` unchanged and add `ops/r3/r3_forceorder_identity_v3.py`, the V3 adapter seam in `src/binance_research/collector.py` and `ops/r3/build_r3_evidence_inventory.py`, `ops/r3/tests/test_forceorder_identity.py`, `ops/r3/tests/test_forceorder_dependency_matrix.py`, a new V3 matrix/amendment/verifier and official-shaped fixtures; `scripts/audit_r2b_premium_coverage.py` and its tests | Official schema plus raw records establish a material V2 `ps` contract defect, so V2 remains immutable and a versioned V3 parser/matrix path is mandatory; there is no “non-scientific validator repair” fallback. Implement fail-closed top-level/nested `ps` pair handling, `st=1` UM/`st=2` CM routing, pair/symbol normalization, contradictory-field rejection, and deterministic identity/dedup. The parser→collector→inventory/verifier chain must be exercised by official-shaped fixtures and census accounting in this phase; the inventory adapter is added here before later A02 edits. Active v8 bytes are never changed. Harden the R2B premium audit's manifest input contract: reject wrong dataset/market/interval, checksum failure, root conflict, and the historical BTC/ETH-only anchor before scanning. Run targeted metadata tests and commit. Any V3/parser change is `R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`. |
| wp2 | `ops/r3/check_r3_evaluation_readiness.py`, the A02 continuation in `ops/r3/build_r3_evidence_inventory.py`, `src/binance_research/cli.py`, `src/binance_research/splits.py`, `src/binance_research/backtest.py`, `src/binance_research/statistics.py`, `src/binance_research/features.py`, direct CLI callers, `tests/test_r16_semantics.py`, `tests/test_splits_statistics.py`, and new focused tests | Preserve the wp1 V3 inventory adapter, then implement fail-closed A02 metadata accounting; align A04 embargo and positional/index handling to timeframe step across `splits.py` and CLI callers; correct A05 short equity/timeline accounting; make A06 Deflated Sharpe units and moments explicit; use decision-time A07 regime data; make A12 gap-safe feature grouping work with arbitrary indices. Preserve dedicated R3 scientific executors and all historical conclusions. Fixtures must assert exact timestamps, short returns, unit conversions, regime look-back, gaps, NaN, and non-default index behavior. |
| wp3 | `campaigns/r3_prospective_context_v1/{campaign_spec.toml,R3_PROTOCOL.md,multiple_testing_plan.md,metrics_contract.md,promotion_policy.md,R3_EVALUATION_AMENDMENT_V2_REPRODUCIBILITY_MANIFEST.json}` and, where R2B reconciliation is proven, `campaigns/r2b_restricted_derivatives_v1/{R2B_PROTOCOL.md,reproducibility_manifest.json}`; `scripts/aggregate_r2a2.py`, `src/binance_research/reporting.py`, runtime/test configuration, and new provenance/portability tests/reports | Reconcile A08 identities and explicitly list abandoned/stale roots without rewriting verdicts; relabel Top100 output as a Top50-membership subset diagnostic; make generic outputs immutable/content-addressed and reject collisions; repair portable defaults and test discovery. No raw/Parquet/cache/checkpoint files are added. Classify any v8-affecting parser change as `R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`. |
| wp4 | `campaigns/r3_prospective_context_v1/full_pytest_receipt*.json` (versioned, never fabricated), a durable final report under `reports/`, and evidence ledger | Run targeted V2/V3/ForceOrder/repair tests, `ops/r3/verify_r3_forceorder_v3_contract.py`, registry/horizon/inventory/ops verifiers, then the mandated `python -m pytest -q tests ops/r3/tests -p no:cacheprovider` under the explicit metadata-only test allowlist (checkpoint/outcome fixtures are not opened). Repeat qualification twice, compare normalized hashes/results, inspect only metadata for v8/holdout/outcome guards, record exact command/exit code/full summary/implementation SHA/source-tree SHA/timestamp/status, and end in `SOL_AUDIT_REPAIR_BRANCH_VERIFIED_READY_FOR_MIGRATION_REVIEW` or an explicit blocked state. |

## Activation and safety scenarios

The new behavior is activated only by the isolated branch's explicit scripts,
tests, or future human-approved migration. The canonical collector cannot see
this worktree. Any test that imports a historical outcome/return module, opens a
checkpoint, touches `scientific_raw_v8`, or reaches a final-holdout path is a
hard failure. The output of every verifier is saved as a receipt; a failed gate
stops the phase rather than being repaired by assumption. The full pytest
command is safe only with a collection-time allowlist that skips tests whose
fixtures open historical outcomes, returns, checkpoint trades, final-holdout
rows, or live v8 raw data; the allowlist and skip count are themselves recorded.
Synthetic checkpoint fixtures that merely construct metadata may run, but no
persisted checkpoint content may be read.

The plan names `scripts/audit_r2b_premium_coverage.py` explicitly. Its manifest
is authoritative only when it is the R2B `premiumIndexKlines` acquisition
manifest, has the expected market/interval/checksums, and resolves to the
claimed causal root; the historical BTC/ETH-only R1 anchor is a hard failure.
No outcome/performance paths may be imported by this audit.

Receipt and report repeatability uses a canonical normalized payload: volatile
timestamps are stored as metadata but excluded from the identity hash. The
comparison hash covers command, exit code, final summary, implementation,
source-tree, registry, root, and guard fields. Generic output writers use a
content-addressed experiment identity; the same identity with identical bytes
is idempotent, while the same identity with different bytes raises and leaves
the original artifact untouched.

## Required phase handoffs

P→A requires this plan and the independent reviewer assignment. A→B records a
read-only audit verdict. B→C names the completed implementation and test
receipt. C→D includes command output and exit code. D closes to IDLE only after
the evidence ledger and final classification are written.

## Plan-verifier execution evidence (2026-09-05)

These commands were run before this plan named them as gates, as required by
PLAN-VERIFIER-REAL-01. Each line states what the command actually reads.

- `python ops/r3/verify_r3_registry_contract.py` — exit `0`; reads
  `campaigns/r3_prospective_context_v1/trial_registry.csv` directly in
  `ops/r3/verify_r3_registry_contract.py:15-31`.
- `python ops/r3/verify_r3_v2_horizon_contract.py` — exit `0`; reads the V1,
  prior-V2, current V2, horizon map, reproducibility manifest, and superseded
  map named at `ops/r3/verify_r3_v2_horizon_contract.py:14-21` and opened in
  `verify()`.
- `python ops/r3/verify_r3_inventory_contract.py` — exit `0`; reads the V2
  matrix, horizon map, amendment, and manifest named at
  `ops/r3/verify_r3_inventory_contract.py:35-39`, and validates both synthetic
  and actual contract metadata in `main()`.
- `python ops/r3/verify_ops_layer.py` — exit `0` (`R3_OPS_C_CHECK=PASS`); its
  source-defined operational checks cover `ops/r3` and launcher metadata.
- `python -m pytest --collect-only -q tests ops/r3/tests -p no:cacheprovider` —
  exit `0`, `396 tests collected`; the explicit paths observe both repair tests
  and the R3 operations tests.

## Adversarial plan-review synthesis (2026-09-05)

The first independent audit returned `FAIL`; all blockers are accepted as
material and are closed by this amendment rather than waived:

- V2 fallback: accepted. Official/raw evidence makes the old `ps` enum contract
  unsafe, so V2 is frozen and a versioned V3 matrix/parser/amendment is required;
  no metadata-only fallback remains.
- Collector field chain: accepted. The V3 work phase names top-level and nested
  normalization, `st` routing, pair/symbol checks, contradiction rejection, and
  parser→collector→inventory tests.
- Verifier coverage: accepted. A dedicated V3 verifier and official-shaped
  fixtures are required; the existing synthetic inventory verifier is not
  represented as sufficient evidence.
- Plan paths: accepted. R3 paths now name `R3_PROTOCOL.md` and the exact R3
  reproducibility manifest; R2B files are explicitly scoped under the R2B
  campaign directory.
- A04 ownership: accepted. `splits.py`, direct CLI callers, and the named split
  and statistics tests are now in scope.
- Determinism and immutability: accepted. Canonical normalized hashes exclude
  volatile timestamps, and same-identity/different-bytes collisions fail closed.
- Acquisition provenance: accepted. `scripts/audit_r2b_premium_coverage.py`
  and its fail-closed R2B manifest contract are named explicitly.

No blocker is rebutted. This synthesis is the change packet for the same
reviewer's re-audit; it does not authorize implementation or any outcome access.

The second audit's residuals are also accepted:

- Preserve the V2 module/API unchanged and place all corrected behavior in the
  explicitly versioned `r3_forceorder_identity_v3.py` adapter.
- The V3 matrix will map every source key, type, required/optional status, and
  collision rule before code is written; no logical tuple field is implicit.
- The V3 verifier command and parser→collector→inventory execution are explicit
  closeout gates.
- Premium manifest path, archive existence, byte checksums, root identity/hash,
  and immutable output collision checks occur before a panel scan.
- Full pytest uses a recorded metadata-only collection allowlist; no outcome or
  checkpoint content is opened.
- V2 bytes are preserved and a new supersession index records their replacement;
  immutable receipts are never edited in place.

The final re-audit residuals are accepted and amended:

- The V3 field table now maps `o.o` to order type, `o.X` to order status,
  `o.T` to order-trade time, and `o.t` to an explicitly optional trade id;
  the identity tuple uses those exact semantics and never treats `o.o` as a
  timestamp or `o.X` as execution type.
- Closeout no longer checks checkpoint-path existence or contents. It proves
  the no-outcome boundary with a recorded static/import execution allowlist;
  synthetic metadata construction remains distinct from reading persisted
  checkpoint data.

The latest audit residuals are accepted:

- The V3 inventory adapter is now explicitly a wp1 deliverable. wp2 may extend
  the same file for A02 readiness only after the parser→collector→inventory
  chain has been qualified and committed.
- `o.st` precedence is executable: official top-level `st` is required; the
  nested value is an optional mirror or a required legacy fallback when the
  top-level key is absent; both values, when present, must agree and neither is
  defaulted.
