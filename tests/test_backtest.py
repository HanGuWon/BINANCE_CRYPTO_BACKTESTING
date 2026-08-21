from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from binance_research.backtest import CostModel, run_backtest


def _bars() -> pd.DataFrame:
    return pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=7, freq="h", tz="UTC"),
        "open": [100, 110, 121, 100, 90, 81, 80],
        "high": [101, 122, 125, 101, 95, 85, 82],
        "low": [99, 108, 99, 89, 80, 79, 78],
        "close": [100, 120, 100, 90, 81, 80, 79],
        "funding_rate": [0, 0.001, 0.001, 0, 0, 0, 0],
    })


def test_next_bar_execution_and_exact_costs() -> None:
    bars = _bars()
    signal = pd.Series([1, 0, 0, 0, 0, 0, 0])
    costs = CostModel(maker_fee_bps=0, taker_fee_bps=5, fallback_spread_bps=2, slippage_bps=1)
    result = run_backtest(bars, signal, costs, holding_bars=2, market_type="um")
    trade = result.trades.iloc[0]
    assert trade["entry_bar"] == 1
    assert trade["exit_bar"] == 3
    assert trade["gross_return"] == pytest.approx(100 / 110 - 1)
    assert trade["fee_cost"] == pytest.approx(0.001)
    assert trade["spread_cost"] == pytest.approx(0.0002)
    assert trade["slippage_cost"] == pytest.approx(0.0002)
    assert trade["funding_cost"] == pytest.approx(0.002)


def test_futures_never_silently_assumes_zero_funding() -> None:
    bars = _bars().drop(columns="funding_rate")
    with pytest.raises(ValueError, match="funding_rate"):
        run_backtest(bars, pd.Series([1] * len(bars)), CostModel(), market_type="um")


def test_mfe_mae_and_long_short_symmetry() -> None:
    bars = _bars()
    costs = CostModel(0, 0, 0, 0)
    long = run_backtest(bars, pd.Series([1, 0, 0, 0, 0, 0, 0]), costs, holding_bars=2, market_type="um").trades.iloc[0]
    short = run_backtest(bars, pd.Series([-1, 0, 0, 0, 0, 0, 0]), costs, holding_bars=2, market_type="um").trades.iloc[0]
    assert long["mfe"] == pytest.approx(125 / 110 - 1)
    assert long["mae"] == pytest.approx(99 / 110 - 1)
    assert short["mfe"] == pytest.approx(-(99 / 110 - 1))
    assert short["mae"] == pytest.approx(-(125 / 110 - 1))
    assert long["gross_return"] == pytest.approx(-short["gross_return"])


def test_deterministic_replay(bars: pd.DataFrame) -> None:
    signal = pd.Series(np.where(np.arange(len(bars)) % 10 == 0, 1, 0), index=bars.index)
    first = run_backtest(bars, signal, CostModel(), holding_bars=4)
    second = run_backtest(bars, signal, CostModel(), holding_bars=4)
    assert_frame_equal(first.trades, second.trades)
    assert first.summary == second.summary

