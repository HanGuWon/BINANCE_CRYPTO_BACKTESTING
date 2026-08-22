"""Causal derivatives semantics used by the R1.6 data gate.

These helpers operate on event timestamps.  They deliberately do not invent
an eight-hour funding grid or repeat sparse events across bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def funding_event_zscore(events: pd.DataFrame, *, period_events: int = 90) -> pd.DataFrame:
    required = {"timestamp", "funding_rate"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"missing funding-event columns: {', '.join(sorted(missing))}")
    if period_events <= 1:
        raise ValueError("period_events must be greater than one")
    frame = events.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"], errors="coerce")
    if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("funding events must be unique and increasing")
    values = frame["funding_rate"]
    mean = values.rolling(period_events, min_periods=period_events).mean()
    std = values.rolling(period_events, min_periods=period_events).std(ddof=0)
    frame["funding_zscore"] = (values - mean).div(std.replace(0, np.nan))
    frame["period_events"] = period_events
    frame["alignment"] = "event_timestamp"
    return frame


def backward_asof_event_feature(
    bars: pd.DataFrame,
    event_features: pd.DataFrame,
    *,
    bar_timestamp: str = "timestamp",
    event_timestamp: str = "timestamp",
    value_column: str = "funding_zscore",
) -> pd.DataFrame:
    """Attach the latest causally known event feature to each completed bar."""
    if bar_timestamp not in bars or event_timestamp not in event_features or value_column not in event_features:
        raise ValueError("bars/events do not contain the requested timestamp/value columns")
    left = bars.copy()
    right = event_features[[event_timestamp, value_column]].copy()
    left[bar_timestamp] = pd.to_datetime(left[bar_timestamp], utc=True)
    right[event_timestamp] = pd.to_datetime(right[event_timestamp], utc=True)
    if not left[bar_timestamp].is_monotonic_increasing or not right[event_timestamp].is_monotonic_increasing:
        raise ValueError("bars and event features must be sorted by timestamp")
    return pd.merge_asof(left, right, left_on=bar_timestamp, right_on=event_timestamp, direction="backward")


def crossed_funding_events(
    positions: pd.DataFrame,
    funding_events: pd.DataFrame,
    *,
    entry_column: str = "entry_timestamp",
    exit_column: str = "exit_timestamp",
    side_column: str = "side",
    rate_column: str = "funding_rate",
) -> pd.DataFrame:
    """Sum only funding events strictly inside each holding interval.

    ``side`` is +1 for a long and -1 for a short.  Positive funding is paid by
    longs and received by shorts, so the signed cash-flow convention is
    ``-side * funding_rate``.
    """
    required_positions = {entry_column, exit_column, side_column}
    required_events = {"timestamp", rate_column}
    if (missing := required_positions - set(positions.columns)):
        raise ValueError(f"missing position columns: {', '.join(sorted(missing))}")
    if (missing := required_events - set(funding_events.columns)):
        raise ValueError(f"missing funding columns: {', '.join(sorted(missing))}")
    events = funding_events.copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True)
    events[rate_column] = pd.to_numeric(events[rate_column], errors="coerce")
    if events["timestamp"].duplicated().any() or not events["timestamp"].is_monotonic_increasing:
        raise ValueError("funding events must be unique and increasing")
    rows: list[dict[str, object]] = []
    for position_id, position in positions.iterrows():
        entry = pd.to_datetime(position[entry_column], utc=True)
        exit_ = pd.to_datetime(position[exit_column], utc=True)
        if pd.isna(entry) or pd.isna(exit_) or exit_ <= entry:
            raise ValueError("position intervals must have exit after entry")
        side = float(position[side_column])
        crossed = events[(events["timestamp"] > entry) & (events["timestamp"] <= exit_)]
        rate_sum = float(crossed[rate_column].sum())
        rows.append({
            "position_id": position_id,
            "crossed_event_count": int(len(crossed)),
            "funding_rate_sum": rate_sum,
            "funding_cashflow_return": -side * rate_sum,
            "first_crossed_event": crossed["timestamp"].min() if len(crossed) else pd.NaT,
            "last_crossed_event": crossed["timestamp"].max() if len(crossed) else pd.NaT,
        })
    return pd.DataFrame(rows)


def validate_metrics_schema(frame: pd.DataFrame) -> dict[str, object]:
    required = {"timestamp", "sum_open_interest", "sum_open_interest_value"}
    missing = sorted(required - set(frame.columns))
    return {
        "schema_status": "PASS" if not missing else "MISSING_REQUIRED_FIELDS",
        "missing_fields": ";".join(missing),
        "timestamp_semantics": "timestamp column requires source verification" if "timestamp" in frame else "UNKNOWN",
        "economic_equivalence_to_openInterestHist": False,
    }


def premium_feature_metadata(*, timeframe: str, coverage: str = "PARTIAL") -> dict[str, object]:
    return {
        "feature_id": "derivatives.premium_zscore",
        "source_dataset": "premiumIndexKlines",
        "source_field": "close",
        "period": 90,
        "period_unit": "bars",
        "alignment": "completed-bar close; gap-safe trailing window",
        "market_support": "um",
        "coverage": coverage,
        "timeframe": timeframe,
    }
