from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from binance_research.features import (
    CORE_FEATURE_SPECS,
    CoreFeatureEngine,
    build_market_breadth,
    classify_aggtrade_side,
    compute_gap_safe_features,
    preregistered_rule_variants,
)


def test_catalog_has_22_unique_preregistered_features() -> None:
    assert len(CORE_FEATURE_SPECS) == 22
    assert len({spec.feature_id for spec in CORE_FEATURE_SPECS}) == 22
    assert all(spec.warmup >= 1 and spec.documentation is not None for spec in CORE_FEATURE_SPECS)


def test_feature_warmup_and_bounds(bars: pd.DataFrame) -> None:
    output = CoreFeatureEngine().compute(bars)
    assert output["ema50_200_spread"].iloc[:199].isna().all()
    assert output["ema50_200_spread"].iloc[199:].notna().all()
    assert output["kaufman_er10"].dropna().between(0, 1).all()
    assert output["rsi14"].dropna().between(0, 100).all()
    assert output["spread_bps"].dropna().gt(0).all()
    assert output["causal_timestamp"].equals(bars["close_time"])


def test_appending_extreme_future_cannot_change_prior_features(bars: pd.DataFrame) -> None:
    engine = CoreFeatureEngine()
    prefix = bars.iloc[:350].copy()
    baseline = engine.compute(prefix)
    future = bars.iloc[350:].copy()
    future.loc[:, ["open", "high", "low", "close", "volume"]] *= 1_000
    extended = engine.compute(pd.concat([prefix, future], ignore_index=True)).iloc[:350]
    assert_frame_equal(baseline.reset_index(drop=True), extended.reset_index(drop=True), check_dtype=False)


def test_zero_volume_is_explicit_nan_not_infinity(bars: pd.DataFrame) -> None:
    zero = bars.copy()
    zero.loc[100:130, ["volume", "taker_buy_volume"]] = 0
    output = CoreFeatureEngine().compute(zero)
    assert not np.isinf(output.select_dtypes(include=[np.number]).to_numpy()).any()
    assert output.loc[119:130, "vwap20"].isna().any()


def test_aggtrade_side_classification_matches_binance_semantics() -> None:
    result = classify_aggtrade_side(pd.Series([False, True, False]))
    assert result.tolist() == [1, -1, 1]


def test_new_listing_does_not_enter_breadth_before_observed() -> None:
    times = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    panel = pd.DataFrame({
        "close_time": list(times) + list(times[2:]),
        "symbol": ["OLD"] * 4 + ["NEW"] * 2,
        "close": [1, 2, 3, 4, 5, 4],
    })
    result = build_market_breadth(panel, ema_period=2)
    early = result[result["close_time"] == times[1]]
    assert len(early) == 1
    assert early["breadth_pct_above_ema"].iloc[0] == 1.0


def test_preregistered_grid_has_exactly_twelve_trials(bars: pd.DataFrame) -> None:
    variants = preregistered_rule_variants(bars)
    assert len(variants.columns) == 12
    assert set(np.unique(variants.to_numpy()[np.isfinite(variants.to_numpy())])) <= {-1.0, 0.0, 1.0}

