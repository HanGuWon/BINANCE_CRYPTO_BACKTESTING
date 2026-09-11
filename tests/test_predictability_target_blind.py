from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

import binance_research.predictability_cli as cli
from binance_research.predictability import build_forward_labels


def _frame(n: int = 16) -> pd.DataFrame:
    times = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open_time": times,
            "close_time": times + pd.Timedelta(minutes=15),
            "open": np.arange(n, dtype=float) + 100,
            "close": np.arange(n, dtype=float) + 101,
            "feature": np.linspace(-1, 1, n),
        }
    )


def test_prospective_recorder_only_builds_labels_in_training_prefix(monkeypatch, tmp_path: Path):
    frame = _frame()
    calls: list[int] = []
    original_builder = cli.build_forward_labels

    def spy_builder(bars, *args, **kwargs):
        calls.append(len(bars))
        assert len(bars) <= 10, "prediction-region rows reached label construction"
        return original_builder(bars, *args, **kwargs)

    class FakeModel:
        def predict_proba(self, values):
            return np.full(len(values), 0.5, dtype=float)

    captured: list[pd.DataFrame] = []
    monkeypatch.setattr(cli, "_load_frame", lambda path: frame.copy())
    monkeypatch.setattr(cli, "_feature_frame", lambda value, timeframe: (value.copy(), ["feature"]))
    monkeypatch.setattr(cli, "build_forward_labels", spy_builder)
    monkeypatch.setattr(cli, "_prepare_output", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_fit_with_metadata", lambda *args, **kwargs: FakeModel())
    monkeypatch.setattr(cli, "write_model_artifact", lambda *args, **kwargs: "a" * 64)
    monkeypatch.setattr(cli, "append_predictions_write_once", lambda path, rows, **kwargs: captured.append(rows.copy()))
    monkeypatch.setattr(cli, "_write_json_once", lambda *args, **kwargs: None)

    args = SimpleNamespace(
        input=tmp_path / "input.csv",
        output=tmp_path / "out",
        mode="prospective",
        timeframe="15m",
        train_rows=10,
        train_end=None,
        horizons=("15m",),
        regularization=1.0,
        market="um",
        symbol="BTCUSDT",
        campaign_id="target-blind-test",
        dataset_sha256="d" * 64,
        source_tree_sha256="s" * 64,
        feature_registry_sha256="f" * 64,
        config_sha256="c" * 64,
    )

    assert cli.record_forward(args) == 0
    assert calls == [10]
    assert captured and not captured[0].empty
    assert set(captured[0]["mode"]) == {"prospective"}
