# Phase 2 — causal materialization and immutable root

Change map:

- scripts/materialize_r2b_premium_panel.py: materialize only from checksum-verified pre-holdout archives into a new root; preserve source availability columns and causal z-score segments.
- scripts/audit_r2b_premium_coverage.py: scan the new schema and report availability-conditioned coverage.
- campaigns/r2b_restricted_derivatives_v1/r2b_data_guard_proof_v2.json: prove availability inequalities, complete buckets, no forward joins, segment boundaries, zero holdout rows, and no holdout paths.
- campaigns/r2b_restricted_derivatives_v1/root_history.md: hash and mark the old repaired root superseded; record the new producer and identity.

Verifier: run the materializer into a fresh D-backed root, then run `python scripts/audit_r2b_premium_coverage.py --panel-root <new-root> --out-dir <audit-dir>` and `python scripts/verify_r2b_causal_root.py --root <new-root> --out <proof>`. The guard exits non-zero on any row where `source_available_time >= executable_open_time`, any incomplete bucket, any forward match, any holdout path/row, or any segment-continuity violation. Record exact commands and exit codes in the campaign receipt; `--help` alone is only a parser smoke test.

Activation scenarios: every row with a source match is checked against strict executable-open availability; incomplete/gapped buckets are absent; the holdout cutoff excludes 2024-02-10 and later.
