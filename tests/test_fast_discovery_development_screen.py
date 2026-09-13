from __future__ import annotations

import pandas as pd

from scripts.run_fast_discovery_v2_development_screen import attach_causal_membership


def test_causal_membership_filters_non_top50_and_hashes_source(tmp_path):
    bars = pd.DataFrame({"open_time": pd.to_datetime(["2024-02-01T00:00Z", "2024-03-01T00:00Z"]), "symbol": ["AAA", "AAA"]})
    universe = pd.DataFrame({"market": ["um", "um"], "symbol": ["AAA", "AAA"], "universe_month": ["2024-02", "2024-03"], "selected_top50": [False, True]})
    path = tmp_path / "universe.csv"
    universe.to_csv(path, index=False)
    filtered, excluded, digest = attach_causal_membership(bars, path, market="um")
    assert excluded == 1
    assert len(filtered) == 1 and filtered.iloc[0].universe_month == "2024-03"
    assert len(digest) == 64
