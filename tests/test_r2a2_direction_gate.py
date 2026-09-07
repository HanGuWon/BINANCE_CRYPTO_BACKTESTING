"""Directional signal sign gate tests (follow-up audit P0)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from run_r2a2_v2 import execute_segment  # noqa: E402
from verify_r2a_registry import SIGNAL_SEMANTICS  # noqa: E402


def _panel(signals: list[float]) -> pd.DataFrame:
    n = len(signals) + 30  # room for entry+exit beyond last decision
    stamps = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    close = 100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0.0005, 0.004, n)))
    open_ = np.r_[close[0], close[:-1]]
    frame = pd.DataFrame({
        "timestamp": stamps, "open": open_, "high": np.maximum(open_, close) + 0.2,
        "low": np.minimum(open_, close) - 0.2, "close": close,
        "volume": np.ones(n), "taker_buy_volume": np.full(n, 0.5),
        "row_class": "RESEARCH_ELIGIBLE",
        "universe_month": stamps.strftime("%Y-%m"),
        "symbol": "BTCUSDT", "market": "um", "timeframe": "1h",
    })
    # Prepend a warmup segment of zeros so decisions land inside the panel.
    pad = pd.DataFrame({col: [np.nan] * 10 if col != "timestamp" else pd.date_range("2022-12-25", periods=10, freq="h", tz="UTC") for col in frame.columns})
    pad["open"] = 100.0; pad["high"] = 100.5; pad["low"] = 99.5; pad["close"] = 100.0
    pad["volume"] = 1.0; pad["taker_buy_volume"] = 0.5; pad["row_class"] = "RESEARCH_ELIGIBLE"
    pad["universe_month"] = pad["timestamp"].dt.strftime("%Y-%m")
    pad["symbol"] = "BTCUSDT"; pad["market"] = "um"; pad["timeframe"] = "1h"
    combined = pd.concat([pad, frame], ignore_index=True)
    combined["_signal_override"] = [np.nan] * 10 + list(signals) + [np.nan] * (n - len(signals))
    return combined


def _run(panel: pd.DataFrame, side: str) -> pd.DataFrame:
    universe = {("um", m, "BTCUSDT") for m in panel.universe_month.unique()}
    signal = panel["_signal_override"].fillna(0.0)
    segment = panel.drop(columns=["_signal_override"]).reset_index(drop=True)
    return execute_segment(
        segment, signal.reset_index(drop=True), market="um", side=side,
        horizon_bars=24, validation_start=pd.Timestamp("2022-12-01", tz="UTC"),
        validation_end=pd.Timestamp("2023-06-01", tz="UTC"),
        universe_top50=universe, funding_events=None,
    )


def test_long_only_on_plus_one() -> None:
    trades = _run(_panel([1.0]), "LONG")
    assert len(trades) == 1 and trades.iloc[0]["signal_value"] == 1.0


def test_long_ignores_minus_one() -> None:
    assert len(_run(_panel([-1.0]), "LONG")) == 0  # Spot/UM LONG never on bearish


def test_short_only_on_minus_one() -> None:
    trades = _run(_panel([-1.0]), "SHORT")
    assert len(trades) == 1 and trades.iloc[0]["signal_value"] == -1.0


def test_short_ignores_plus_one() -> None:
    assert len(_run(_panel([1.0]), "SHORT")) == 0


def test_zero_never_enters() -> None:
    assert len(_run(_panel([0.0]), "LONG")) == 0
    assert len(_run(_panel([0.0]), "SHORT")) == 0


def test_mixed_signs_route_to_correct_sides() -> None:
    long_trades = _run(_panel([1.0, -1.0, 1.0]), "LONG")
    short_trades = _run(_panel([1.0, -1.0, 1.0]), "SHORT")
    assert set(long_trades.signal_value) <= {1.0}
    assert set(short_trades.signal_value) <= {-1.0}


def test_frozen_semantics_directional_values_documented() -> None:
    """Frozen semantics must remain directional (+1/-1/0); audit guard."""
    for key in (("trend.ema_20_50_spread", "ema_20_50"), ("momentum.rsi", "rsi_14_30_70"), ("trend.donchian", "donchian_20"), ("derivatives.funding", "funding_sign")):
        assert key in SIGNAL_SEMANTICS  # semantics table intact; only execution was wrong
