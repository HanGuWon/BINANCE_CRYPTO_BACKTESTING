# 010 — Phase 1 (r3-v3-discovery-launch)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

1. `campaigns/r3_prospective_context_v1/full_pytest_receipt_v3_expected_set_repair.json`
   (read only): reconcile its implementation commit `778ba211...` against final
   HEAD `3d7d0d3`; do not rewrite historical receipt content.
2. `campaigns/r3_prospective_context_v1/R3_V3_IDENTITY_RECONCILIATION_RECEIPT.json`
   (NEW, append-only): record final HEAD/origin, ancestor relationship, scoped
   status, source-tree SHA, registry SHA, and the fact that post-test commit
   `3d7d0d3` changed only the receipt JSON.
3. D roots (external, create only when empty): preserve v1/v2; require empty
   `launch_control\\2026-09-production-v3`, empty
   `engineering_shadow_september_launch_v3`, and absent/empty
   `scientific_raw_v1`. No deletion of unexplained files.

## TESTS

No source behavior change. Existing identity/root guards in
`tests/test_r3_production_wiring.py` remain the regression surface; add only a
receipt-schema assertion if the reconciliation artifact is committed.

## Verification (C)

`git branch --show-current`; `git rev-parse HEAD`; `git rev-parse
origin/research/r2b-restricted-derivatives-v1`; `git rev-list --left-right
--count ...`; `git merge-base --is-ancestor 778ba211... HEAD`; scoped
`git status --porcelain -- scripts src tests configs`; Python source/registry hash
probe; PowerShell root inventory and v1/v2 SHA checks. Expected exit code 0 and
clean scoped output. Commit the reconciliation receipt before A closes.
