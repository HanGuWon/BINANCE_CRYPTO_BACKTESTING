# 000 — reconcile-stale-r3-worktree-v8: Plan

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## Objective

Reconcile the detached `C:\Users\user\.codex\worktrees\ef86\BINANCE 지표용 테스트`
worktree at `9a70508` with the canonical active-v8 repository without rollback,
force-push, historical rewrite, deletion, or stopping the live collector. Prove
the collector's actual source workspace and frozen identity, classify the stale
worktree and `.codexclaw` contents, add an append-only canonical state index and
human-readable current report, and re-verify the existing v8 service using only
operational metadata. Outcomes, returns, PnL, H01-H06 performance, final holdout,
and R2B2 remain out of scope.

Observed failure: a separate worktree appears detached at `9a70508` and reports
an older `f716784` remote-tip context, while the canonical worktree is already on
the active-v8 lineage. The active collector command identifies the canonical
worktree, so stale cleanup must not touch its evidence.

## Loop-spec

- Loop archetype: verifier-defined repair/audit.
- Write scope / out-of-scope: only `devlog/_plan/`, `campaigns/r3_prospective_context_v1/operations/`,
  `campaigns/r3_prospective_context_v1/R3_CANONICAL_STATE_INDEX.json`,
  `reports/R3_CURRENT_STATE.md`, and README/operations documentation as required;
  no `scripts/`, `src/`, `tests/`, `configs/`, raw data, manifests, v1-v7 evidence,
  outcomes, or final holdout changes.
- Budget / bounds: one PABCD cycle per work phase; no reboot; no live restart unless
  immutable evidence is demonstrably safe; leave the authorized collector running;
  all checks use read-only operational metadata and repository hashes.

## Work-phase map (one phase = one full PABCD cycle)

| WP | Doc | Slice | Depends on |
|----|-----|-------|------------|
| wp0 | 010 | enumerate worktrees/copies and active collector identity | — |
| wp1 | 020 | explain stale refs and establish canonical lineage | wp0 |
| wp2 | 030 | preserve stale material and write canonical/current-state docs | wp1 |
| wp3 | 040 | verify durable v8 operations and outcome-blind receipts | wp2 |
| wp4 | 050 | final tests, identity audit, and exact terminal state | wp3 |

## Accept criteria

- All discovered worktrees/copies are recorded; active collector source cwd and
  frozen implementation/source-tree/registry/root/roster/manifest/seal match.
- `9a70508/f716784` is explained from shared worktree/ref/reflog evidence; no
  rollback, `git reset`, `git checkout`, force-push, deletion, or live collector
  stop occurs.
- Canonical index and current-state report classify historical/superseded/invalid
  artifacts without rewriting their bytes; README remains outcome-blind.
- Live v8 has exactly one authorized writer, fresh SCIENTIFIC cycles, chain PASS,
  seal SEALED, and documented gaps; launcher/resume and duplicate protection hold.
- Targeted/full tests and final checks pass with scientific scope clean, no outcome
  access, final holdout untouched, R2B2 not started, and collector still running.

## A-gate audit synthesis (2026-09-03)

- Blocker 1 (under-specified artifacts): the first draft named new JSON/Markdown
  files but did not define their required fields or exact before/after edits.
  Repair: phase 3 now specifies schemas, enumerated classifications, and literal
  README/runbook insertions.
- Blocker 2 (pytest access boundary): the first draft allowed an unrestricted full
  pytest command. Repair: phase 5 makes the existing dated receipt authoritative
  when the scientific scope is unchanged and requires an outcome/holdout/R2B2
  access guard plus receipt-field assertions before any optional rerun.
- Residual (stale safety): the plan now names reset, checkout, force-push,
  deletion, and collector-stop prohibitions explicitly; stale files remain
  untouched and only the canonical worktree may be written.
- Residual (`.codexclaw`): the classification artifact now requires one entry per
  discovered path (or an exact enumerated file list), category, byte count, and
  preserve/no-ignore action, with a deterministic check that no blanket ignore or
  deletion was applied.
