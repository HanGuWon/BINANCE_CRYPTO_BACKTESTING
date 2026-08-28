"""Outcome-blind normalizers for prospective R3 public stream envelopes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import Any

import pandas as pd

from .data import KLINE_COLUMNS


class StreamSchemaError(ValueError):
    pass


def _row_identity(stream: str, symbol: str, row: Any) -> str:
    encoded = json.dumps([stream, symbol, row], sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: Any) -> pd.Timestamp:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        number = float(value)
        value = pd.to_datetime(number, unit="ms" if abs(number) >= 1e11 else "s", utc=True)
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        raise StreamSchemaError(f"invalid stream timestamp: {value!r}")
    return ts


def normalize_stream_payload(stream: str, symbol: str, payload: Any, *, receipt_time: Any) -> list[dict[str, Any]]:
    """Normalize one response while retaining source-row identity and timing.

    Arrays are never reduced to a single "latest" value.  Klines are accepted
    only after their native close time; the final forming candle is rejected.
    """
    receipt = _timestamp(receipt_time)
    if stream == "klines_15m":
        if not isinstance(payload, list):
            raise StreamSchemaError("klines payload must be an array")
        records: list[dict[str, Any]] = []
        for index, row in enumerate(payload):
            if not isinstance(row, (list, tuple)) or len(row) < len(KLINE_COLUMNS):
                raise StreamSchemaError("malformed kline row")
            close_time = pd.to_datetime(pd.to_numeric(row[6]), unit="ms", utc=True)
            if close_time >= receipt:
                continue
            records.append({"stream": stream, "symbol": symbol, "source_row_index": index,
                            "source_row_identity": _row_identity(stream, symbol, row),
                            "source_open_time": pd.to_datetime(pd.to_numeric(row[0]), unit="ms", utc=True).isoformat(),
                            "source_available_time": close_time.isoformat(),
                            "observation_time": close_time.isoformat(), "value": row[4],
                            "row": list(row)})
        return records
    if isinstance(payload, list):
        records = []
        for index, row in enumerate(payload):
            if not isinstance(row, dict):
                raise StreamSchemaError(f"{stream} array row must be an object")
            observation_value = next((row.get(key) for key in ("time", "timestamp", "T", "E", "createTime") if row.get(key) is not None), None)
            observation = _timestamp(observation_value) if observation_value is not None else None
            records.append({"stream": stream, "symbol": str(row.get("symbol") or symbol),
                            "source_row_index": index, "source_row_identity": _row_identity(stream, symbol, row),
                            "observation_time": observation.isoformat() if observation is not None else None,
                            "source_available_time": receipt.isoformat(), "value": row, "row": row})
        return records
    if not isinstance(payload, dict):
        raise StreamSchemaError(f"{stream} payload must be an object or array")
    observation_value = next((payload.get(key) for key in ("time", "timestamp", "T", "E", "eventTime") if payload.get(key) is not None), None)
    observation = _timestamp(observation_value) if observation_value is not None else None
    return [{"stream": stream, "symbol": symbol, "source_row_index": 0,
             "source_row_identity": _row_identity(stream, symbol, payload),
             "observation_time": observation.isoformat() if observation is not None else None,
             "source_available_time": receipt.isoformat(), "value": payload, "row": payload}]
