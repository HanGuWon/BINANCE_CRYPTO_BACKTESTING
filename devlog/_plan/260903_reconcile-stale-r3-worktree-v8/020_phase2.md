# 020 — Phase 2 (reconcile-stale-r3-worktree-v8)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- MODIFY (documentation only): `devlog/_plan/260903_reconcile-stale-r3-worktree-v8/020_phase2.md`
  records verified chronology and ref/worktree classification.
- NEW: no scientific code or data; the canonical index/report are deferred to
  phase 3 after this lineage audit.
- DELETE: none; do not remove the detached worktree or old refs.

## TESTS

- Compare `9a70508`, `f716784`, `ecebc49`, `457106a`, and canonical HEAD with
  `git show`, `git merge-base --is-ancestor`, reflogs, shared `.git/worktrees`
  metadata, and remote/config inspection.
- Hash/compare stale tracked modifications without opening forbidden outcome
  materializations; check scientific-scope status separately.

## Verification (C)

- Prove stale worktree is detached, shares the canonical Git common directory and
  origin, and has no scientific-scope diff; explain `f716784` as the historical
  remote ref observed after the stale worktree was created at `9a70508`.
- Prove `ecebc49` and `457106a` are ancestors of canonical HEAD and origin is in
  parity; verify actual data root is `D:\BINANCE_CRYPTO_BACKTESTING_DATA`.

## Captured finding

The detached path is an abandoned Codex worktree, not an alternate clone. Its
`.git` file points to the canonical worktree common directory and its
`config.worktree` contains only the Codex local-environment marker. It was
created with `HEAD=ORIG_HEAD=9a70508` at `2026-09-02T10:14:15+09:00` and has
remained detached. The shared branch was pushed to `f716784` at
`2026-09-02T11:08:50+09:00` (origin reflog `11:08:52`), then advanced through
the v8 evidence commits to `0a8c5f2`. Therefore a check performed from the
stale worktree at that time correctly saw `f716784` as the then-current remote
tip, but the worktree itself was never synchronized. Current comparison is
`9a70508` detached, `27` commits behind and `0` ahead of canonical origin.

Its only tracked modifications are `.codexclaw/goalplans/repair-the-r3-
prospective-context-v1-launch-cont/goalplan.json` and
`devlog/_plan/260827_r2b-preoutcome-freeze-20260827/030_phase3.md`; both have
the same SHA-256 bytes as the canonical worktree's corresponding uncommitted
files and neither is under `scripts/`, `src/`, `tests/`, or `configs/`.
There are no scientific-scope untracked paths. The worktree is not used by the
collector and will be left untouched/read-only by documented disposition.
