from __future__ import annotations

import pandas as pd
import pytest

from binance_research.data import DataIntegrityError
from binance_research.data import infer_timestamp_unit, normalize_timestamp
from scripts.build_r16_1d_universe import _summarize_1d_archive
from scripts.build_r17_cohorts_strict import strict_verified_manifest
from binance_research.features import CoreFeatureEngine, compute_gap_safe_features
from binance_research.panel import select_verified_causal_liquidity_universe
from scripts.materialize_r15_anchor_panel import _resample_contiguous


def test_gap_safe_features_reset_state_and_warmup_after_gap(bars: pd.DataFrame) -> None:
    gapped = bars.copy()
    gapped.loc[250:, "open_time"] += pd.Timedelta(hours=5)
    gapped.loc[250:, "close_time"] += pd.Timedelta(hours=5)

    output = compute_gap_safe_features(CoreFeatureEngine(), gapped, "1h")

    assert output.loc[250:255, "roc6"].isna().all()
    assert pd.isna(output.loc[250, "rsi14"])
    assert output.loc[250:448, "ema50_200_spread"].isna().all()
    expected_delta = gapped.loc[250, "taker_buy_volume"] - (
        gapped.loc[250, "volume"] - gapped.loc[250, "taker_buy_volume"]
    )
    assert output.loc[250, "cvd"] == pytest.approx(expected_delta)


def test_verified_liquidity_universe_ranks_markets_independently() -> None:
    frame = pd.DataFrame(
        {
            "market": ["spot", "spot", "um", "um"],
            "universe_month": ["2024-03-01"] * 4,
            "volume_month": ["2024-02-01"] * 4,
            "symbol": ["SPOT_A", "SPOT_B", "UM_A", "UM_B"],
            "prior_month_quote_volume": [100.0, 50.0, 10.0, 20.0],
            "first_observed": ["2024-01-01T00:00:00Z"] * 4,
            "coverage_ratio": [1.0] * 4,
        }
    )

    result = select_verified_causal_liquidity_universe(frame, top_n=1)
    selected = result[result["selected_top_n"]]

    assert set(zip(selected["market"], selected["symbol"])) == {("spot", "SPOT_A"), ("um", "UM_B")}


def test_verified_liquidity_universe_rejects_non_prior_volume_month() -> None:
    frame = pd.DataFrame(
        {
            "market": ["spot"],
            "universe_month": ["2024-03-01"],
            "volume_month": ["2024-03-01"],
            "symbol": ["AUSDT"],
            "prior_month_quote_volume": [100.0],
            "first_observed": ["2024-01-01T00:00:00Z"],
        }
    )

    with pytest.raises(ValueError, match="immediately preceding"):
        select_verified_causal_liquidity_universe(frame)


def test_anchor_resample_rejects_off_grid_source() -> None:
    times = pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:10:00Z", "2024-01-01T00:25:00Z"])
    frame = pd.DataFrame(
        {
            "open_time": times,
            "open": [1.0, 1.1, 1.2],
            "high": [1.2, 1.3, 1.4],
            "low": [0.9, 1.0, 1.1],
            "close": [1.1, 1.2, 1.3],
            "volume": [10.0, 10.0, 10.0],
            "close_time": times + pd.Timedelta(minutes=15) - pd.Timedelta(milliseconds=1),
            "quote_volume": [11.0, 12.0, 13.0],
            "trade_count": [1, 1, 1],
            "taker_buy_volume": [5.0, 5.0, 5.0],
            "taker_buy_quote_volume": [5.5, 6.0, 6.5],
        }
    )

    with pytest.raises(DataIntegrityError, match="OFF_GRID_PHASE"):
        _resample_contiguous(frame, "1h")


def test_missing_integrity_status_fails_closed() -> None:
    frame = pd.DataFrame(
        {
            "market": ["spot"],
            "symbol": ["AUSDT"],
            "archive_month": ["2024-01"],
            "raw_path": ["data/raw/spot/klines/AUSDT/1d/AUSDT-1d-2024-01.zip"],
            "published_sha256": ["a" * 64],
            "computed_sha256": ["a" * 64],
        }
    )

    with pytest.raises(RuntimeError, match="MISSING_INTEGRITY_PROVENANCE"):
        strict_verified_manifest(frame)


def test_spot_post_2025_microsecond_timestamps_normalize() -> None:
    assert infer_timestamp_unit(pd.Series([1609459200000])) == "ms"
    assert normalize_timestamp(pd.Series([1609459200000])).iloc[0] == pd.Timestamp("2021-01-01T00:00:00Z")
    assert infer_timestamp_unit(pd.Series([1735689600000000])) == "us"
    assert normalize_timestamp(pd.Series([1735689600000000])).iloc[0] == pd.Timestamp("2025-01-01T00:00:00Z")


def test_implausible_epoch_fail_closed() -> None:
    from binance_research.data import DataIntegrityError
    with pytest.raises(DataIntegrityError, match="implausible epoch"):
        infer_timestamp_unit(pd.Series([12345]))
    assert infer_timestamp_unit(pd.Series([1e19])) == "ns"
