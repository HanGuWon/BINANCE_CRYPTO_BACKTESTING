from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from binance_research.fast_discovery_signals import S0_SIGNAL_SEMANTICS, apply_s0_signal_semantics


def test_directional_semantics_preserve_sign_zero_and_nan() -> None:
    frame = pd.DataFrame(
        {
            "donchian_breakout20": [1.0, -1.0, 0.0, np.nan],
            "roc6": [2.0, -3.0, 0.0, np.nan],
            "vwap_deviation20": [0.2, -0.2, 0.0, np.nan],
            "taker_buy_sell_ratio": [1.2, 0.8, 1.0, np.nan],
            "cvd_slope6": [3.0, -3.0, 0.0, np.nan],
        }
    )
    result = apply_s0_signal_semantics(frame, primitives=list(frame.columns))
    assert result["sig_donchian_breakout20"].tolist()[:3] == [1.0, -1.0, 0.0]
    assert result["sig_roc6"].tolist()[:3] == [1.0, -1.0, 0.0]
    assert result["sig_vwap_deviation20"].tolist()[:3] == [-1.0, 1.0, 0.0]
    assert result["sig_taker_buy_sell_ratio"].tolist()[:3] == [1.0, -1.0, 0.0]
    assert result["sig_cvd_slope6"].tolist()[:3] == [1.0, -1.0, 0.0]
    assert result[["sig_donchian_breakout20", "sig_roc6", "sig_vwap_deviation20", "sig_taker_buy_sell_ratio", "sig_cvd_slope6"]].iloc[3].isna().all()


def test_continuous_primitives_are_not_polarity_reinterpreted() -> None:
    frame = pd.DataFrame({name: [1.25, -0.5, np.nan] for name in ("rvol20", "bb_bandwidth20", "premium", "premium_zscore90")})
    result = apply_s0_signal_semantics(frame, primitives=list(frame.columns))
    for name in frame:
        pd.testing.assert_series_equal(result[f"sig_{name}"], frame[name], check_names=False)


def test_unknown_primitive_fails_closed_and_future_append_does_not_rewrite_history() -> None:
    frame = pd.DataFrame({"roc6": [1.0, -1.0, 0.0]})
    with pytest.raises(ValueError, match="unknown S0 primitive"):
        apply_s0_signal_semantics(frame, primitives=["not_registered"])
    before = apply_s0_signal_semantics(frame, primitives=["roc6"])
    appended = apply_s0_signal_semantics(pd.concat([frame, pd.DataFrame({"roc6": [99.0]})], ignore_index=True), primitives=["roc6"])
    pd.testing.assert_series_equal(before["sig_roc6"], appended["sig_roc6"].iloc[:3].reset_index(drop=True), check_names=False)


def test_semantics_table_has_explicit_kind_equation_and_polarity() -> None:
    assert len(S0_SIGNAL_SEMANTICS) == 9
    assert all(set(spec) == {"kind", "equation", "polarity"} for spec in S0_SIGNAL_SEMANTICS.values())


