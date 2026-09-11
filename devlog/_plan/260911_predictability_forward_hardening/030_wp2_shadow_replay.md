# WP2 — Shadow replay isolation
MODIFY src/binance_research/predictability_cli.py, src/binance_research/forward.py; NEW tests/test_predictability_shadow_identity.py.
Introduce explicit SHADOW_REPLAY_NON_PROSPECTIVE mode and identity/storage namespace; replay rows cannot enter prospective store.
Activation: invoke replay then prospective append and assert disjoint identity and files.
