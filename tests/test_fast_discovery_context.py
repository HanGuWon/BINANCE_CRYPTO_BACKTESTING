from __future__ import annotations

import pandas as pd
import pytest

from binance_research.fast_discovery_context import build_relative_strength


def _fixtures() -> tuple[pd.DataFrame, pd.DataFrame]:
    times = pd.date_range("2024-01-01", periods=6, freq="h", tz="UTC")
    rows = []
    for symbol, closes in (("AAAUSDT", [100, 101, 102, 104, 106, 108]), ("BBBUSDT", [100, 99, 98, 97, 96, 95])):
        for ts, close in zip(times, closes):
            rows.append({"open_time": ts, "close_time": ts + pd.Timedelta(minutes=59), "next_open_time": ts + pd.Timedelta(hours=1), "symbol": symbol, "segment_id": "segment-0001", "market": "um", "universe_month": "2024-01", "selected_top50": True, "close": float(close)})
    panel = pd.DataFrame(rows)
    benchmark = pd.DataFrame({"open_time": times, "close": [100, 100, 100, 100, 100, 100]})
    return panel, benchmark


def test_relative_strength_is_trailing_and_ranked_only_within_selected_cohort() -> None:
    panel, benchmark = _fixtures()
    result = build_relative_strength(panel, benchmark, lookback_bars=2)
    aaa = result[(result.symbol == "AAAUSDT") & (result.open_time == pd.Timestamp("2024-01-01T03:00Z"))].iloc[0]
    bbb = result[(result.symbol == "BBBUSDT") & (result.open_time == pd.Timestamp("2024-01-01T03:00Z"))].iloc[0]
    assert aaa.relative_strength_24h == pytest.approx(104 / 101 - 1)
    assert bbb.relative_strength_24h == pytest.approx(97 / 99 - 1)
    assert aaa.relative_strength_rank > bbb.relative_strength_rank
    assert result.attrs["holdout_status"] == "UNTOUCHED"


def test_unselected_symbol_cannot_influence_cross_sectional_rank() -> None:
    panel, benchmark = _fixtures()
    panel.loc[(panel.symbol == "BBBUSDT") & (panel.open_time == pd.Timestamp("2024-01-01T03:00Z")), "selected_top50"] = False
    result = build_relative_strength(panel, benchmark, lookback_bars=2)
    aaa = result[(result.symbol == "AAAUSDT") & (result.open_time == pd.Timestamp("2024-01-01T03:00Z"))].iloc[0]
    bbb = result[(result.symbol == "BBBUSDT") & (result.open_time == pd.Timestamp("2024-01-01T03:00Z"))].iloc[0]
    assert aaa.relative_strength_rank == pytest.approx(1.0)
    assert pd.isna(bbb.relative_strength_rank)


def test_missing_segment_or_duplicate_benchmark_fails_closed() -> None:
    panel, benchmark = _fixtures()
    with pytest.raises(ValueError, match="segment_id"):
        build_relative_strength(panel.drop(columns="segment_id"), benchmark, lookback_bars=2)
    duplicate = pd.concat([benchmark, benchmark.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        build_relative_strength(panel, duplicate, lookback_bars=2)

