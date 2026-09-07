# 030 — Phase 3 (r3-v8-wp6-closeout-20260907)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- MODIFY: operations tests only, if needed, to assert live receipt schema,
  guardian state/receipt throttling, and immutable synthetic qualification.
- NEW: an operations test receipt under `.codexclaw/evidence/...`; this is
  local orchestration evidence and is not Git content.
- DELETE: none.

## TESTS

- Focused guardian/auth/accounting/synthetic receipt tests (35 expected).
- Full `pytest -q ops/r3/tests` operations suite.
- Full repository `python -m pytest -q` as a read-only regression check; no
  scientific source changes are permitted.

## Verification (C)

- CXC `receipt test` for focused tests: exit 0 and exact final summary recorded.
- CXC `receipt test` for `pytest -q ops/r3/tests`: exit 0.
- CXC `receipt test` for `python -m pytest -q`: exit 0; receipt pins command,
  implementation/source identities, timestamp, and clean scientific scope.
