# WP2 — Shadow replay isolation
MODIFY src/binance_research/predictability_cli.py, src/binance_research/forward.py; NEW tests/test_predictability_shadow_identity.py.
Introduce explicit SHADOW_REPLAY_NON_PROSPECTIVE mode and identity/storage namespace; replay rows cannot enter prospective store.
Activation: invoke replay then prospective append and assert disjoint identity and files.

## WP2 implementation evidence (2026-09-11)
prediction_identity now binds mode; recorder normalizes shadow-replay to SHADOW_REPLAY_NON_PROSPECTIVE, exposes the explicit parser choice, and propagates the namespace through prediction rows and evaluator identity checks. tests/test_predictability_forward_contracts.py::test_prediction_identity_separates_shadow_and_prospective_modes proves disjoint IDs.
