from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from binance_research.predictability import build_forward_labels
from binance_research.predictability_cli import evaluate_forward
from binance_research.forward import prediction_identity


def test_evaluator_uses_stored_b1_as_paired_baseline(tmp_path: Path):
    times = pd.date_range("2025-01-01", periods=12, freq="15min", tz="UTC")
    frame = pd.DataFrame({"open_time": times, "close_time": times + pd.Timedelta(minutes=15), "open": np.arange(12) + 100.0, "close": np.arange(12) + 101.0})
    input_path = tmp_path / "bars.csv"
    frame.to_csv(input_path, index=False)
    labels = build_forward_labels(frame, source_timeframe="15m", horizon="15m")
    decision = labels.loc[0, "decision_time"]
    row = {
        "campaign_id": "cmp", "market": "um", "symbol": "BTCUSDT", "timeframe": "15m",
        "decision_time": str(decision), "horizon": "15m", "feature_id": "x", "model": "B1+I", "model_id": "m",
        "mode": "prospective", "b1_probability_up": 0.5, "b1_plus_i_probability_up": 0.9, "probability_up": 0.9,
        "model_artifact_sha256": "a" * 64, "dataset_sha256": "d" * 64, "source_tree_sha256": "s" * 64,
        "feature_registry_sha256": "f" * 64, "config_sha256": "c" * 64,
    }
    row["prediction_id"] = prediction_identity(market="um", symbol="BTCUSDT", timeframe="15m", decision_time=decision, horizon="15m", model_id="m", campaign_id="cmp", mode="prospective", model_artifact_sha256="a" * 64, dataset_sha256="d" * 64, source_tree_sha256="s" * 64, feature_registry_sha256="f" * 64, config_sha256="c" * 64)
    prediction_path = tmp_path / "predictions.csv"
    pd.DataFrame([row]).to_csv(prediction_path, index=False)
    output = tmp_path / "evaluation"
    args = SimpleNamespace(input=input_path, predictions=prediction_path, output=output, timeframe="15m")
    assert evaluate_forward(args) == 0
    result = pd.read_csv(output / "forward_evaluation.csv")
    assert result.loc[0, "paired_count"] == 1
    assert result.loc[0, "log_loss_improvement"] != 0
    assert result.loc[0, "independent_block_count"] == 1
    assert "holm_adjusted_p_value" in result.columns
    assert "holm_reject" in result.columns

