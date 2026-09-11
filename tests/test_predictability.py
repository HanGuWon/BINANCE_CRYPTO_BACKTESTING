from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from binance_research.predictability import (
    build_forward_labels,
    evaluate_walk_forward,
    fit_logistic_model,
    probability_metrics,
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
