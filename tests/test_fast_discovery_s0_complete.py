from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import binance_research.fast_discovery as fd


def _frame() -> pd.DataFrame:
    n = 96
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
            "open": np.linspace(100, 110, n),
            "close": np.linspace(100.5, 110.5, n),
            "symbol": ["AAAUSDT"] * n,
            "segment_id": ["seg1"] * n,
            "premium": np.sin(np.arange(n) / 5),
        }
    )


def _evaluation(frame, feature_columns, **kwargs):
    name = feature_columns[0]
    return pd.DataFrame(
        [
            {"model": "I:" + name, "horizon": "1h", "fold": 0, "validation_rows": 8, "log_loss_improvement": 0.2, "brier_improvement": 0.1, "validation_calendar_blocks": "2024-01-03T00:00:00+00:00|2024-01-04T00:00:00+00:00"},
            {"model": "I:" + name, "horizon": "1h", "fold": 1, "validation_rows": 8, "log_loss_improvement": 0.1, "brier_improvement": 0.05, "validation_calendar_blocks": "2024-01-05T00:00:00+00:00"},
            {"model": "I:" + name, "horizon": "4h", "fold": 0, "validation_rows": 8, "log_loss_improvement": -0.2, "brier_improvement": -0.1, "validation_calendar_blocks": "2024-01-03T00:00:00+00:00|2024-01-04T00:00:00+00:00"},
        ]
    )


def test_complete_s0_keeps_every_candidate_horizon_and_separates_blocks(monkeypatch) -> None:
    monkeypatch.setattr(fd, "evaluate_walk_forward", _evaluation)
    complete, rejected, cache = fd.screen_s0_complete(_frame(), horizons=("1h", "4h"), primitives=("premium", "missing"), minimum_train=8, validation_size=8, step_size=8)
    assert len(complete) == 4
    assert set(complete["feature_id"]) == {"premium", "missing"}
    premium_1h = complete.query("feature_id == 'premium' and horizon == '1h'").iloc[0]
    assert premium_1h.status == "S0_REJECTED"  # one-symbol fixture fails the real multi-symbol gate
    assert premium_1h.valid_temporal_folds == 2
    assert premium_1h.independent_calendar_block_count == 3
    assert premium_1h.brier_improvement == pytest.approx(0.075)
    missing = complete[complete.feature_id == "missing"]
    assert set(missing.status) == {"HISTORICAL_UNAVAILABLE"}
    assert len(rejected) == 4
    assert cache.misses == 1

