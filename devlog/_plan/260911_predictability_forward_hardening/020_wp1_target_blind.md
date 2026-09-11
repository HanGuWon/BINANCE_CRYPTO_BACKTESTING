# WP1 — Target-blind prospective recording
MODIFY src/binance_research/predictability_cli.py, src/binance_research/forward.py; NEW tests/test_predictability_target_blind.py.
Training label construction remains prefix-only. Prospective prediction path computes schedule timestamps without reading prediction-region future close/labels.
Activation: sentinel dataset raises on any future target access; prospective command must complete and write rows.

## WP1 implementation review (2026-09-11)
Current isolated code now uses schedule_forward_times for decision/next-open/target-exit timestamps and calls build_forward_labels only on enriched.iloc[:train_end]. The target-blind sentinel is tests/test_predictability_target_blind.py.
P→A review command: python -m pytest -q tests/test_predictability_target_blind.py -p no:cacheprovider (1 passed in 0.54s).
Remaining WP1 risk to audit in A/B: feature generation still receives the full frame; the sentinel must be extended if feature code is found to access future targets rather than causal current features.
