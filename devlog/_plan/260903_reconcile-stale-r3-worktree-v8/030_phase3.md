# 030 — Phase 3 (reconcile-stale-r3-worktree-v8)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/R3_CANONICAL_STATE_INDEX.json`, an
  append-only current-state index containing canonical HEAD/origin, frozen v8
  identity, root/roster/manifest/seal, current receipts, worktree classification,
  and a supersession taxonomy. Existing receipt bytes are not rewritten.
- NEW: `reports/R3_CURRENT_STATE.md`, generated from the canonical evidence and
  explicitly marking R1/R2A/R2B history, R3 prospective purpose, six hypotheses,
  current v8 collection, and the no-outcome boundary.
- NEW: `campaigns/r3_prospective_context_v1/operations/R3_STALE_WORKTREE_DISPOSITION_20260903.md`
  marking the detached Codex worktree as stale/read-only and naming the no-reset,
  no-delete, no-merge disposition.
- NEW: `campaigns/r3_prospective_context_v1/operations/R3_CODEXCLAW_CLASSIFICATION_20260903.json`
  classifying preserved `.codexclaw` paths as referenced evidence, operational
  state, or disposable session noise without deleting or blanket-ignoring them.
- MODIFY: `README.md` only to add the actual R1 → R2A/R2A.2 → R2B → R3
  prospective structure and state that R3 has no outcome result yet.
- MODIFY: `campaigns/r3_prospective_context_v1/operations/R3_PROSPECTIVE_OPERATIONS_RUNBOOK_V1.md`
  only if stale-worktree/canonical-index references are missing; preserve all
  scientific semantics and existing gap rules.
- DELETE: none.

### Exact schemas and before/after edits

`R3_CANONICAL_STATE_INDEX.json` is a single JSON object with required keys
`record_type`, `recorded_at_utc`, `current_state`, `canonical_repository`,
`canonical_branch`, `canonical_head`, `origin_head`, `ahead_behind`,
`frozen_identity` (implementation/source_tree/registry/root/roster/manifest/seal),
`collector` (source_cwd, writer_pids, writer_count, cycle_count, health_count,
chain, seal, gaps), `receipts` (pytest/operations/final-audit paths),
`supersession_chain[]`, `worktrees[]`, `codexclaw_classification_path`,
`outcome_boundary`, and `prohibitions`. `current_state` is exactly one of the
documented R3 states; `supersession_chain[]` entries each have `artifact`,
`classification` (`CURRENT`, `SUPERSEDED`, `INVALID_SUPERSEDED`, or
`HISTORICAL_EVIDENCE`), and `reason`. It contains no return/performance fields.

`R3_CODEXCLAW_CLASSIFICATION_20260903.json` has `record_type`, `recorded_at_utc`,
`root`, `total_files`, `total_bytes`, `entries[]`, and `ignore_mutation`.
Every `entries[]` element is one discovered path with `path`, `category`
(`A_REFERENCED_EVIDENCE`, `B_OPERATIONAL_STATE`, or `C_SESSION_NOISE`),
`tracked_state`, `bytes`, and `action` (`PRESERVE`, never `DELETE`);
`ignore_mutation` must be `false` and `deleted_paths` must be an empty array.
The 2026-09-03 inventory has 58 files and is enumerated path-by-path in this
artifact, including all `evidence/`, `goalplans/`, `sessions/`, `attest.json`,
`ledger.jsonl`, and `render-observations.jsonl` paths.

`R3_STALE_WORKTREE_DISPOSITION_20260903.md` contains the exact stale path,
HEAD/common-dir/origin/27-behind-0-ahead facts, tracked-modification SHA equality,
empty scientific-scope diff, active-collector exclusion, and the
no-reset/no-checkout/no-merge/no-delete/no-force-push disposition.

`reports/R3_CURRENT_STATE.md` is generated from the index and must include the
literal sections `R1`, `R2A/R2A.2`, `R2B`, `R3 purpose`, `Frozen six hypotheses`,
`Current v8 collection`, `Scientific identity`, `September roster`, `D-backed
root`, `Operational health`, `Outcome boundary`, and `Next milestone`. The
before state is `reports/.gitkeep` only; the after state is this report plus no
other report deletion.

`README.md` before/after diff is limited to one new `## R3 prospective state`
section immediately after `## Research state`, stating that R3 collects
prospective evidence only, has no outcome result, and leaves the historical V2.1
foundation intact. No existing quick-start or research-contract lines are
removed.

The runbook before/after diff adds only a `## Canonical/stale worktree` paragraph
linking the index and disposition, while retaining the existing frozen identity,
gap, service, October, and outcome-prohibition text verbatim.

## TESTS

- JSON parse/schema checks for the new index; path/link existence checks for the
  report and runbook; README diff review for outcome-blind wording.
- `.codexclaw` inventory by path/size and references; classify evidence, operations,
  and disposable session noise without blanket ignore/delete.
- Require an entry for every 2026-09-03 `.codexclaw` file in the classification
  JSON; compare `git check-ignore` results for representative A/B/C paths and
  assert no `.gitignore` diff and no deletion command was issued.

## Verification (C)

- New index contains exactly one current state, explicit historical/superseded/
  invalid classifications, frozen hashes, and no return/performance fields.
- Report/runbook/README agree with the live v8 identity and say evaluation remains
  unauthorized; `git diff --check` passes; scientific scope stays clean.
