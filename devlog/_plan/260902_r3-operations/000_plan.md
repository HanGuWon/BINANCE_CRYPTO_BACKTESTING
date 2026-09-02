# R3 operations-only stabilization roadmap

## Loop-spec header

- Loop archetype: spec-satisfaction repair and operations hardening; no outcome optimization.
- Trigger: the v8 prospective collector is live but its lifetime currently depends on the launching session.
- Goal: make the already-sealed v8 collector durable, observable, and restart-safe without changing scientific code or raw evidence.
- Non-goals: returns, PnL, Sharpe, hit rate, H01-H06 evaluation, R2B2, holdout access, roster changes, registry changes, raw rewrites, v9 creation, or private APIs.
- Verifier: outcome-blind operational scripts, process-tree/Task Scheduler inspection, manifest/seal verifiers, daily receipt schema checks, and `python -m pytest -q` only when the scientific source scope is unchanged.
- Stop condition: stabilized verified, stabilized (documented safe-skip), or explicit blocked state for identity drift, multiple writers, or implementation repair.
- Memory artifact: `campaigns/r3_prospective_context_v1/operations/` receipts plus this numbered plan and `.codexclaw` ledger.
- Expected terminal outcomes: `R3_PROSPECTIVE_COLLECTION_OPERATIONALLY_STABILIZED_VERIFIED`, `R3_PROSPECTIVE_COLLECTION_OPERATIONALLY_STABILIZED`, `R3_BLOCKED_POST_LAUNCH_IDENTITY_DRIFT`, `R3_BLOCKED_MULTIPLE_WRITERS`, `R3_ACTIVE_COLLECTION_IMPLEMENTATION_REPAIR_REQUIRED`, `UNSAFE`, `NEEDS_HUMAN`, or `BUDGET_EXHAUSTED`.
- Escalation: upward, reclaim any failed operational slice after two worker failures; downward, add a new work-phase through P only. No mid-launch scientific patch.
- HOTL resource bounds: local filesystem/process inspection only; no credentials or private APIs; D-backed evidence writes only under operations receipts; each phase ≤ 20 minutes of active shell work plus bounded test waits; no destructive retention.

## Dependency-ordered work phases

1. `wp0-roadmap`: lock this roadmap and numbered phase contracts (docs only).
2. `wp1-live`: verify identity, process tree, single-writer proof, continued cycles, chain/seal, and storage baseline.
3. `wp2-ops`: add only operations-layer launcher, watchdog, daily receipt, and runbook files under `ops/r3/` and `campaigns/.../operations/`.
4. `wp3-qualify`: configure a native Task Scheduler task, smoke-test single-instance/resume behavior, and calculate storage projections; never stop the live v8 process unless an explicit safety check proves the sealed root is protected.
5. `wp4-final`: repeat live checks, run tests, append final receipt, and report the exact terminal state.

## Scope boundary

IN: `ops/r3/**`, operations receipts/runbook, Task Scheduler registration/export, devlog evidence, and `.codexclaw` ledgers.

OUT: `scripts/`, `src/`, `tests/`, `configs/`, frozen registry, launch manifest/seal, roster, `scientific_raw_v8/raw_v1/**`, failed v3-v7 roots, and any outcome/holdout material.

## Source of truth

The frozen scientific identity remains the v8 launch manifest and receipt under
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8`.
The operations runbook is additive and cannot reinterpret H01-H06.

## Locked verifier and safety rules

- The Phase 1 baseline is the freshly recorded count and last cycle from the v8 metadata/health files. “Continued” means the count increases beyond that baseline; if the next scheduled boundary has not arrived, the receipt says `WAITING_FOR_NEXT_BOUNDARY` rather than applying a hard-coded count.
- The existing `single_instance_lock` PID file is the sole writer lock. No second named mutex is introduced. Task Scheduler uses `MultipleInstancesPolicy=IgnoreNew`; the launcher holds the process synchronously so the scientific lock lifetime equals the collector lifetime.
- A production-v8 restart test is opt-in only after a preflight proves evidence protection. The default is a documented safe-skip; never terminate the live collector merely to satisfy a test. Any authorized resume appends `RESTART_GAP` through the existing resume guard.
- All phase receipts repeat the exact v8 launch-manifest path/SHA, seal path/SHA, roster SHA, and `outcomes_accessed=false`; v3-v7 roots remain preserved and are not opened by operational verifiers.
