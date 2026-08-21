from __future__ import annotations

import pandas as pd
import pytest

from binance_research.data import (
    DataIntegrityError,
    deduplicate_klines,
    infer_timestamp_unit,
    normalize_archive_rows,
    normalize_klines,
    resample_klines,
    symbol_lifecycle_table,
    validate_klines,
)


def _row(timestamp: int, open_: float = 10, high: float = 12, low: float = 9, close: float = 11):
    return [timestamp, open_, high, low, close, 5, timestamp + 59_999, 55, 10, 3, 33, 0]


def test_timestamp_unit_detection_and_utc_conversion() -> None:
    assert infer_timestamp_unit(pd.Series([1_735_689_600_000])) == "ms"
    assert infer_timestamp_unit(pd.Series([1_735_689_600_000_000])) == "us"
    milliseconds = normalize_klines([_row(1_735_689_600_000)])
    microseconds = normalize_klines([_row(1_735_689_600_000_000)])
    assert milliseconds.loc[0, "open_time"] == microseconds.loc[0, "open_time"]
    assert str(milliseconds["open_time"].dtype) == "datetime64[ns, UTC]"


def test_integrity_detects_gap_duplicate_and_impossible_ohlc() -> None:
    rows = [_row(1_700_000_000_000), _row(1_700_000_000_000), _row(1_700_000_120_000, high=8)]
    issues = validate_klines(normalize_klines(rows), "1m")
    codes = {issue.code for issue in issues}
    assert {"DUPLICATE_TIMESTAMP", "MISSING_INTERVAL", "IMPOSSIBLE_OHLC"} <= codes


def test_duplicate_policy_accepts_identical_and_rejects_conflict() -> None:
    identical = normalize_klines([_row(1_700_000_000_000), _row(1_700_000_000_000)])
    assert len(deduplicate_klines(identical)) == 1
    conflicting = normalize_klines([_row(1_700_000_000_000), _row(1_700_000_000_000, close=10.5)])
    with pytest.raises(DataIntegrityError, match="conflicting"):
        deduplicate_klines(conflicting)


def test_resampling_drops_incomplete_target_bucket() -> None:
    base = 1_704_067_200_000
    frame = normalize_klines([_row(base + offset * 60_000, close=11 + offset) for offset in range(4)])
    result = resample_klines(frame, "2h")
    assert result.empty


def test_aggtrade_archive_schema_and_side_timestamp_are_preserved() -> None:
    raw = pd.DataFrame([[1, "10.5", "2", 7, 8, 1_735_689_600_000, True, True]])
    frame = normalize_archive_rows(raw, "aggTrades", "spot")
    assert frame.columns.tolist() == [
        "agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
        "timestamp", "is_buyer_maker", "is_best_match",
    ]
    assert str(frame["timestamp"].dtype) == "datetime64[ns, UTC]"


def test_symbol_lifecycle_uses_each_symbols_observed_window() -> None:
    frame = pd.DataFrame({
        "symbol": ["OLD", "OLD", "NEW", "NEW"],
        "open_time": pd.to_datetime([
            "2024-01-01T00:00:00Z", "2024-01-01T02:00:00Z",
            "2024-02-01T00:00:00Z", "2024-02-01T01:00:00Z",
        ]),
    })
    lifecycle = symbol_lifecycle_table(frame, "1h").set_index("symbol")
    assert lifecycle.loc["OLD", "missing_intervals_inside_lifecycle"] == 1
    assert lifecycle.loc["NEW", "first_observed"].month == 2


def test_resampling_preserves_completed_utc_alignment() -> None:
    base = 1_704_067_200_000
    frame = normalize_klines([_row(base + offset * 60_000) for offset in range(120)])
    result = resample_klines(frame, "2h")
    assert len(result) == 1
    assert result.loc[0, "open"] == 10
    assert result.loc[0, "volume"] == 600
