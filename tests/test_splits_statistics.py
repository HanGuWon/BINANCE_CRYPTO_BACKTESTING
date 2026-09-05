from __future__ import annotations

import numpy as np
import pandas as pd

import pytest

from binance_research.splits import chronological_split, expanding_walk_forward, next_executable_open
from binance_research.statistics import annualize_sharpe, block_bootstrap_mean_ci, correlation_matrix, deflated_sharpe_probability, hierarchical_feature_clusters, trade_overlap_matrix


def test_chronological_split_and_embargo_never_shuffle() -> None:
    frame = pd.DataFrame({"value": range(100)})
    split = chronological_split(frame, 0.6, 0.2, embargo_bars=2)
    assert split.train["value"].tolist() == list(range(60))
    assert split.validation["value"].tolist() == list(range(62, 80))
    assert split.test["value"].tolist() == list(range(82, 100))
    assert split.embargo_rows["value"].tolist() == [60, 61, 80, 81]


def test_expanding_walk_forward_is_temporally_ordered() -> None:
    folds = expanding_walk_forward(120, 50, 10, 10, embargo_bars=2)
    assert folds
    assert all(fold.train_end < fold.validation_start < fold.validation_end < fold.test_start < fold.test_end for fold in folds)
    assert all(left.train_end < right.train_end for left, right in zip(folds, folds[1:]))


def test_split_preserves_arbitrary_labels_and_next_open_is_strict() -> None:
    frame = pd.DataFrame({"value": range(10)}, index=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    split = chronological_split(frame, 0.6, 0.2, embargo_bars=1)
    assert split.train.index.tolist() == [10, 20, 30, 40, 50, 60]
    assert split.validation.index.tolist() == [80]
    assert split.test.index.tolist() == [100]
    assert next_executable_open("2024-01-01T00:00:00+00:00", "15m") == pd.Timestamp("2024-01-01T00:15:00+00:00")
    assert next_executable_open("2024-01-01T00:14:59+00:00", "1h") == pd.Timestamp("2024-01-01T01:00:00+00:00")
    with pytest.raises(ValueError, match="explicit timezone"):
        next_executable_open("2024-01-01T00:00:00", "1h")


def test_statistics_are_deterministic_and_overlap_is_jaccard() -> None:
    values = pd.Series(np.arange(100, dtype=float))
    assert block_bootstrap_mean_ci(values, 5, samples=200, seed=1) == block_bootstrap_mean_ci(values, 5, samples=200, seed=1)
    signals = pd.DataFrame({"a": [1, 0, 1, 0], "b": [1, 1, 0, 0]})
    overlap = trade_overlap_matrix(signals)
    assert overlap.loc["a", "b"] == 1 / 3
    corr = correlation_matrix(pd.DataFrame({"a": range(30), "b": range(29, -1, -1)}))
    assert corr.loc["a", "b"] == -1
    clusters = hierarchical_feature_clusters(corr)
    assert clusters.index.tolist() == ["a", "b"]


def test_deflated_sharpe_requires_periodic_units_and_explicit_moments() -> None:
    trials = pd.Series([0.1, 0.2, 0.3])
    periodic = deflated_sharpe_probability(0.2, trials, 100, skewness=0.1, excess_kurtosis=0.2, moment_policy="observed")
    annualized_input = deflated_sharpe_probability(0.2 * np.sqrt(24), trials, 100, skewness=0.1, excess_kurtosis=0.2, moment_policy="observed")
    assert periodic != annualized_input
    assert annualize_sharpe(0.2, 24) == pytest.approx(0.2 * np.sqrt(24))
    with pytest.raises(ValueError, match="finite"):
        deflated_sharpe_probability(np.nan, trials, 100, skewness=0.0, excess_kurtosis=0.0)
    with pytest.raises(ValueError, match="gaussian_zero"):
        deflated_sharpe_probability(0.2, trials, 100, skewness=0.1, excess_kurtosis=0.0, moment_policy="gaussian_zero")
