# WP1 — Target-blind prospective recording
MODIFY src/binance_research/predictability_cli.py, src/binance_research/forward.py; NEW tests/test_predictability_target_blind.py.
Training label construction remains prefix-only. Prospective prediction path computes schedule timestamps without reading prediction-region future close/labels.
Activation: sentinel dataset raises on any future target access; prospective command must complete and write rows.
