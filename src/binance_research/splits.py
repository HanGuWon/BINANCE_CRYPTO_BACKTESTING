from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ChronologicalPartitions:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    embargo_rows: pd.DataFrame


@dataclass(frozen=True)
class GlobalCalendarPartitions:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    boundaries: dict[str, str]
    purge_bars: dict[str, int]


HORIZON_PURGE_BARS_24H = {"15m": 96, "1h": 24, "4h": 6}


def global_calendar_split(
    frame: pd.DataFrame,
    *,
    timestamp_column: str = "timestamp",
    train_end: str,
    validation_end: str,
    timeframe: str,
    operational_embargo_bars: int = 0,
) -> GlobalCalendarPartitions:
    """Split every symbol on shared UTC dates and purge future-label leakage."""
    if timeframe not in HORIZON_PURGE_BARS_24H:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    if operational_embargo_bars < 0:
        raise ValueError("operational_embargo_bars must be non-negative")
    if timestamp_column not in frame:
        raise ValueError(f"missing split timestamp column: {timestamp_column}")
    ordered = frame.copy()
    ordered[timestamp_column] = pd.to_datetime(ordered[timestamp_column], utc=True)
    train_boundary = pd.Timestamp(train_end, tz="UTC")
    validation_boundary = pd.Timestamp(validation_end, tz="UTC")
    if validation_boundary <= train_boundary:
        raise ValueError("validation_end must be after train_end")
    purge = HORIZON_PURGE_BARS_24H[timeframe]
    # Calendar boundaries are authoritative; purge is represented as a UTC
    # timestamp mask when the source rows are regular, without percentage-based
    # per-symbol partitions.
    step = pd.Timedelta({"15m": "15min", "1h": "1h", "4h": "4h"}[timeframe])
    train_cut = train_boundary - purge * step
    validation_cut = validation_boundary - purge * step
    embargo_delta = operational_embargo_bars * step
    validation_start = train_boundary + embargo_delta
    test_start = validation_boundary + embargo_delta
    train = ordered[ordered[timestamp_column] < train_cut].copy()
    validation = ordered[(ordered[timestamp_column] >= validation_start) & (ordered[timestamp_column] < validation_cut)].copy()
    test = ordered[ordered[timestamp_column] >= test_start].copy()
    return GlobalCalendarPartitions(
        train=train,
        validation=validation,
        test=test,
        boundaries={"train_end": train_boundary.isoformat(), "validation_end": validation_boundary.isoformat()},
        purge_bars={"target_horizon": purge, "operational_embargo": operational_embargo_bars},
    )


def horizon_purge_bars(timeframe: str, *, target_hours: int = 24) -> int:
    if target_hours != 24:
        minutes = {"15m": 15, "1h": 60, "4h": 240}.get(timeframe)
        if minutes is None:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        return int((target_hours * 60) / minutes)
    try:
        return HORIZON_PURGE_BARS_24H[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe}") from exc


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
