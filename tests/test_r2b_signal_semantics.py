"""Regression tests for the frozen R2B premium signal equations."""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
from r2b_signals import signal_from_frame, signal_from_values, segment_local_zscore, side_accepts_signal  # noqa: E402


def test_pressure_and_reversion_polarity_zero_and_nan() -> None:
    values = pd.Series([0.5, -0.5, 0.0, np.nan, "bad"])
    assert signal_from_values(values, "PRESSURE_CONTINUATION").tolist()[:3] == [1.0, -1.0, 0.0]
    assert signal_from_values(values, "CROWDING_REVERSION").tolist()[:3] == [-1.0, 1.0, 0.0]
    assert math.isnan(signal_from_values(values, "PRESSURE_CONTINUATION").iloc[3])
    assert math.isnan(signal_from_values(values, "PRESSURE_CONTINUATION").iloc[4])


def test_directional_side_gate_rejects_opposite_zero_and_nan() -> None:
    assert side_accepts_signal(1.0, "LONG")
    assert side_accepts_signal(-1.0, "SHORT")
    for value in (-1.0, 0.0, 1.0, np.nan):
        assert side_accepts_signal(value, "LONG") is (value == 1.0)
        assert side_accepts_signal(value, "SHORT") is (value == -1.0)


def test_raw_and_zscore_inputs_are_not_conflated() -> None:
    frame = pd.DataFrame({"premium": [0.1, -0.1], "premium_zscore90": [-2.0, 2.0]})
    assert signal_from_frame(frame, "derivatives.premium", "PRESSURE_CONTINUATION").tolist() == [1.0, -1.0]
    assert signal_from_frame(frame, "derivatives.premium_zscore", "PRESSURE_CONTINUATION").tolist() == [-1.0, 1.0]


def test_zscore_warmup_and_gap_reset() -> None:
    values = pd.Series(np.arange(8, dtype=float))
    segments = pd.Series([0, 0, 0, 0, 1, 1, 1, 1])
    zscore = segment_local_zscore(values, segments, period=4)
    assert zscore.iloc[:3].isna().all()
    assert zscore.iloc[4:7].isna().all()
    assert zscore.iloc[3] == zscore.iloc[7]


def test_appending_future_observations_does_not_change_history() -> None:
    base = pd.DataFrame({"premium": [0.1, -0.1, 0.0, 0.2]})
    appended = pd.concat([base, pd.DataFrame({"premium": [-0.8, 0.9]})], ignore_index=True)
    before = signal_from_frame(base, "derivatives.premium", "PRESSURE_CONTINUATION")
    after = signal_from_frame(appended, "derivatives.premium", "PRESSURE_CONTINUATION").iloc[: len(base)]
    pd.testing.assert_series_equal(before, after, check_names=False)
