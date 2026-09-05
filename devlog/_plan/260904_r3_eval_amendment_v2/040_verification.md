# Phase 4 — Verification, Identity Seal, and Remote Sync

## Scope

Run focused governance tests and final metadata/watch checks, then commit and push
only intentional docs/ops changes. Never run evaluation or stop the collector.

## Exact checks

1. Run focused checker/inventory tests with the Hermes dependency environment and
   inspect full output/exit code.
2. Compute V1/V2/horizon/manifest/registry/source-tree SHA256. Verify frozen
   implementation commit and D-backed v8 root/launch manifest/seal/roster.
3. Run `r3_ops.py watch --exact-v8` with the Hermes site-packages path. Require
   one authorized writer, live lock, no duplicate, chain true, seal true, root
   unchanged, and outcomes false. If a dead collector is detected, use only
   `launch_r3_v8_resume.ps1` after stale-PID proof and record the restart gap in a
   new append-only receipt; never create a root or rewrite a manifest.
4. Verify `git status --short -- scripts src tests configs` is empty; compute
   HEAD/origin and `git rev-list --left-right --count` as `0 0`. Full worktree
   user-owned `.codexclaw`, data, and devlog noise remains untouched.
5. Commit in logical units and push normally (the standing repository instruction
   authorizes reflecting changes at the GitHub repository). Verify remote tip.
6. Final state must be `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`, with
   evaluation `NOT_STARTED`, final holdout `UNTOUCHED`, and R2B2 `NOT_STARTED`.

## Verification evidence

The final attestation cites focused pytest output, the V2 readiness/inventory
receipts, the live watch output, source/registry hashes, and Git 0/0. A passing
test without a live watch is insufficient; a live watch without contract tests is
also insufficient.
