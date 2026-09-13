from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from binance_research.fast_discovery_context import build_btc_regime, build_top50_breadth


def test_btc_regime_is_trailing_and_nan_during_warmup() -> None:
    stamps = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    benchmark = pd.DataFrame({"open_time": stamps, "close": [100.0, 100.0, 100.0, 102.0, 98.0]})
    result = build_btc_regime(benchmark, ema_span=3, threshold=0.005)
    assert result["btc_regime"].iloc[:2].isna().all()
    assert result["btc_regime"].iloc[3] == 1.0
    assert result.attrs["role"] == "CONTEXT_OR_REGIME_FILTER"


def test_breadth_uses_only_selected_top50_rows() -> None:
    stamps = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    rows = []
    for symbol, closes, selected in (("AAA", [1, 2, 3, 4], True), ("BBB", [4, 3, 2, 1], True), ("CCC", [100, 1, 1, 1], False)):
        for ts, close in zip(stamps, closes):
            rows.append({"open_time": ts, "symbol": symbol, "segment_id": "seg", "market": "um", "close": float(close), "selected_top50": selected})
    result = build_top50_breadth(pd.DataFrame(rows), ema_span=2)
    at_last = result[result.open_time == stamps[-1]]
    assert at_last["top50_breadth"].dropna().iloc[0] == pytest.approx(0.5)
    assert result.attrs["holdout_status"] == "UNTOUCHED"


def test_breadth_requires_segment_identity_and_future_rows_do_not_change_history() -> None:
    stamps = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    panel = pd.DataFrame({"open_time": stamps, "symbol": ["AAA"] * 4, "segment_id": ["seg"] * 4, "market": ["um"] * 4, "close": [1.0, 2.0, 3.0, 4.0], "selected_top50": [True] * 4})
    before = build_top50_breadth(panel, ema_span=2)
    after = build_top50_breadth(pd.concat([panel, panel.iloc[[-1]].assign(open_time=stamps[-1] + pd.Timedelta(hours=1), close=99.0)], ignore_index=True), ema_span=2)
    pd.testing.assert_series_equal(before["top50_breadth"], after["top50_breadth"].iloc[:4], check_names=False)
    with pytest.raises(ValueError, match="segment_id"):
        build_top50_breadth(panel.drop(columns="segment_id"), ema_span=2)
