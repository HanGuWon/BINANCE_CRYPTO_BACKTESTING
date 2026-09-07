# 050 — Phase 5 (reconcile-stale-r3-worktree-v8)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- NEW or append-only: `campaigns/r3_prospective_context_v1/operations/R3_V8_FINAL_OPERATIONS_AUDIT_20260903.json`
  and, if the full suite is rerun, a dated pytest receipt; preserve earlier
  receipts as historical evidence.
- NEW (only if a fresh full suite is required):
  `ops/r3/verify_r3_no_forbidden_access.py`, a deterministic source/test guard
  that rejects outcome/holdout/R2B2 path imports or performance-field reads and
  emits `R3_FORBIDDEN_ACCESS_GUARD=PASS`. It is operations-only and does not
  inspect any forbidden data.
- MODIFY: no scientific source, registry, raw root, manifest, seal, or roster.
- DELETE: none.

## TESTS

- Prefer the existing canonical dated receipt (`331 passed, 1 warning`) because
  the scientific scope is unchanged. Do not rerun pytest solely for this goal.
  If a fresh run is required, first run
  `python ops/r3/verify_r3_no_forbidden_access.py`, then run
  `python ops/r3/run_full_pytest_receipt.py` through `cxc receipt test`, and
  assert the receipt has `outcomes_accessed=false`, `final_holdout=UNTOUCHED`,
  `r2b2=NOT_STARTED`, and the frozen source-tree SHA. The guard and receipt are
  the deterministic boundary; no command may open return/performance files.
- Final direct checks: branch/origin parity, ancestry, worktree/process identity,
  chain/seal, root path, writer count, outcome flags, holdout/R2B2 negative status.

## Verification (C)

- Targeted tests exit 0. A fresh full suite, if run, must exit 0 only after the
  guard passes; otherwise the existing canonical 331-pass receipt remains the
  sole test evidence. Canonical index/report paths exist and parse; scoped Git
  status is clean; no forbidden outcome data is opened.
- Leave the authorized collector running and set the exact evidence-backed terminal
  state, preferably `R3_PROSPECTIVE_COLLECTION_OPERATIONALLY_STABILIZED_VERIFIED`
  only if all gates (including safe resume qualification) truly pass.
