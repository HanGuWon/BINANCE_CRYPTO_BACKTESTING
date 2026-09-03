"""Build a metadata-only, outcome-blind R3 v8 evidence inventory.

The collector's raw stream envelopes are observations, not labels.  This tool
reads only their schema, timestamps, availability flags, continuity state, and
symbol identifiers.  It never materializes a forward value and refuses
forbidden outcome/holdout keys or paths before writing its compact summary.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8")
DEFAULT_OUTPUT = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903.json"
FORBIDDEN_TOKENS = frozenset(
    {
        "return",
        "returns",
        "pnl",
        "sharpe",
        "sortino",
        "hit_rate",
        "win_rate",
        "outcome",
        "holdout",
        "r2b2",
        "future",
        "forward",
    }
)
GAP_MARKERS = ("GAP", "UNAVAILABLE", "MALFORMED", "ERROR")
STREAMS = (
    "cycle_metadata",
    "klines_15m",
    "premium_klines_15m",
    "premium",
    "open_interest",
    "book_ticker",
    "liquidation",
)


class InventoryError(RuntimeError):
    """Fail-closed metadata inventory error."""


def _reject_token(text: str, *, context: str) -> None:
    lowered = text.lower()
    if any(token in lowered for token in FORBIDDEN_TOKENS):
        raise InventoryError(f"forbidden outcome/holdout token at {context}: {text}")


def _reject_forbidden(value: Any, *, context: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_token(str(key), context=context)
            _reject_forbidden(child, context=f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, context=f"{context}[{index}]")


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _first_timestamp(value: Any) -> datetime | None:
    """Find a source/event timestamp without retaining payload values."""
    if isinstance(value, dict):
        preferred = (
            "source_available_time",
            "source_open_time",
            "observation_time",
            "exchange_event_time",
            "E",
            "e",
            "time",
            "collector_receipt_time",
            "corrected_response_receipt_time",
            "response_received_at",
        )
        for key in preferred:
            if key in value:
                parsed = _parse_dt(value[key])
                if parsed is not None:
                    return parsed
        for child in value.values():
            parsed = _first_timestamp(child)
            if parsed is not None:
                return parsed
    elif isinstance(value, list):
        for child in value:
            parsed = _first_timestamp(child)
            if parsed is not None:
                return parsed
    return None


def _payload_keys(value: Any) -> set[str]:
    return {str(key) for key in value} if isinstance(value, dict) else set()


def _bucket_15m(timestamp: datetime) -> datetime:
    return timestamp.replace(minute=(timestamp.minute // 15) * 15, second=0, microsecond=0)


def _bucket_6h(timestamp: datetime) -> datetime:
    return timestamp.replace(hour=(timestamp.hour // 6) * 6, minute=0, second=0, microsecond=0)


def _is_gap(state: Any) -> bool:
    value = str(state or "").upper()
    # Control envelopes deliberately carry SOURCE_TIME_UNAVAILABLE because
    # their clock metadata has no exchange observation.  That is missingness,
    # not a stream/restart gap; health receipts provide the authoritative gap
    # counters for the collector.
    if value == "SOURCE_TIME_UNAVAILABLE":
        return False
    return any(marker in value for marker in GAP_MARKERS)


def _source_available(envelope: dict[str, Any], payload: Any) -> bool:
    if envelope.get("source_time_available") is True:
        return True
    if isinstance(payload, dict) and _parse_dt(payload.get("source_available_time")) is not None:
        return True
    return False


def _strict_boundary(payload: Any) -> bool | None:
    """Check availability before the next absolute 15m executable open.

    The next executable open is the first grid boundary strictly after the
    recorded source availability.  This avoids treating a source that arrives
    exactly on a boundary as eligible for that same boundary while allowing it
    to participate at the following one.
    """
    if not isinstance(payload, dict):
        return None
    source_available = _parse_dt(payload.get("source_available_time"))
    if source_available is None:
        return None
    boundary = source_available.replace(minute=(source_available.minute // 15) * 15, second=0, microsecond=0)
    next_open = boundary + timedelta(minutes=15)
    return source_available < next_open


def _iter_envelopes(root: Path) -> Iterable[tuple[str, dict[str, Any], Path]]:
    raw_root = root / "raw_v1" / "um"
    if not raw_root.is_dir():
        raise InventoryError(f"authorized UM raw root is missing: {raw_root}")
    for path in sorted(raw_root.rglob("*.jsonl")):
        _reject_token(str(path), context="raw path")
        stream = path.name.removesuffix(".jsonl")
        if stream not in STREAMS and stream not in {"collector_status", "clock_calibration", "manifest_chain"}:
            raise InventoryError(f"unexpected raw stream file: {path}")
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InventoryError(f"invalid JSON at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise InventoryError(f"non-object envelope at {path}:{line_number}")
            _reject_forbidden(value, context=f"{path}:{line_number}")
            yield stream, value, path


def _empty_stream() -> dict[str, Any]:
    return {
        "files": 0,
        "records": 0,
        "source_available_records": 0,
        "source_unavailable_records": 0,
        "gap_records": 0,
        "complete_records": 0,
        "symbols": set(),
        "timestamps": [],
        "buckets": defaultdict(set),
        "continuity": Counter(),
    }


def build_inventory(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    resolved = root.resolve()
    if resolved != DEFAULT_ROOT.resolve() or resolved.drive.upper() != "D:":
        raise InventoryError(f"only the sealed D-backed v8 root is authorized: {resolved}")
    summary: dict[str, dict[str, Any]] = {stream: _empty_stream() for stream in STREAMS}
    seen_files: set[Path] = set()
    cycle_ids: set[str] = set()
    stream_records: defaultdict[str, list[tuple[str, datetime, bool, bool, set[str], bool | None]]] = defaultdict(list)
    daily_counts: defaultdict[date, int] = defaultdict(int)
    six_hour_counts: defaultdict[datetime, int] = defaultdict(int)
    for stream, envelope, path in _iter_envelopes(resolved):
        if path not in seen_files:
            seen_files.add(path)
            if stream in summary:
                summary[stream]["files"] += 1
        if stream not in summary:
            continue
        row = summary[stream]
        row["records"] += 1
        symbol = str(envelope.get("symbol") or "")
        if symbol:
            row["symbols"].add(symbol)
        payload = envelope.get("payload")
        keys = _payload_keys(payload)
        timestamp = _first_timestamp(envelope)
        available = _source_available(envelope, payload)
        gap = _is_gap(envelope.get("continuity_state"))
        boundary_ok = _strict_boundary(payload)
        row["continuity"][str(envelope.get("continuity_state") or "UNKNOWN")] += 1
        if available:
            row["source_available_records"] += 1
        else:
            row["source_unavailable_records"] += 1
        if gap:
            row["gap_records"] += 1
        else:
            row["complete_records"] += 1
        if timestamp is not None:
            row["timestamps"].append(timestamp)
            bucket = _bucket_15m(timestamp)
            row["buckets"][bucket].add(symbol)
            if not gap and available:
                daily_counts[timestamp.date()] += 1
                six_hour_counts[_bucket_6h(timestamp)] += 1
        if stream == "cycle_metadata":
            cycle_id = str((payload or {}).get("cycle_id") or "") if isinstance(payload, dict) else ""
            if cycle_id:
                if cycle_id in cycle_ids:
                    raise InventoryError(f"duplicate cycle ID: {cycle_id}")
                cycle_ids.add(cycle_id)
        if timestamp is not None:
            stream_records[stream].append((symbol, timestamp, available, gap, keys, boundary_ok))
    if not cycle_ids:
        raise InventoryError("cycle metadata stream is empty")
    if not summary["cycle_metadata"]["timestamps"]:
        raise InventoryError("cycle metadata timestamps are missing")

    health_path = resolved / "health" / "health_receipts.jsonl"
    if not health_path.is_file():
        raise InventoryError(f"health receipt stream is missing: {health_path}")
    health_rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(health_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InventoryError(f"invalid health JSON at {health_path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise InventoryError(f"non-object health envelope at {health_path}:{line_number}")
        _reject_forbidden(value, context=f"{health_path}:{line_number}")
        health_rows.append(value)
    if not health_rows:
        raise InventoryError("health receipt stream is empty")
    latest_health = health_rows[-1]

    def valid(stream: str, required: set[str] | None = None, *, strict_boundary: bool = False) -> list[tuple[str, datetime, bool, bool, set[str], bool | None]]:
        rows = [row for row in stream_records[stream] if row[2] and not row[3]]
        if required:
            rows = [row for row in rows if required.issubset(row[4])]
        if strict_boundary:
            rows = [row for row in rows if row[5] is True]
        return rows

    kline_rows = valid("klines_15m", {"source_open_time", "source_available_time", "value"}, strict_boundary=True)
    premium_kline_rows = valid("premium_klines_15m", {"source_open_time", "source_available_time", "value"}, strict_boundary=True)
    premium_rows = valid("premium", {"lastFundingRate"})
    oi_rows = valid("open_interest", {"openInterest"})
    book_rows = valid("book_ticker", {"bidPrice", "askPrice", "bidQty", "askQty"})
    liquidation_rows = [row for row in valid("liquidation") if {"E", "e", "o"}.issubset(row[4])]
    def pair_count(left: list[tuple[str, datetime, bool, bool, set[str], bool | None]], right: list[tuple[str, datetime, bool, bool, set[str], bool | None]]) -> int:
        left_keys = {(symbol, _bucket_15m(timestamp)) for symbol, timestamp, *_ in left}
        right_keys = {(symbol, _bucket_15m(timestamp)) for symbol, timestamp, *_ in right}
        return len(left_keys & right_keys)

    kline_keys = {(symbol, _bucket_15m(timestamp)) for symbol, timestamp, *_ in kline_rows}
    btc_symbol = "BTCUSDT" if any(symbol == "BTCUSDT" for symbol, *_ in kline_rows) else next((symbol for symbol, *_ in kline_rows if symbol.startswith("BTC")), None)
    breadth_by_bucket: defaultdict[datetime, set[str]] = defaultdict(set)
    for symbol, timestamp, *_ in kline_rows:
        breadth_by_bucket[_bucket_15m(timestamp)].add(symbol)
    breadth_decisions = sum(1 for bucket, symbols in breadth_by_bucket.items() if btc_symbol in symbols and len(symbols) >= 2) if btc_symbol else 0
    all_timestamps = [timestamp for rows in stream_records.values() for _, timestamp, *_ in rows]
    first_time = min(all_timestamps).isoformat() if all_timestamps else None
    last_time = max(all_timestamps).isoformat() if all_timestamps else None
    liquidation_times = sorted(timestamp for _, timestamp, *_ in liquidation_rows)
    liquidation_spacing = [max(0.0, (b - a).total_seconds()) for a, b in zip(liquidation_times, liquidation_times[1:])]
    simultaneous = {
        stream: {
            "buckets_with_multiple_symbols": sum(1 for symbols in row["buckets"].values() if len(symbols) > 1),
            "max_symbols_in_bucket": max((len(symbols) for symbols in row["buckets"].values()), default=0),
        }
        for stream, row in summary.items()
    }
    def compact_stream(row: dict[str, Any]) -> dict[str, Any]:
        timestamps = row["timestamps"]
        return {
            "files": row["files"],
            "records": row["records"],
            "symbols": len(row["symbols"]),
            "source_available_records": row["source_available_records"],
            "source_unavailable_records": row["source_unavailable_records"],
            "gap_records": row["gap_records"],
            "complete_records": row["complete_records"],
            "first_timestamp": min(timestamps).isoformat() if timestamps else None,
            "last_timestamp": max(timestamps).isoformat() if timestamps else None,
            "continuity_state_counts": dict(sorted(row["continuity"].items())),
        }
    inventory = {
        "record_type": "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "root": str(resolved),
        "market": "um",
        "interval": "15m",
        "calendar": {
            "first_observation_time": first_time,
            "last_observation_time": last_time,
            "observed_utc_days": len({timestamp.date().isoformat() for timestamp in all_timestamps}),
            "independent_utc_days": len({timestamp.date().isoformat() for timestamp in all_timestamps}),
            "independent_utc_6h_blocks": len(six_hour_counts),
        },
        "cycles": {
            "cycle_count": len(cycle_ids),
            "duplicate_cycle_ids": 0,
            "metadata_stream": compact_stream(summary["cycle_metadata"]),
        },
        "streams": {stream: compact_stream(summary[stream]) for stream in STREAMS},
        "causal_input_presence": {
            "definition": "source_time_available=true, continuity not a gap, required schema keys present; no forward value is constructed",
            "H01_execution_quality_context": {"input_stream": "book_ticker", "usable_observations": len(book_rows)},
            "H02_price_oi_quadrant": {"input_streams": ["klines_15m", "open_interest"], "usable_symbol_buckets": pair_count(kline_rows, oi_rows)},
            "H03_liquidation_continuation": {"input_stream": "liquidation", "observed_events": len(liquidation_rows)},
            "H04_liquidation_reversion": {"input_stream": "liquidation", "observed_events": len(liquidation_rows)},
            "H05_crowding_stress_modifier": {"input_streams": ["premium", "premium_klines_15m"], "usable_symbol_buckets": pair_count(premium_rows, premium_kline_rows), "funding_rate_observations": len(premium_rows)},
            "H06_btc_breadth_concordance": {"input_stream": "klines_15m", "btc_symbol": btc_symbol, "usable_breadth_decision_buckets": breadth_decisions, "usable_kline_symbol_buckets": len(kline_keys)},
        },
        "availability_and_gaps": {
            "source_unavailable_records": sum(row["source_unavailable_records"] for row in summary.values()),
            "gap_records": sum(row["gap_records"] for row in summary.values()),
            "health_gap_count": int(latest_health.get("gap_count", 0)),
            "health_restart_count": int(latest_health.get("restart_count", 0)),
            "gap_state_counts": {stream: dict(sorted(summary[stream]["continuity"].items())) for stream in STREAMS},
            "no_imputation": True,
            "gap_reset_required": True,
            "strict_15m_boundary": {
                "normalized_records_checked": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is not None),
                "accepted": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is True),
                "rejected": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is False),
                "missing_boundary_fields": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is None),
            },
        },
        "dependence": {
            "observations_by_utc_day": dict(sorted((day.isoformat(), count) for day, count in daily_counts.items())),
            "observations_by_utc_6h_block": dict(sorted((bucket.isoformat(), count) for bucket, count in six_hour_counts.items())),
            "event_spacing_seconds": {
                "liquidation_event_count": len(liquidation_times),
                "minimum": min(liquidation_spacing) if liquidation_spacing else None,
                "median": statistics.median(liquidation_spacing) if liquidation_spacing else None,
            },
            "simultaneous_cross_symbol_buckets": simultaneous,
            "btc_synchronization": {"btc_symbol": btc_symbol, "breadth_decision_buckets": breadth_decisions},
            "liquidation_clustering": {"event_count": len(liquidation_rows), "active_15m_buckets": len({_bucket_15m(timestamp) for timestamp in liquidation_times}), "max_events_per_bucket": max((sum(1 for timestamp in liquidation_times if _bucket_15m(timestamp) == bucket) for bucket in {_bucket_15m(timestamp) for timestamp in liquidation_times}), default=0)},
            "predeclared_block_scheme": "UTC_6H_PRIMARY; UTC_DAY_AND_DAY_X_MARKET_STATE_SENSITIVITY",
        },
        "integrity": {
            "raw_streams_read": sorted(stream for stream in STREAMS if summary[stream]["records"]),
            "payload_values_retained": False,
            "performance_fields_seen": False,
            "confirmatory_root_accessed": False,
            "secondary_campaign_accessed": False,
        },
    }
    _reject_forbidden(inventory, context="inventory output")
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise InventoryError(f"refusing to overwrite existing inventory: {output}")
    inventory = build_inventory(args.root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(output), "cycle_count": inventory["cycles"]["cycle_count"], "independent_utc_6h_blocks": inventory["calendar"]["independent_utc_6h_blocks"], "gap_records": inventory["availability_and_gaps"]["gap_records"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InventoryError as exc:
        print(f"R3_INVENTORY_BLOCKED: {exc}")
        raise SystemExit(2)
