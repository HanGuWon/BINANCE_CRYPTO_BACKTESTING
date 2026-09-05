# Phase 3 — semantics freeze and UM-only qualification

Change map:

- campaigns/r2b_restricted_derivatives_v1/R2B_SIGNAL_SEMANTICS_AMENDMENT_001.md: preregister equations, signs, thresholds, missing/warmup, event/state behavior, and final family size using no outcome artifacts.
- campaigns/r2b_restricted_derivatives_v1/campaign_spec.toml, multiple_testing_plan.md, metrics_contract.md, promotion_policy.md: reconcile the UM-only family and causal fields.
- scripts/r2b_qualification.py (new explicit owner) and tests/test_r2b_qualification.py: slow reference versus optimized parity across all UM timeframes/sides/horizons, positive/negative funding, gaps, missingness, warmup, sign rejection, next-open. The test must construct independent reference decisions and cannot call the optimized executor to derive expected rows.
- campaigns/r2b_restricted_derivatives_v1/qualification_receipt.json, trial_registry.csv: deterministic qualification receipt and registry hash.
- campaigns/r2b_restricted_derivatives_v1/semantics_design_exclusion_list.md: explicit exclusion of historical performance-like artifacts from semantics design.

Verifier: targeted qualification test collection/run and a deterministic registry hash command; each must observe the listed files and remain pre-outcome.

Activation scenarios: +1 enters only LONG, -1 only SHORT, 0/NaN never enters; funding cashflow signs are exercised in both directions; gap segments reset warmup and signal state.
