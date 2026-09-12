"""Independent local contract review for the Fast Discovery V2 panel assembler."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from binance_research.fast_discovery_panel import assemble_causal_panel


def _fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    starts = pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:15:00Z", "2024-01-01T00:45:00Z"])
    bars = pd.DataFrame({
        "open_time": starts,
        "close_time": starts + pd.Timedelta(minutes=14, seconds=59),
        "open": [100.0, 101.0, 103.0], "high": [101.0, 102.0, 104.0],
        "low": [99.0, 100.0, 102.0], "close": [100.5, 101.5, 103.5],
        "volume": [10.0, 11.0, 12.0], "symbol": ["AAAUSDT"] * 3,
    })
    membership = pd.DataFrame({"market": ["um"], "universe_month": ["2024-01"], "symbol": ["AAAUSDT"], "selected_top50": [True], "cohort_source_sha256": ["review-cohort"]})
    context = pd.DataFrame({"timestamp": pd.to_datetime(["2023-12-31T23:59:00Z", "2024-01-01T00:30:00Z"]), "premium": [0.1, 0.9]})
    return bars, membership, context


def main() -> int:
    bars, membership, context = _fixture()
    panel = assemble_causal_panel(bars, membership, market="um", timeframe="15m", premium=context)
    assert panel["selected_top50"].all()
    assert list(panel["segment_id"]) == ["segment-0001", "segment-0001", "segment-0002"]
    assert panel.loc[0, "premium"] == 0.1
    assert panel.loc[1, "premium"] == 0.1
    assert panel.loc[2, "premium"] == 0.9
    assert (panel["premium_source_available_time"] < panel["next_open_time"]).all()
    try:
        assemble_causal_panel(bars, membership.assign(universe_month="2024-02"), market="um", timeframe="15m")
    except ValueError as exc:
        assert "no point-in-time Top50 membership" in str(exc)
    else:
        raise AssertionError("future membership was accepted")
    try:
        assemble_causal_panel(bars, membership, market="um", timeframe="15m", holdout_start="2024-01-01T00:30:00Z")
    except ValueError as exc:
        assert "final holdout" in str(exc)
    else:
        raise AssertionError("holdout rows were accepted")
    print(json.dumps({"verdict": "LOCAL_INDEPENDENT_REVIEW_PASS", "checks": 6, "holdout": "UNTOUCHED", "outcomes_accessed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

