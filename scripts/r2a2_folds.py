"""Deterministic fold boundaries for R2A.2 (fixed six-month calendar blocks).

Each validation block is [start, end). Training is expanding from data start to
the block start minus horizon-specific purge; the frozen one-bar operational
embargo applies at split boundaries only. No future fold influences an earlier
fold because every fold's training window ends before its own validation start.
"""

from __future__ import annotations

import pandas as pd

# Frozen in campaigns/r2a2_temporal_horizon_v1/campaign_spec.toml
FOLD_BLOCKS = [
    ("2020-H1", "2020-01-01", "2020-07-01"),
    ("2020-H2", "2020-07-01", "2021-01-01"),
    ("2021-H1", "2021-01-01", "2021-07-01"),
    ("2021-H2", "2021-07-01", "2022-01-01"),
    ("2022-H1", "2022-01-01", "2022-07-01"),
    ("2022-H2", "2022-07-01", "2023-01-01"),
    ("2023-H1", "2023-01-01", "2023-07-01"),
    ("2023-H2", "2023-07-01", "2024-01-01"),
]
HORIZON_BARS_24H = {"15m": 96, "1h": 24, "4h": 6}
STEP = {"15m": pd.Timedelta("15min"), "1h": pd.Timedelta("1h"), "4h": pd.Timedelta("4h")}
OPERATIONAL_EMBARGO_BARS = 1


def fold_bounds(fold_id: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    for name, start, end in FOLD_BLOCKS:
        if name == fold_id:
            return pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    raise KeyError(f"unknown fold: {fold_id}")


def split_for_fold(frame: pd.DataFrame, *, timeframe: str, horizon_bars: int, fold_id: str):
    """Return (train, validation) with horizon-specific purge + operational embargo.

    purge = (horizon_bars / HORIZON_BARS_24H[timeframe]) * 24h equivalent, expressed
    in bars of this timeframe. Validation rows are [start+embargo, end). Train rows
    are strictly < validation_start - purge_bars*step so no training label window
    overlaps the validation execution window.
    """
    if timeframe not in STEP:
        raise ValueError(f"unsupported timeframe {timeframe}")
    step = STEP[timeframe]
    start, end = fold_bounds(fold_id)
    purge_24h_equivalent = horizon_bars * (HORIZON_BARS_24H[timeframe] / horizon_bars)
    purge_bars = int(round(horizon_bars))  # purge equals the holding horizon itself:
    # a 24h-equivalent label horizon means the last train decision must be at least
    # `horizon` bars before the first validation entry to avoid overlap.
    embargo_delta = OPERATIONAL_EMBARGO_BARS * step
    validation_start = start + embargo_delta
    train_cut = validation_start - purge_bars * step
    stamps = frame["timestamp"]
    train = frame[stamps < train_cut].copy()
    validation = frame[(frame["timestamp"] >= validation_start) & (frame["timestamp"] < end)].copy()
    return train, validation
