"""Finalist-only S2 replay handoff for Fast Discovery development screens.

This adapter does not discover candidates or run historical outcomes. It validates
an explicit finalist contract and delegates each segment to the proven execution
function supplied by the caller.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
import pandas as pd


FINALIST_FIELDS = ("candidate_id", "feature_id", "variant", "side", "horizon_bars")
TRADE_FIELDS = (
    "decision_time", "symbol", "side", "signal_value", "entry_time", "exit_time",
    "gross_return", "funding_cashflow", "net_return",
)


def replay_finalists(
    frame: pd.DataFrame,
    finalists: pd.DataFrame,
    *,
    signal_builder: Callable[[pd.DataFrame, str, str, str], pd.Series],
    executor: Callable[..., pd.DataFrame],
    market: str,
    timeframe: str,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    universe_top50: set[tuple[str, str, str]],
    funding_events: pd.DataFrame | None,
) -> pd.DataFrame:
    """Replay only explicitly-finalist candidates over development segments.

    ``executor`` is expected to implement the corrected next-open, directional,
    per-symbol non-overlap and funding semantics. No candidate generation occurs
    here; an empty finalist table is a deterministic no-op.
    """
    if finalists.empty:
        return pd.DataFrame(columns=("candidate_id",) + TRADE_FIELDS)
    missing = set(FINALIST_FIELDS) - set(finalists.columns)
    if missing:
        raise ValueError(f"finalist contract missing columns: {', '.join(sorted(missing))}")
    if "final_holdout" in frame and bool(frame["final_holdout"].fillna(False).astype(bool).any()):
        raise ValueError("S2 replay refuses final-holdout observations")
    if market not in {"spot", "um"}:
        raise ValueError("market must be spot or um")
    if timeframe not in {"15m", "1h", "4h"}:
        raise ValueError("unsupported timeframe")
    if not isinstance(validation_start, pd.Timestamp) or not isinstance(validation_end, pd.Timestamp):
        raise TypeError("validation bounds must be pandas timestamps")

    segments: Iterable[tuple[Any, pd.DataFrame]]
    if "segment_id" in frame.columns:
        segments = frame.groupby("segment_id", sort=True)
    else:
        segments = (("segment-0001", frame),)
    records: list[pd.DataFrame] = []
    for finalist in finalists.itertuples(index=False):
        feature_id = str(finalist.feature_id)
        variant = str(finalist.variant)
        side = str(finalist.side).upper()
        horizon_bars = int(finalist.horizon_bars)
        if side not in {"LONG", "SHORT"} or horizon_bars <= 0:
            raise ValueError("finalist side/horizon_bars is invalid")
        for _, segment in segments:
            group = segment.reset_index(drop=True)
            if feature_id not in group.columns:
                raise ValueError(f"finalist feature unavailable: {feature_id}")
            signal = signal_builder(group, feature_id, variant, market)
            if len(signal) != len(group):
                raise ValueError("signal builder returned an unexpected length")
            trades = executor(
                group,
                signal,
                market=market,
                side=side,
                horizon_bars=horizon_bars,
                validation_start=validation_start,
                validation_end=validation_end,
                universe_top50=universe_top50,
                funding_events=funding_events,
            )
            if trades is None or trades.empty:
                continue
            out = trades.copy()
            out.insert(0, "candidate_id", str(finalist.candidate_id))
            records.append(out)
    if not records:
        return pd.DataFrame(columns=("candidate_id",) + TRADE_FIELDS)
    result = pd.concat(records, ignore_index=True)
    missing_trade = set(TRADE_FIELDS) - set(result.columns)
    if missing_trade:
        raise ValueError(f"executor output missing fields: {', '.join(sorted(missing_trade))}")
    return result
