# R3 stale worktree disposition — 2026-09-03

## Classification

`C:\Users\user\.codex\worktrees\ef86\BINANCE 지표용 테스트` is an abandoned
Codex worktree, not a second clone. Its `.git` file points at the canonical
repository's worktree metadata and its common directory is:

`C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\.git`

It is detached at `9a70508eafe973405cfad165a0c8598288bc7aa0` with the same
`ORIG_HEAD`. The worktree metadata was created at `2026-09-02T10:14:15+09:00`
and names the historical branch `research/r2b-restricted-derivatives-v1`.

The shared branch reached `f716784661a902126f6bc84198459c817204cd97` at
`2026-09-02T11:08:50+09:00` (origin reflog `11:08:52+09:00`) and later advanced
through v8 evidence and operations commits to canonical `0a8c5f21d882af521511e29643d26ac85f2056b7`.
The stale worktree is therefore `0` commits ahead and `27` commits behind the
canonical tip. The old audit's `f716784` reference was a then-current shared
remote tip observed after the detached worktree had been created, not a second
remote or a live source.

Its two tracked modifications are limited to a `.codexclaw` goalplan and a
pre-outcome devlog file. Their SHA-256 bytes equal the corresponding canonical
working-tree files; `scripts`, `src`, `tests`, and `configs` have no changes or
untracked paths. The active collector's psutil cwd and command point to the
canonical worktree, never this path.

## Disposition

The stale worktree is preserved untouched and treated as read-only by procedure.
No `git reset`, `git checkout`, branch reattachment, merge, force-push, deletion,
or historical rewrite is performed. No v1–v7 launch evidence, raw data,
manifest, seal, roster, or current collector is touched. Any future work must
use the canonical path explicitly and re-audit this disposition before considering
an update. The canonical state index is the authoritative current-state source.
