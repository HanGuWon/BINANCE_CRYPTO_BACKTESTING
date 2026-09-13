from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from binance_research.derivatives import crossed_funding_events, crossed_funding_events_fast


def test_fast_funding_replay_matches_slow_at_boundaries_and_both_sides() -> None:
    events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01 00:00Z", "2024-01-01 01:00Z", "2024-01-01 02:00Z", "2024-01-01 04:00Z"]),
            "funding_rate": [0.001, -0.0005, 0.002, -0.001],
        }
    )
    positions = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2024-01-01 00:00Z", "2024-01-01 02:00Z", "2024-01-01 05:00Z"]),
            "exit_timestamp": pd.to_datetime(["2024-01-01 02:00Z", "2024-01-01 04:00Z", "2024-01-01 06:00Z"]),
            "side": [1, -1, 1],
        }
    )
    slow = crossed_funding_events(positions, events)
    fast = crossed_funding_events_fast(positions, events)
    pdt.assert_frame_equal(fast, slow)
    assert fast.loc[0, "crossed_event_count"] == 2
    assert fast.loc[1, "crossed_event_count"] == 1
    assert fast.loc[2, "crossed_event_count"] == 0
    assert fast.loc[0, "funding_cashflow_return"] == pytest.approx(-0.0015)
    assert fast.loc[1, "funding_cashflow_return"] == pytest.approx(-0.001)


def test_fast_funding_replay_preserves_nan_rate_count_and_no_event_window() -> None:
    events = pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-01 01:00Z", "2024-01-01 02:00Z"]), "funding_rate": [np.nan, 0.001]})
    positions = pd.DataFrame({"entry_timestamp": pd.to_datetime(["2024-01-01 00:00Z", "2024-01-01 03:00Z"]), "exit_timestamp": pd.to_datetime(["2024-01-01 02:00Z", "2024-01-01 04:00Z"]), "side": [1, -1]})
    slow = crossed_funding_events(positions, events)
    fast = crossed_funding_events_fast(positions, events)
    pdt.assert_frame_equal(fast, slow)
    assert fast.loc[0, "crossed_event_count"] == 2
    assert fast.loc[0, "funding_rate_sum"] == pytest.approx(0.001)
    assert fast.loc[1, "crossed_event_count"] == 0



