from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import binance_research.fast_discovery as fd


def test_role_grammar_keeps_trigger_scale_and_never_averages() -> None:
    frame = pd.DataFrame(
        {
            "trigger": [1.0, -1.0, 0.0, np.nan, 0.5],
            "regime": [100.0, -100.0, 100.0, 100.0, 1.0],
            "rvol20": [2.0, 2.0, 2.0, 2.0, 2.0],
        }
    )
    result = fd.compose_role_aware_signal(frame, trigger="trigger", regime_filter="regime", participation="rvol20")
    pd.testing.assert_series_equal(result, pd.Series([1.0, -1.0, 0.0, 0.0, 0.5]), check_names=False)
    assert result.iloc[0] != pytest.approx(frame.loc[0, ["trigger", "regime", "rvol20"]].mean())


def test_role_grammar_requires_directional_regime_concordance() -> None:
    frame = pd.DataFrame(
        {
            "trigger": [1.0, -1.0, 1.0, -1.0, 0.0],
            "regime": [-1.0, 1.0, 1.0, -1.0, 1.0],
            "rvol20": [2.0] * 5,
        }
    )
    result = fd.compose_role_aware_signal(frame, trigger="trigger", regime_filter="regime", participation="rvol20")
    assert result.tolist() == [0.0, 0.0, 1.0, -1.0, 0.0]


def test_ratio_participation_confirms_trigger_direction() -> None:
    frame = pd.DataFrame(
        {
            "trigger": [1.0, -1.0, 1.0, -1.0, 1.0],
            "regime": [1.0, -1.0, 1.0, -1.0, 1.0],
            "taker_buy_sell_ratio": [1.2, 0.8, 0.8, 1.2, 1.0],
        }
    )
    result = fd.compose_role_aware_signal(frame, trigger="trigger", regime_filter="regime", participation="taker_buy_sell_ratio")
    assert result.tolist() == [1.0, -1.0, 0.0, 0.0, 0.0]


def test_role_grammar_fails_closed_for_missing_component() -> None:
    frame = pd.DataFrame({"trigger": [1.0], "regime": [1.0]})
    with pytest.raises(ValueError, match="rvol20"):
        fd.compose_role_aware_signal(frame, trigger="trigger", regime_filter="regime", participation="rvol20")


def test_s1_requires_primary_trigger_s0_survivor(monkeypatch) -> None:
    frame = pd.DataFrame(
        {
            "donchian_breakout20": [1.0, -1.0],
            "ema20_slope_5": [1.0, -1.0],
            "rvol20": [2.0, 2.0],
            "roc6": [1.0, -1.0],
            "sig_ema20_50": [1.0, -1.0],
            "taker_buy_sell_ratio": [1.2, 0.8],
            "bb_bandwidth20": [1.0, 1.0],
            "premium_zscore90": [1.0, -1.0],
        }
    )
    monkeypatch.setattr(fd, "evaluate_walk_forward", lambda *args, **kwargs: pd.DataFrame())
    s0 = pd.DataFrame([{"feature_id": "ema20_slope_5", "status": "S0_SURVIVOR"}])
    result = fd._evaluate_s1(frame, s0, timeframe="1h")
    assert set(result["status"]) == {"REJECTED"}
    assert "primary trigger" in result.iloc[0]["reason"]
    assert set(result["role_grammar"]) == {fd.S1_ROLE_GRAMMAR}


def test_registry_declares_frozen_role_grammar() -> None:
    registry = fd.build_s1_registry()
    assert list(registry["role_grammar"].unique()) == [fd.S1_ROLE_GRAMMAR]
    assert set(registry["trigger"]) == {combo[0] for combo in fd.S1_COMBINATIONS}
    assert len(registry) == fd.S1_MAX_COMBINATIONS
    assert int(registry["component_count"].max()) <= fd.S1_MAX_COMPONENTS



