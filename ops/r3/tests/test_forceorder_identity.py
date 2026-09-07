from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.r3 import r3_forceorder_identity as identity


def _envelope(*, event_ms: int = 1, receipt: str = "1970-01-01T00:00:00.001Z", state: str = "COMPLETE") -> dict:
    return {
        "market_type": "UM",
        "symbol": "btcusdt",
        "stream": "LIQUIDATION",
        "endpoint": "wss://fstream.binance.com/market/ws/btcusdt@forceOrder",
        "collector_receipt_time": receipt,
        "sequence_id": 7,
        "continuity_state": state,
        "payload": {
            "e": "forceOrder",
            "E": event_ms,
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",
                "o": "LIMIT",
                "f": "IOC",
                "q": "1.0000",
                "p": "100.00",
                "ap": "100.0",
                "X": "FILLED",
                "l": "1",
                "z": "1.000",
                "T": event_ms,
                "t": 0,
                "ps": "BOTH",
                "st": 1,
                "m": False,
                "wt": "CONTRACT_PRICE",
                "ot": "LIMIT",
            },
        },
    }


def _bars(start: datetime, count: int = 4) -> set[datetime]:
    return {start + timedelta(minutes=15 * index) for index in range(count)}


def test_key_is_stable_under_reordering_receipts_and_sequence_changes() -> None:
    first = _envelope()
    second = deepcopy(first)
    second["collector_receipt_time"] = "1970-01-01T00:00:00.123Z"
    second["sequence_id"] = 999
    second["payload"] = {"o": dict(reversed(list(first["payload"]["o"].items()))), "E": 1, "e": "forceOrder"}
    assert identity.forceorder_identity_key(first) == identity.forceorder_identity_key(second)


def test_t_is_not_a_timestamp_alias_and_missing_T_is_invalid() -> None:
    missing_t = deepcopy(_envelope())
    del missing_t["payload"]["o"]["T"]
    with pytest.raises(identity.ForceOrderIdentityError, match="ORDER_SCHEMA_INVALID"):
        identity.forceorder_identity_key(missing_t)
    explicit = deepcopy(_envelope())
    explicit["payload"]["o"]["t"] = "0000"
    record = identity.validate_forceorder_envelope(explicit)
    assert record.identity_tuple[4] == "0"
    assert record.identity_tuple[3] == 1


def test_decimal_canonicalization_and_null_optionals_are_exact() -> None:
    first = _envelope()
    second = deepcopy(first)
    order = second["payload"]["o"]
    order.update({"q": "1e0", "p": "1.0000e2", "ap": "100.000", "l": "01.0", "z": "1e0"})
    assert identity.forceorder_identity_key(first) == identity.forceorder_identity_key(second)
    negative_zero = deepcopy(first)
    negative_zero["payload"]["o"]["z"] = "-0"
    assert '"z":"0"' in identity.validate_forceorder_envelope(negative_zero).canonical_payload_json
    for key in ("t", "ps", "st", "m", "wt", "ot"):
        order.pop(key, None)
    canonical = identity.validate_forceorder_envelope(second).canonical_payload_json
    assert '"t":null' in canonical and '"st":null' in canonical


@pytest.mark.parametrize(
    ("field", "value"),
    [("market_type", "cm"), ("stream", "depth"), ("endpoint", "wss://fstream.binance.com/market/ws/btcusdt@aggTrade"), ("symbol", "ETHUSDT")],
)
def test_um_transport_and_symbol_firewall_fails_closed(field: str, value: str) -> None:
    envelope = _envelope()
    envelope[field] = value
    with pytest.raises(identity.ForceOrderIdentityError):
        identity.forceorder_identity_key(envelope)


@pytest.mark.parametrize(
    ("field", "value"),
    [("S", "HOLD"), ("o", "UNKNOWN"), ("f", "DAY"), ("X", "UNKNOWN"), ("ps", "HEDGE")],
)
def test_unknown_side_order_or_status_enum_is_invalid(field: str, value: str) -> None:
    envelope = _envelope()
    envelope["payload"]["o"][field] = value
    with pytest.raises(identity.ForceOrderIdentityError):
        identity.forceorder_identity_key(envelope)


def test_duplicate_representative_prefers_complete_and_accounting_is_disjoint() -> None:
    first = _envelope()
    gap = deepcopy(first)
    gap["collector_receipt_time"] = "1970-01-01T00:00:00.000Z"
    gap["continuity_state"] = "RESTART_GAP"
    receipt = identity.deduplicate_forceorders([gap, first])
    assert receipt.raw_envelope_count == 2
    assert receipt.unique_event_count == 1
    assert receipt.duplicate_envelope_count == 1
    assert receipt.collision_envelope_count == 0
    assert receipt.invalid_envelope_count == 0
    assert receipt.representatives[0].continuity_state == "COMPLETE"
    assert receipt.invariant_ok


def test_tuple_digest_collision_reclassifies_every_member(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity, "_sha256_text", lambda _: "f" * 64)
    first = _envelope(event_ms=1)
    second = _envelope(event_ms=2)
    receipt = identity.deduplicate_forceorders([first, second])
    assert receipt.unique_event_count == 0
    assert receipt.duplicate_envelope_count == 0
    assert receipt.collision_envelope_count == 2
    assert receipt.invalid_envelope_count == 0
    assert receipt.invariant_ok


def test_h03_h04_endpoint_counts_include_replays_but_minima_use_unique() -> None:
    first = _envelope()
    gap = deepcopy(first)
    gap["continuity_state"] = "SEQUENCE_GAP"
    missing = _envelope(event_ms=3_600_001)
    bars = _bars(datetime(1970, 1, 1, 0, 15, tzinfo=UTC))
    receipt = identity.deduplicate_forceorders([first, gap, missing], complete_bar_opens=bars)
    assert receipt.h03.raw_endpoint_count == 3
    assert receipt.h03.unique_endpoint_count == 1
    assert receipt.h03.duplicate_endpoint_count == 0
    assert receipt.h03.invalid_endpoint_count == 2
    assert receipt.h04.raw_endpoint_count == 3
    assert receipt.h04.unique_endpoint_count == 1
    assert receipt.h04.invariant_ok and receipt.invariant_ok


def test_strict_grid_rejects_equality_by_advancing_to_next_open() -> None:
    envelope = _envelope(receipt="1970-01-01T00:15:00Z")
    record = identity.validate_forceorder_envelope(envelope)
    assert record.executable_open == datetime(1970, 1, 1, 0, 30, tzinfo=UTC)


def test_malformed_corrected_receipt_is_invalid_not_fallback() -> None:
    envelope = _envelope()
    envelope["corrected_response_receipt_time"] = "not-a-timestamp"
    receipt = identity.deduplicate_forceorders([envelope])
    assert receipt.invalid_envelope_count == 1
    assert "CORRECTED_RECEIPT_TIMESTAMP_INVALID" in receipt.invalid_reasons


def test_payload_schema_rejects_unknown_keys_and_non_forceorder_events() -> None:
    envelope = _envelope()
    envelope["payload"]["unexpected"] = 1
    with pytest.raises(identity.ForceOrderIdentityError, match="PAYLOAD_SCHEMA_INVALID"):
        identity.forceorder_identity_key(envelope)
    event = _envelope()
    event["payload"]["e"] = "aggTrade"
    with pytest.raises(identity.ForceOrderIdentityError, match="EVENT_TYPE_INVALID"):
        identity.forceorder_identity_key(event)


def test_static_firewall_has_no_outcome_field_or_root_access() -> None:
    source = Path(identity.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("gross_return", "net_return", "pnl", "sharpe", "hit_rate", "final_holdout"):
        assert forbidden not in source
    assert "scientific_raw_v8" not in source
