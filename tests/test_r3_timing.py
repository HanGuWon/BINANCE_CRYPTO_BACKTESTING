from __future__ import annotations

from datetime import UTC, datetime

import pytest

from binance_research.r3_timing import calibrate_server_clock, calibrated_now, cycle_boundaries, next_quarter_hour
from binance_research.data import BinanceRestClient


def test_clock_calibration_uses_request_midpoint() -> None:
    sample = calibrate_server_clock(local_before_ms=1_000, server_ms=1_125, local_after_ms=1_050)
    assert sample.offset_ms == 100.0
    assert sample.round_trip_ms == 50
    assert calibrated_now(datetime.fromtimestamp(2, UTC), sample).timestamp() == 2.1


def test_next_quarter_hour_is_absolute_and_utc() -> None:
    now = datetime(2026, 8, 29, 12, 7, 31, tzinfo=UTC)
    assert next_quarter_hour(now) == datetime(2026, 8, 29, 12, 15, tzinfo=UTC)
    delayed = datetime(2026, 8, 29, 12, 14, 59, tzinfo=UTC)
    assert next_quarter_hour(delayed) == datetime(2026, 8, 29, 12, 15, tzinfo=UTC)


def test_scheduler_rejects_non_grid_interval() -> None:
    with pytest.raises(ValueError):
        next_quarter_hour(datetime.now(UTC), interval_seconds=901)


def test_cycle_boundaries_use_candle_boundary_and_strict_next_open() -> None:
    result = cycle_boundaries(datetime(2026, 8, 30, 12, 15, tzinfo=UTC), actual_start=datetime(2026, 8, 30, 12, 15, 6, tzinfo=UTC), required_available=datetime(2026, 8, 30, 12, 15, 6, tzinfo=UTC))
    assert result["target_bar_open"] == "2026-08-30T12:00:00+00:00"
    assert result["target_bar_close"] == "2026-08-30T12:15:00+00:00"
    assert result["scheduled_collection_time"] == "2026-08-30T12:15:05+00:00"
    assert result["eligible_next_execution_time"] == "2026-08-30T12:30:00+00:00"


def test_rest_client_clock_calibration_requires_server_time(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient(BinanceRestClient):
        def get_with_metadata(self, market: str, path: str, params: dict[str, object] | None = None):
            return {"serverTime": 1_025}, object()

    monkeypatch.setattr("binance_research.data.datetime", type("Clock", (), {"now": staticmethod(lambda tz: datetime.fromtimestamp(1, UTC))}))
    sample = FakeClient().calibrate_server_clock()
    assert sample.server_ms == 1_025
