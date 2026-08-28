from __future__ import annotations

import pandas as pd
import pytest

from binance_research.r3_materializer import materialize_causal_observations, reject_nonfinite


def _event(event_ms: int, receipt: str, value: float, **extra):
    return {"stream": "depth", "symbol": "BTCUSDT", "exchange_event_time": event_ms, "collector_receipt_time": receipt, "continuity_state": "COMPLETE", "payload": {"v": value}, "value": value, **extra}


def test_strict_availability_and_no_future_receipt_revision() -> None:
    rows = materialize_causal_observations([_event(1000, "2024-01-01T00:00:02Z", 1), _event(2000, "2024-01-01T00:00:04Z", 2)], ["2024-01-01T00:00:03Z", "2024-01-01T00:00:05Z"])
    assert list(rows["feature_value"]) == [1, 2]
    assert all(pd.to_datetime(rows["availability_time"], utc=True) < pd.to_datetime(rows["decision_time"], utc=True))


def test_duplicate_and_sequence_gap_restart_segment() -> None:
    first = _event(1000, "2024-01-01T00:00:01Z", 1, sequence_id=1)
    duplicate = dict(first)
    gap = _event(3000, "2024-01-01T00:00:03Z", 3, sequence_id=3, continuity_state="SEQUENCE_GAP")
    rows = materialize_causal_observations([first, duplicate, gap], ["2024-01-01T00:00:02Z", "2024-01-01T00:00:04Z"])
    assert rows.iloc[-1]["data_quality_state"] == "SEQUENCE_GAP"
    assert rows.iloc[-1]["continuity_segment"] > rows.iloc[0]["continuity_segment"]


def test_missing_event_time_and_restart_gap_are_retained_but_not_values() -> None:
    rows = materialize_causal_observations([{"stream": "oi", "symbol": "BTCUSDT", "collector_receipt_time": "2024-01-01T00:00:01Z", "continuity_state": "COMPLETE", "value": 9}, {**_event(2000, "2024-01-01T00:00:02Z", 2), "continuity_state": "RESTART_GAP"}], ["2024-01-01T00:00:03Z"])
    assert rows.iloc[0]["data_quality_state"] in {"SOURCE_TIME_UNAVAILABLE", "RESTART_GAP"}


def test_nonfinite_quantity_is_fail_closed() -> None:
    with pytest.raises(ValueError):
        reject_nonfinite(float("nan"))
    with pytest.raises(ValueError):
        reject_nonfinite(float("inf"))


def test_required_gap_fixture_states_are_preserved() -> None:
    states = ["POLL_GAP", "RESTART_GAP", "SEQUENCE_GAP", "SCHEMA_ERROR", "RATE_LIMIT_GAP"]
    events = [_event(1000 + i * 1000, f"2024-01-01T00:00:0{i+1}Z", float(i), continuity_state=state) for i, state in enumerate(states)]
    rows = materialize_causal_observations(events, ["2024-01-01T00:01:00Z"])
    assert set(rows["data_quality_state"]) & set(states)


def test_out_of_order_and_missing_oi_or_liquidation_are_fail_closed() -> None:
    out_of_order = _event(3000, "2024-01-01T00:00:03Z", 3)
    earlier = _event(2000, "2024-01-01T00:00:04Z", 2)
    missing_oi = {"stream": "oi", "symbol": "BTCUSDT", "collector_receipt_time": "2024-01-01T00:00:05Z", "continuity_state": "POLL_GAP"}
    no_liquidation = {"stream": "liquidation", "symbol": "BTCUSDT", "collector_receipt_time": "2024-01-01T00:00:06Z", "continuity_state": "SOURCE_TIME_UNAVAILABLE"}
    rows = materialize_causal_observations([out_of_order, earlier, missing_oi, no_liquidation], ["2024-01-01T00:00:03.500Z", "2024-01-01T00:00:04.500Z", "2024-01-01T00:00:05.500Z", "2024-01-01T00:00:06.500Z"])
    assert "SEQUENCE_GAP" in set(rows["data_quality_state"])
    assert "POLL_GAP" in set(rows["data_quality_state"])
