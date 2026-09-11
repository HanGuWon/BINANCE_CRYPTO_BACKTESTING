from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from binance_research.predictability import (
    build_forward_labels,
    evaluate_walk_forward,
    fit_logistic_model,
    mature_training_mask,
    probability_metrics,
    resolve_horizon_bars,
)


def _bars(rows: int = 420) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="15min", tz="UTC")
    close = 100 + 5 * np.sin(np.arange(rows, dtype=float) / 3)
    return pd.DataFrame(
        {
            "open_time": index,
            "open": np.r_[close[0], close[:-1]],
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.linspace(100, 200, rows),
            "signal": np.sin(np.arange(rows) / 7),
        }
    )


def test_labels_use_next_open_and_future_close() -> None:
    bars = pd.DataFrame({"open": [10.0, 20.0, 30.0], "close": [11.0, 21.0, 33.0]})
    labels = build_forward_labels(bars, 1)
    assert labels.loc[0, "future_log_return"] == pytest.approx(np.log(21 / 20))
    assert labels.loc[1, "future_log_return"] == pytest.approx(np.log(33 / 30))
    assert np.isnan(labels.loc[2, "future_log_return"])


def test_probability_metrics_distinguish_perfect_and_inverted_predictions() -> None:
    labels = pd.Series([0, 0, 1, 1])
    perfect = probability_metrics(labels, [0.01, 0.1, 0.9, 0.99])
    inverted = probability_metrics(labels, [0.99, 0.9, 0.1, 0.01])
    assert perfect["direction_accuracy"] == 1.0
    assert perfect["log_loss"] < inverted["log_loss"]
    assert perfect["roc_auc"] == pytest.approx(1.0)
    assert inverted["roc_auc"] == pytest.approx(0.0)


def test_logistic_model_is_deterministic_and_uses_training_scaling() -> None:
    frame = pd.DataFrame({"x": np.linspace(-3, 3, 40)})
    target = (frame["x"] > 0).astype(float)
    first = fit_logistic_model(frame, target, ["x"], regularization=1.0)
    second = fit_logistic_model(frame, target, ["x"], regularization=1.0)
    assert first == second
    assert first.predict_proba(pd.DataFrame({"x": [-2.0, 2.0]}))[0] < 0.5
    assert first.predict_proba(pd.DataFrame({"x": [-2.0, 2.0]}))[1] > 0.5


def test_walk_forward_compares_baseline_and_indicator() -> None:
    bars = _bars()
    bars["signal"] = np.where(np.arange(len(bars)) % 2 == 0, 1.0, -1.0)
    result = evaluate_walk_forward(bars, ["signal"], horizons=["15m"], minimum_train=160, validation_size=80, step_size=80)
    assert {"B0", "B1", "B1+I", "I:signal"}.issubset(set(result["model"]))
    assert result["log_loss_improvement"].notna().all()
    assert (result["count"] > 0).all()
    assert result["horizon"].eq("15m").all()


def test_horizon_resolution_is_duration_based_and_rejects_invalid_mappings() -> None:
    assert resolve_horizon_bars("15m", "15m") == 1
    assert resolve_horizon_bars("15m", "1h") == 4
    assert resolve_horizon_bars("1h", "1h") == 1
    assert resolve_horizon_bars("1h", "4h") == 4
    assert resolve_horizon_bars("1h", "24h") == 24
    assert resolve_horizon_bars("4h", "4h") == 1
    assert resolve_horizon_bars("4h", "24h") == 6
    with pytest.raises(ValueError, match="shorter"):
        resolve_horizon_bars("1h", "15m")
    with pytest.raises(ValueError, match="shorter"):
        resolve_horizon_bars("4h", "1h")
    with pytest.raises(ValueError, match="unsupported horizon"):
        resolve_horizon_bars("15m", "2h")


def test_labels_are_gap_safe_and_expose_strict_maturity_times() -> None:
    times = pd.date_range("2024-01-01", periods=8, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open_time": times,
            "close_time": times + pd.Timedelta(minutes=15),
            "open": np.arange(8, dtype=float) + 100,
            "close": np.arange(8, dtype=float) + 101,
        }
    )
    labels = build_forward_labels(bars, source_timeframe="15m", horizon="1h")
    assert labels.loc[0, "label_status"] == "ELIGIBLE"
    assert labels.loc[0, "entry_time"] == times[1]
    assert labels.loc[0, "exit_time"] == times[4]
    assert labels.loc[0, "decision_time"] == times[0] + pd.Timedelta(minutes=15)
    assert labels.loc[0, "label_available_time"] == times[4] + pd.Timedelta(minutes=15)
    boundary = labels.loc[4, "decision_time"]
    mature = mature_training_mask(labels.iloc[:5], boundary)
    assert not bool(mature.iloc[0])
    gapped = bars.drop(index=2).reset_index(drop=True)
    gapped_labels = build_forward_labels(gapped, source_timeframe="15m", horizon="1h")
    assert gapped_labels.loc[0, "label_status"] == "GAP"
    assert not bool(gapped_labels.loc[0, "eligible"])


def test_appending_future_rows_does_not_change_historical_labels() -> None:
    bars = _bars(12)
    base = build_forward_labels(bars.iloc[:8], source_timeframe="15m", horizon="1h")
    extended = build_forward_labels(bars, source_timeframe="15m", horizon="1h")
    for column in ("future_log_return", "direction_up", "label_status", "eligible", "entry_index", "exit_index"):
        # Only rows already mature in the shorter snapshot are invariant; appending
        # rows legitimately turns its prior insufficient tail into eligible labels.
        left = base.loc[:3, column].to_numpy()
        right = extended.loc[:3, column].to_numpy()
        if np.issubdtype(left.dtype, np.number):
            np.testing.assert_allclose(left, right, equal_nan=True)
        else:
            np.testing.assert_array_equal(left, right)

def test_split_purge_rejects_non_integral_duration() -> None:
    from binance_research.splits import horizon_purge_bars

    assert horizon_purge_bars("15m", target_hours=1) == 4
    assert horizon_purge_bars("4h", target_hours=24) == 6
    with pytest.raises(ValueError, match="not divisible"):
        horizon_purge_bars("4h", target_hours=1)