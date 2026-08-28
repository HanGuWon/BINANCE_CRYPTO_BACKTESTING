"""Structural and directional guards for the dedicated R2B runner."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from r2b_historical_runner import derive_execution_segments, execute_frame, load_registry  # noqa: E402
from r2b_signals import side_accepts_signal  # noqa: E402


def test_historical_registry_expands_to_576_units() -> None:
    trials, folds = load_registry()
    assert len(trials) == 72
    assert len({str(row["fold_id"]) for row in folds}) == 8
    units = {(str(f["fold_id"]), str(t["trial_id"])) for f in folds for t in trials if f["timeframe"] == t["timeframe"] and int(f["horizon_bars"]) == int(t["horizon_bars"])}
    assert len(units) == 576


def test_runner_side_gate_is_strict_and_nan_safe() -> None:
    assert side_accepts_signal(1.0, "LONG")
    assert not side_accepts_signal(-1.0, "LONG")
    assert side_accepts_signal(-1.0, "SHORT")
    assert not side_accepts_signal(1.0, "SHORT")
    assert not side_accepts_signal(0.0, "LONG")
    assert not side_accepts_signal(float("nan"), "SHORT")


def _gap_fixture() -> pd.DataFrame:
    timestamps = pd.to_datetime(
        ["2020-10-31 23:45Z", "2020-12-01 00:00Z", "2020-12-01 00:15Z", "2020-12-01 00:30Z"]
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "segment_id": [0, 0, 0, 0],
            "symbol": ["IOTAUSDT"] * 4,
            "open": [100.0, 101.0, 102.0, 103.0],
            "premium": [1.0, -1.0, -1.0, -1.0],
            "source_open_time": timestamps,
            "source_available_time": timestamps - pd.Timedelta(minutes=1),
        }
    )


def test_membership_gap_creates_new_execution_segment() -> None:
    segmented = derive_execution_segments(_gap_fixture(), "15m")
    assert segmented.loc[0, "execution_segment_id"] != segmented.loc[1, "execution_segment_id"]
    assert segmented.loc[1:, "execution_segment_id"].nunique() == 1


def test_no_trade_crosses_membership_gap() -> None:
    panel = derive_execution_segments(_gap_fixture(), "15m")
    trial = {
        "timeframe": "15m",
        "side": "LONG",
        "horizon_bars": 1,
        "feature_id": "derivatives.premium",
        "signal_variant": "PRESSURE_CONTINUATION",
    }
    trades = execute_frame(
        panel,
        trial,
        pd.Timestamp("2020-10-01", tz="UTC"),
        pd.Timestamp("2021-01-01", tz="UTC"),
        pd.DataFrame(columns=["timestamp", "funding_rate"]),
    )
    assert trades.empty


def test_missing_execution_price_breaks_continuity() -> None:
    panel = _gap_fixture()
    panel.loc[1, "open"] = float("nan")
    segmented = derive_execution_segments(panel, "15m")
    assert segmented.loc[0, "execution_segment_id"] != segmented.loc[1, "execution_segment_id"]
    assert segmented.loc[1, "execution_segment_id"] != segmented.loc[2, "execution_segment_id"]
