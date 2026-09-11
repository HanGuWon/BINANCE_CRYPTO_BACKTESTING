# WP5 — B0/B1/B1+I comparison
MODIFY src/binance_research/forward.py, evaluator/aggregator module; NEW tests/test_predictability_comparison.py.
Require all three probabilities on identical rows. Primary delta_log_loss = loss(B1)-loss(B1+I); retain Brier, ROC-AUC, balanced accuracy, accuracy as secondary.
Activation: fixture with known probabilities asserts exact paired loss and positive sign convention.
