from __future__ import annotations

from r3_collection_smoke import run_smoke


def test_collection_only_smoke_has_no_outcome_analysis() -> None:
    result = run_smoke()
    assert result["status"] == "PASS"
    assert result["stream_count"] == 5
    assert result["api_key_streams_present"] == []
    assert result["outcome_fields_present"] == []
    assert result["bytes_written"] > 0
    assert result["request_weight_budget_per_minute_upper_bound"] == 100
