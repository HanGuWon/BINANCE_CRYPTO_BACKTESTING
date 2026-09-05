"""Frozen, outcome-blind R2B premium signal semantics.

This module is deliberately small and independent from the historical R2A
engine.  It maps a causal premium observation to a directional signal without
ever selecting a polarity from returns.  ``NaN`` remains ``NaN`` so warmup and
missing observations cannot be confused with a valid zero signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = {
    "derivatives.premium": "premium",
    "derivatives.premium_zscore": "premium_zscore90",
}
SIGNAL_VARIANTS = ("PRESSURE_CONTINUATION", "CROWDING_REVERSION")


def signal_from_values(values: pd.Series, variant: str) -> pd.Series:
    """Apply the strict zero-centred equation from amendment 002."""
    if variant not in SIGNAL_VARIANTS:
        raise ValueError(f"unknown R2B signal variant: {variant}")
    numeric = pd.to_numeric(values, errors="coerce")
    result = pd.Series(np.nan, index=numeric.index, dtype="float64")
    finite = numeric.notna()
    positive = finite & numeric.gt(0)
    negative = finite & numeric.lt(0)
    if variant == "PRESSURE_CONTINUATION":
        result.loc[positive] = 1.0
        result.loc[negative] = -1.0
    else:
        result.loc[positive] = -1.0
        result.loc[negative] = 1.0
    result.loc[finite & numeric.eq(0)] = 0.0
    return result


def segment_local_zscore(
    values: pd.Series,
    segment_ids: pd.Series | None = None,
    *,
    period: int = 90,
) -> pd.Series:
    """Compute a trailing z-score independently in each causal segment.

    The current materializer supplies ``premium_zscore90``.  This helper is
    used by synthetic qualification and regression tests to prove the same
    gap-reset contract without reading historical data.
    """
    if period <= 1:
        raise ValueError("period must be greater than one")
    numeric = pd.to_numeric(values, errors="coerce")
    if segment_ids is None:
        segment_ids = pd.Series(0, index=numeric.index)
    if len(segment_ids) != len(numeric):
        raise ValueError("segment_ids length must match values")
    result = pd.Series(np.nan, index=numeric.index, dtype="float64")
    groups: dict[object, list[int]] = {}
    for position, segment in enumerate(segment_ids.to_numpy()):
        groups.setdefault(segment, []).append(position)
    for indexes in groups.values():
        series = numeric.iloc[indexes]
        mean = series.rolling(period, min_periods=period).mean()
        std = series.rolling(period, min_periods=period).std(ddof=0).replace(0, np.nan)
        result.iloc[indexes] = ((series - mean) / std).to_numpy()
    return result


def signal_from_frame(
    frame: pd.DataFrame,
    feature_id: str,
    variant: str,
    *,
    segment_column: str = "segment_id",
) -> pd.Series:
    """Generate one frozen signal series from a causal panel frame."""
    if feature_id not in FEATURE_COLUMNS:
        raise ValueError(f"unsupported R2B feature: {feature_id}")
    source_column = FEATURE_COLUMNS[feature_id]
    if source_column in frame:
        values = pd.to_numeric(frame[source_column], errors="coerce")
    elif feature_id == "derivatives.premium_zscore" and "premium" in frame:
        values = segment_local_zscore(
            frame["premium"], frame[segment_column] if segment_column in frame else None
        )
    else:
        # Missing source is a no-signal condition, never an imputed zero.
        values = pd.Series(np.nan, index=frame.index, dtype="float64")
    return signal_from_values(values, variant)


def side_accepts_signal(signal_value: float, side: str) -> bool:
    """Return whether a directional trial may enter on this raw signal."""
    required = {"LONG": 1.0, "SHORT": -1.0}.get(str(side))
    if required is None:
        raise ValueError(f"unsupported side: {side}")
    return bool(np.isfinite(signal_value) and float(signal_value) == required)
