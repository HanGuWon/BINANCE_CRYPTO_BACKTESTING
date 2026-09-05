# 010 — Phase 1 (reconcile-stale-r3-worktree-v8)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- NEW (after the read-only audit):
  `campaigns/r3_prospective_context_v1/operations/R3_WORKTREE_DISCOVERY_20260903.json`
  containing the captured `git worktree`, identity, remote/ref, process, and
  active-source evidence. It must not contain outcome/performance fields.
- NO CHANGE: all scientific files, active `scientific_raw_v8`, manifests, seals,
  rosters, v1-v7 evidence, and the detached worktree contents during discovery.
- DELETE: none.

## TESTS

- Read-only Git commands: `git worktree list --porcelain`, `git rev-parse
  --show-toplevel`, `HEAD`, branch, `branch -vv`, `remote -v`, origin ref,
  bounded `git log`, and `git status --short` for both worktrees.
- Process inspection: WMI/psutil process tree, cwd, command, executable,
  root/roster/manifest/seal and process start time.

## Verification (C)

- All discovery commands exit 0 (or explicitly report an absent optional ref),
  active command path is canonical, and no mutation command is run in this phase.
- `git status --short -- scripts src tests configs` remains empty.
