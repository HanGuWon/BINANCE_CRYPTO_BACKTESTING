# 000 — repair-r3-entrypoint-import: Plan

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## Objective

Repair the direct production entrypoint import bootstrap after the sealed launch
failed at `scripts/prepare_r3_post_boundary_launch.py:190` with
`No module named 'scripts.build_r16_1d_universe'`. Keep the repair limited to
repository-root/src bootstrap, absolute child-script paths, and regression tests;
do not relaunch production or start scientific collection.

## Loop-spec

- Loop archetype: verifier-defined
- Write scope / out-of-scope: modify `scripts/prepare_r3_post_boundary_launch.py`
  and focused tests only; preserve D-backed failed-v1 evidence; no outcome,
  holdout, R2B2, historical-root, or production-run writes.
- Budget / bounds: one repair commit, focused tests, full pytest, then stop.

## Work-phase map (one phase = one full PABCD cycle)

| WP | Doc | Slice | Depends on |
|----|-----|-------|------------|
| phase01 | 010_phase1.md | reproduce failure and audit imports | — |
| phase02 | 020_phase2.md | canonical bootstrap and absolute child path | phase01 |
| phase03 | 030_phase3.md | subprocess/import-closure regression tests | phase02 |
| phase04 | 040_phase4.md | verification, identity commit, v2 preflight | phase03 |

## Accept criteria

- Direct script imports project modules from arbitrary CWD.
- Child collector path is derived from `REPO_ROOT`.
- Failed v1 root remains unchanged; v2 root stays empty.
- Focused/full pytest pass and new source identity is committed.
