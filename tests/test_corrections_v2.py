from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from binance_research.alignment import PointInTimeSource, build_research_panel, causal_asof_join
from binance_research.backtest import CostModel, run_backtest
from binance_research.collector import liquidation_stream_url, route_liquidation_event
from binance_research.data import ArchiveRequest, CoverageStatus, normalize_klines, resample_klines, rest_coverage_status
from binance_research.registry import code_hash


def test_v2_spot_is_long_only() -> None:
    bars = pd.DataFrame({"open": [100, 101, 102, 103], "high": [101, 102, 103, 104], "low": [99, 100, 101, 102], "close": [100, 101, 102, 103]})
    result = run_backtest(bars, pd.Series([-1, -1, -1, -1]), CostModel(0, 0, 0, 0), holding_bars=1, market_type="spot")
    assert result.trades.empty
    assert result.summary["execution_scope"] == "spot_long_only"


def test_v2_point_in_time_join_is_backward_only() -> None:
    bars = pd.DataFrame({"close_time": pd.to_datetime(["2026-01-01T10:00:00Z", "2026-01-01T11:00:00Z"])})
    source = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01T10:30:00Z", "2026-01-01T11:30:00Z"]), "open_interest": [100.0, 200.0]})
    joined = causal_asof_join(bars, source, value_columns=("open_interest",), source_name="oi")
    assert pd.isna(joined.loc[0, "oi_open_interest"])
    assert joined.loc[1, "oi_open_interest"] == 100.0
    assert joined.loc[1, "oi_source_time"] <= joined.loc[1, "close_time"]


def test_v2_short_retention_state_is_real() -> None:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    assert rest_coverage_status("openInterestHist", datetime(2026, 1, 1, tzinfo=UTC), now) == CoverageStatus.HISTORICAL_UNAVAILABLE
    assert rest_coverage_status("openInterestHist", datetime(2026, 8, 10, tzinfo=UTC), now) == CoverageStatus.PARTIAL


def test_v2_open_interest_uses_calendar_month_boundary() -> None:
    now = datetime(2026, 3, 31, tzinfo=UTC)
    cutoff = pd.Timestamp(now) - pd.DateOffset(months=1)
    assert rest_coverage_status("openInterestHist", cutoff.to_pydatetime(), now) == CoverageStatus.PARTIAL
    assert rest_coverage_status("openInterestHist", (cutoff - pd.Timedelta(minutes=1)).to_pydatetime(), now) == CoverageStatus.HISTORICAL_UNAVAILABLE


def test_v2_incomplete_resample_is_dropped() -> None:
    base = 1_704_067_200_000
    rows = [[base + i * 60_000, 10, 12, 9, 11, 5, base + i * 60_000 + 59_999, 55, 10, 3, 33, 0] for i in range(90)]
    assert len(resample_klines(normalize_klines(rows), "1h")) == 1


def test_v2_daily_archive_and_repro_hash(tmp_path: Path) -> None:
    request = ArchiveRequest("spot", "klines", "BTCUSDT", 2026, 8, "1h", "daily", 20)
    assert request.url().endswith("/BTCUSDT-1h-2026-08-20.zip")
    (tmp_path / "src").mkdir()
    (tmp_path / "configs").mkdir()
    (tmp_path / "src" / "x.py").write_text("VALUE=1\n", encoding="utf-8")
    config = tmp_path / "configs" / "core.toml"
    config.write_text("x=1\n", encoding="utf-8")
    first = code_hash(tmp_path)
    config.write_text("x=2\n", encoding="utf-8")
    assert code_hash(tmp_path) != first


def test_v2_risk_is_bar_level_and_includes_inactive_bars() -> None:
    bars = pd.DataFrame({
        "open": [100, 100, 90, 120, 120, 120, 120, 120],
        "high": [100, 101, 95, 125, 121, 121, 121, 121],
        "low": [99, 99, 85, 110, 119, 119, 119, 119],
        "close": [100, 100, 90, 120, 120, 120, 120, 120],
    })
    result = run_backtest(bars, pd.Series([1, 0, 0, 0, 0, 0, 0, 0]), CostModel(0, 0, 0, 0), holding_bars=2)
    assert len(result.timeline) == len(bars)
    assert result.summary["timeline_observations"] == len(bars)
    assert result.summary["maximum_drawdown"] < 0
    assert result.timeline.iloc[-1] == 0


def test_v2_execution_scope_and_fail_closed_funding() -> None:
    bars = pd.DataFrame({"open": [100, 101, 102, 103], "high": [101, 102, 103, 104], "low": [99, 100, 101, 102], "close": [100, 101, 102, 103], "funding_rate": [0.0, 0.0, 0.0, 0.0]})
    result = run_backtest(bars, pd.Series([-1, -1, -1, -1]), CostModel(0, 0, 0, 0), holding_bars=1, market_type="um")
    assert result.summary["execution_scope"] == "futures_long_short"
    bars.loc[1, "funding_rate"] = float("nan")
    with pytest.raises(ValueError, match="funding_rate"):
        run_backtest(bars, pd.Series([1, 0, 0, 0]), CostModel(0, 0, 0, 0), holding_bars=1, market_type="um")


def test_v2_alignment_provenance_staleness_and_multiple_sources() -> None:
    bars = pd.DataFrame({"close_time": pd.to_datetime(["2026-01-01 12:00Z", "2026-01-01 10:00Z", "2026-01-01 11:00Z"])})
    oi = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01 09:00Z", "2026-01-01 10:30Z"]), "value": [1.0, 2.0]})
    premium = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01 10:00Z"]), "value": [0.1]})
    joined = build_research_panel(bars, {
        "oi": PointInTimeSource(oi, "timestamp", ("value",), max_age=pd.Timedelta(minutes=45)),
        "premium": PointInTimeSource(premium, "timestamp", ("value",)),
    })
    assert joined["close_time"].dt.hour.tolist() == [12, 10, 11]
    assert joined.loc[0, "oi_coverage"] == "STALE"
    assert pd.isna(joined.loc[0, "oi_value"])
    assert joined.loc[2, "oi_value"] == 2.0
    assert joined.loc[2, "premium_coverage"] == "AVAILABLE"


def test_v2_liquidation_routing_preserves_event_symbol() -> None:
    assert route_liquidation_event({"st": 2, "o": {"s": "BTCUSD_PERP"}}) == ("cm", "BTCUSD_PERP")
    assert route_liquidation_event({"o": {"s": "ETHUSDT"}}, "ETHUSDT") == ("um", "ETHUSDT")
    assert route_liquidation_event({"st": 99, "o": {"s": "XRPUSDT"}}) == ("unknown", "XRPUSDT")


def test_v2_liquidation_uses_market_stream_namespace() -> None:
    assert liquidation_stream_url("ALL") == "wss://fstream.binance.com/market/ws/!forceOrder@arr"
    assert liquidation_stream_url("BTCUSDT") == "wss://fstream.binance.com/market/ws/btcusdt@forceOrder"
