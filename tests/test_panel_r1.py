from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from binance_research.alignment import PointInTimeSource, causal_asof_join
from binance_research.data import resample_klines
from binance_research.data import ArchiveRequest, BinanceArchiveClient, DataIntegrityError, sha256_bytes
from binance_research.panel import (
    feature_availability_matrix,
    lifecycle_records,
    select_causal_liquidity_universe,
)


def _bars(times: list[str], symbol: str = "BTCUSDT") -> pd.DataFrame:
    index = pd.to_datetime(times, utc=True)
    return pd.DataFrame(
        {
            "open_time": index,
            "close_time": index + pd.Timedelta(minutes=14, seconds=59),
            "open": range(1, len(index) + 1),
            "high": range(2, len(index) + 2),
            "low": range(1, len(index) + 1),
            "close": range(2, len(index) + 2),
            "volume": 1.0,
            "quote_volume": 10.0,
            "trade_count": 1,
            "taker_buy_volume": 0.5,
            "taker_buy_quote_volume": 5.0,
            "symbol": symbol,
        }
    )


def test_r1_asof_join_cannot_use_future_observation() -> None:
    left = pd.DataFrame({"close_time": pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T01:00Z"]), "x": [1, 2]})
    source = PointInTimeSource(
        pd.DataFrame({"source_time": pd.to_datetime(["2024-01-01T00:30Z", "2024-01-01T02:00Z"]), "value": [3, 99]}),
        "source_time",
        ("value",),
    )
    result = causal_asof_join(
        left,
        source.frame,
        bar_timestamp="close_time",
        observation_timestamp=source.timestamp_column,
        value_columns=source.value_columns,
        source_name="future_value",
    )
    assert pd.isna(result.loc[0, "future_value_value"])
    assert result.loc[1, "future_value_value"] == 3
    assert result.loc[1, "future_value_age"] == pd.Timedelta(minutes=30)


def test_future_symbol_does_not_enter_earlier_month_and_delisted_remains_observed() -> None:
    volumes = pd.DataFrame(
        {
            "universe_month": ["2024-02-01", "2024-02-01", "2024-03-01"],
            "symbol": ["OLDUSDT", "FUTUREUSDT", "OLDUSDT"],
            "prior_month_quote_volume": [100.0, 999.0, 0.1],
            "first_observed": ["2024-01-01T00:00Z", "2024-02-15T00:00Z", "2024-01-01T00:00Z"],
        }
    )
    result = select_causal_liquidity_universe(volumes, top_n=50)
    future = result[result.symbol == "FUTUREUSDT"].iloc[0]
    assert bool(future.selected_top50) is False
    assert future.eligibility_reason == "NOT_OBSERVED_BEFORE_UNIVERSE_MONTH"
    life = lifecycle_records([_bars(["2024-01-01T00:00Z", "2024-01-01T00:15Z"], "OLDUSDT")], market="spot", interval="15m")
    assert life.iloc[0].symbol == "OLDUSDT"
    assert life.iloc[0].delisting_effective_end == "UNKNOWN"


def test_future_liquidity_rewrite_does_not_change_prior_membership() -> None:
    base = pd.DataFrame(
        {
            "universe_month": ["2024-02-01", "2024-02-01", "2024-03-01", "2024-03-01"],
            "symbol": ["A", "B", "A", "B"],
            "prior_month_quote_volume": [100.0, 50.0, 10.0, 5.0],
            "first_observed": ["2024-01-01T00:00Z"] * 4,
        }
    )
    changed = base.copy()
    changed.loc[(changed.universe_month == "2024-03") & (changed.symbol == "B"), "prior_month_quote_volume"] = 1_000_000
    original = select_causal_liquidity_universe(base, top_n=1)
    revised = select_causal_liquidity_universe(changed, top_n=1)
    original_feb = original[original.universe_month == "2024-02"].sort_values("symbol")
    revised_feb = revised[revised.universe_month == "2024-02"].sort_values("symbol")
    assert list(original_feb.selected_top_n) == list(revised_feb.selected_top_n)
    assert list(original_feb["rank"]) == list(revised_feb["rank"])


def test_partial_canonical_resample_is_dropped() -> None:
    source = _bars(["2024-01-01T00:00Z", "2024-01-01T00:15Z", "2024-01-01T00:30Z"])
    result = resample_klines(source.drop(columns="symbol"), "1h")
    assert result.empty


def test_all_22_features_are_classified() -> None:
    matrix = feature_availability_matrix()
    assert len(matrix) == 22
    assert set(matrix.coverage_status).issubset({"AVAILABLE", "PARTIAL", "HISTORICAL_UNAVAILABLE"})
    assert matrix.feature_id.is_unique
    assert matrix.forward_shadow_required.any()


def test_modified_existing_raw_object_fails_closed(tmp_path) -> None:
    row = "1704067200000,1,2,0.5,1.5,10,1704068099999,15,1,5,7.5,0\n".encode()
    payload_buffer = io.BytesIO()
    with zipfile.ZipFile(payload_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BTCUSDT-1h-2024-01.csv", row)
    payload = payload_buffer.getvalue()
    checksum = sha256_bytes(payload)

    class FakeArchiveClient(BinanceArchiveClient):
        def _fetch(self, url: str) -> bytes:
            return (checksum + "  payload\n").encode() if url.endswith(".CHECKSUM") else payload

    client = FakeArchiveClient(tmp_path)
    request = ArchiveRequest("spot", "klines", "BTCUSDT", 2024, 1, interval="1h")
    path, _ = client.download(request)
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(DataIntegrityError, match="immutable raw object differs"):
        client.download(request)
