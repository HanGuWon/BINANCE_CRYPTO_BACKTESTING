from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from binance_research.collector import observed_forceorder_pressure_v3, route_liquidation_event_v3
from ops.r3 import r3_forceorder_identity_v3 as identity
from ops.r3.build_r3_evidence_inventory import InventoryError, build_forceorder_metadata


def _payload(*, symbol: str = "BTCUSDT", pair: str = "BTCUSDT", subtype: int = 1, event_ms: int = 1, top_level: bool = True) -> dict:
    order = {
        "s": symbol, "S": "SELL", "o": "LIMIT", "f": "IOC", "q": "1", "p": "100", "ap": "100",
        "X": "FILLED", "l": "1", "z": "1", "T": event_ms, "t": 0, "m": False,
        "wt": "CONTRACT_PRICE", "ot": "LIMIT",
    }
    payload = {"e": "forceOrder", "E": event_ms, "o": order}
    if top_level:
        payload.update({"ps": pair, "st": subtype})
    else:
        order.update({"ps": pair, "st": subtype})
    return payload


def _envelope(payload: dict, *, market: str = "UM", symbol: str = "BTCUSDT") -> dict:
    return {
        "market_type": market,
        "symbol": symbol,
        "stream": "LIQUIDATION",
        "endpoint": "wss://fstream.binance.com/market/ws/!forceOrder@arr",
        "collector_receipt_time": "1970-01-01T00:00:00.001Z",
        "continuity_state": "COMPLETE",
        "payload": payload,
    }


def _assert_reject(payload: dict, reason: str) -> None:
    with pytest.raises(identity.ForceOrderIdentityV3Error, match=reason):
        identity.normalize_forceorder_payload_v3(payload)


def test_official_top_level_um_and_cm_have_distinct_market_identity() -> None:
    um = identity.validate_forceorder_envelope_v3(_envelope(_payload()))
    cm_payload = _payload(symbol="BTCUSD_PERP", pair="BTCUSD", subtype=2, event_ms=2)
    cm = identity.validate_forceorder_envelope_v3(_envelope(cm_payload, market="CM", symbol="BTCUSD_PERP"))
    assert um.market_type == "um" and um.pair_symbol == "BTCUSDT" and um.subtype == 1
    assert cm.market_type == "cm" and cm.pair_symbol == "BTCUSD" and cm.subtype == 2
    assert um.identity_key != cm.identity_key


def test_legacy_nested_pair_and_subtype_are_explicit_fallbacks() -> None:
    record = identity.validate_forceorder_envelope_v3(_envelope(_payload(symbol="ETHUSDT", pair="ETHUSDT", top_level=False), symbol="ETHUSDT"))
    assert record.pair_symbol == "ETHUSDT" and record.subtype == 1


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda p: p["o"].update({"ps": "ETHUSDT"}), "PAIR_SYMBOL_CONFLICT"),
        (lambda p: p["o"].update({"st": 2}), "ST_CONFLICT"),
        (lambda p: p["o"].update({"s": "ETHUSDT"}), "SYMBOL_PAIR_MISMATCH"),
    ],
)
def test_v3_conflicts_fail_closed(mutator, reason: str) -> None:
    payload = _payload()
    mutator(payload)
    with pytest.raises(identity.ForceOrderIdentityV3Error, match=reason):
        identity.normalize_forceorder_payload_v3(payload)


def test_v3_never_treats_pair_symbol_as_position_side() -> None:
    payload = _payload()
    assert identity.normalize_forceorder_payload_v3(payload)[1]["ps"] == "BTCUSDT"
    payload["ps"] = "BOTH"
    with pytest.raises(identity.ForceOrderIdentityV3Error):
        identity.normalize_forceorder_payload_v3(payload)


def test_collector_v3_and_parser_agree_on_all_identity_fields() -> None:
    payload = _payload(symbol="BTCUSD_PERP", pair="BTCUSD", subtype=2, event_ms=2)
    identity_tuple, normalized = identity.normalize_forceorder_payload_v3(payload)
    assert route_liquidation_event_v3(payload) == ("cm", "BTCUSD_PERP")
    observed = observed_forceorder_pressure_v3(payload)
    assert (observed["market"], observed["symbol"], observed["pair_symbol"], observed["subtype"]) == (identity_tuple[0], identity_tuple[2], identity_tuple[3], identity_tuple[16])
    assert observed["exchange_event_time"] == identity_tuple[4]
    assert observed["trade_order_time"] == identity_tuple[5]
    assert observed["position_side"] is None
    assert normalized["o"]["T"] == observed["trade_order_time"]


def test_inventory_selector_defaults_to_v2_and_unknown_version_fails_closed() -> None:
    envelope = _envelope(_payload())
    v2 = build_forceorder_metadata([envelope])
    assert v2["identity_key_version"] == "forceorder:v2"
    with pytest.raises(InventoryError, match="unknown forceOrder identity version"):
        build_forceorder_metadata([envelope], identity_version="v9")  # type: ignore[arg-type]


def test_inventory_v3_counts_replays_and_markets_without_payload_values() -> None:
    um = _envelope(_payload())
    replay = deepcopy(um)
    replay["collector_receipt_time"] = "1970-01-01T00:00:00.002Z"
    cm = _envelope(_payload(symbol="BTCUSD_PERP", pair="BTCUSD", subtype=2, event_ms=2), market="CM", symbol="BTCUSD_PERP")
    metadata = build_forceorder_metadata([um, replay, cm], identity_version="v3", complete_bar_opens={datetime(1970, 1, 1, 0, 15, tzinfo=UTC)})
    assert metadata["unique_event_count"] == 2
    assert metadata["duplicate_envelope_count"] == 1
    assert metadata["representative_market_counts"] == {"cm": 1, "um": 1}
    assert "canonical_payload_json" not in metadata


def test_v3_collision_reclassifies_every_member(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity, "_sha256_text", lambda _value: "f" * 64)
    first = _envelope(_payload(event_ms=10))
    second = _envelope(_payload(event_ms=11))
    receipt = identity.deduplicate_forceorders_v3([first, second])
    assert receipt.collision_envelope_count == 2
    assert receipt.unique_event_count == 0 and receipt.invariant_ok


def test_v3_module_is_metadata_only_and_does_not_touch_restricted_roots() -> None:
    source = Path(identity.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("gross_return", "net_return", "pnl", "sharpe", "final_holdout", "scientific_raw_v8"):
        assert forbidden not in source


def test_v3_signed_pressure_preserves_sell_positive_and_buy_negative() -> None:
    sell = observed_forceorder_pressure_v3(_payload())
    buy_payload = _payload()
    buy_payload["o"]["S"] = "BUY"
    buy = observed_forceorder_pressure_v3(buy_payload)
    assert sell["signed_observed_notional"] == 100.0
    assert buy["signed_observed_notional"] == -100.0
    assert sell["position_side"] is None and buy["position_side"] is None


def test_v3_rejects_nonfinite_values_unknown_keys_and_unsupported_subtype() -> None:
    nan_payload = _payload()
    nan_payload["o"]["ap"] = "NaN"
    _assert_reject(nan_payload, "ap_DECIMAL_INVALID")
    unknown_payload = _payload()
    unknown_payload["unexpected"] = 1
    _assert_reject(unknown_payload, "PAYLOAD_SCHEMA_INVALID")
    unsupported = _payload(subtype=3)
    _assert_reject(unsupported, "ST_INVALID")


def test_v3_strict_source_boundary_rejects_equality_and_missing_time() -> None:
    assert identity.source_available_before_next_executable_open(
        datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 1, 0, 15, tzinfo=UTC),
    )
    assert not identity.source_available_before_next_executable_open(
        datetime(2026, 9, 1, 0, 15, tzinfo=UTC),
        datetime(2026, 9, 1, 0, 15, tzinfo=UTC),
    )
    assert not identity.source_available_before_next_executable_open(None, datetime(2026, 9, 1, 0, 15, tzinfo=UTC))


def test_v3_gap_state_is_retained_and_not_endpoint_eligible() -> None:
    envelope = _envelope(_payload())
    envelope["continuity_state"] = "RESTART_GAP"
    record = identity.validate_forceorder_envelope_v3(
        envelope,
        complete_bar_opens={datetime(1970, 1, 1, 0, 15, tzinfo=UTC)},
    )
    assert record.continuity_state == "RESTART_GAP"
    assert record.h03_status == "endpoint_invalid"
    assert record.h04_status == "endpoint_invalid"


def test_v3_future_append_does_not_change_prior_identity() -> None:
    payload = _payload(event_ms=123)
    before = identity.normalize_forceorder_payload_v3(payload)[0]
    later = _payload(event_ms=456)
    receipt = identity.deduplicate_forceorders_v3([_envelope(payload), _envelope(later)])
    assert before == identity.normalize_forceorder_payload_v3(payload)[0]
    assert receipt.unique_event_count == 2


def test_v2_public_pair_symbol_is_explicitly_invalid_but_v3_accepts() -> None:
    payload = _payload(top_level=False)
    from ops.r3.r3_forceorder_identity import ForceOrderIdentityError, validate_forceorder_envelope
    with pytest.raises(ForceOrderIdentityError, match="ps_ENUM_INVALID"):
        validate_forceorder_envelope(_envelope(payload))
    identity_tuple, normalized = identity.normalize_forceorder_payload_v3(_payload())
    assert identity_tuple[0] == "um" and normalized["ps"] == "BTCUSDT"
