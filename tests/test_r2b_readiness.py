from __future__ import annotations

import pandas as pd

from binance_research.features import CORE_FEATURE_SPECS
from materialize_r2b_premium_panel import resample_source
from acquire_r2b_premium_history import candidate_symbols


def test_r2b_candidate_symbols_is_pre_holdout_and_um_only(tmp_path) -> None:
    universe = pd.DataFrame(
        {
            "market": ["um", "um", "spot", "um"],
            "symbol": ["B", "A", "S", "LATE"],
            "selected_top50": [True, True, True, True],
            "universe_month": ["2023-12", "2024-01", "2024-01", "2024-02"],
        }
    )
    path = tmp_path / "universe.csv"
    universe.to_csv(path, index=False)
    assert candidate_symbols(path, "2024-01") == ["A", "B"]


def test_r2b_resample_drops_incomplete_buckets_and_preserves_segments() -> None:
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    timestamps = [start + pd.Timedelta(minutes=15 * i) for i in [0, 1, 2, 3, 4, 6, 7]]
    source = pd.DataFrame(
        {
            "timestamp": timestamps,
            "premium": [1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 8.0],
            "segment_id": [0, 0, 0, 0, 0, 1, 1],
            "premium_zscore90": [float("nan")] * 7,
        }
    )
    result = resample_source(source, "1h")
    assert result["timestamp"].tolist() == [start]
    assert result["premium"].tolist() == [4.0]
    assert result["segment_id"].tolist() == [0]


def test_r2b_premium_features_have_no_implicit_direction_rule() -> None:
    specs = {spec.feature_id: spec for spec in CORE_FEATURE_SPECS}
    assert "derivatives.premium_zscore" in specs
    assert specs["derivatives.premium_zscore"].signal_column is None
    assert "derivatives.premium" not in specs


def test_r2b_registry_is_metadata_only_and_explicitly_blocked() -> None:
    registry = pd.read_csv("campaigns/r2b_restricted_derivatives_v1/trial_registry.csv")
    assert len(registry) == 36
    assert registry.status.eq("BLOCKED_IMPLEMENTATION").all()
    assert registry.signal_rule.eq("UNDEFINED_SIGNAL_SEMANTICS").all()
    assert set(registry.feature_id) == {"derivatives.premium", "derivatives.premium_zscore"}
    assert set(registry.timeframe) == {"15m", "1h", "4h"}
    assert set(registry.side) == {"LONG", "SHORT"}
