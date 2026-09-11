# WP3 — Incremental append
MODIFY src/binance_research/forward.py, src/binance_research/predictability_cli.py; NEW tests/test_predictability_incremental.py.
Split immutable campaign/model contract from append-only run receipt/high-water metadata. Preserve old rows and prediction_recorded_at; append only new eligible decisions; recover interrupted temp append.
Activation: T0→T1→T2, same-cutoff no-op, restart, and crash-temp fixtures with byte-for-byte old-row assertions.

## WP3 implementation evidence (2026-09-11)
append_predictions_write_once now preserves stored prediction_recorded_at on exact replay, while append_jsonl_atomic provides immutable campaign metadata plus append-only run receipts and stale-temp refusal. Tests cover T0→T1→T2-style replay, same-cutoff no-op, high-water receipt order, and interrupted append detection.
