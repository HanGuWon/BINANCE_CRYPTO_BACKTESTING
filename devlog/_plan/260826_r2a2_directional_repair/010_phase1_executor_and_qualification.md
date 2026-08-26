# Phase 1 — executor and qualification

MODIFY `scripts/run_r2a2_v2.py`: initialize per-segment non-overlap sentinel at `-1`; key signal cache by `(market,timeframe,symbol,segment_id,feature_id,variant)`; enforce LONG `raw == +1`, SHORT `raw == -1`.

VERIFY `tests/test_r2a2_direction_gate.py`, `tests/test_r2a2_segments.py`, and `tests/test_r2a2_qualification.py`, then full pytest. Archive `checkpoints_v3` as invalid if interrupted and record SHA256 hashes. Commit implementation before any full campaign.
