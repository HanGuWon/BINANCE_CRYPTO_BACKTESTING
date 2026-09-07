from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.r3 import r3_forceorder_identity as forceorder
from ops.r3.build_r3_evidence_inventory import (
    PRIMARY_HYPOTHESES,
    InventoryError,
    _scoped_gap_blocks,
    _used_roster_identities,
)
from ops.r3.check_r3_evaluation_readiness import (
    ReadinessInputError,
    validate_per_hypothesis_gates,
    validate_scoped_gap_blocks,
)


def _blocks(count: int = 30) -> list[str]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [(start + timedelta(hours=6 * index)).isoformat() for index in range(count)]


def _strict_inventory() -> dict:
    block_ids = _blocks()
    used_sha = "a" * 64
    records = [
        {
            "category": "SOURCE_UNAVAILABLE",
            "stream": "book_ticker",
            "start_time": "2026-01-01T01:00:00+00:00",
            "end_time": None,
            "utc_6h_block_ids": ["2026-01-01T00:00:00+00:00"],
            "scopes": ["R3_H01"],
        },
        {
            "category": "RESTART_GAP",
            "stream": "collector_status",
            "start_time": "2026-01-02T00:00:00+00:00",
            "end_time": "2026-01-02T06:00:00+00:00",
            "utc_6h_block_ids": ["2026-01-02T00:00:00+00:00", "2026-01-02T06:00:00+00:00"],
            "scopes": ["GLOBAL"],
        },
    ]
    usable_blocks = {hypothesis: list(block_ids) for hypothesis in PRIMARY_HYPOTHESES}
    usable_days = {hypothesis: [f"2026-01-{index:02d}" for index in range(1, 31)] for hypothesis in PRIMARY_HYPOTHESES}
    contributions = {
        hypothesis: {used_sha: {"effective_month": "2026-09", "complete_count": 1}}
        for hypothesis in PRIMARY_HYPOTHESES
    }
    return {
        "record_type": "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2",
        "calendar": {"independent_utc_days": 30, "independent_utc_6h_blocks": 120},
        "gap_blocks_by_scope": {
            "GLOBAL": ["2026-01-02T00:00:00+00:00", "2026-01-02T06:00:00+00:00"],
            "R3_H01": ["2026-01-01T00:00:00+00:00"],
        },
        "availability_and_gaps": {
            "gap_records": records,
            "gap_accounting_complete": True,
            "health_gap_count": 3,
            "health_restart_count": 1,
            "source_unavailable_records": 1,
            "no_imputation": True,
        },
        "streams": {},
        "cycles": {},
        "verified_roster_months": ["2026-09"],
        "used_roster_identities": [{"effective_month": "2026-09", "roster_sha256": used_sha}],
        "usable_blocks_by_hypothesis": usable_blocks,
        "usable_days_by_hypothesis": usable_days,
        "roster_contribution_by_hypothesis": contributions,
        "integrity": {
            "payload_values_retained": False,
            "performance_fields_seen": False,
            "confirmatory_root_accessed": False,
            "secondary_campaign_accessed": False,
        },
    }


def test_scoped_gap_union_preserves_source_scope_and_global_scope() -> None:
    records = [
        {
            "category": "SOURCE_UNAVAILABLE",
            "start_time": "2026-01-01T05:59:00+00:00",
            "end_time": "2026-01-01T06:01:00+00:00",
            "utc_6h_block_ids": ["2026-01-01T00:00:00+00:00", "2026-01-01T06:00:00+00:00"],
            "scopes": ["R3_H01"],
        },
        {
            "category": "RESTART_GAP",
            "start_time": "2026-01-01T06:00:00+00:00",
            "end_time": None,
            "utc_6h_block_ids": ["2026-01-01T06:00:00+00:00"],
            "scopes": ["GLOBAL"],
        },
    ]
    result = _scoped_gap_blocks(records)
    assert result["R3_H01"] == {"2026-01-01T00:00:00+00:00", "2026-01-01T06:00:00+00:00"}
    assert result["GLOBAL"] == {"2026-01-01T06:00:00+00:00"}


def test_scoped_gap_duplicate_ids_and_legacy_rollover_fail_closed() -> None:
    duplicate = {
        "category": "SOURCE_UNAVAILABLE",
        "start_time": "2026-01-01T01:00:00+00:00",
        "utc_6h_block_ids": ["2026-01-01T00:00:00+00:00"] * 2,
        "scopes": ["R3_H01"],
    }
    with pytest.raises(InventoryError, match="duplicate"):
        _scoped_gap_blocks([duplicate])
    legacy = deepcopy(duplicate)
    legacy["category"] = "UNIVERSE_ROLLOVER_GAP"
    legacy["utc_6h_block_ids"] = ["2026-01-01T00:00:00+00:00"]
    with pytest.raises(InventoryError, match="legacy"):
        _scoped_gap_blocks([legacy])


def test_checker_validates_exact_scoped_maps_and_per_h_minima() -> None:
    inventory = _strict_inventory()
    scoped = validate_scoped_gap_blocks(inventory)
    assert scoped["excluded_block_ids_by_hypothesis"]["R3_H01"] == [
        "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00", "2026-01-02T06:00:00+00:00"
    ]
    receipt = validate_per_hypothesis_gates(inventory, inventory["used_roster_identities"])
    assert set(receipt["hypotheses"]) == set(PRIMARY_HYPOTHESES)
    inventory["usable_blocks_by_hypothesis"]["R3_H01"].append(inventory["usable_blocks_by_hypothesis"]["R3_H01"][0])
    with pytest.raises(ReadinessInputError, match="duplicates"):
        validate_per_hypothesis_gates(inventory, inventory["used_roster_identities"])


def test_global_calendar_gate_is_direct_and_not_gap_subtracted() -> None:
    inventory = _strict_inventory()
    inventory["calendar"]["independent_utc_6h_blocks"] = 119
    with pytest.raises(ReadinessInputError, match="global complete calendar"):
        validate_per_hypothesis_gates(inventory, inventory["used_roster_identities"])


def test_used_roster_identity_counts_one_same_sha_month_and_enforces_membership() -> None:
    roster = {
        "effective_month": "2026-09", "roster_sha256": "a" * 64,
        "symbols": ["BTCUSDT"], "effective_start": "2026-09-01T00:00:00+00:00", "effective_end": "2026-10-01T00:00:00+00:00",
    }
    duplicate = dict(roster, artifact="duplicate.json")
    cycles = [{"cycle_id": "c1", "timestamp": "2026-09-05T00:00:00+00:00", "roster_sha256": "a" * 64}]
    rows = {"a" * 64: [{"symbol": "BTCUSDT", "timestamp": "2026-09-05T00:15:00+00:00"}]}
    used, diagnostics = _used_roster_identities(cycles, [roster, duplicate], rows)
    assert diagnostics == []
    assert len(used) == 1 and used[0]["membership"]["symbol_count"] == 1
    bad_rows = {"a" * 64: [{"symbol": "ETHUSDT", "timestamp": "2026-09-05T00:15:00+00:00"}]}
    with pytest.raises(InventoryError, match="outside verified roster"):
        _used_roster_identities(cycles, [roster], bad_rows)


def _forceorder_envelope(event_ms: int = 1, receipt: str = "1970-01-01T00:00:00.001Z") -> dict:
    return {
        "market_type": "UM", "symbol": "btcusdt", "stream": "LIQUIDATION",
        "endpoint": "wss://fstream.binance.com/market/ws/btcusdt@forceOrder",
        "collector_receipt_time": receipt, "continuity_state": "COMPLETE",
        "payload": {"e": "forceOrder", "E": event_ms, "o": {
            "s": "BTCUSDT", "S": "SELL", "o": "LIMIT", "f": "IOC", "q": "1", "p": "100", "ap": "100",
            "X": "FILLED", "l": "1", "z": "1", "T": event_ms, "t": 0, "ps": "BOTH", "st": 1,
            "m": False, "wt": "CONTRACT_PRICE", "ot": "LIMIT",
        }},
    }


def test_forceorder_accounting_has_global_h03_h04_counts_and_no_payload_values(monkeypatch: pytest.MonkeyPatch) -> None:
    first = _forceorder_envelope()
    duplicate = deepcopy(first)
    duplicate["collector_receipt_time"] = "1970-01-01T00:00:00.002Z"
    invalid = deepcopy(first)
    invalid["market_type"] = "CM"
    receipt = forceorder.deduplicate_forceorders([first, duplicate, invalid])
    assert receipt.raw_envelope_count == 3
    assert receipt.unique_event_count == 1 and receipt.duplicate_envelope_count == 1 and receipt.invalid_envelope_count == 1
    assert receipt.h03.invariant_ok and receipt.h04.invariant_ok and receipt.invariant_ok
    exported = receipt.as_dict()
    assert not any(key in exported for key in ("payload", "canonical_payload_json", "raw_payload_sha256"))
    monkeypatch.setattr(forceorder, "_sha256_text", lambda _value: "f" * 64)
    collision = forceorder.deduplicate_forceorders([_forceorder_envelope(1), _forceorder_envelope(2)])
    assert collision.collision_envelope_count == 2
    assert collision.h03.invariant_ok and collision.h04.invariant_ok


def test_inventory_modules_are_outcome_blind_and_tests_do_not_touch_d_root() -> None:
    source = Path(__file__).resolve().parents[1] / "build_r3_evidence_inventory.py"
    text = source.read_text(encoding="utf-8").lower()
    assert "materializer" not in text and "executor" not in text
    assert '"payload_values_retained"' in text
