from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ChronologicalPartitions:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    embargo_rows: pd.DataFrame


def chronological_split(
    frame: pd.DataFrame,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
    embargo_bars: int = 0,
) -> ChronologicalPartitions:
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train + validation must leave a test partition")
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be non-negative")
    n = len(frame)
    if n < 5:
        raise ValueError("at least five chronological observations are required")
    train_end = int(n * train_fraction)
    validation_end = int(n * (train_fraction + validation_fraction))
    validation_start = min(train_end + embargo_bars, validation_end)
    test_start = min(validation_end + embargo_bars, n)
    embargo_positions = list(range(train_end, validation_start)) + list(range(validation_end, test_start))
    return ChronologicalPartitions(
        train=frame.iloc[:train_end].copy(),
        validation=frame.iloc[validation_start:validation_end].copy(),
        test=frame.iloc[test_start:].copy(),
        embargo_rows=frame.iloc[embargo_positions].copy(),
    )


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int
    test_start: int
    test_end: int


def expanding_walk_forward(
    n_observations: int,
    minimum_train: int,
    validation_size: int,
    test_size: int,
    step_size: int | None = None,
    embargo_bars: int = 0,
) -> list[WalkForwardFold]:
    if min(n_observations, minimum_train, validation_size, test_size) <= 0:
        raise ValueError("walk-forward sizes must be positive")
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be non-negative")
    step = step_size or test_size
    folds: list[WalkForwardFold] = []
    train_end = minimum_train
    fold = 0
    while True:
        validation_start = train_end + embargo_bars
        validation_end = validation_start + validation_size
        test_start = validation_end + embargo_bars
        test_end = test_start + test_size
        if test_end > n_observations:
            break
        folds.append(WalkForwardFold(fold, 0, train_end, validation_start, validation_end, test_start, test_end))
        fold += 1
        train_end += step
    return folds

