# Phase 4 — readiness freeze

Change map:

- campaigns/r2b_restricted_derivatives_v1/reproducibility_manifest.json: pin implementation commit, clean source-tree hash, registry/data/root/qualification/proof hashes.
- campaigns/r2b_restricted_derivatives_v1/full_pytest_receipt.json: capture full pytest stdout/count/exit code.
- campaigns/r2b_restricted_derivatives_v1/root_history.md and readiness audit: reconcile abandoned roots and exact producers.

Verifier: targeted causal/readiness/qualification tests followed by python -m pytest -q; git status --short must show no scientific source modifications beyond intentionally committed compact artifacts. No outcome command is permitted in this phase.

Activation scenario: the final report can be generated from fresh receipts and manifests without opening any final-holdout path.
