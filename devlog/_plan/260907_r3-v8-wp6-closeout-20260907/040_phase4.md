# 040 — Phase 4 (r3-v8-wp6-closeout-20260907)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- MODIFY: none in scientific scope.  Commit only intentional operations,
  governance, receipts, and closeout documentation created by WP6.
- NEW: `devlog/_plan/260905_sol-audit-independent-attestation-20260905/181_wp6_closeout_receipt_20260907.json`
  containing branch/HEAD, guardian and collector evidence, all hashes, test
  receipts, and the exact final state.
- DELETE: none; `.codexclaw` evidence and research data remain untracked.

## TESTS

- `git diff --check` on the intentional allowlist.
- `git status --short -- scripts src tests configs` is empty.
- Re-read continuation/firewall/synthetic receipts and verify final-holdout and
  outcome firewall fields without opening excluded performance artifacts.

## Verification (C)

- Commit the allowlist with one normal commit; no force push and no data files.
- `git status` shows only pre-existing/untracked non-scientific evidence outside
  the intentional commit; scientific source status remains clean.
- Final closeout receipt and CXC criterion c-5 evidence are written only after
  the guardian is still alive, the collector is still producing cycles, chain /
  seal remain valid, and migration/outcomes/holdout remain untouched.
