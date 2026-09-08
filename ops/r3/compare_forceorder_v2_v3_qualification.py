"""Outcome-blind synthetic qualification for the ForceOrder V3 adapter.

The optimized side is the public metadata adapter.  The reference side below
is deliberately self-contained: it implements the frozen field normalization,
strict next-open rule, and signed-pressure equation without importing the V3
normalizer.  No research root or outcome-like field is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

import pandas as pd

from binance_research.r3_materializer import FORCEORDER_V3_COLUMNS, materialize_forceorder_v3_metadata


GRID_STEP = timedelta(minutes=15)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
FORBIDDEN = ("outcome", "holdout", "return", "pnl", "r2b2")
COMPARE_FIELDS = tuple(FORCEORDER_V3_COLUMNS)
V2_FIELDS = ("v2_status",)
QUALIFICATION_FIELDS = COMPARE_FIELDS + V2_FIELDS
ALLOWED_MARKETS = {"um", "cm"}
ALLOWED_SUBTYPES = {1: "um", 2: "cm"}
ENUMS = {
    "S": {"BUY", "SELL"},
    "o": {"LIMIT", "MARKET", "STOP", "TAKE_PROFIT", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET", "LIQUIDATION"},
    "f": {"GTC", "IOC", "FOK", "GTX"},
    "X": {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"},
    "wt": {"MARK_PRICE", "CONTRACT_PRICE"},
    "ot": {"LIMIT", "MARKET", "STOP", "TAKE_PROFIT", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET", "LIQUIDATION"},
}
ORDER_REQUIRED = {"s", "S", "o", "f", "q", "p", "ap", "X", "l", "z", "T"}
ORDER_ALLOWED = ORDER_REQUIRED | {"t", "ps", "st", "b", "a", "m", "wt", "ot"}
STATES = {"COMPLETE", "RESTART_GAP", "POLL_GAP", "SOURCE_TIME_UNAVAILABLE", "SEQUENCE_GAP", "SCHEMA_ERROR", "RATE_LIMIT_GAP", "CLOCK_UNCERTAINTY_GAP"}


class ReferenceInvalid(ValueError):
    """Reference-side deterministic rejection."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _fail(reason: str) -> None:
    raise ReferenceInvalid(reason)


def _symbol(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field}_EMPTY" if isinstance(value, str) else f"{field}_NOT_STRING")
    return value.strip().upper()


def _market(value: Any) -> str:
    if not isinstance(value, str):
        _fail("MARKET_TYPE_INVALID")
    result = value.strip().casefold()
    aliases = {"um": "um", "usd-m": "um", "usdⓈ-m": "um", "usdⓈm": "um", "cm": "cm", "coin-m": "cm", "coinⓂ-m": "cm", "coinⓂm": "cm"}
    if result not in aliases:
        _fail("MARKET_TYPE_INVALID")
    return aliases[result]


def _enum(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        _fail(f"{field}_ENUM_INVALID")
    result = value.strip().upper()
    if result not in ENUMS[field]:
        _fail(f"{field}_ENUM_INVALID")
    return result


def _integer(value: Any, field: str, *, max_value: int = 2**63 - 1) -> int:
    if isinstance(value, bool):
        _fail(f"{field}_INTEGER_INVALID")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value.strip(), 10)
    else:
        _fail(f"{field}_INTEGER_INVALID")
    if result < 0 or result > max_value:
        _fail(f"{field}_INTEGER_INVALID")
    return result


def _decimal(value: Any, field: str, *, positive: bool = False) -> str:
    if isinstance(value, bool) or value is None:
        _fail(f"{field}_DECIMAL_INVALID")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        _fail(f"{field}_DECIMAL_INVALID")
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        _fail(f"{field}_DECIMAL_INVALID")
    if number.is_zero():
        return "0"
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            _fail(f"{field}_TIMESTAMP_INVALID")
    else:
        _fail(f"{field}_TIMESTAMP_INVALID")
    if parsed.tzinfo is None:
        _fail(f"{field}_TIMESTAMP_INVALID")
    return parsed.astimezone(UTC)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReferenceInvalid("JSON_CANONICALIZATION_INVALID") from exc


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _next_open(event: datetime, available: datetime) -> datetime:
    boundary = max(event, available)
    elapsed = boundary - EPOCH
    candidate = EPOCH + (elapsed // GRID_STEP + 1) * GRID_STEP
    while candidate <= event or candidate <= available:
        candidate += GRID_STEP
    return candidate


def _pair_matches(event_symbol: str, pair_symbol: str) -> bool:
    return event_symbol == pair_symbol or event_symbol.startswith(pair_symbol + "_")


def _endpoint_status(executable: datetime | None, state: str, opens: set[datetime], *, delayed: bool) -> str:
    if executable is None or state != "COMPLETE":
        return "endpoint_invalid"
    required = {executable + GRID_STEP * offset for offset in ((0, 1, 2, 3) if delayed else (0,))}
    return "endpoint_eligible" if required.issubset(opens) else "endpoint_invalid"


def _slow_validate(envelope: Mapping[str, Any], *, complete_bar_opens: Iterable[Any]) -> dict[str, Any]:
    """Independent reference implementation of the frozen V3 contract."""
    endpoint = envelope.get("endpoint")
    stream = envelope.get("stream")
    if not isinstance(endpoint, str) or not isinstance(stream, str) or stream.strip().casefold() != "liquidation":
        _fail("ENDPOINT_STREAM_INVALID")
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        _fail("ENDPOINT_INVALID")
    if parsed.scheme.casefold() != "wss" or parsed.hostname not in {"fstream.binance.com", "dstream.binance.com"} or parsed.port is not None or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or not parsed.path.startswith("/market/ws/"):
        _fail("ENDPOINT_INVALID")
    stream_token = parsed.path[len("/market/ws/") :]
    if re.fullmatch(r"(?:!forceorder@arr|[a-z0-9_]+@forceOrder)", stream_token, flags=re.IGNORECASE) is None:
        _fail("ENDPOINT_INVALID")
    market_type = _market(envelope.get("market_type"))
    envelope_symbol = _symbol(envelope.get("symbol"), "ENVELOPE_SYMBOL")
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        _fail("PAYLOAD_NOT_MAPPING")
    if set(payload) - {"e", "E", "o", "ps", "st"} or not {"e", "E", "o"}.issubset(payload):
        _fail("PAYLOAD_SCHEMA_INVALID")
    if payload.get("e") != "forceOrder":
        _fail("EVENT_TYPE_INVALID")
    event_ms = _integer(payload["E"], "E")
    order = payload.get("o")
    if not isinstance(order, Mapping) or set(order) - ORDER_ALLOWED or not ORDER_REQUIRED.issubset(order):
        _fail("ORDER_SCHEMA_INVALID")
    pair_top = _symbol(payload["ps"], "PAIR_SYMBOL") if "ps" in payload else None
    pair_nested = _symbol(order["ps"], "PAIR_SYMBOL") if "ps" in order else None
    if pair_top is not None and pair_nested is not None and pair_top != pair_nested:
        _fail("PAIR_SYMBOL_CONFLICT")
    pair_symbol = pair_top or pair_nested
    if pair_symbol is None:
        _fail("PAIR_SYMBOL_MISSING")
    subtype_top = _integer(payload["st"], "ST") if "st" in payload else None
    subtype_nested = _integer(order["st"], "ST") if "st" in order else None
    if subtype_top is not None and subtype_top not in ALLOWED_SUBTYPES or subtype_nested is not None and subtype_nested not in ALLOWED_SUBTYPES:
        _fail("ST_INVALID")
    if subtype_top is not None and subtype_nested is not None and subtype_top != subtype_nested:
        _fail("ST_CONFLICT")
    subtype = subtype_top if subtype_top is not None else subtype_nested
    if subtype is None:
        _fail("ST_MISSING")
    event_symbol = _symbol(order["s"], "ORDER_SYMBOL")
    if not _pair_matches(event_symbol, pair_symbol):
        _fail("SYMBOL_PAIR_MISMATCH")
    forced_side = _enum(order["S"], "S")
    order_type = _enum(order["o"], "o")
    time_in_force = _enum(order["f"], "f")
    status = _enum(order["X"], "X")
    trade_id = None if order.get("t") is None else str(_integer(order["t"], "T_ID"))
    normalized_order = {
        "s": event_symbol, "S": forced_side, "o": order_type, "f": time_in_force,
        "q": _decimal(order["q"], "q", positive=True), "p": _decimal(order["p"], "p"),
        "ap": _decimal(order["ap"], "ap"), "X": status, "l": _decimal(order["l"], "l"),
        "z": _decimal(order["z"], "z"), "T": _integer(order["T"], "T"), "t": trade_id,
        "b": _decimal(order.get("b"), "b") if order.get("b") is not None else None,
        "a": _decimal(order.get("a"), "a") if order.get("a") is not None else None,
        "m": order.get("m") if order.get("m") is not None else None,
        "wt": _enum(order.get("wt"), "wt", optional=True), "ot": _enum(order.get("ot"), "ot", optional=True),
    }
    if normalized_order["m"] is not None and not isinstance(normalized_order["m"], bool):
        _fail("m_BOOLEAN_INVALID")
    normalized_payload = {"e": "forceOrder", "E": event_ms, "ps": pair_symbol, "st": subtype, "o": normalized_order}
    identity = (ALLOWED_SUBTYPES[subtype], "forceOrder", event_symbol, pair_symbol, event_ms, normalized_order["T"], trade_id, forced_side, order_type, time_in_force, normalized_order["q"], normalized_order["p"], normalized_order["ap"], status, normalized_order["l"], normalized_order["z"], subtype)
    identity_json = _canonical({"identity_tuple": list(identity)})
    canonical_payload_json = _canonical(normalized_payload)
    raw_payload_json = _canonical(payload)
    event_time = EPOCH + timedelta(milliseconds=event_ms)
    collector = _timestamp(envelope["collector_receipt_time"], "COLLECTOR_RECEIPT") if envelope.get("collector_receipt_time") is not None else None
    corrected = _timestamp(envelope["corrected_response_receipt_time"], "CORRECTED_RECEIPT") if envelope.get("corrected_response_receipt_time") is not None else None
    available = corrected or collector
    executable = _next_open(event_time, available) if available is not None else None
    state = str(envelope.get("continuity_state") or "COMPLETE").strip().upper()
    if state not in STATES:
        _fail("CONTINUITY_STATE_INVALID")
    opens = {_timestamp(value, "BAR_OPEN") for value in complete_bar_opens}
    signed_base = Decimal(identity[14]) * Decimal(identity[12] or identity[11])
    signed = signed_base if identity[7] == "SELL" else -signed_base
    return {
        "identity_key": f"forceorder:v3:{_sha(identity_json)}", "market_type": identity[0], "event_symbol": identity[2], "pair_symbol": identity[3], "subtype": identity[16],
        "event_time_ms": identity[4], "order_trade_time_ms": identity[5], "trade_id": identity[6], "forced_side": identity[7], "position_side": None,
        "source_event_time_ms": identity[4], "source_available_time": available, "executable_open": executable, "continuity_state": state,
        "h03_status": _endpoint_status(executable, state, opens, delayed=False), "h04_status": _endpoint_status(executable, state, opens, delayed=True),
        "signed_observed_notional": format(signed, "f"), "raw_payload_sha256": _sha(raw_payload_json), "canonical_payload_sha256": _sha(canonical_payload_json),
        "identity_tuple_sha256": _sha(identity_json),
        "causal_eligibility": "ELIGIBLE" if available is not None and executable is not None and available < executable else "INELIGIBLE_SOURCE_TIME",
        "v3_status": "VALID", "v3_invalid_reason": None,
    }


def _invalid(reason: str) -> dict[str, Any]:
    result = {field: None for field in COMPARE_FIELDS}
    result.update({"causal_eligibility": "INELIGIBLE_SCHEMA", "v3_status": "INVALID", "v3_invalid_reason": reason})
    return result


def slow_reference(envelope: Mapping[str, Any], *, complete_bar_opens: Iterable[Any]) -> dict[str, Any]:
    try:
        return _slow_validate(envelope, complete_bar_opens=complete_bar_opens)
    except ReferenceInvalid as exc:
        return _invalid(exc.reason)


def _v2_status(envelope: Mapping[str, Any]) -> str:
    """Classify the immutable V2 contract without changing it."""
    from ops.r3.r3_forceorder_identity import ForceOrderIdentityError, validate_forceorder_envelope

    try:
        validate_forceorder_envelope(envelope)
    except ForceOrderIdentityError as exc:
        return f"INVALID:{exc.reason}"
    return "VALID"


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NaT or (isinstance(value, pd.Timestamp) and pd.isna(value)):
        return None
    return value.to_pydatetime() if isinstance(value, pd.Timestamp) else value


def _optimized_rows(envelopes: list[dict[str, Any]], complete_bar_opens: Iterable[Any]) -> list[dict[str, Any]]:
    frame = materialize_forceorder_v3_metadata(envelopes, complete_bar_opens=complete_bar_opens)
    rows = [{field: _clean(row[field]) for field in COMPARE_FIELDS} for row in frame.to_dict(orient="records")]
    for row, envelope in zip(rows, envelopes, strict=True):
        row["v2_status"] = _v2_status(envelope)
    return rows


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: tuple("" if row.get(field) is None else str(row.get(field)) for field in ("identity_key", "identity_tuple_sha256", "canonical_payload_sha256", "v3_status", "v3_invalid_reason")))


def _classification(rows: list[dict[str, Any]]) -> dict[str, int]:
    groups: dict[str, list[dict[str, Any]]] = {}
    invalid = 0
    for row in rows:
        if row.get("v3_status") != "VALID":
            invalid += 1
            continue
        groups.setdefault(str(row.get("identity_key")), []).append(row)
    unique = duplicates = collisions = 0
    for members in groups.values():
        identities = {str(row.get("identity_tuple_sha256")) for row in members}
        payloads = {str(row.get("canonical_payload_sha256")) for row in members}
        if len(identities) > 1 or len(payloads) > 1:
            collisions += len(members)
        else:
            unique += 1
            duplicates += len(members) - 1
    if len(rows) != unique + duplicates + collisions + invalid:
        raise AssertionError("synthetic accounting invariant failed")
    return {"unique_event_count": unique, "duplicate_envelope_count": duplicates, "collision_envelope_count": collisions, "invalid_envelope_count": invalid}


def compare_synthetic(envelopes: list[dict[str, Any]], *, complete_bar_opens: Iterable[Any]) -> dict[str, Any]:
    complete = tuple(complete_bar_opens)
    optimized = _optimized_rows(envelopes, complete)
    reference = []
    for envelope in envelopes:
        row = slow_reference(envelope, complete_bar_opens=complete)
        row["v2_status"] = _v2_status(envelope)
        reference.append(row)
    optimized = _sort_rows(optimized)
    reference = _sort_rows(reference)
    mismatches: list[dict[str, Any]] = []
    for index, (actual, expected) in enumerate(zip(optimized, reference, strict=True)):
        for field in QUALIFICATION_FIELDS:
            if _clean(actual.get(field)) != _clean(expected.get(field)):
                mismatches.append({"index": index, "field": field, "optimized": repr(_clean(actual.get(field))), "reference": repr(_clean(expected.get(field)))})
    if mismatches:
        raise AssertionError(json.dumps(mismatches[:8], sort_keys=True))
    v2 = Counter(str(row["v2_status"]) for row in optimized)
    v3 = Counter(str(row["v3_status"]) for row in optimized)
    markets = Counter(str(row["market_type"]) for row in optimized if row["v3_status"] == "VALID")
    sides = Counter(str(row["forced_side"]) for row in optimized if row["v3_status"] == "VALID")
    fixture_ids = [_sha(_canonical(envelope)) for envelope in envelopes]
    return {
        "record_type": "R3_FORCEORDER_V3_QUALIFICATION_RECEIPT",
        "status": "PASS",
        "fixture_count": len(envelopes),
        "valid_count": v3["VALID"],
        "invalid_count": v3["INVALID"],
        "v2_status_counts": dict(sorted(v2.items())),
        "v3_status_counts": dict(sorted(v3.items())),
        "market_counts": dict(sorted(markets.items())),
        "forced_side_counts": dict(sorted(sides.items())),
        "classification": _classification(optimized),
        "compared_fields": list(QUALIFICATION_FIELDS),
        "fixture_set_sha256": _sha("\n".join(fixture_ids)),
        "optimized_and_reference_identical": True,
        "outcome_blind": True,
        "raw_v8_mutated": False,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
    }


def _base_payload(*, symbol: str = "BTCUSDT", pair: str = "BTCUSDT", subtype: int = 1, event_ms: int = 1, side: str = "SELL", nested: bool = False) -> dict[str, Any]:
    order: dict[str, Any] = {"s": symbol, "S": side, "o": "LIMIT", "f": "IOC", "q": "1", "p": "100", "ap": "100", "X": "FILLED", "l": "1", "z": "1", "T": event_ms, "t": 0, "m": False, "wt": "CONTRACT_PRICE", "ot": "LIMIT"}
    payload: dict[str, Any] = {"e": "forceOrder", "E": event_ms, "o": order}
    if nested:
        order.update({"ps": pair, "st": subtype})
    else:
        payload.update({"ps": pair, "st": subtype})
    return payload


def _envelope(payload: dict[str, Any], *, market: str = "UM", symbol: str = "BTCUSDT", receipt: str = "1970-01-01T00:00:00.001Z", state: str = "COMPLETE") -> dict[str, Any]:
    return {"market_type": market, "symbol": symbol, "stream": "LIQUIDATION", "endpoint": "wss://fstream.binance.com/market/ws/!forceOrder@arr", "collector_receipt_time": receipt, "continuity_state": state, "payload": payload}


def build_synthetic_fixtures() -> tuple[list[dict[str, Any]], tuple[datetime, ...]]:
    fixtures: list[dict[str, Any]] = []
    fixtures.append(_envelope(_base_payload()))
    fixtures.append(_envelope(_base_payload(symbol="ETHUSDT", pair="ETHUSDT", event_ms=2, side="BUY", nested=True), symbol="ETHUSDT"))
    fixtures.append(_envelope(_base_payload(symbol="BTCUSD_PERP", pair="BTCUSD", subtype=2, event_ms=3), market="CM", symbol="BTCUSD_PERP"))
    # Public pair-symbol semantics are intentionally V2-invalid but V3-valid.
    fixtures.append(_envelope(_base_payload(symbol="SOLUSDT", pair="SOLUSDT", event_ms=4), symbol="SOLUSDT"))
    # Same identity with a different receipt is a deterministic duplicate.
    duplicate = deepcopy(fixtures[1])
    duplicate["collector_receipt_time"] = "1970-01-01T00:00:00.002Z"
    fixtures.append(duplicate)
    # Same identity tuple but a changed optional order field is a collision.
    collision = deepcopy(fixtures[0])
    collision["payload"]["o"]["b"] = "7"
    fixtures.append(collision)
    gap = _envelope(_base_payload(event_ms=5), state="RESTART_GAP")
    fixtures.append(gap)
    malformed = _envelope(_base_payload(event_ms=6))
    malformed["payload"]["o"]["ap"] = "NaN"
    fixtures.append(malformed)
    unsupported = _envelope(_base_payload(event_ms=7, subtype=3))
    fixtures.append(unsupported)
    missing_pair = _envelope(_base_payload(event_ms=8))
    missing_pair["payload"].pop("ps")
    fixtures.append(missing_pair)
    missing_side = _envelope(_base_payload(event_ms=9))
    missing_side["payload"]["o"].pop("S")
    fixtures.append(missing_side)
    missing_order_time = _envelope(_base_payload(event_ms=10))
    missing_order_time["payload"]["o"].pop("T")
    fixtures.append(missing_order_time)
    missing_source = _envelope(_base_payload(event_ms=11))
    missing_source.pop("collector_receipt_time")
    fixtures.append(missing_source)
    bad_endpoint = _envelope(_base_payload(event_ms=12))
    bad_endpoint["endpoint"] = "wss://evil.example/market/ws/!forceorder@arr"
    fixtures.append(bad_endpoint)
    bad_stream_token = _envelope(_base_payload(event_ms=13))
    bad_stream_token["endpoint"] = "wss://fstream.binance.com/market/ws/not-a-forceorder"
    fixtures.append(bad_stream_token)
    overflow = _envelope(_base_payload(event_ms=14))
    overflow["payload"]["E"] = 2**63
    fixtures.append(overflow)
    return fixtures, (datetime(1970, 1, 1, 0, 15, tzinfo=UTC), datetime(1970, 1, 1, 0, 30, tzinfo=UTC), datetime(1970, 1, 1, 0, 45, tzinfo=UTC), datetime(1970, 1, 1, 1, 0, tzinfo=UTC))


def qualify_synthetic() -> dict[str, Any]:
    fixtures, opens = build_synthetic_fixtures()
    result = compare_synthetic(fixtures, complete_bar_opens=opens)
    # Public strict-boundary helper and the reference inequality must agree.
    from ops.r3.r3_forceorder_identity_v3 import source_available_before_next_executable_open
    strict_left = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    strict_right = datetime(2026, 9, 1, 0, 15, tzinfo=UTC)
    if source_available_before_next_executable_open(strict_left, strict_right) != (strict_left < strict_right):
        raise AssertionError("public strict-boundary acceptance mismatch")
    if source_available_before_next_executable_open(strict_right, strict_right) is not False:
        raise AssertionError("public strict-boundary equality was accepted")
    # Appending a future envelope cannot change the earlier normalized row.
    earlier_rows = _optimized_rows([fixtures[0]], opens)
    earlier = earlier_rows[0]
    future = deepcopy(fixtures[0])
    future["payload"]["E"] = 2_000_000
    future["payload"]["o"]["T"] = 2_000_000
    appended_rows = _optimized_rows([fixtures[0], future], opens)
    appended = next(row for row in appended_rows if row.get("identity_tuple_sha256") == earlier.get("identity_tuple_sha256"))
    if earlier != appended:
        raise AssertionError("future append changed a historical normalized row")
    result.update({"strict_boundary_equality_rejected": True, "future_append_invariant": True})
    return result


def _write_once(path: Path, value: dict[str, Any]) -> None:
    if any(token in path.as_posix().lower() for token in FORBIDDEN):
        raise ValueError("forbidden qualification receipt path")
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = qualify_synthetic()
    if args.output:
        _write_once(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
