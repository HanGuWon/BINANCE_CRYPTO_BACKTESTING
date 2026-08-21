from __future__ import annotations

import numpy as np
import pandas as pd

from binance_research.experiments import apply_quantile_model, fit_quantile_model, predictive_study


def test_quantile_boundaries_are_frozen_from_training_only() -> None:
    training = pd.Series(np.arange(100, dtype=float))
    model = fit_quantile_model(training, 5)
    validation = pd.Series([10.0, 90.0, 1e9])
    before = apply_quantile_model(validation, model)
    after = apply_quantile_model(pd.concat([validation, pd.Series([-1e12, 1e12])], ignore_index=True).iloc[:3], model)
    assert before.tolist() == after.tolist()


def test_predictive_return_enters_at_next_open() -> None:
    bars = pd.DataFrame({
        "open": [100, 200, 300, 400, 500, 600],
        "high": [101, 220, 330, 440, 550, 660],
        "low": [99, 180, 270, 360, 450, 540],
        "close": [100, 210, 320, 430, 540, 650],
    })
    feature = pd.Series([-3, -2, -1, 1, 2, 3], dtype=float)
    model = fit_quantile_model(pd.Series(np.arange(20, dtype=float)), 2)
    result = predictive_study(bars, feature, [1], model, "x", "validation")
    overall = result[result["slice"] == "overall"].iloc[0]
    expected = np.mean([210 / 200 - 1, 320 / 300 - 1, 430 / 400 - 1, 540 / 500 - 1, 650 / 600 - 1])
    assert overall["mean_future_return"] == pytest.approx(expected)


import pytest

