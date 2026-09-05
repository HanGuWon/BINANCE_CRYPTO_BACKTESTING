# Phase 1 — executor and qualification

MODIFY `scripts/run_r2a2_v2.py`: initialize per-segment non-overlap sentinel at `-1`; key signal cache by `(market,timeframe,symbol,segment_id,feature_id,variant)`; enforce LONG `raw == +1`, SHORT `raw == -1`.

VERIFY `tests/test_r2a2_direction_gate.py`, `tests/test_r2a2_segments.py`, and the registry-derived `tests/test_r2a2_qualification.py` matrix (Spot/UM, all timeframes and registered horizons, UM LONG/SHORT, positive/negative event funding, funding/funding_zscore, and gap segments), then full pytest. Archive every interrupted or mismatched checkpoint as invalid and record SHA256 hashes. Commit the clean implementation before any full campaign.
