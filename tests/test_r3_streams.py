from __future__ import annotations

import json

import pytest

from binance_research.r3_streams import StreamSchemaError, normalize_stream_payload


def _kline(close_time: int) -> list[object]:
    return [0, "1", "2", "0.5", "1.5", "10", close_time, "15", 2, "5", "7", "0"]


def test_closed_kline_normalizer_rejects_forming_candle() -> None:
    rows = normalize_stream_payload("klines_15m", "BTCUSDT", [_kline(899_999), _kline(1_800_000)], receipt_time="1970-01-01T00:30:00Z")
    assert len(rows) == 1
    assert rows[0]["source_available_time"] == "1970-01-01T00:30:00+00:00"


def test_premium_kline_uses_same_closed_row_and_receipt_availability_rule() -> None:
    rows = normalize_stream_payload("premium_klines_15m", "BTCUSDT", [_kline(899_999), _kline(1_800_000)], receipt_time="1970-01-01T00:15:02Z")
    assert len(rows) == 1
    assert rows[0]["stream"] == "premium_klines_15m"
    assert rows[0]["source_available_time"] == "1970-01-01T00:15:02+00:00"


def test_array_streams_keep_each_row_identity_and_observation_time() -> None:
    payload = [{"symbol": "BTCUSDT", "timestamp": 1_700_000_000_000, "sumOpenInterest": "1"}, {"symbol": "ETHUSDT", "timestamp": 1_700_000_005_000, "sumOpenInterest": "2"}]
    rows = normalize_stream_payload("oi_history", "BTCUSDT", payload, receipt_time="2024-01-01T00:00:00Z")
    assert [row["symbol"] for row in rows] == ["BTCUSDT", "ETHUSDT"]
    assert len({row["source_row_identity"] for row in rows}) == 2
    assert rows[0]["observation_time"].startswith("2023-11-14T22:13:20")


def test_malformed_array_fails_closed() -> None:
    with pytest.raises(StreamSchemaError):
        normalize_stream_payload("taker_ratio", "BTCUSDT", [["not-an-object"]], receipt_time="2024-01-01T00:00:00Z")
