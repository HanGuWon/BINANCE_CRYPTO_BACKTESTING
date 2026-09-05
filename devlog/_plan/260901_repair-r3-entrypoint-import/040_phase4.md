# 040 — Phase 4 (repair-r3-entrypoint-import)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

(fill in: exact file paths with before/after diffs — a copy-paste-executable PRD)

## TESTS

(fill in: test files + cases)

## Verification (C)

(fill in: exact commands + expected exit codes)
# Phase 4 — Final Verification and Freeze

Run focused and full pytest, verify the failed v1 root is immutable, reserve an
empty `launch_control/2026-09-production-v2` root, compute the new scientific
source hash, commit the repair, and perform a non-mutating arbitrary-CWD
preflight. Do not run `--execute-production`.

Verification: test receipts, git identity/status, root listings, and final
repair receipt.
