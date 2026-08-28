"""Outcome-blind causal materialization for R3 forward event envelopes."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC
from typing import Any, Iterable

import pandas as pd

GAP_STATES = frozenset({"COMPLETE", "RESTART_GAP", "POLL_GAP", "SOURCE_TIME_UNAVAILABLE", "SEQUENCE_GAP", "SCHEMA_ERROR", "RATE_LIMIT_GAP"})


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        return pd.Timestamp(value, tz="UTC")
    except (TypeError, ValueError):
        return None


def _identity(record: dict[str, Any]) -> str:
    payload = json.dumps(record.get("payload"), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{record.get('stream')}|{record.get('symbol')}|{record.get('sequence_id')}|{payload}".encode()).hexdigest()


def materialize_causal_observations(
    envelopes: Iterable[dict[str, Any]],
    decision_times: Iterable[Any],
    *,
    value_key: str = "value",
) -> pd.DataFrame:
    """Attach only observations known strictly before each decision time.

    Raw envelopes are copied, never rewritten. Duplicate identities are
    dropped deterministically. Out-of-order timestamps and explicit gap states
    begin a new continuity segment; invalid/missing source timing is retained
    as a row but cannot supply a feature value.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    segment = 0
    last_event: pd.Timestamp | None = None
    for raw in envelopes:
        record = dict(raw)
        identity = str(record.get("source_identity") or _identity(record))
        if identity in seen:
            continue
        seen.add(identity)
        event_time = _timestamp(record.get("exchange_event_time"))
        receipt_time = _timestamp(record.get("collector_receipt_time"))
        state = str(record.get("continuity_state") or "COMPLETE")
        if state not in GAP_STATES:
            state = "SCHEMA_ERROR"
        if last_event is not None and event_time is not None and event_time < last_event:
            state = "SEQUENCE_GAP"
        if state != "COMPLETE":
            segment += 1
        if event_time is not None:
            last_event = event_time
        rows.append({
            "source_event_time": event_time,
            "source_receipt_time": receipt_time,
            "availability_time": receipt_time,
            "feature_value": record.get(value_key) if state == "COMPLETE" and event_time is not None else None,
            "source_identity": identity,
            "continuity_segment": segment,
            "data_quality_state": state if event_time is not None or state != "COMPLETE" else "SOURCE_TIME_UNAVAILABLE",
        })
    source = pd.DataFrame(rows, columns=["source_event_time", "source_receipt_time", "availability_time", "feature_value", "source_identity", "continuity_segment", "data_quality_state"])
    if source.empty:
        return pd.DataFrame(columns=["source_event_time", "source_receipt_time", "availability_time", "decision_time", "feature_value", "source_identity", "continuity_segment", "data_quality_state"])
    source = source.sort_values(["availability_time", "source_identity"], na_position="last").reset_index(drop=True)
    decisions = sorted({_timestamp(value) for value in decision_times if _timestamp(value) is not None})
    output: list[dict[str, Any]] = []
    for decision in decisions:
        eligible = source[(source["availability_time"].notna()) & (source["availability_time"] < decision)]
        if eligible.empty:
            continue
        selected = eligible.iloc[-1]
        output.append({"source_event_time": selected.source_event_time, "source_receipt_time": selected.source_receipt_time, "availability_time": selected.availability_time, "decision_time": decision, "feature_value": selected.feature_value, "source_identity": selected.source_identity, "continuity_segment": int(selected.continuity_segment), "data_quality_state": selected.data_quality_state})
    return pd.DataFrame(output, columns=["source_event_time", "source_receipt_time", "availability_time", "decision_time", "feature_value", "source_identity", "continuity_segment", "data_quality_state"])


def reject_nonfinite(value: Any) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite feature value")
    return parsed
