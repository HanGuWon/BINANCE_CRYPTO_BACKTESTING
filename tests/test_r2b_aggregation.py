"""Contract tests for the corrected R2B aggregator."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from aggregate_r2b import aggregate_series, calendar_block_bootstrap, concentration, replication_grade  # noqa: E402


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "decision_time": pd.to_datetime(["2020-01-01T00:00Z", "2020-01-01T00:00Z", "2020-02-01T00:00Z"]),
            "symbol": ["A", "B", "A"],
            "net_return": [0.1, 0.3, -0.2],
        }
    )


def test_decision_time_series_equal_weights_simultaneous_signals() -> None:
    series = aggregate_series(_trades())
    assert series.iloc[0] == 0.2
    assert series.iloc[1] == -0.2


def test_calendar_month_bootstrap_is_deterministic_and_joint() -> None:
    first = calendar_block_bootstrap(aggregate_series(_trades()))
    second = calendar_block_bootstrap(aggregate_series(_trades()))
    assert first.tolist() == second.tolist()
    assert len(first) == 1000


def test_aggregate_symbol_concentration_definition() -> None:
    result = concentration(_trades())
    assert result["top_symbol"] == "B"
    assert result["top_symbol_share_abs"] == pytest.approx(0.75)


def test_positive_fold_and_catastrophic_gates_are_required() -> None:
    row = type("Row", (), {"valid_fold_count": 4, "positive_fold_fraction": 0.75, "fdr_q_value": 0.05, "aggregate_hac_t": 3.0, "max_top_symbol_share_abs": 0.5, "worst_fold_aggregate_mean": 0.01, "best_fold_aggregate_mean": 0.02})()
    assert replication_grade(row) == "TEMPORAL_REPLICATION"
    row.worst_fold_aggregate_mean = -0.05
    assert replication_grade(row) == "NO_REPLICATION"
