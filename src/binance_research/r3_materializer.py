"""Outcome-blind causal materialization for R3 forward event envelopes."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC
from typing import Any, Iterable

import pandas as pd

FORCEORDER_V3_COLUMNS = (
    "identity_key", "market_type", "event_symbol", "pair_symbol", "subtype",
    "event_time_ms", "order_trade_time_ms", "trade_id", "forced_side",
    "position_side", "source_event_time_ms", "source_available_time",
    "executable_open", "continuity_state", "h03_status", "h04_status",
    "signed_observed_notional", "raw_payload_sha256", "canonical_payload_sha256",
    "identity_tuple_sha256", "causal_eligibility", "v3_status", "v3_invalid_reason",
)

GAP_STATES = frozenset({"COMPLETE", "RESTART_GAP", "POLL_GAP", "SOURCE_TIME_UNAVAILABLE", "SEQUENCE_GAP", "SCHEMA_ERROR", "RATE_LIMIT_GAP", "CLOCK_UNCERTAINTY_GAP"})


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        return pd.Timestamp(value, tz="UTC")
    except (TypeError, ValueError):
        return None


def _identity(record: dict[str, Any]) -> str:
    payload = json.dumps(record.get("payload"), sort_keys=True, separators=(",", ":"), default=str)
    value = json.dumps(record.get("value"), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{record.get('market_type', record.get('market'))}|{record.get('stream')}|{record.get('symbol')}|{record.get('sequence_id')}|{record.get('exchange_event_time')}|{record.get('collector_receipt_time')}|{payload}|{value}".encode()).hexdigest()


def materialize_causal_observations(
    envelopes: Iterable[dict[str, Any]],
    decision_times: Iterable[Any],
    *,
    value_key: str = "value",
    evidence_mode: str | None = None,
) -> pd.DataFrame:
    """Attach only observations known strictly before each decision time.

    Raw envelopes are copied, never rewritten. Duplicate identities are
    dropped deterministically. Out-of-order timestamps and explicit gap states
    begin a new continuity segment; invalid/missing source timing is retained
    as a row but cannot supply a feature value.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    segments: dict[tuple[str, str, str], int] = {}
    last_events: dict[tuple[str, str, str], pd.Timestamp] = {}
    for raw in envelopes:
        record = dict(raw)
        if evidence_mode == "SCIENTIFIC" and record.get("evidence_mode") != "SCIENTIFIC":
            raise ValueError("scientific materialization requires SCIENTIFIC evidence_mode")
        if evidence_mode is None and record.get("evidence_mode") in {"ENGINEERING_PILOT", "ENGINEERING_SHADOW"}:
            pass
        identity = str(record.get("source_identity") or _identity(record))
        if identity in seen:
            continue
        seen.add(identity)
        event_time = _timestamp(record.get("exchange_event_time"))
        receipt_time = _timestamp(record.get("collector_receipt_time"))
        corrected_receipt = _timestamp(record.get("corrected_response_receipt_time"))
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        payload_available = _timestamp(payload.get("source_available_time"))
        availability = payload_available or corrected_receipt or receipt_time
        value = payload.get(value_key) if value_key in payload else record.get(value_key)
        key = (str(record.get("market_type", record.get("market", "unknown"))), str(record.get("symbol", "")), str(record.get("stream", "")))
        segments.setdefault(key, 0)
        state = str(record.get("continuity_state") or "COMPLETE")
        if state not in GAP_STATES:
            state = "SCHEMA_ERROR"
        if key in last_events and event_time is not None and event_time < last_events[key]:
            state = "SEQUENCE_GAP"
        if state != "COMPLETE":
            segments[key] += 1
        if event_time is not None:
            last_events[key] = event_time
        rows.append({
            "market": key[0], "symbol": key[1], "stream": key[2],
            "source_event_time": event_time,
            "source_receipt_time": receipt_time,
            "availability_time": availability,
            "feature_value": value if state == "COMPLETE" and event_time is not None else None,
            "source_identity": identity,
            "continuity_segment": segments[key],
            "data_quality_state": state if event_time is not None or state != "COMPLETE" else "SOURCE_TIME_UNAVAILABLE",
        })
    source = pd.DataFrame(rows, columns=["market", "symbol", "stream", "source_event_time", "source_receipt_time", "availability_time", "feature_value", "source_identity", "continuity_segment", "data_quality_state"])
    if source.empty:
        return pd.DataFrame(columns=["market", "symbol", "stream", "source_event_time", "source_receipt_time", "availability_time", "decision_time", "feature_value", "source_identity", "continuity_segment", "data_quality_state"])
    source = source.sort_values(["market", "symbol", "stream", "availability_time", "source_identity"], na_position="last").reset_index(drop=True)
    decisions = sorted({_timestamp(value) for value in decision_times if _timestamp(value) is not None})
    output: list[dict[str, Any]] = []
    for decision in decisions:
        eligible = source[(source["availability_time"].notna()) & (source["availability_time"] < decision)]
        if eligible.empty:
            continue
        for key, group in eligible.groupby(["market", "symbol", "stream"], sort=True):
            selected = group.iloc[-1]
            output.append({"market": key[0], "symbol": key[1], "stream": key[2], "source_event_time": selected.source_event_time, "source_receipt_time": selected.source_receipt_time, "availability_time": selected.availability_time, "decision_time": decision, "feature_value": selected.feature_value, "source_identity": selected.source_identity, "continuity_segment": int(selected.continuity_segment), "data_quality_state": selected.data_quality_state})
    return pd.DataFrame(output, columns=["market", "symbol", "stream", "source_event_time", "source_receipt_time", "availability_time", "decision_time", "feature_value", "source_identity", "continuity_segment", "data_quality_state"])


def reject_nonfinite(value: Any) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite feature value")
    return parsed


def materialize_forceorder_v3_metadata(
    envelopes: Iterable[dict[str, Any]], *,
    complete_bar_opens: Iterable[Any] = (),
) -> pd.DataFrame:
    """Normalize constructed ForceOrder V3 envelopes without outcome fields.

    This adapter is intentionally independent of forward-return materializers:
    it emits identity, timing, continuity, and signed-pressure metadata only.
    Invalid envelopes remain visible with their deterministic reason.
    """
    from decimal import Decimal
    from ops.r3.r3_forceorder_identity_v3 import (
        ForceOrderIdentityV3Error,
        validate_forceorder_envelope_v3,
    )

    rows: list[dict[str, Any]] = []
    complete = tuple(complete_bar_opens)
    for envelope in envelopes:
        try:
            record = validate_forceorder_envelope_v3(envelope, complete_bar_opens=complete)
        except ForceOrderIdentityV3Error as exc:
            invalid = {column: None for column in FORCEORDER_V3_COLUMNS}
            invalid.update({"causal_eligibility": "INELIGIBLE_SCHEMA", "v3_status": "INVALID", "v3_invalid_reason": exc.reason})
            rows.append(invalid)
            continue
        identity = record.identity_tuple
        base = Decimal(identity[14]) * Decimal(identity[12] or identity[11])
        signed = base if identity[7] == "SELL" else -base
        rows.append({
            "identity_key": record.identity_key,
            "market_type": record.market_type,
            "event_symbol": record.event_symbol,
            "pair_symbol": record.pair_symbol,
            "subtype": record.subtype,
            "event_time_ms": record.identity_tuple[4],
            "order_trade_time_ms": record.identity_tuple[5],
            "trade_id": record.identity_tuple[6],
            "forced_side": record.identity_tuple[7],
            "position_side": None,
            "source_event_time_ms": record.identity_tuple[4],
            "source_available_time": record.source_available_time,
            "executable_open": record.executable_open,
            "continuity_state": record.continuity_state,
            "h03_status": record.h03_status,
            "h04_status": record.h04_status,
            "signed_observed_notional": format(signed, "f"),
            "raw_payload_sha256": record.raw_payload_sha256,
            "canonical_payload_sha256": record.canonical_payload_sha256,
            "identity_tuple_sha256": hashlib.sha256(record.identity_json.encode("utf-8")).hexdigest(),
            "causal_eligibility": (
                "ELIGIBLE"
                if record.source_available_time is not None
                and record.executable_open is not None
                and record.source_available_time < record.executable_open
                else "INELIGIBLE_SOURCE_TIME"
            ),
            "v3_status": "VALID",
            "v3_invalid_reason": None,
        })
    return pd.DataFrame(rows, columns=FORCEORDER_V3_COLUMNS)
