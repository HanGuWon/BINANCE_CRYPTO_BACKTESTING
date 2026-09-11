# Predictability V1 Forward Hardening — Diff-Level Roadmap

## Loop-spec
Scope: isolated research/predictability-v1 only; canonical R3/live processes read-only.
No real predictive results, historical outcomes, R2B2, or final-holdout access.
All work phases execute dependency-ordered P→A→B→C→D cycles.

## Phase map
roadmap (docs-only) → WP0 integrated audit → WP1 target-blind recorder → WP2 shadow identity → WP3 incremental append → WP4 frozen-model policy → WP5 B0/B1/B1+I comparison → WP6 block inference → WP7 Holm family → WP8 provenance → WP9 artifact verification → WP10 split manifest → WP11 multi-symbol dry-run → WP12 adversarial tests → WP13 regression/reproducibility → WP14 preregistration proposal.

## Repository conventions and SoT
Python package under src/binance_research; tests under tests; durable plans under devlog/_plan.
Existing predictability contract files are src/binance_research/predictability.py, src/binance_research/predictability_cli.py, src/binance_research/forward.py, and tests/test_predictability*.py.
This unit's SoT is devlog/_plan/260911_predictability_forward_hardening/000_plan.md; contract changes must also update the proposal and tests.

## Scope boundary
IN: only the isolated worktree's predictability implementation, tests, docs, receipts, and preregistration proposal.
OUT: canonical R3 source/live processes, real-data outcome execution, final holdout, R2B/R2B2, remote push.

## Evidence floor
Each phase must record a fresh command, exit code, and artifact path. Conditional branches must have an activation fixture and observable assertion.
