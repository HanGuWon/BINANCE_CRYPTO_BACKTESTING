from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class PointInTimeSource:
    frame: pd.DataFrame
    timestamp_column: str
    value_columns: tuple[str, ...]
    max_age: pd.Timedelta | None = None
    coverage_status: str | None = None


def _utc(values: pd.Series) -> pd.Series:
    result = pd.to_datetime(values, utc=True, errors="raise")
    if result.isna().any():
        raise ValueError("point-in-time timestamps cannot contain NaT")
    return result


def causal_asof_join(
    bars: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    bar_timestamp: str = "close_time",
    observation_timestamp: str = "timestamp",
    value_columns: tuple[str, ...],
    source_name: str,
    max_age: pd.Timedelta | None = None,
    coverage_status: str | None = None,
) -> pd.DataFrame:
    """Backward as-of align one source, preserving order and provenance."""
    if bar_timestamp not in bars:
        raise ValueError(f"missing bar timestamp column: {bar_timestamp}")
    missing = {observation_timestamp, *value_columns} - set(observations.columns)
    if missing:
        raise ValueError(f"missing point-in-time source columns: {', '.join(sorted(missing))}")
    if max_age is not None and max_age < pd.Timedelta(0):
        raise ValueError("max_age must be non-negative")
    left = bars.copy()
    left[bar_timestamp] = _utc(left[bar_timestamp])
    order_column = "__pit_original_order"
    if order_column in left:
        raise ValueError(f"reserved column already present: {order_column}")
    left[order_column] = range(len(left))
    source_time = f"{source_name}_source_time"
    renamed_values = {column: f"{source_name}_{column}" for column in value_columns}
    right = observations[[observation_timestamp, *value_columns]].copy()
    right[observation_timestamp] = _utc(right[observation_timestamp])
    right = right.sort_values(observation_timestamp, kind="stable").rename(
        columns={observation_timestamp: source_time, **renamed_values}
    )
    merged = pd.merge_asof(
        left.sort_values(bar_timestamp, kind="stable"), right,
        left_on=bar_timestamp, right_on=source_time,
        direction="backward", allow_exact_matches=True,
    )
    age_column, status_column = f"{source_name}_age", f"{source_name}_coverage"
    merged[age_column] = merged[bar_timestamp] - merged[source_time]
    matched_status = coverage_status or "AVAILABLE"
    merged[status_column] = matched_status
    no_prior = merged[source_time].isna()
    merged.loc[no_prior, status_column] = (
        "HISTORICAL_UNAVAILABLE" if coverage_status == "HISTORICAL_UNAVAILABLE" else "NO_PRIOR_OBSERVATION"
    )
    if max_age is not None:
        stale = merged[age_column].notna() & (merged[age_column] > max_age)
        for column in renamed_values.values():
            merged.loc[stale, column] = pd.NA
        merged.loc[stale, status_column] = "STALE"
    return merged.sort_values(order_column, kind="stable").drop(columns=order_column).reset_index(drop=True)


def build_research_panel(
    bars: pd.DataFrame,
    sources: Mapping[str, PointInTimeSource],
    *,
    bar_timestamp: str = "close_time",
) -> pd.DataFrame:
    panel = bars.copy()
    for name, source in sources.items():
        panel = causal_asof_join(
            panel, source.frame, bar_timestamp=bar_timestamp,
            observation_timestamp=source.timestamp_column,
            value_columns=source.value_columns, source_name=name,
            max_age=source.max_age, coverage_status=source.coverage_status,
        )
    return panel
