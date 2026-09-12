from __future__ import annotations

import pandas as pd
import pytest

from binance_research.fast_discovery_blocks import calendar_block_ids, independent_calendar_block_count, require_independent_calendar_blocks


def test_calendar_blocks_are_utc_day_boundaries_and_ignore_missing_days() -> None:
    stamps = pd.Series(pd.to_datetime(["2024-01-01T23:59Z", "2024-01-02T00:01Z", "2024-01-04T12:00Z"]))
    blocks = calendar_block_ids(stamps)
    assert blocks.iloc[0] == pd.Timestamp("2024-01-01T00:00Z")
    assert blocks.iloc[1] == pd.Timestamp("2024-01-02T00:00Z")
    assert blocks.iloc[2] == pd.Timestamp("2024-01-04T00:00Z")
    assert independent_calendar_block_count(stamps) == 3


def test_block_count_is_not_row_count_and_minimum_is_enforced() -> None:
    stamps = pd.Series(pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T01:00Z", "2024-01-03T00:00Z"]))
    assert independent_calendar_block_count(stamps) == 2
    require_independent_calendar_blocks(stamps, minimum_blocks=2)
    with pytest.raises(ValueError, match="observed 2"):
        require_independent_calendar_blocks(stamps, minimum_blocks=3)


def test_invalid_timestamps_and_block_size_fail_closed() -> None:
    with pytest.raises(ValueError, match="block_days"):
        calendar_block_ids(pd.Series(pd.to_datetime(["2024-01-01T00:00Z"])), block_days=0)
    with pytest.raises(ValueError, match="NaT"):
        calendar_block_ids(pd.Series([pd.NaT]))
