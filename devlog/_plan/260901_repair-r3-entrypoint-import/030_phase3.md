# 030 — Phase 3 (repair-r3-entrypoint-import)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

(fill in: exact file paths with before/after diffs — a copy-paste-executable PRD)

## TESTS

(fill in: test files + cases)

## Verification (C)

(fill in: exact commands + expected exit codes)
# Phase 3 — Regression Tests

Modify `tests/test_r3_production_wiring.py` (or the smallest adjacent test file)
to run the real entrypoint as a subprocess from a neutral CWD using a
non-mutating preflight/import mode, and to assert all production callback
dependencies resolve without proof-lambda bypasses. Tests must not acquire live
data or launch a collector.

Verification: focused R3 tests and explicit no-side-effect assertions.
