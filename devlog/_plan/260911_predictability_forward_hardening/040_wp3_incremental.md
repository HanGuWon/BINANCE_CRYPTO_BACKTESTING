# WP3 — Incremental append
MODIFY src/binance_research/forward.py, src/binance_research/predictability_cli.py; NEW tests/test_predictability_incremental.py.
Split immutable campaign/model contract from append-only run receipt/high-water metadata. Preserve old rows and prediction_recorded_at; append only new eligible decisions; recover interrupted temp append.
Activation: T0→T1→T2, same-cutoff no-op, restart, and crash-temp fixtures with byte-for-byte old-row assertions.
