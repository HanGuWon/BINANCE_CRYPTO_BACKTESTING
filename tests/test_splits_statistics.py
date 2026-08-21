from __future__ import annotations

import numpy as np
import pandas as pd

from binance_research.splits import chronological_split, expanding_walk_forward
from binance_research.statistics import block_bootstrap_mean_ci, correlation_matrix, hierarchical_feature_clusters, trade_overlap_matrix


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
