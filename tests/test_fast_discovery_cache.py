from __future__ import annotations

import pandas as pd

from binance_research.fast_discovery_cache import PrimitiveFeatureCache, frame_sha256, primitive_cache_key


def _panel() -> pd.DataFrame:
    first = pd.date_range("2024-01-01", periods=40, freq="h", tz="UTC")
    second = pd.date_range("2024-01-03", periods=40, freq="h", tz="UTC")
    timestamps = first.append(second)
    values = pd.Series(range(80), dtype=float) + 100
    return pd.DataFrame(
        {
            "open_time": timestamps,
            "open": values,
            "high": values + 1,
            "low": values - 1,
            "close": values + 0.5,
            "volume": values * 2,
            "symbol": ["AAAUSDT"] * 80,
            "segment_id": ["segment-0001"] * 40 + ["segment-0002"] * 40,
            "future_return": [0.0] * 80,
        }
    )


def test_cached_and_uncached_feature_values_are_identical() -> None:
    panel = _panel()
    cache = PrimitiveFeatureCache()
    first = cache.materialize(panel, market="um", timeframe="1h", feature_ids=["rvol20", "ema20_50_spread"])
    assert cache.stats.misses == 4
    second = cache.materialize(panel, market="um", timeframe="1h", feature_ids=["rvol20", "ema20_50_spread"])
    assert cache.stats.hits == 4
    pd.testing.assert_frame_equal(first[["rvol20", "ema20_50_spread"]], second[["rvol20", "ema20_50_spread"]])


def test_cache_hash_excludes_outcomes_but_changes_for_source_values() -> None:
    panel = _panel()
    changed_outcome = panel.assign(future_return=99.0)
    changed_source = panel.assign(close=999.0)
    assert frame_sha256(panel) == frame_sha256(changed_outcome)
    assert frame_sha256(panel) != frame_sha256(changed_source)


def test_cache_identity_binds_all_required_dimensions() -> None:
    base = primitive_cache_key(source_hash="s", market="um", timeframe="1h", symbol="AAAUSDT", segment_id="segment-0001", feature_id="rvol20")
    assert base != primitive_cache_key(source_hash="s", market="spot", timeframe="1h", symbol="AAAUSDT", segment_id="segment-0001", feature_id="rvol20")
    assert base != primitive_cache_key(source_hash="s", market="um", timeframe="4h", symbol="AAAUSDT", segment_id="segment-0001", feature_id="rvol20")
    assert base != primitive_cache_key(source_hash="s", market="um", timeframe="1h", symbol="BBBUSDT", segment_id="segment-0001", feature_id="rvol20")
    assert base != primitive_cache_key(source_hash="s", market="um", timeframe="1h", symbol="AAAUSDT", segment_id="segment-0002", feature_id="rvol20")
    assert base != primitive_cache_key(source_hash="s", market="um", timeframe="1h", symbol="AAAUSDT", segment_id="segment-0001", feature_id="ema20_50_spread")


def test_gap_segment_restarts_feature_warmup() -> None:
    result = PrimitiveFeatureCache().materialize(_panel(), market="um", timeframe="1h", feature_ids=["rvol20"])
    assert result.loc[39, "rvol20"] == result.loc[39, "rvol20"]
    assert pd.isna(result.loc[40, "rvol20"])
