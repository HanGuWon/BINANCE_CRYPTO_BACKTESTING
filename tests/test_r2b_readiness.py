from __future__ import annotations

import pandas as pd
from pathlib import Path

from binance_research.features import CORE_FEATURE_SPECS
from materialize_r2b_premium_panel import align_source_to_decisions, resample_source
from acquire_r2b_premium_history import candidate_symbols
from audit_r2b_premium_coverage import validate_premium_manifest


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
            "source_open_time": timestamps,
            "source_close_time": [t + pd.Timedelta(minutes=14, seconds=59, milliseconds=999) for t in timestamps],
            "source_available_time": [t + pd.Timedelta(minutes=14, seconds=59, milliseconds=999) for t in timestamps],
            "source_max_constituent_close_time": [t + pd.Timedelta(minutes=14, seconds=59, milliseconds=999) for t in timestamps],
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


def test_r2b_alignment_rejects_source_close_after_executable_boundary() -> None:
    source = pd.DataFrame(
        {
            "source_open_time": pd.to_datetime(["2024-01-01T00:15Z", "2024-01-01T01:15Z"]),
            "source_close_time": pd.to_datetime(["2024-01-01T00:29:59.999Z", "2024-01-01T01:29:59.999Z"]),
            "source_available_time": pd.to_datetime(["2024-01-01T00:29:59.999Z", "2024-01-01T01:29:59.999Z"]),
            "premium": [0.1, 0.2],
            "premium_zscore90": [float("nan"), 1.0],
        }
    )
    decisions = pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T00:30Z", "2024-01-01T02:00Z"])})
    aligned = align_source_to_decisions(decisions, source, pd.Timedelta(minutes=15))
    assert aligned["premium"].isna().tolist() == [True, False, False]
    assert aligned.loc[1, "source_open_time"] == pd.Timestamp("2024-01-01T00:15Z")
    assert aligned.loc[2, "source_open_time"] == pd.Timestamp("2024-01-01T01:15Z")


def test_r2b_alignment_accepts_completed_source_before_next_open_and_never_forward_fills() -> None:
    source = pd.DataFrame(
        {
            "source_open_time": pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T01:00Z"]),
            "source_close_time": pd.to_datetime(["2024-01-01T00:14:59.999Z", "2024-01-01T01:14:59.999Z"]),
            "source_available_time": pd.to_datetime(["2024-01-01T00:14:59.999Z", "2024-01-01T01:14:59.999Z"]),
            "premium": [0.1, 0.2],
            "premium_zscore90": [float("nan"), 1.0],
        }
    )
    decisions = pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T00:30Z", "2024-01-01T02:00Z"])})
    aligned = align_source_to_decisions(decisions, source, pd.Timedelta(minutes=15))
    assert aligned["premium"].tolist() == [0.1, 0.1, 0.2]


def test_r2b_exact_boundary_is_rejected() -> None:
    source = pd.DataFrame({
        "source_open_time": pd.to_datetime(["2024-01-01T00:00Z"]),
        "source_close_time": pd.to_datetime(["2024-01-01T00:15Z"]),
        "source_available_time": pd.to_datetime(["2024-01-01T00:15Z"]),
        "premium": [0.1],
        "premium_zscore90": [float("nan")],
    })
    aligned = align_source_to_decisions(pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-01T00:00Z"])}), source, pd.Timedelta(minutes=15))
    assert aligned["premium"].isna().all()

def test_r2b_causal_contract_names_strict_next_open_and_derived_max_close() -> None:
    spec = Path("campaigns/r2b_restricted_derivatives_v1/campaign_spec.toml").read_text(encoding="utf-8")
    protocol = Path("campaigns/r2b_restricted_derivatives_v1/R2B_PROTOCOL.md").read_text(encoding="utf-8")
    assert 'asof = "source_available_time < next_executable_open_time"' in spec
    assert "maximum constituent 15m close time" in spec
    assert "source_available_time < next_executable_open_time" in protocol
    assert "source_available_time >= next_executable_open_time" in protocol


def test_r2b_aggregated_availability_uses_last_constituent_close_for_1h_and_4h() -> None:
    start = pd.Timestamp("2024-01-01T00:00Z")
    timestamps = [start + pd.Timedelta(minutes=15 * i) for i in range(16)]
    closes = [ts + pd.Timedelta(minutes=14, seconds=59, milliseconds=999) for ts in timestamps]
    source = pd.DataFrame({
        "source_open_time": timestamps,
        "source_close_time": closes,
        "source_available_time": closes,
        "source_max_constituent_close_time": closes,
        "premium": list(range(16)),
        "segment_id": [0] * 16,
    })
    one_hour = resample_source(source, "1h")
    four_hour = resample_source(source, "4h")
    assert one_hour.loc[0, "premium"] == 3
    assert one_hour.loc[0, "source_max_constituent_close_time"] == closes[3]
    assert one_hour.loc[0, "source_available_time"] == closes[3]
    assert four_hour.loc[0, "premium"] == 15
    assert four_hour.loc[0, "source_available_time"] == closes[15]


def test_r2b_gap_segments_reset_zscore_and_do_not_bridge_alignment() -> None:
    start = pd.Timestamp("2024-01-01T00:00Z")
    timestamps = [start + pd.Timedelta(minutes=15 * i) for i in [0, 1, 2, 10, 11, 12]]
    closes = [ts + pd.Timedelta(minutes=14, seconds=59, milliseconds=999) for ts in timestamps]
    source = pd.DataFrame({
        "source_open_time": timestamps,
        "source_close_time": closes,
        "source_available_time": closes,
        "source_max_constituent_close_time": closes,
        "premium": [1.0, 2.0, 3.0, 10.0, 11.0, 12.0],
        "segment_id": [0, 0, 0, 1, 1, 1],
    })
    result = resample_source(source, "15m")
    assert result["segment_id"].tolist() == [0, 0, 0, 1, 1, 1]
    assert result.loc[3, "premium_zscore90"] != result.loc[2, "premium_zscore90"] or pd.isna(result.loc[3, "premium_zscore90"])
    decisions = pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-01T00:30Z"])})
    aligned = align_source_to_decisions(decisions, source, pd.Timedelta(minutes=15))
    assert aligned.loc[0, "source_open_time"] == pd.Timestamp("2024-01-01T00:30Z")


def test_r2b_pre_holdout_cutoff_is_strict() -> None:
    source = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-02-09T23:45Z", "2024-02-10T00:00Z"]),
            "premium": [0.1, 0.9],
            "segment_id": [0, 0],
            "premium_zscore90": [float("nan"), float("nan")],
        }
    )
    cutoff = pd.Timestamp("2024-02-10T00:00Z")
    assert source.loc[source.timestamp < cutoff, "premium"].tolist() == [0.1]


def _manifest_row(**overrides):
    row = {
        "dataset": "premiumIndexKlines",
        "market": "um",
        "interval": "15m",
        "symbol": "AAAUSDT",
        "integrity_status": "PASS",
        "published_sha256": "a" * 64,
        "computed_sha256": "a" * 64,
    }
    row.update(overrides)
    return row


def test_r2b_manifest_contract_accepts_authoritative_shape(tmp_path) -> None:
    rows = [_manifest_row(symbol=f"S{i}USDT") for i in range(3)]
    path = tmp_path / "premium_archive_manifest.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    result = validate_premium_manifest(path)
    assert len(result) == 3


def test_r2b_manifest_contract_rejects_wrong_dataset_market_checksum_and_r1_anchor(tmp_path) -> None:
    base = [_manifest_row(symbol=f"S{i}USDT") for i in range(3)]
    cases = [
        ({"dataset": "klines"}, "dataset"),
        ({"market": "spot"}, "market"),
        ({"integrity_status": "FAIL"}, "integrity"),
        ({"computed_sha256": "b" * 64}, "checksum"),
    ]
    for override, label in cases:
        path = tmp_path / f"{label}.csv"
        rows = [dict(row, **override) for row in base]
        pd.DataFrame(rows).to_csv(path, index=False)
        try:
            validate_premium_manifest(path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"manifest case {label} was accepted")
    anchor = tmp_path / "r1_full_history_v1" / "derivative_archive_manifest.csv"
    anchor.parent.mkdir()
    pd.DataFrame(base).to_csv(anchor, index=False)
    try:
        validate_premium_manifest(anchor)
    except ValueError:
        pass
    else:
        raise AssertionError("historical R1 anchor manifest was accepted")


def test_r2b_registry_is_metadata_only_and_explicitly_blocked() -> None:
    registry = pd.read_csv("campaigns/r2b_restricted_derivatives_v1/trial_registry.csv")
    assert len(registry) == 36
    assert registry.status.eq("BLOCKED_IMPLEMENTATION").all()
    assert registry.signal_rule.eq("UNDEFINED_SIGNAL_SEMANTICS").all()
    assert set(registry.feature_id) == {"derivatives.premium", "derivatives.premium_zscore"}
    assert set(registry.timeframe) == {"15m", "1h", "4h"}
    assert set(registry.side) == {"LONG", "SHORT"}
