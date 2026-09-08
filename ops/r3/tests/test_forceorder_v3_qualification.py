from __future__ import annotations

from datetime import UTC, datetime

from binance_research.r3_materializer import materialize_forceorder_v3_metadata
from ops.r3.compare_forceorder_v2_v3_qualification import (
    QUALIFICATION_FIELDS,
    build_synthetic_fixtures,
    compare_synthetic,
    qualify_synthetic,
)


def test_slow_reference_matches_optimized_across_um_cm_sides_and_invalids() -> None:
    fixtures, opens = build_synthetic_fixtures()
    receipt = compare_synthetic(fixtures, complete_bar_opens=opens)
    assert receipt["status"] == "PASS"
    assert receipt["optimized_and_reference_identical"] is True
    assert receipt["market_counts"] == {"cm": 1, "um": 7}
    assert receipt["forced_side_counts"] == {"BUY": 2, "SELL": 6}
    assert receipt["classification"] == {
        "unique_event_count": 5,
        "duplicate_envelope_count": 1,
        "collision_envelope_count": 2,
        "invalid_envelope_count": 8,
    }


def test_missing_source_is_explicitly_ineligible() -> None:
    fixtures, opens = build_synthetic_fixtures()
    missing = next(envelope for envelope in fixtures if "collector_receipt_time" not in envelope)
    frame = materialize_forceorder_v3_metadata([missing], complete_bar_opens=opens)
    row = frame.iloc[0].to_dict()
    assert row["v3_status"] == "VALID"
    assert row["source_available_time"] is None
    assert row["executable_open"] is None
    assert row["causal_eligibility"] == "INELIGIBLE_SOURCE_TIME"


def test_v2_status_is_a_field_comparison_not_only_a_count() -> None:
    assert "v2_status" in QUALIFICATION_FIELDS
    receipt = qualify_synthetic()
    assert receipt["v2_status_counts"]["INVALID:ps_ENUM_INVALID"] == 2
    assert receipt["strict_boundary_equality_rejected"] is True
    assert receipt["future_append_invariant"] is True


def test_strict_boundary_is_exclusive() -> None:
    from ops.r3.r3_forceorder_identity_v3 import source_available_before_next_executable_open

    point = datetime(2026, 9, 1, 0, 15, tzinfo=UTC)
    assert not source_available_before_next_executable_open(point, point)
    assert source_available_before_next_executable_open(datetime(2026, 9, 1, 0, 14, tzinfo=UTC), point)


def test_repeated_qualification_is_byte_stable() -> None:
    assert qualify_synthetic() == qualify_synthetic()
