from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from ops.r3.check_r3_evaluation_readiness import ReadinessInputError, _validate_metadata_envelope, derive_gap_accounting
from ops.r3.tests.test_evaluation_readiness import _inventory


REFERENCE_TIME = datetime(2026, 1, 3, tzinfo=timezone.utc)


def test_missing_observed_at_is_rejected_without_a_zero_fallback() -> None:
    inventory = _inventory()
    inventory.pop("observed_at_utc")
    with pytest.raises(ReadinessInputError, match="observed_at_utc"):
        _validate_metadata_envelope(inventory, REFERENCE_TIME)


def test_stale_and_future_observation_windows_are_deterministic() -> None:
    inventory = _inventory()
    inventory["observed_at_utc"] = "2025-12-20T00:00:00+00:00"
    with pytest.raises(ReadinessInputError, match="stale"):
        _validate_metadata_envelope(inventory, REFERENCE_TIME)
    inventory["observed_at_utc"] = "2026-01-03T00:06:00+00:00"
    with pytest.raises(ReadinessInputError, match="clock-skew"):
        _validate_metadata_envelope(inventory, REFERENCE_TIME)


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda value: value["cycles"].update({"cycle_count": "200"}), "cycle_count"),
        (lambda value: value["cycles"]["cycle_id_timestamps"].pop(), "cycle_count"),
        (lambda value: value["causal_input_presence"]["H01_execution_quality_context"].update({"usable_observations": 999999}), "cannot exceed"),
    ],
)
def test_type_and_cross_file_count_mismatches_fail_closed(mutator, message: str) -> None:
    inventory = _inventory()
    mutator(inventory)
    with pytest.raises(ReadinessInputError, match=message):
        _validate_metadata_envelope(inventory, REFERENCE_TIME)


def test_explicit_gap_receipt_is_the_only_source_for_exclusion() -> None:
    inventory = _inventory()
    inventory["availability_and_gaps"]["gap_records"] = [
        {"category": "RESTART_GAP", "start_time": "2026-01-01T01:00:00+00:00"}
    ]
    accounting = derive_gap_accounting(inventory)
    assert accounting["excluded_block_ids"] == ["2026-01-01T00:00:00+00:00"]
    assert accounting["aggregate_gap_count"] == 0


def test_availability_counter_without_an_explicit_record_is_rejected() -> None:
    inventory = deepcopy(_inventory())
    inventory["availability_and_gaps"]["rollover_gap_count"] = 1
    with pytest.raises(ReadinessInputError, match="aggregate gap"):
        derive_gap_accounting(inventory)
