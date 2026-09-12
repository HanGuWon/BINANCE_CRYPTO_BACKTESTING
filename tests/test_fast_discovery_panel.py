from __future__ import annotations

import pandas as pd
import pytest

from binance_research.fast_discovery_panel import assemble_causal_panel


def _bars() -> pd.DataFrame:
    starts = pd.to_datetime(
        ["2024-01-01T00:00:00Z", "2024-01-01T00:15:00Z", "2024-01-01T00:45:00Z"]
    )
    return pd.DataFrame(
        {
            "open_time": starts,
            "close_time": starts + pd.Timedelta(minutes=14, seconds=59),
            "open": [100.0, 101.0, 103.0],
            "high": [101.0, 102.0, 104.0],
            "low": [99.0, 100.0, 102.0],
            "close": [100.5, 101.5, 103.5],
            "volume": [10.0, 11.0, 12.0],
            "quote_volume": [1000.0, 1111.0, 1242.0],
            "taker_buy_volume": [5.0, 6.0, 7.0],
            "symbol": ["AAAUSDT"] * 3,
        }
    )


def _membership() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market": ["um"],
            "universe_month": ["2024-01"],
            "symbol": ["AAAUSDT"],
            "selected_top50": [True],
            "cohort_source_sha256": ["cohort-sha"],
        }
    )


def test_assembler_assigns_gap_segments_and_point_in_time_membership() -> None:
    panel = assemble_causal_panel(_bars(), _membership(), market="um", timeframe="15m")
    assert list(panel["segment_id"]) == ["segment-0001", "segment-0001", "segment-0002"]
    assert panel["selected_top50"].all()
    assert set(panel["cohort_source_sha256"]) == {"cohort-sha"}
    assert set(panel["market"]) == {"um"}
    assert set(panel["timeframe"]) == {"15m"}
    assert "source_available_time" in panel
    assert panel["source_available_time"].isna().all()


def test_membership_is_required_and_future_symbol_is_excluded() -> None:
    membership = _membership().assign(universe_month="2024-02")
    with pytest.raises(ValueError, match="no point-in-time Top50 membership"):
        assemble_causal_panel(_bars(), membership, market="um", timeframe="15m")


def test_context_join_is_strictly_before_next_open_and_no_future_fill() -> None:
    premium = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2023-12-31T23:59:00Z", "2024-01-01T00:15:00Z", "2024-01-01T01:00:00Z"]
            ),
            "premium": [0.1, 0.2, 0.3],
        }
    )
    panel = assemble_causal_panel(
        _bars(), _membership(), market="um", timeframe="15m", premium=premium
    )
    assert panel.loc[0, "premium"] == pytest.approx(0.1)
    assert panel.loc[1, "premium"] == pytest.approx(0.2)
    assert panel.loc[2, "premium"] == pytest.approx(0.2)
    assert panel.loc[0, "premium_source_available_time"] < panel.loc[0, "next_open_time"]


def test_holdout_rows_are_rejected() -> None:
    with pytest.raises(ValueError, match="final holdout"):
        assemble_causal_panel(
            _bars(), _membership(), market="um", timeframe="15m", holdout_start="2024-01-01T00:30:00Z"
        )


def test_source_hash_changes_when_bar_changes() -> None:
    first = assemble_causal_panel(_bars(), _membership(), market="um", timeframe="15m")
    changed = _bars().copy()
    changed.loc[0, "close"] = 999.0
    second = assemble_causal_panel(changed, _membership(), market="um", timeframe="15m")
    assert first.attrs["source_sha256"] != second.attrs["source_sha256"]






def test_multiple_symbols_can_share_timestamps_but_keep_segments_isolated() -> None:
    bars = pd.concat([_bars(), _bars().assign(symbol="BBBUSDT")], ignore_index=True)
    membership = pd.concat([_membership(), _membership().assign(symbol="BBBUSDT")], ignore_index=True)
    panel = assemble_causal_panel(bars, membership, market="um", timeframe="15m")
    assert len(panel) == 6
    assert panel.groupby("symbol")["segment_id"].nunique().to_dict() == {"AAAUSDT": 2, "BBBUSDT": 2}


def test_symbol_keyed_context_cannot_cross_contaminate_symbols() -> None:
    bars = pd.concat([_bars(), _bars().assign(symbol="BBBUSDT")], ignore_index=True)
    membership = pd.concat([_membership(), _membership().assign(symbol="BBBUSDT")], ignore_index=True)
    premium = pd.DataFrame(
        {
            "symbol": ["AAAUSDT", "BBBUSDT"],
            "timestamp": pd.to_datetime(["2023-12-31T23:59:00Z"] * 2),
            "premium": [0.1, 0.9],
        }
    )
    panel = assemble_causal_panel(bars, membership, market="um", timeframe="15m", premium=premium)
    assert set(panel.loc[panel.symbol == "AAAUSDT", "premium"]) == {0.1}
    assert set(panel.loc[panel.symbol == "BBBUSDT", "premium"]) == {0.9}
