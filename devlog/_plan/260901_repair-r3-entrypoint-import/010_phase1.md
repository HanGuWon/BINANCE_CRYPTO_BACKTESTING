# 010 — Phase 1 (repair-r3-entrypoint-import)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

(fill in: exact file paths with before/after diffs — a copy-paste-executable PRD)

## TESTS

(fill in: test files + cases)

## Verification (C)

(fill in: exact commands + expected exit codes)
# Phase 1 — Reproduce and Audit

Modify: none. Read `scripts/prepare_r3_post_boundary_launch.py`, enumerate every
`scripts.*` import and repo-relative operational path, and preserve the failed
v1 temporal receipt unchanged. Evidence: direct production failure output and
the import/path inventory.

Verification: read-only `rg`/`python` probes and control-root hash comparison.
