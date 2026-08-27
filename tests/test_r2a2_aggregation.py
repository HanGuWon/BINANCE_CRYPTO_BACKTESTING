"""Regression tests for the frozen R2A.2 aggregation contract."""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from scripts.aggregate_r2a2 import (
    BOOTSTRAP_SAMPLES,
    SEED,
    calendar_block_bootstrap,
    evaluate_temporal_replication,
)


def _row(**overrides: object) -> object:
    values = {
        "valid_fold_count": 4,
        "positive_fold_fraction": 0.75,
        "fdr_q_value": 0.01,
        "aggregate_hac_t": 3.1,
        "max_top_symbol_share_abs": 0.4,
        "worst_fold_aggregate_mean": 0.01,
        "best_fold_aggregate_mean": 0.03,
    }
    values.update(overrides)
    return type("Row", (), values)()


def _trades() -> pd.DataFrame:
    return pd.DataFrame({
        "decision_time": pd.to_datetime(["2020-01-02", "2020-01-02", "2020-02-02", "2020-02-02"], utc=True),
        "symbol": ["AAA", "BBB", "AAA", "BBB"],
        "net_return": [0.10, 0.30, -0.20, 0.00],
    })


def test_calendar_bootstrap_is_1000_and_seed_deterministic() -> None:
    values = calendar_block_bootstrap(_trades())
    assert len(values) == BOOTSTRAP_SAMPLES == 1000
    assert np.array_equal(values, calendar_block_bootstrap(_trades(), samples=1000, seed=SEED))


def test_calendar_bootstrap_preserves_cross_sectional_blocks() -> None:
    trades = _trades()
    # Sampling the DataFrame must equal sampling its already equal-weighted
    # decision-time series: symbols in a month are never sampled separately.
    series = trades.groupby("decision_time", sort=True).net_return.mean()
    np.testing.assert_array_equal(calendar_block_bootstrap(trades), calendar_block_bootstrap(series))


@pytest.mark.parametrize("field,value", [
    ("max_top_symbol_share_abs", 0.5001),
    ("aggregate_hac_t", 2.99),
    ("fdr_q_value", 0.0501),
    ("positive_fold_fraction", 0.749),
])
def test_every_replication_criterion_is_required(field: str, value: float) -> None:
    assert evaluate_temporal_replication(_row(**{field: value})) == "NO_REPLICATION"


def test_catastrophic_reversal_cannot_pass() -> None:
    assert evaluate_temporal_replication(_row(worst_fold_aggregate_mean=-0.25, best_fold_aggregate_mean=0.10)) == "NO_REPLICATION"


def test_fewer_than_four_valid_folds_is_insufficient() -> None:
    assert evaluate_temporal_replication(_row(valid_fold_count=3)) == "INSUFFICIENT_FOLDS"


def test_missing_required_evidence_fails_closed() -> None:
    assert evaluate_temporal_replication(_row(max_top_symbol_share_abs=float("nan"))) == "INSUFFICIENT_EVIDENCE"
