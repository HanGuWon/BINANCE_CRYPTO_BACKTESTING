# 020 — Phase 2 (repair-r3-entrypoint-import)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

(fill in: exact file paths with before/after diffs — a copy-paste-executable PRD)

## TESTS

(fill in: test files + cases)

## Verification (C)

(fill in: exact commands + expected exit codes)
# Phase 2 — Bootstrap and Child Path

Modify `scripts/prepare_r3_post_boundary_launch.py`: define `REPO_ROOT` from
`__file__`, insert repository root and `REPO_ROOT/src` idempotently before local
imports, and use an absolute `REPO_ROOT / "scripts" /
"run_r3_prospective_collector.py"` child path. Do not move/duplicate modules or
change scientific semantics.

Verification: import closure and syntax checks; no production invocation.
