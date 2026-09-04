"""Replay-safe, metadata-only identity handling for Binance UM forceOrder events.

This module deliberately operates on constructed envelopes.  It does not read
the scientific context root and it does not import any response or outcome
material.  The public functions are used by governance/inventory checks and
return only identity, timing, continuity, and accounting metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


UTC_GRID_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
GRID_STEP = timedelta(minutes=15)
MAX_INT_MS = 2**63 - 1

PAYLOAD_TOP_LEVEL_REQUIRED = frozenset({"e", "E", "o"})
PAYLOAD_TOP_LEVEL_ALLOWED = frozenset({"e", "E", "o", "st"})
ORDER_REQUIRED = frozenset({"s", "S", "o", "f", "q", "p", "ap", "X", "l", "z", "T"})
ORDER_ALLOWED = frozenset({"s", "S", "o", "f", "q", "p", "ap", "X", "l", "z", "T", "t", "ps", "st", "b", "a", "m", "wt", "ot"})
ORDER_OPTIONAL = ORDER_ALLOWED - ORDER_REQUIRED
DECIMAL_FIELDS = frozenset({"q", "p", "ap", "l", "z", "b", "a"})

ENUMS: dict[str, frozenset[str]] = {
    "S": frozenset({"BUY", "SELL"}),
    "o": frozenset({"LIMIT", "MARKET", "STOP", "TAKE_PROFIT", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET", "LIQUIDATION"}),
    "ot": frozenset({"LIMIT", "MARKET", "STOP", "TAKE_PROFIT", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET", "LIQUIDATION"}),
    "f": frozenset({"GTC", "IOC", "FOK", "GTX"}),
    "X": frozenset({"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}),
    "ps": frozenset({"BOTH", "LONG", "SHORT"}),
    "wt": frozenset({"MARK_PRICE", "CONTRACT_PRICE"}),
}

_INTEGER_RE = re.compile(r"^[0-9]+$")
_STREAM_RE = re.compile(r"^(?:!forceorder@arr|[a-z0-9_]+@forceorder)$", re.IGNORECASE)
_ALLOWED_ST = {"1": "UM", "UM": "UM", "USD-M": "UM", "USDⓈ-M": "UM"}


class ForceOrderIdentityError(ValueError):
    """Raised when an envelope is not admissible under the frozen contract."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class EndpointCounts:
    """Per-hypothesis accounting over the transport-valid endpoint universe."""

    raw_endpoint_count: int
    unique_endpoint_count: int
    duplicate_endpoint_count: int
    collision_endpoint_count: int
    invalid_endpoint_count: int

    @property
    def invariant_ok(self) -> bool:
        return self.raw_endpoint_count == (
            self.unique_endpoint_count
            + self.duplicate_endpoint_count
            + self.collision_endpoint_count
            + self.invalid_endpoint_count
        )


@dataclass(frozen=True)
class ValidatedForceOrder:
    """Canonical metadata retained for one admissible input envelope."""

    identity_key: str
    identity_tuple: tuple[Any, ...]
    identity_json: str
    canonical_payload_json: str
    canonical_payload_sha256: str
    raw_payload_sha256: str
    source_available_time: datetime | None
    collector_receipt_time: datetime | None
    continuity_state: str
    executable_open: datetime | None
    h03_status: str
    h04_status: str


@dataclass(frozen=True)
class DeduplicationReceipt:
    """Deterministic global and H03/H04 identity accounting."""

    raw_envelope_count: int
    unique_event_count: int
    duplicate_envelope_count: int
    collision_envelope_count: int
    invalid_envelope_count: int
    h03: EndpointCounts
    h04: EndpointCounts
    representatives: tuple[ValidatedForceOrder, ...]
    invalid_reasons: tuple[str, ...]

    @property
    def invariant_ok(self) -> bool:
        global_ok = self.raw_envelope_count == (
            self.unique_event_count
            + self.duplicate_envelope_count
            + self.collision_envelope_count
            + self.invalid_envelope_count
        )
        return global_ok and self.h03.invariant_ok and self.h04.invariant_ok

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe metadata without payload or market values."""

        def endpoint(value: EndpointCounts) -> dict[str, int | bool]:
            return {
                "raw_endpoint_count": value.raw_endpoint_count,
                "unique_endpoint_count": value.unique_endpoint_count,
                "duplicate_endpoint_count": value.duplicate_endpoint_count,
                "collision_endpoint_count": value.collision_endpoint_count,
                "invalid_endpoint_count": value.invalid_endpoint_count,
                "invariant_ok": value.invariant_ok,
            }

        return {
            "raw_envelope_count": self.raw_envelope_count,
            "unique_event_count": self.unique_event_count,
            "duplicate_envelope_count": self.duplicate_envelope_count,
            "collision_envelope_count": self.collision_envelope_count,
            "invalid_envelope_count": self.invalid_envelope_count,
            "h03": endpoint(self.h03),
            "h04": endpoint(self.h04),
            "invariant_ok": self.invariant_ok,
            "invalid_reasons": list(self.invalid_reasons),
        }


def _fail(reason: str) -> None:
    raise ForceOrderIdentityError(reason)


def _canonical_symbol(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail(f"{field}_NOT_STRING")
    result = value.strip().upper()
    if not result:
        _fail(f"{field}_EMPTY")
    return result


def _canonical_market_type(value: Any) -> str:
    if not isinstance(value, str) or value.strip().casefold() != "um":
        _fail("MARKET_TYPE_NOT_UM")
    return "um"


def _canonical_enum(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        _fail(f"{field}_ENUM_INVALID")
    result = value.strip().upper()
    allowed = ENUMS.get(field)
    if allowed is None or result not in allowed:
        _fail(f"{field}_ENUM_INVALID")
    return result


def _canonical_st(value: Any, *, optional: bool = True) -> str | None:
    if value is None and optional:
        return None
    if isinstance(value, bool):
        _fail("ST_INVALID")
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        _fail("ST_INVALID")
    token = value.strip().upper()
    if token not in _ALLOWED_ST:
        _fail("ST_INVALID")
    return "UM"


def _canonical_integer(value: Any, field: str, *, max_value: int = MAX_INT_MS) -> int:
    if isinstance(value, bool):
        _fail(f"{field}_INTEGER_INVALID")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        text = value.strip()
        if not _INTEGER_RE.fullmatch(text):
            _fail(f"{field}_INTEGER_INVALID")
        result = int(text, 10)
    else:
        _fail(f"{field}_INTEGER_INVALID")
    if result < 0 or result > max_value:
        _fail(f"{field}_INTEGER_INVALID")
    return result


def _canonical_trade_id(value: Any) -> str | None:
    if value is None:
        return None
    return str(_canonical_integer(value, "T_ID"))


def _canonical_decimal(value: Any, field: str) -> str:
    if isinstance(value, bool) or value is None:
        _fail(f"{field}_DECIMAL_INVALID")
    if isinstance(value, Decimal):
        source = value
    elif isinstance(value, (int, str)):
        source = str(value).strip() if isinstance(value, str) else Decimal(value)
    else:
        _fail(f"{field}_DECIMAL_INVALID")
    try:
        number = source if isinstance(source, Decimal) else Decimal(source)
    except (InvalidOperation, ValueError):
        _fail(f"{field}_DECIMAL_INVALID")
    if not number.is_finite() or number < 0:
        _fail(f"{field}_DECIMAL_INVALID")
    if number.is_zero():
        return "0"
    try:
        rendered = format(number, "f")
    except (ValueError, OverflowError):
        _fail(f"{field}_DECIMAL_INVALID")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _parse_timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            _fail(f"{field}_TIMESTAMP_INVALID")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            _fail(f"{field}_TIMESTAMP_INVALID")
    else:
        _fail(f"{field}_TIMESTAMP_INVALID")
    if parsed.tzinfo is None:
        _fail(f"{field}_TIMESTAMP_INVALID")
    return parsed.astimezone(UTC)


def _validate_endpoint(endpoint: Any, stream: Any) -> None:
    if not isinstance(endpoint, str) or not isinstance(stream, str) or stream.strip().casefold() != "liquidation":
        _fail("ENDPOINT_STREAM_INVALID")
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        _fail("ENDPOINT_INVALID")
    if parsed.scheme.casefold() != "wss" or parsed.hostname != "fstream.binance.com" or parsed.port is not None or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        _fail("ENDPOINT_INVALID")
    if not parsed.path.startswith("/market/ws/"):
        _fail("ENDPOINT_INVALID")
    stream_token = parsed.path[len("/market/ws/") :]
    if not _STREAM_RE.fullmatch(stream_token):
        _fail("ENDPOINT_INVALID")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        _fail("JSON_CANONICALIZATION_INVALID")
    raise AssertionError("unreachable")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized_payload(payload: Mapping[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if set(payload) - PAYLOAD_TOP_LEVEL_ALLOWED or not PAYLOAD_TOP_LEVEL_REQUIRED.issubset(payload):
        _fail("PAYLOAD_SCHEMA_INVALID")
    if payload.get("e") != "forceOrder":
        _fail("EVENT_TYPE_INVALID")
    event_ms = _canonical_integer(payload["E"], "E")
    order = payload.get("o")
    if not isinstance(order, Mapping) or set(order) - ORDER_ALLOWED or not ORDER_REQUIRED.issubset(order):
        _fail("ORDER_SCHEMA_INVALID")
    event_symbol = _canonical_symbol(order["s"], "ORDER_SYMBOL")
    forced_side = _canonical_enum(order["S"], "S")
    order_type = _canonical_enum(order["o"], "o")
    time_in_force = _canonical_enum(order["f"], "f")
    status = _canonical_enum(order["X"], "X")
    position_side = _canonical_enum(order.get("ps"), "ps", optional=True)
    working_type = _canonical_enum(order.get("wt"), "wt", optional=True)
    original_type = _canonical_enum(order.get("ot"), "ot", optional=True)
    trade_id = _canonical_trade_id(order.get("t"))
    subtype_top = _canonical_st(payload.get("st"))
    subtype_nested = _canonical_st(order.get("st"))
    if subtype_top is not None and subtype_nested is not None and subtype_top != subtype_nested:
        _fail("ST_CONFLICT")
    subtype = subtype_top or subtype_nested
    normalized_order: dict[str, Any] = {
        "s": event_symbol,
        "S": forced_side,
        "o": order_type,
        "f": time_in_force,
        "q": _canonical_decimal(order["q"], "q"),
        "p": _canonical_decimal(order["p"], "p"),
        "ap": _canonical_decimal(order["ap"], "ap"),
        "X": status,
        "l": _canonical_decimal(order["l"], "l"),
        "z": _canonical_decimal(order["z"], "z"),
        "T": _canonical_integer(order["T"], "T"),
        "t": trade_id,
        "ps": position_side,
        "st": subtype,
        "b": _canonical_decimal(order.get("b"), "b") if order.get("b") is not None else None,
        "a": _canonical_decimal(order.get("a"), "a") if order.get("a") is not None else None,
        "m": order.get("m") if order.get("m") is not None else None,
        "wt": working_type,
        "ot": original_type,
    }
    if normalized_order["m"] is not None and not isinstance(normalized_order["m"], bool):
        _fail("m_BOOLEAN_INVALID")
    normalized_payload: dict[str, Any] = {"e": "forceOrder", "E": event_ms, "o": normalized_order, "st": subtype}
    identity_tuple = (
        "um",
        event_symbol,
        event_ms,
        normalized_order["T"],
        trade_id,
        forced_side,
        order_type,
        time_in_force,
        normalized_order["q"],
        normalized_order["p"],
        normalized_order["ap"],
        status,
        normalized_order["l"],
        normalized_order["z"],
        position_side,
        subtype,
    )
    return identity_tuple, normalized_payload


def _next_grid_open(event_time: datetime, source_available: datetime) -> datetime:
    boundary = max(event_time, source_available)
    elapsed = boundary - UTC_GRID_EPOCH
    steps = elapsed // GRID_STEP + 1
    candidate = UTC_GRID_EPOCH + steps * GRID_STEP
    while candidate <= event_time or candidate <= source_available:
        candidate += GRID_STEP
    return candidate


def _endpoint_status(executable_open: datetime | None, continuity_state: str, complete_bar_opens: set[datetime], *, delayed: bool) -> str:
    if executable_open is None:
        return "endpoint_invalid"
    if continuity_state != "COMPLETE":
        return "endpoint_invalid"
    if delayed:
        required = {executable_open + GRID_STEP * offset for offset in (0, 1, 2, 3)}
    else:
        required = {executable_open}
    return "endpoint_eligible" if required.issubset(complete_bar_opens) else "endpoint_invalid"


def validate_forceorder_envelope(envelope: Mapping[str, Any], *, complete_bar_opens: Iterable[datetime] = ()) -> ValidatedForceOrder:
    """Validate and canonicalize one constructed UM forceOrder envelope."""

    if not isinstance(envelope, Mapping):
        _fail("ENVELOPE_NOT_MAPPING")
    _validate_endpoint(envelope.get("endpoint"), envelope.get("stream"))
    market_type = _canonical_market_type(envelope.get("market_type"))
    envelope_symbol = _canonical_symbol(envelope.get("symbol"), "ENVELOPE_SYMBOL")
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        _fail("PAYLOAD_NOT_MAPPING")
    identity_tuple, normalized_payload = _normalized_payload(payload)
    if identity_tuple[0] != market_type or envelope_symbol != identity_tuple[1]:
        _fail("SYMBOL_OR_MARKET_MISMATCH")

    collector = None
    if envelope.get("collector_receipt_time") is not None:
        collector = _parse_timestamp(envelope["collector_receipt_time"], "COLLECTOR_RECEIPT")
    corrected = None
    if envelope.get("corrected_response_receipt_time") is not None:
        corrected = _parse_timestamp(envelope["corrected_response_receipt_time"], "CORRECTED_RECEIPT")
    source_available = corrected or collector
    event_time = UTC_GRID_EPOCH + timedelta(milliseconds=identity_tuple[2])
    executable = _next_grid_open(event_time, source_available) if source_available is not None else None
    state = str(envelope.get("continuity_state") or "COMPLETE").strip().upper()
    if state not in {"COMPLETE", "RESTART_GAP", "POLL_GAP", "SOURCE_TIME_UNAVAILABLE", "SEQUENCE_GAP", "SCHEMA_ERROR", "RATE_LIMIT_GAP", "CLOCK_UNCERTAINTY_GAP"}:
        _fail("CONTINUITY_STATE_INVALID")
    complete = {_parse_timestamp(value, "BAR_OPEN") for value in complete_bar_opens}
    identity_json = _canonical_json({"identity_tuple": list(identity_tuple)})
    canonical_payload_json = _canonical_json(normalized_payload)
    raw_payload_json = _canonical_json(payload)
    return ValidatedForceOrder(
        identity_key=f"forceorder:v2:{_sha256_text(identity_json)}",
        identity_tuple=identity_tuple,
        identity_json=identity_json,
        canonical_payload_json=canonical_payload_json,
        canonical_payload_sha256=_sha256_text(canonical_payload_json),
        raw_payload_sha256=_sha256_text(raw_payload_json),
        source_available_time=source_available,
        collector_receipt_time=collector,
        continuity_state=state,
        executable_open=executable,
        h03_status=_endpoint_status(executable, state, complete, delayed=False),
        h04_status=_endpoint_status(executable, state, complete, delayed=True),
    )


def forceorder_identity_key(envelope: Mapping[str, Any]) -> str:
    """Return the replay-safe key, raising on any contract violation."""

    return validate_forceorder_envelope(envelope).identity_key


def _representative(group: Sequence[ValidatedForceOrder]) -> ValidatedForceOrder:
    def sort_key(record: ValidatedForceOrder) -> tuple[Any, ...]:
        complete_rank = 0 if record.continuity_state == "COMPLETE" and record.source_available_time is not None else 1
        source_rank = record.source_available_time or datetime.max.replace(tzinfo=UTC)
        receipt_rank = record.collector_receipt_time or datetime.max.replace(tzinfo=UTC)
        return (complete_rank, source_rank, receipt_rank, record.canonical_payload_sha256, record.raw_payload_sha256)

    return min(group, key=sort_key)


def deduplicate_forceorders(envelopes: Iterable[Mapping[str, Any]], *, complete_bar_opens: Iterable[datetime] = ()) -> DeduplicationReceipt:
    """Validate, classify, and deterministically deduplicate constructed events."""

    raw = list(envelopes)
    complete = tuple(complete_bar_opens)
    valid: list[ValidatedForceOrder] = []
    invalid_reasons: list[str] = []
    for envelope in raw:
        try:
            valid.append(validate_forceorder_envelope(envelope, complete_bar_opens=complete))
        except ForceOrderIdentityError as exc:
            invalid_reasons.append(exc.reason)

    groups: dict[str, list[ValidatedForceOrder]] = {}
    for record in valid:
        groups.setdefault(record.identity_key, []).append(record)
    unique = duplicates = collisions = 0
    representatives: list[ValidatedForceOrder] = []
    h03 = [0, 0, 0, 0, 0]  # raw, unique, duplicate, collision, invalid
    h04 = [0, 0, 0, 0, 0]
    for key in sorted(groups):
        group = groups[key]
        tuple_set = {record.identity_json for record in group}
        payload_set = {record.canonical_payload_sha256 for record in group}
        is_collision = len(tuple_set) > 1 or len(payload_set) > 1
        representative = _representative(group)
        if is_collision:
            collisions += len(group)
        else:
            unique += 1
            duplicates += len(group) - 1
            representatives.append(representative)
        for index, record in enumerate(group):
            for statuses, counts in ((record.h03_status, h03), (record.h04_status, h04)):
                counts[0] += 1
                if is_collision:
                    counts[3] += 1
                elif statuses == "endpoint_eligible" and record is representative:
                    counts[1] += 1
                elif statuses == "endpoint_eligible":
                    counts[2] += 1
                else:
                    counts[4] += 1
    receipt = DeduplicationReceipt(
        raw_envelope_count=len(raw),
        unique_event_count=unique,
        duplicate_envelope_count=duplicates,
        collision_envelope_count=collisions,
        invalid_envelope_count=len(invalid_reasons),
        h03=EndpointCounts(*h03),
        h04=EndpointCounts(*h04),
        representatives=tuple(representatives),
        invalid_reasons=tuple(sorted(invalid_reasons)),
    )
    if not receipt.invariant_ok:
        raise AssertionError("forceOrder accounting invariant violated")
    return receipt


__all__ = [
    "DeduplicationReceipt",
    "EndpointCounts",
    "ForceOrderIdentityError",
    "ValidatedForceOrder",
    "deduplicate_forceorders",
    "forceorder_identity_key",
    "validate_forceorder_envelope",
]
