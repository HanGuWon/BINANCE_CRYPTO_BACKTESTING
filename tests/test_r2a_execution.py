"""Regression tests for the R2A execution engine (pre-outcome correctness)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from binance_research.derivatives import crossed_funding_events  # noqa: E402
from r2a_engine import (  # noqa: E402
    HOLDOUT_BOUNDARY_BY_TF,
    HoldoutViolation,
    OPERATIONAL_EMBARGO_BARS,
    SPLIT_FIRST_VALIDATION,
    SPLIT_LAST_TRAIN,
    SPLIT_LAST_VALIDATION,
    _execute_symbol,
    assert_no_holdout,
    compute_signal,
    evaluate_trial,
    run_single_trial,
)
from verify_r2a_registry import HORIZON_BARS_24H  # noqa: E402


def _panel(n: int = 400, market: str = "um", timeframe: str = "1h") -> pd.DataFrame:
    stamps = pd.date_range("2023-06-01", periods=n, freq=timeframe.replace("m", "min") if timeframe.endswith("m") else "1h", tz="UTC")
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.003, n)))
    open_ = np.r_[close[0], close[:-1]]
    frame = pd.DataFrame({
        "timestamp": stamps,
        "open": open_, "high": np.maximum(open_, close) + 0.2,
        "low": np.minimum(open_, close) - 0.2, "close": close,
        "volume": rng.lognormal(4, 0.3, n),
        "taker_buy_volume": rng.uniform(0.3, 0.7) * rng.lognormal(4, 0.3, n),
        "row_class": "RESEARCH_ELIGIBLE",
        "universe_month": stamps.strftime("%Y-%m"),
        "symbol": "BTCUSDT", "market": market, "timeframe": timeframe,
        "btc_regime": np.where(np.arange(n) % 5 == 0, 0.0, 1.0),
        "market_breadth": rng.uniform(0.2, 0.8, n),
        "funding_rate": np.zeros(n),
        "funding_zscore90_y": np.zeros(n),
        "funding_zscore90": np.zeros(n),
    })
    frame["taker_buy_volume"] = frame["volume"] * rng.uniform(0.3, 0.7, n)
    return frame


def test_holdout_timestamps_rejected() -> None:
    panel = _panel(50)
    panel.loc[panel.index[-1], "timestamp"] = HOLDOUT_BOUNDARY_BY_TF["1h"]
    with pytest.raises(HoldoutViolation):
        assert_no_holdout(panel, timeframe="1h")


def test_exact_purge_embargo_boundaries_match_split_metadata() -> None:
    metadata = pd.read_csv(ROOT / "campaigns" / "r1_final_panel_v1" / "split_metadata_final.csv")
    for row in metadata.itertuples(index=False):
        assert SPLIT_LAST_TRAIN[row.timeframe] == pd.Timestamp(row.last_train_timestamp_utc)
        assert SPLIT_FIRST_VALIDATION[row.timeframe] == pd.Timestamp(row.first_validation_timestamp_utc)
        assert SPLIT_LAST_VALIDATION[row.timeframe] == pd.Timestamp(row.last_validation_timestamp_utc)
        assert int(row.operational_embargo_bars) == OPERATIONAL_EMBARGO_BARS
        assert HORIZON_BARS_24H[row.timeframe] == int(row.purge_bars_24h)


def test_next_open_execution_and_same_close_impossible() -> None:
    trial = {"trial_id": "T0001", "feature_id": "momentum.rsi", "variant": "rsi_14_30_70", "market": "spot", "timeframe": "1h", "side": "LONG"}
    panel = _panel(market="spot")
    universe = {("spot", month, "BTCUSDT") for month in panel.universe_month.unique()}
    trades, eligible = _execute_symbol(panel, trial, universe, {})
    if len(trades):
        decision_times = pd.to_datetime(trades.decision_time, utc=True).to_numpy()
        entry_times = pd.to_datetime(trades.entry_time, utc=True).to_numpy()
        assert (entry_times > decision_times).all()  # never same bar (same-close)


def test_funding_event_cost_crossing() -> None:
    events = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=10, freq="8h", tz="UTC"),
        "funding_rate": [0.0001] * 10,
    })
    positions = pd.DataFrame({
        "entry_timestamp": [events.timestamp.iloc[0]],
        "exit_timestamp": [events.timestamp.iloc[3]],
        "side": [1],
    })
    crossed = crossed_funding_events(positions, events)
    assert crossed.loc[0, "crossed_event_count"] == 3
    assert crossed.loc[0, "funding_cashflow_return"] == pytest.approx(-0.0003)


def test_deterministic_signal_and_bootstrap_reproducibility(bars: pd.DataFrame) -> None:
    first = compute_signal(_panel(), "momentum.rsi", "rsi_14_30_70", "um")
    second = compute_signal(_panel(), "momentum.rsi", "rsi_14_30_70", "um")
    pd.testing.assert_series_equal(first, second)
    trial = {"trial_id": "T0001", "feature_id": "momentum.rsi", "variant": "rsi_14_30_70", "market": "um", "timeframe": "1h", "side": "LONG"}
    panel = _panel()
    universe = {("um", month, "BTCUSDT") for month in panel.universe_month.unique()}
    evidence_a, trades_a = run_single_trial(trial, panel, universe_top50=universe)
    evidence_b, trades_b = run_single_trial(trial, panel, universe_top50=universe)
    assert evidence_a == evidence_b
    pd.testing.assert_frame_equal(trades_a, trades_b)


def test_evaluation_metrics_contract() -> None:
    trades = pd.DataFrame({
        "universe_month": ["2024-01"] * 40,
        "gross_return": np.linspace(0.001, 0.01, 40),
        "net_return": np.linspace(0.0005, 0.009, 40),
    })
    evidence = evaluate_trial(trades, periods_per_year=365 * 24, total_eligible_rows=1000, holding_bars=24)
    for key in ("observations", "signals", "executed_trades", "signal_frequency", "exposure", "turnover", "hit_rate", "mean_net_return", "hac_t_stat"):
        assert key in evidence and np.isfinite(evidence[key]) or key == "bootstrap_ci_low"
