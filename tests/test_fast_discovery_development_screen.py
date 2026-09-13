from __future__ import annotations

import pandas as pd

from scripts.run_fast_discovery_v2_development_screen import attach_causal_membership, run


def test_causal_membership_filters_non_top50_and_hashes_source(tmp_path):
    bars = pd.DataFrame({"open_time": pd.to_datetime(["2024-02-01T00:00Z", "2024-03-01T00:00Z"]), "symbol": ["AAA", "AAA"]})
    universe = pd.DataFrame({"market": ["um", "um"], "symbol": ["AAA", "AAA"], "universe_month": ["2024-02", "2024-03"], "selected_top50": [False, True]})
    path = tmp_path / "universe.csv"
    universe.to_csv(path, index=False)
    filtered, excluded, digest = attach_causal_membership(bars, path, market="um")
    assert excluded == 1
    assert len(filtered) == 1 and filtered.iloc[0].universe_month == "2024-03"
    assert len(digest) == 64


def test_runner_receipt_contains_phase_benchmarks(monkeypatch, tmp_path):
    bars = pd.DataFrame({"open_time": pd.to_datetime(["2024-02-01T00:00Z", "2024-02-01T01:00Z"]), "symbol": ["AAA", "AAA"], "open": [1.0, 1.0], "close": [1.0, 1.0], "segment_id": ["s", "s"]})
    universe = pd.DataFrame({"market": ["um"], "symbol": ["AAA"], "universe_month": ["2024-02"], "selected_top50": [True]})
    universe_path = tmp_path / "universe.csv"
    universe.to_csv(universe_path, index=False)
    monkeypatch.setattr("scripts.run_fast_discovery_v2_development_screen.load_window", lambda *args, **kwargs: (bars.copy(), ["archive.zip"]))
    monkeypatch.setattr("scripts.run_fast_discovery_v2_development_screen.CoreFeatureEngine", lambda: type("Engine", (), {"compute": lambda self, frame: pd.DataFrame(index=frame.index)})())
    cache = type("Cache", (), {"hits": 2, "misses": 3})()
    monkeypatch.setattr("scripts.run_fast_discovery_v2_development_screen.screen_s0_panel", lambda *args, **kwargs: (pd.DataFrame([{"feature_id": "x", "status": "S0_REJECTED"}]), pd.DataFrame(), cache))
    receipt = run(raw_root=tmp_path, output=tmp_path / "out", symbols=["AAA"], timeframe="1h", months=["2024-02"], universe_path=universe_path)
    assert receipt["benchmark"]["s1_status"] == "NOT_RUN"
    assert receipt["benchmark"]["s2_status"] == "NOT_RUN"
    assert receipt["benchmark"]["cache_hits"] == 2
    assert receipt["benchmark"]["cache_misses"] == 3
    assert receipt["benchmark"]["total_seconds"] >= 0

