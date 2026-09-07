"""Build a metadata-only, outcome-blind R3 v8 evidence inventory.

The collector's raw stream envelopes are observations, not labels.  This tool
reads only their schema, timestamps, availability flags, continuity state, and
symbol identifiers.  It never materializes a forward value and refuses
forbidden outcome/holdout keys or paths before writing its compact summary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from ops.r3.r3_forceorder_identity import (
        ForceOrderIdentityError,
        ValidatedForceOrder,
        deduplicate_forceorders,
        validate_forceorder_envelope,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script invocation
    from r3_forceorder_identity import (  # type: ignore[no-redef]
        ForceOrderIdentityError,
        ValidatedForceOrder,
        deduplicate_forceorders,
        validate_forceorder_envelope,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8")
DEFAULT_OUTPUT = None
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
PRIMARY_HYPOTHESES = ("R3_H01", "R3_H02", "R3_H03", "R3_H04", "R3_H05", "R3_H06")
HYPOTHESIS_SCOPES: dict[str, tuple[str, ...]] = {
    "book_ticker": ("R3_H01",),
    "klines_15m": ("R3_H02", "R3_H06"),
    "open_interest": ("R3_H02",),
    "premium": ("R3_H05",),
    "premium_klines_15m": ("R3_H05",),
    "liquidation": ("R3_H03", "R3_H04"),
}
VALID_GAP_CATEGORIES = frozenset({"MISSING_CYCLE", "RESTART_GAP", "SOURCE_UNAVAILABLE", "ROLLOVER_GAP", "INCOMPLETE_BUCKET"})
PER_H_TEMPORAL_MINIMA = {
    hypothesis: {"usable_blocks": 30, "usable_days": 30, "per_roster_minimum": 1}
    for hypothesis in PRIMARY_HYPOTHESES
}


class InventoryError(RuntimeError):
    """Fail-closed metadata inventory error."""


def _reject_token(text: str, *, context: str) -> None:
    lowered = text.lower()
    if any(token in lowered for token in FORBIDDEN_TOKENS):
        raise InventoryError(f"forbidden outcome/holdout token at {context}: {text}")


_SEMANTIC_VALUE_KEYS = frozenset({"continuity_state", "state", "record_type", "path", "root", "file", "artifact", "uri", "source", "stream", "definition", "reason", "category"})


def _reject_forbidden(value: Any, *, context: str, parent_key: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_token(str(key), context=context)
            _reject_forbidden(child, context=f"{context}.{key}", parent_key=str(key).lower())
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, context=f"{context}[{index}]", parent_key=parent_key)
    elif isinstance(value, str):
        # Scalar strings are part of the firewall too; only the fixed record
        # type marker is allowed to contain the word outcome.
        if parent_key in _SEMANTIC_VALUE_KEYS and value.lower() not in {"r3_outcome_blind_evidence_inventory_v2", "r3_outcome_blind_evidence_inventory"}:
            _reject_token(value, context=context)


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


def _inclusive_6h_blocks(start: datetime, end: datetime | None = None) -> tuple[str, ...]:
    """Expand a closed interval to every UTC six-hour block it touches."""
    if end is None:
        end = start
    if end < start:
        raise InventoryError("gap end precedes gap start")
    cursor = _bucket_6h(start)
    last = _bucket_6h(end)
    blocks: list[str] = []
    while cursor <= last:
        blocks.append(cursor.isoformat())
        cursor += timedelta(hours=6)
    return tuple(blocks)


def _gap_scopes(stream: str, state: str) -> tuple[str, ...]:
    """Return affected hypothesis scopes for one continuity incident."""
    normalized_stream = str(stream or "").strip().lower()
    normalized_state = str(state or "").strip().upper()
    if normalized_state == "UNIVERSE_ROLLOVER_GAP":
        raise InventoryError("legacy gap category UNIVERSE_ROLLOVER_GAP is not accepted; use ROLLOVER_GAP")
    scopes = list(HYPOTHESIS_SCOPES.get(normalized_stream, ()))
    if normalized_stream == "collector_status" or normalized_state in {"RESTART_GAP", "ROLLOVER_GAP"}:
        scopes.append("GLOBAL")
    unknown = sorted(set(scopes) - set(PRIMARY_HYPOTHESES) - {"GLOBAL"})
    if unknown:
        raise InventoryError(f"unknown gap scopes: {unknown}")
    return tuple(dict.fromkeys(scopes))


def _scoped_gap_blocks(records: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """Validate and union explicit gap blocks by hypothesis scope."""
    result: dict[str, set[str]] = defaultdict(set)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise InventoryError(f"gap record {index} is not an object")
        category = str(record.get("category", "")).strip().upper()
        if category == "UNIVERSE_ROLLOVER_GAP" or category not in VALID_GAP_CATEGORIES:
            raise InventoryError(f"gap record {index} has unknown/legacy category")
        start = _parse_dt(record.get("start_time"))
        end = _parse_dt(record.get("end_time")) if record.get("end_time") not in (None, "") else None
        if start is None:
            raise InventoryError(f"gap record {index} has invalid start_time")
        expected = _inclusive_6h_blocks(start, end)
        supplied = record.get("utc_6h_block_ids")
        if not isinstance(supplied, list):
            raise InventoryError(f"gap record {index} must supply utc_6h_block_ids")
        if len(supplied) != len(set(map(str, supplied))):
            raise InventoryError(f"gap record {index} contains duplicate block ids")
        supplied_ids = tuple(map(str, supplied))
        if set(supplied_ids) != set(expected):
            raise InventoryError(f"gap record {index} block ids do not match its closed interval")
        scopes = record.get("scopes")
        if not isinstance(scopes, list) or len(scopes) != len(set(map(str, scopes))):
            raise InventoryError(f"gap record {index} must supply unique scopes")
        normalized_scopes = {str(scope) for scope in scopes}
        if not normalized_scopes or not normalized_scopes.issubset(set(PRIMARY_HYPOTHESES) | {"GLOBAL"}):
            raise InventoryError(f"gap record {index} has unknown/empty scopes")
        for scope in normalized_scopes:
            result[scope].update(expected)
    return {scope: set(blocks) for scope, blocks in sorted(result.items())}


def _membership_sha(symbols: Sequence[str]) -> str:
    canonical = json.dumps(sorted(set(map(str, symbols))), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _used_roster_identities(
    cycles: Sequence[dict[str, Any]],
    verified_rosters: Sequence[dict[str, Any]],
    complete_rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve used verified rosters and enforce symbol-qualified membership."""
    normalized: list[dict[str, Any]] = []
    for index, roster in enumerate(verified_rosters):
        sha = str(roster.get("roster_sha256") or "")
        month = str(roster.get("effective_month") or "")
        symbols = sorted(set(map(str, roster.get("symbols", []))))
        start = _parse_dt(roster.get("effective_start"))
        end = _parse_dt(roster.get("effective_end"))
        if not sha or not month or not symbols or start is None or end is None or end <= start:
            raise InventoryError(f"verified roster {index} lacks an exact interval/membership")
        normalized.append({**roster, "effective_month": month, "roster_sha256": sha, "symbols": symbols, "effective_start": start.isoformat(), "effective_end": end.isoformat(), "_start": start, "_end": end})
    # Different identities may not overlap. Same-month/same-SHA duplicate
    # artifacts are intentionally collapsed later.
    for left_index, left in enumerate(normalized):
        for right in normalized[left_index + 1 :]:
            if left["roster_sha256"] == right["roster_sha256"]:
                continue
            if left["_start"] < right["_end"] and right["_start"] < left["_end"]:
                raise InventoryError("verified roster intervals overlap with different SHAs")
    diagnostics: list[dict[str, Any]] = []
    matched_cycles: defaultdict[str, list[str]] = defaultdict(list)
    for cycle in cycles:
        cycle_id = str(cycle.get("cycle_id") or "")
        cycle_time = _parse_dt(cycle.get("timestamp") or cycle.get("cycle_time"))
        if not cycle_id or cycle_time is None:
            diagnostics.append({"cycle_id": cycle_id, "reason": "CYCLE_ID_OR_TIME_INVALID"})
            continue
        candidates_by_sha = {
            roster["roster_sha256"]: roster
            for roster in normalized
            if roster["_start"] <= cycle_time < roster["_end"]
        }
        declared_sha = str(cycle.get("roster_sha256") or "")
        if declared_sha:
            candidates_by_sha = {sha: roster for sha, roster in candidates_by_sha.items() if sha == declared_sha}
        candidates = list(candidates_by_sha.values())
        if len(candidates) != 1:
            diagnostics.append({"cycle_id": cycle_id, "reason": "ROSTER_INTERVAL_UNMATCHED" if not candidates else "ROSTER_INTERVAL_AMBIGUOUS"})
            continue
        matched_cycles[candidates[0]["roster_sha256"]].append(cycle_id)
    used: list[dict[str, Any]] = []
    for sha, cycle_ids in sorted(matched_cycles.items()):
        roster = next(roster for roster in normalized if roster["roster_sha256"] == sha)
        rows = complete_rows.get(sha, ())
        counts: Counter[str] = Counter()
        for row in rows:
            if not isinstance(row, Mapping):
                raise InventoryError("complete_rows must contain symbol-qualified objects")
            symbol = str(row.get("symbol") or "")
            timestamp = _parse_dt(row.get("timestamp"))
            if not symbol or timestamp is None:
                raise InventoryError("complete source row lacks symbol/timestamp")
            if not (roster["_start"] <= timestamp < roster["_end"]):
                continue
            if symbol not in set(roster["symbols"]):
                raise InventoryError(f"complete source row symbol is outside verified roster membership: {symbol}")
            counts[symbol] += 1
        if not counts:
            diagnostics.append({"roster_sha256": sha, "reason": "NO_COMPLETE_MEMBERSHIP_ROW", "cycle_ids": sorted(cycle_ids)})
            continue
        used.append({
            "effective_month": roster["effective_month"],
            "roster_sha256": sha,
            "membership": {"symbols": roster["symbols"], "symbol_count": len(roster["symbols"]), "membership_sha256": _membership_sha(roster["symbols"])},
            "cycle_ids": sorted(set(cycle_ids)),
            "complete_rows": dict(sorted(counts.items())),
        })
    return used, diagnostics


def _is_gap(state: Any) -> bool:
    value = str(state or "").upper()
    # Control envelopes deliberately carry SOURCE_TIME_UNAVAILABLE because
    # their clock metadata has no exchange observation.  That is missingness,
    # not a stream/restart gap; health receipts provide the authoritative gap
    # counters for the collector.
    if value == "SOURCE_TIME_UNAVAILABLE":
        return False
    if value in {"RESTART", "RESTARTED", "RESTART_GAP", "MISSING", "MISSING_CYCLE"} or "RESTART" in value:
        return True
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
    # Use a recorded executable-open binding when present. Otherwise the next
    # 15m grid boundary strictly after availability is the executable open.
    # Equality is rejected by the strict comparison.
    next_open = _parse_dt(payload.get("next_executable_open_time") or payload.get("eligible_next_execution_time"))
    if next_open is None:
        boundary = source_available.replace(minute=(source_available.minute // 15) * 15, second=0, microsecond=0)
        # Match next_quarter_hour(available - 1 microsecond): an observation
        # arriving exactly at a grid boundary is bound to that open and is
        # rejected by the strict inequality; an observation after the boundary
        # is deferred to the following open.
        next_open = boundary if source_available == boundary else boundary + timedelta(minutes=15)
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
    cycle_metadata_records: list[dict[str, str]] = []
    stream_records: defaultdict[str, list[tuple[str, datetime, bool, bool, set[str], bool | None]]] = defaultdict(list)
    liquidation_envelopes: list[dict[str, Any]] = []
    complete_bar_opens: set[datetime] = set()
    daily_counts: defaultdict[date, int] = defaultdict(int)
    six_hour_counts: defaultdict[datetime, int] = defaultdict(int)
    explicit_gap_records: list[dict[str, Any]] = []
    for stream, envelope, path in _iter_envelopes(resolved):
        if path not in seen_files:
            seen_files.add(path)
            if stream in summary:
                summary[stream]["files"] += 1
        if stream not in summary:
            # Collector control status is retained only when it records a
            # continuity incident; its error payload is never copied.
            status = str(envelope.get("continuity_state") or "").upper()
            status_time = _first_timestamp(envelope)
            if stream == "collector_status" and _is_gap(status) and status_time is None:
                raise InventoryError(f"collector continuity incident has no timestamp: {path}")
            if stream == "collector_status" and status_time is not None and _is_gap(status):
                category = "RESTART_GAP" if "RESTART" in status else "SOURCE_UNAVAILABLE"
                explicit_gap_records.append({"category": category, "stream": stream, "symbol": None, "cycle_id": None, "start_time": status_time.isoformat(), "end_time": None, "utc_6h_block_ids": [_bucket_6h(status_time).isoformat()], "scopes": list(_gap_scopes(stream, category)), "continuity_state": status, "source_time_available": False})
            continue
        row = summary[stream]
        row["records"] += 1
        symbol = str(envelope.get("symbol") or "")
        if symbol:
            row["symbols"].add(symbol)
        payload = envelope.get("payload")
        if stream == "liquidation":
            # Keep the strict envelope fields only long enough to hand them to
            # the replay-safe identity helper; no payload field is emitted.
            liquidation_envelopes.append({
                "market_type": envelope.get("market_type"),
                "symbol": envelope.get("symbol"),
                "stream": envelope.get("stream") or stream,
                "endpoint": envelope.get("endpoint"),
                "payload": payload,
                "collector_receipt_time": envelope.get("collector_receipt_time"),
                "corrected_response_receipt_time": envelope.get("corrected_response_receipt_time"),
                "continuity_state": envelope.get("continuity_state"),
            })
        keys = _payload_keys(payload)
        timestamp = _first_timestamp(envelope)
        available = _source_available(envelope, payload)
        gap = _is_gap(envelope.get("continuity_state"))
        if stream != "cycle_metadata" and (gap or not available) and timestamp is None:
            raise InventoryError(f"continuity/source-unavailable record has no timestamp: {path}")
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
            # Control-cycle envelopes intentionally have no exchange source
            # timestamp. For every actual stream, preserve missing source and
            # restart evidence as compact timestamped records. No payload is
            # retained and no gap is imputed or backfilled.
            if stream in {"klines_15m", "premium_klines_15m"} and not gap and available and boundary_ok is True and isinstance(payload, dict):
                source_open = _parse_dt(payload.get("source_open_time"))
                if source_open is not None:
                    complete_bar_opens.add(source_open)
            if stream != "cycle_metadata":
                state = str(envelope.get("continuity_state") or "").upper()
                category = None
                if "RESTART" in state:
                    category = "RESTART_GAP"
                elif not available:
                    category = "SOURCE_UNAVAILABLE"
                elif _is_gap(state):
                    category = "MISSING_CYCLE"
                if category:
                    end_time = None
                    if isinstance(payload, dict):
                        candidate_end = _parse_dt(payload.get("gap_end_time") or payload.get("continuity_end_time"))
                        if candidate_end is not None and candidate_end >= timestamp:
                            end_time = candidate_end.isoformat()
                    end_dt = _parse_dt(end_time) if end_time else timestamp
                    cursor = _bucket_6h(timestamp)
                    last_block = _bucket_6h(end_dt)
                    block_ids: list[str] = []
                    while cursor <= last_block:
                        block_ids.append(cursor.isoformat())
                        cursor += timedelta(hours=6)
                    explicit_gap_records.append({
                        "category": category,
                        "stream": stream,
                        "symbol": symbol or None,
                        "cycle_id": str((payload or {}).get("cycle_id") or "") if isinstance(payload, dict) else None,
                        "start_time": timestamp.isoformat(),
                        "end_time": end_time,
                        "utc_6h_block_ids": block_ids,
                        "scopes": list(_gap_scopes(stream, category)),
                        "continuity_state": state or None,
                        "source_time_available": bool(available),
                    })
        if stream == "cycle_metadata":
            cycle_id = str((payload or {}).get("cycle_id") or "") if isinstance(payload, dict) else ""
            if cycle_id:
                if cycle_id in cycle_ids:
                    raise InventoryError(f"duplicate cycle ID: {cycle_id}")
                cycle_ids.add(cycle_id)
                if timestamp is None:
                    raise InventoryError(f"cycle metadata timestamp is missing for {cycle_id}")
                cycle_metadata_records.append({"cycle_id": cycle_id, "timestamp": timestamp.isoformat(), "roster_sha256": str((payload or {}).get("roster_sha256") or "") if isinstance(payload, dict) else ""})
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
    previous_gap = 0
    previous_restart = 0
    previous_health_time: datetime | None = None
    for health in health_rows:
        gap_count = int(health.get("gap_count", 0))
        restart_count = int(health.get("restart_count", 0))
        health_time = _parse_dt(health.get("timestamp"))
        if health_time is None:
            raise InventoryError("health receipt timestamp is missing or invalid")
        if previous_health_time is not None and health_time < previous_health_time:
            raise InventoryError("health receipt timestamps are not monotone")
        if gap_count < previous_gap or restart_count < previous_restart:
            raise InventoryError("health gap/restart counters are not monotone")
        previous_health_time = health_time
        previous_gap, previous_restart = gap_count, restart_count

    # Accredit only immutable, hash-verified roster artifacts. This is
    # metadata-only: symbols are retained as identities, never as outcomes.
    verified_rosters: list[dict[str, Any]] = []
    unverified_rosters: list[dict[str, str]] = []
    roster_dir = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "rosters"
    roster_candidates = [path for path in sorted(roster_dir.glob("*.json")) if re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])\.json", path.name)]
    for roster_path in roster_candidates:
        if roster_path.name.endswith("_replay.json"):
            continue
        try:
            roster = json.loads(roster_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InventoryError(f"roster artifact cannot be parsed: {roster_path}") from exc
        if not isinstance(roster, dict) or roster.get("schema") != "r3_roster_v1" or roster.get("market") != "um":
            raise InventoryError(f"roster artifact schema/market invalid: {roster_path}")
        source_path = Path(str(roster.get("source_path", "")))
        if not source_path.is_absolute():
            source_path = REPO_ROOT / source_path
        source_sha = str(roster.get("source_sha256", ""))
        if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest() != source_sha:
            raise InventoryError(f"roster source hash mismatch: {roster_path}")
        body = {
            "effective_month": roster.get("effective_month"),
            "market": roster.get("market"),
            "symbols": tuple(sorted(set(roster.get("symbols", [])))),
            "prior_ranking": tuple(sorted(roster.get("prior_ranking", []), key=lambda row: str(row.get("symbol", "")) if isinstance(row, dict) else str(row))),
            "source_sha256": source_sha,
            "effective_start": roster.get("effective_start"),
            "effective_end": roster.get("effective_end"),
        }
        roster_sha = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
        if roster.get("roster_sha256") != roster_sha:
            raise InventoryError(f"roster hash mismatch: {roster_path}")
        replay_path = roster_path.with_name(roster_path.stem + "_replay.json")
        if not replay_path.is_file() and roster.get("effective_month") == "2026-09":
            replay_path = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\september_roster_replay.json")
        if not replay_path.is_file():
            unverified_rosters.append({"effective_month": str(roster.get("effective_month")), "artifact": str(roster_path), "reason": "REPLAY_PROOF_MISSING"})
            continue
        try:
            replay = json.loads(replay_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InventoryError(f"roster replay proof cannot be parsed: {replay_path}") from exc
        replay_proof = replay.get("proof", replay)
        replay_ok = replay.get("status") == "PASS" and replay_proof.get("replayed") is True and replay_proof.get("roster_sha256") == roster_sha
        if not replay_ok:
            raise InventoryError(f"roster replay proof mismatch: {replay_path}")
        verified_rosters.append({
            "effective_month": roster.get("effective_month"),
            "roster_sha256": roster_sha,
            "symbol_count": len(roster.get("symbols", [])),
            "symbols": sorted(set(map(str, roster.get("symbols", [])))),
            "effective_start": roster.get("effective_start"),
            "effective_end": roster.get("effective_end"),
            "artifact": str(roster_path),
        })
    if not verified_rosters:
        raise InventoryError("no verified roster artifacts found")

    def valid(stream: str, required: set[str] | None = None, *, strict_boundary: bool = False) -> list[tuple[str, datetime, bool, bool, set[str], bool | None]]:
        rows = [row for row in stream_records[stream] if row[2] and not row[3]]
        if required:
            rows = [row for row in rows if required.issubset(row[4])]
        if strict_boundary:
            rows = [row for row in rows if row[5] is True]
        return rows

    def raw(stream: str, required: set[str] | None = None) -> list[tuple[str, datetime, bool, bool, set[str], bool | None]]:
        rows = list(stream_records[stream])
        if required:
            rows = [row for row in rows if required.issubset(row[4])]
        return rows

    kline_rows = valid("klines_15m", {"source_open_time", "source_available_time", "value"}, strict_boundary=True)
    premium_kline_rows = valid("premium_klines_15m", {"source_open_time", "source_available_time", "value"}, strict_boundary=True)
    premium_rows = valid("premium", {"lastFundingRate"})
    oi_rows = valid("open_interest", {"openInterest"})
    book_rows = valid("book_ticker", {"bidPrice", "askPrice", "bidQty", "askQty"})
    liquidation_rows = [row for row in valid("liquidation") if {"E", "e", "o"}.issubset(row[4])]
    raw_kline_rows = raw("klines_15m", {"source_open_time", "source_available_time", "value"})
    raw_premium_kline_rows = raw("premium_klines_15m", {"source_open_time", "source_available_time", "value"})
    raw_premium_rows = raw("premium", {"lastFundingRate"})
    raw_oi_rows = raw("open_interest", {"openInterest"})
    raw_book_rows = raw("book_ticker", {"bidPrice", "askPrice", "bidQty", "askQty"})
    raw_liquidation_rows = [row for row in raw("liquidation") if {"E", "e", "o"}.issubset(row[4])]

    # The forceOrder helper is the sole source of H03/H04 identity counts.
    # Validate once here for metadata-only block maps, then use the helper's
    # deterministic receipt for all global and endpoint accounting.
    forceorder_valid: list[ValidatedForceOrder] = []
    forceorder_invalid_reasons: list[str] = []
    for envelope in liquidation_envelopes:
        try:
            forceorder_valid.append(validate_forceorder_envelope(envelope, complete_bar_opens=complete_bar_opens))
        except ForceOrderIdentityError as exc:
            forceorder_invalid_reasons.append(exc.reason)
    forceorder_receipt = deduplicate_forceorders(liquidation_envelopes, complete_bar_opens=complete_bar_opens)
    if forceorder_invalid_reasons and sorted(forceorder_invalid_reasons) != list(forceorder_receipt.invalid_reasons):
        raise InventoryError("forceOrder validation receipt mismatch")

    def forceorder_event_time(record: ValidatedForceOrder) -> datetime:
        return datetime.fromtimestamp(int(record.identity_tuple[2]) / 1000.0, tz=UTC)

    forceorder_h03_rows = [(str(record.identity_tuple[1]), forceorder_event_time(record)) for record in forceorder_receipt.representatives if record.h03_status == "endpoint_eligible"]
    forceorder_h04_rows = [(str(record.identity_tuple[1]), forceorder_event_time(record)) for record in forceorder_receipt.representatives if record.h04_status == "endpoint_eligible"]

    # Prove roster membership using symbol-qualified complete primary rows.
    # Keep one deterministic witness per symbol in the compact inventory; the
    # source stream itself remains immutable and is never copied to output.
    complete_rows_by_roster: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    roster_intervals: dict[str, tuple[datetime, datetime, set[str]]] = {}
    for roster in verified_rosters:
        start = _parse_dt(roster.get("effective_start"))
        end = _parse_dt(roster.get("effective_end"))
        if start is None or end is None:
            raise InventoryError("verified roster interval is invalid")
        roster_intervals[str(roster["roster_sha256"])] = (start, end, set(map(str, roster.get("symbols", []))))
    witness_by_roster_symbol: dict[tuple[str, str], datetime] = {}
    for symbol, timestamp, available, gap, _keys, boundary_ok in kline_rows:
        if not available or gap or boundary_ok is not True:
            continue
        for sha, (start, end, members) in roster_intervals.items():
            if start <= timestamp < end:
                if symbol not in members:
                    raise InventoryError(f"complete source row symbol is outside verified roster membership: {symbol}")
                witness_by_roster_symbol.setdefault((sha, symbol), timestamp)
    for (sha, symbol), timestamp in sorted(witness_by_roster_symbol.items()):
        complete_rows_by_roster[sha].append({"symbol": symbol, "timestamp": timestamp.isoformat()})
    used_roster_identities, roster_diagnostics = _used_roster_identities(cycle_metadata_records, verified_rosters, complete_rows_by_roster)
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
    # Derive exact per-hypothesis block counts from the same metadata-only
    # rows used for raw counts. These maps let the readiness checker exclude
    # affected blocks without subtracting aggregate counters.
    def block_count(rows: list[tuple[str, datetime, bool, bool, set[str], bool | None]], *, unique_symbol_bucket: bool = False) -> dict[str, int]:
        if unique_symbol_bucket:
            keys = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in rows}
            counts = Counter(bucket for _, bucket in keys)
        else:
            counts = Counter(_bucket_6h(timestamp) for _, timestamp, *_ in rows)
        return {bucket.isoformat(): int(count) for bucket, count in sorted(counts.items())}

    def block_count_pairs(rows: Iterable[tuple[str, datetime]], *, unique_symbol_bucket: bool = False) -> dict[str, int]:
        pairs = list(rows)
        if unique_symbol_bucket:
            keys = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp in pairs}
            counts = Counter(bucket for _, bucket in keys)
        else:
            counts = Counter(_bucket_6h(timestamp) for _, timestamp in pairs)
        return {bucket.isoformat(): int(count) for bucket, count in sorted(counts.items())}

    h02_pairs = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in kline_rows} & {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in oi_rows}
    h05_pairs = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in premium_rows} & {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in premium_kline_rows}
    h06_keys = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in kline_rows}
    raw_h02_pairs = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in raw_kline_rows} & {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in raw_oi_rows}
    raw_h05_pairs = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in raw_premium_rows} & {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in raw_premium_kline_rows}
    raw_h06_keys = {(symbol, _bucket_6h(timestamp)) for symbol, timestamp, *_ in raw_kline_rows}
    forceorder_raw_h03_rows = [(str(record.identity_tuple[1]), forceorder_event_time(record)) for record in forceorder_valid if record.h03_status == "endpoint_eligible"]
    forceorder_raw_h04_rows = [(str(record.identity_tuple[1]), forceorder_event_time(record)) for record in forceorder_valid if record.h04_status == "endpoint_eligible"]
    eligible_by_hypothesis = {
        "R3_H01": block_count(book_rows, unique_symbol_bucket=True),
        "R3_H02": {bucket.isoformat(): sum(1 for _, b in h02_pairs if b == bucket) for bucket in sorted({b for _, b in h02_pairs})},
        "R3_H03": block_count_pairs(forceorder_h03_rows),
        "R3_H04": block_count_pairs(forceorder_h04_rows),
        "R3_H05": {bucket.isoformat(): sum(1 for _, b in h05_pairs if b == bucket) for bucket in sorted({b for _, b in h05_pairs})},
        "R3_H06": {bucket.isoformat(): sum(1 for _, b in h06_keys if b == bucket) for bucket in sorted({b for _, b in h06_keys})},
    }
    raw_by_hypothesis = {
        "R3_H01": block_count(raw_book_rows, unique_symbol_bucket=True),
        "R3_H02": {bucket.isoformat(): sum(1 for _, b in raw_h02_pairs if b == bucket) for bucket in sorted({b for _, b in raw_h02_pairs})},
        "R3_H03": block_count_pairs(forceorder_raw_h03_rows),
        "R3_H04": block_count_pairs(forceorder_raw_h04_rows),
        "R3_H05": {bucket.isoformat(): sum(1 for _, b in raw_h05_pairs if b == bucket) for bucket in sorted({b for _, b in raw_h05_pairs})},
        "R3_H06": {bucket.isoformat(): sum(1 for _, b in raw_h06_keys if b == bucket) for bucket in sorted({b for _, b in raw_h06_keys})},
    }
    gap_blocks_by_scope = _scoped_gap_blocks(explicit_gap_records)
    excluded_by_hypothesis = {
        hypothesis: set(gap_blocks_by_scope.get(hypothesis, set())) | set(gap_blocks_by_scope.get("GLOBAL", set()))
        for hypothesis in PRIMARY_HYPOTHESES
    }
    explicit_by_category = Counter(record["category"] for record in explicit_gap_records)
    actual_incident_keys = {(record["category"], record.get("cycle_id") or record["start_time"]) for record in explicit_gap_records}
    health_gap_count = int(latest_health.get("gap_count", 0))
    health_restart_count = int(latest_health.get("restart_count", 0))
    actual_restart_count = len({key for key in actual_incident_keys if key[0] == "RESTART_GAP"})
    actual_gap_count = len(actual_incident_keys)
    if health_restart_count != actual_restart_count or health_gap_count != actual_gap_count:
        raise InventoryError(f"health counters do not reconcile to observed continuity incidents: health=({health_gap_count},{health_restart_count}) observed=({actual_gap_count},{actual_restart_count})")
    for hypothesis, mapping in eligible_by_hypothesis.items():
        eligible_by_hypothesis[hypothesis] = {block: count for block, count in mapping.items() if block not in excluded_by_hypothesis[hypothesis]}
    eligible_counts = {hypothesis: sum(mapping.values()) for hypothesis, mapping in eligible_by_hypothesis.items()}
    raw_counts = {hypothesis: sum(mapping.values()) for hypothesis, mapping in raw_by_hypothesis.items()}
    eligible_calendar_by_block = {bucket.isoformat(): count for bucket, count in sorted(six_hour_counts.items())}
    usable_calendar_by_block = {bucket: count for bucket, count in eligible_calendar_by_block.items() if bucket not in set(gap_blocks_by_scope.get("GLOBAL", set()))}

    h_rows: dict[str, list[tuple[str, datetime]]] = {
        "R3_H01": [(symbol, timestamp) for symbol, timestamp, *_ in book_rows],
        "R3_H02": [(symbol, bucket) for symbol, bucket in sorted(h02_pairs)],
        "R3_H03": forceorder_h03_rows,
        "R3_H04": forceorder_h04_rows,
        "R3_H05": [(symbol, bucket) for symbol, bucket in sorted(h05_pairs)],
        "R3_H06": [(symbol, bucket) for symbol, bucket in sorted(h06_keys)],
    }
    usable_days_by_hypothesis: dict[str, list[str]] = {}
    for hypothesis, rows in h_rows.items():
        excluded = excluded_by_hypothesis[hypothesis]
        usable_days_by_hypothesis[hypothesis] = sorted({timestamp.date().isoformat() for _symbol, timestamp in rows if _bucket_6h(timestamp).isoformat() not in excluded})
    roster_contribution_by_hypothesis: dict[str, dict[str, dict[str, Any]]] = {hypothesis: {} for hypothesis in PRIMARY_HYPOTHESES}
    for identity in used_roster_identities:
        sha = str(identity["roster_sha256"])
        roster = next(roster for roster in verified_rosters if str(roster["roster_sha256"]) == sha)
        start = _parse_dt(roster["effective_start"])
        end = _parse_dt(roster["effective_end"])
        members = set(identity["membership"]["symbols"])
        for hypothesis in PRIMARY_HYPOTHESES:
            excluded = excluded_by_hypothesis[hypothesis]
            complete_count = sum(1 for symbol, timestamp in h_rows[hypothesis] if symbol in members and start is not None and end is not None and start <= timestamp < end and _bucket_6h(timestamp).isoformat() not in excluded)
            roster_contribution_by_hypothesis[hypothesis][sha] = {"effective_month": identity["effective_month"], "complete_count": int(complete_count)}

    inventory = {
        "record_type": "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "root": str(resolved),
        "market": "um",
        "interval": "15m",
        "verified_roster_months": sorted({entry["effective_month"] for entry in used_roster_identities}),
        "used_roster_identities": used_roster_identities,
        "roster_use_diagnostics": roster_diagnostics,
        "verified_roster_artifacts": verified_rosters,
        "unverified_roster_artifacts": unverified_rosters,
        "calendar": {
            "first_observation_time": first_time,
            "last_observation_time": last_time,
            "observed_utc_days": len({timestamp.date().isoformat() for timestamp in all_timestamps}),
            "independent_utc_days": len({timestamp.date().isoformat() for timestamp in all_timestamps}),
            "independent_utc_6h_blocks": len(six_hour_counts),
            "raw_by_utc_6h_block": {bucket.isoformat(): count for bucket, count in sorted(six_hour_counts.items())},
            "eligible_by_utc_6h_block": eligible_calendar_by_block,
            "usable_by_utc_6h_block": usable_calendar_by_block,
            "global_gate_targets": {"independent_utc_days": 30, "independent_utc_6h_blocks": 120},
        },
        "cycles": {
            "cycle_count": len(cycle_ids),
            "duplicate_cycle_ids": 0,
            "cycle_id_timestamps": cycle_metadata_records,
            "metadata_stream": compact_stream(summary["cycle_metadata"]),
        },
        "streams": {stream: compact_stream(summary[stream]) for stream in STREAMS},
        "causal_input_presence": {
            "definition": "source_time_available=true, continuity not a gap, required schema keys present; no derived label is constructed",
            "H01_execution_quality_context": {"input_stream": "book_ticker", "raw_observations": raw_counts["R3_H01"], "primary_eligible_observations": eligible_counts["R3_H01"], "usable_observations": eligible_counts["R3_H01"], "raw_by_utc_6h_block": raw_by_hypothesis["R3_H01"], "eligible_by_utc_6h_block": eligible_by_hypothesis["R3_H01"]},
            "H02_price_oi_quadrant": {"input_streams": ["klines_15m", "open_interest"], "raw_symbol_buckets": raw_counts["R3_H02"], "primary_eligible_symbol_buckets": eligible_counts["R3_H02"], "usable_symbol_buckets": eligible_counts["R3_H02"], "raw_by_utc_6h_block": raw_by_hypothesis["R3_H02"], "eligible_by_utc_6h_block": eligible_by_hypothesis["R3_H02"]},
            "H03_liquidation_continuation": {"input_stream": "liquidation", "raw_events": raw_counts["R3_H03"], "primary_eligible_events": eligible_counts["R3_H03"], "observed_events": eligible_counts["R3_H03"], "raw_by_utc_6h_block": raw_by_hypothesis["R3_H03"], "eligible_by_utc_6h_block": eligible_by_hypothesis["R3_H03"]},
            "H04_liquidation_reversion": {"input_stream": "liquidation", "raw_events": raw_counts["R3_H04"], "primary_eligible_events": eligible_counts["R3_H04"], "observed_events": eligible_counts["R3_H04"], "raw_by_utc_6h_block": raw_by_hypothesis["R3_H04"], "eligible_by_utc_6h_block": eligible_by_hypothesis["R3_H04"]},
            "H05_crowding_stress_modifier": {"input_streams": ["premium", "premium_klines_15m"], "raw_symbol_buckets": raw_counts["R3_H05"], "primary_eligible_symbol_buckets": eligible_counts["R3_H05"], "usable_symbol_buckets": eligible_counts["R3_H05"], "funding_rate_observations": len(premium_rows), "raw_by_utc_6h_block": raw_by_hypothesis["R3_H05"], "eligible_by_utc_6h_block": eligible_by_hypothesis["R3_H05"]},
            "H06_btc_breadth_concordance": {"input_stream": "klines_15m", "btc_symbol": btc_symbol, "usable_breadth_decision_buckets": breadth_decisions, "raw_symbol_buckets": raw_counts["R3_H06"], "primary_eligible_symbol_buckets": eligible_counts["R3_H06"], "usable_kline_symbol_buckets": eligible_counts["R3_H06"], "raw_by_utc_6h_block": raw_by_hypothesis["R3_H06"], "eligible_by_utc_6h_block": eligible_by_hypothesis["R3_H06"]},
        },
        "gap_blocks_by_scope": {scope: sorted(blocks) for scope, blocks in sorted(gap_blocks_by_scope.items())},
        "excluded_block_ids_by_hypothesis": {hypothesis: sorted(blocks) for hypothesis, blocks in sorted(excluded_by_hypothesis.items())},
        "usable_blocks_by_hypothesis": {hypothesis: sorted(eligible_by_hypothesis[hypothesis]) for hypothesis in PRIMARY_HYPOTHESES},
        "usable_days_by_hypothesis": usable_days_by_hypothesis,
        "roster_contribution_by_hypothesis": roster_contribution_by_hypothesis,
        "per_hypothesis_temporal_minima": PER_H_TEMPORAL_MINIMA,
        "forceorder_accounting": {
            **forceorder_receipt.as_dict(),
            "identity_key_version": "forceorder:v2",
            "per_block_unique_representatives": {
                "R3_H03": block_count_pairs(forceorder_h03_rows),
                "R3_H04": block_count_pairs(forceorder_h04_rows),
            },
            "representative_block_basis": "normalized exchange event time E",
        },
        "availability_and_gaps": {
            "source_unavailable_records": sum(1 for record in explicit_gap_records if record["category"] == "SOURCE_UNAVAILABLE"),
            "gap_records": explicit_gap_records,
            "gap_accounting_complete": True,
            "health_gap_count": health_gap_count,
            "health_restart_count": health_restart_count,
            "gap_state_counts": {stream: dict(sorted(summary[stream]["continuity"].items())) for stream in STREAMS},
            "no_imputation": True,
            "gap_reset_required": True,
            "strict_15m_boundary": {
                "normalized_records_checked": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is not None),
                "accepted": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is True),
                "rejected": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is False),
                "missing_boundary_fields": sum(1 for stream in ("klines_15m", "premium_klines_15m") for row in stream_records[stream] if row[5] is None),
            },
            "gap_block_accounting": {"excluded_block_ids": sorted(set(gap_blocks_by_scope.get("GLOBAL", set()))), "gap_blocks_by_scope": {scope: sorted(blocks) for scope, blocks in sorted(gap_blocks_by_scope.items())}, "raw_gap_count": len(explicit_gap_records), "explicit_records_by_category": dict(sorted(explicit_by_category.items())), "health_counters_reconciled": True},
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


def _safe_output_path(path: Path) -> None:
    lowered = str(path).replace("\\", "/").lower()
    forbidden = ("final_holdout", "holdout", "r2b2", "future_return", "gross_return", "net_return", "/pnl", "sharpe", "hit_rate")
    if any(token in lowered for token in forbidden):
        raise InventoryError(f"forbidden output path: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    requested_output = args.output or (REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / f"R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2_{stamp}.json")
    # Inspect the lexical path before resolving it: resolving first would
    # follow an output symlink and defeat the confinement check.
    output_lexical = Path(os.path.abspath(str(requested_output)))
    cursor = output_lexical
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise InventoryError(f"refusing to write through symlink output component: {cursor}")
        cursor = cursor.parent
    output = output_lexical.resolve()
    _safe_output_path(output)
    operations_root = (REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations").resolve()
    if output.parent != operations_root:
        raise InventoryError(f"inventory output must remain under the approved operations root: {operations_root}")
    if output.is_symlink():
        raise InventoryError("refusing to write through a symlink output")
    if not re.fullmatch(r"R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2_20\d{6}T\d{6}Z\.json", output.name):
        raise InventoryError("inventory output must use R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2_<UTC timestamp>.json")
    if output.exists():
        raise InventoryError(f"refusing to overwrite existing inventory: {output}")
    inventory = build_inventory(args.root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Evaluate the newly written snapshot immediately against the frozen V2
    # spec and emit versioned readiness/report/index artifacts. These files
    # contain metadata only and refuse overwrite.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from ops.r3.check_r3_evaluation_readiness import _load_roster_months, evaluate_readiness
    spec_path = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "campaign_spec.toml"
    import tomllib
    spec = tomllib.loads(spec_path.read_text(encoding="utf-8"))
    contract = {key: spec.get(key) for key in ("evaluation_horizon_keys", "evaluation_horizon_sha256", "evaluation_horizon_interval", "evaluation_horizon_bars", "evaluation_horizon_alternatives")}
    verified_roster_paths = [Path(entry["artifact"]) for entry in inventory.get("verified_roster_artifacts", [])]
    readiness = evaluate_readiness(contract, inventory, spec, roster_months=_load_roster_months(verified_roster_paths), human_authorized=False)
    readiness_path = output.with_name(f"R3_EVALUATION_READINESS_V2_{stamp}.json")
    _safe_output_path(readiness_path)
    if readiness_path.exists():
        raise InventoryError(f"refusing to overwrite existing readiness receipt: {readiness_path}")
    readiness_path.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path = REPO_ROOT / "reports" / f"R3_EVIDENCE_ACCRUAL_V2_{stamp}.md"
    _safe_output_path(report_path)
    if report_path.exists():
        raise InventoryError(f"refusing to overwrite existing accrual report: {report_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    prior_v1_receipts = sorted(str(path) for path in (REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations").glob("R3_*20260903*.json"))
    report_path.write_text(
        "# R3 V2 evidence accrual (metadata-only)\n\n"
        f"- Inventory: `{output}`\n- Readiness: `{readiness_path}`\n"
        f"- State: `{readiness['state']}`\n- Cycles: {inventory['cycles']['cycle_count']}\n"
        f"- UTC 6h blocks (raw): {inventory['calendar']['independent_utc_6h_blocks']}\n"
        f"- Explicit gap records: {readiness['gap_accounting']['raw_gap_count']}\n"
        f"- Excluded UTC 6h blocks: {readiness['gap_accounting']['excluded_block_count']}\n"
        f"- Verified roster months: {len(inventory.get('verified_roster_months', []))}\n"
        f"- Superseded V1 receipt lineage: {', '.join(prior_v1_receipts) if prior_v1_receipts else 'none found'}\n"
        "\nNo response, forward value, return, ranking, or holdout field was read or retained.\n",
        encoding="utf-8",
    )
    index_path = output.with_name(f"R3_V2_CURRENT_STATE_{stamp}.json")
    _safe_output_path(index_path)
    if index_path.exists():
        raise InventoryError(f"refusing to overwrite existing state index: {index_path}")
    index_path.write_text(json.dumps({"record_type": "R3_V2_METADATA_STATE_INDEX", "inventory": str(output), "readiness": str(readiness_path), "accrual_report": str(report_path), "superseded_v1_receipts": prior_v1_receipts, "v1_disposition": "SUPERSEDED_PREREGISTRATION_BLOCKED_NOT_INVALID_OUTCOME_EVIDENCE", "state": readiness["state"], "outcome_values_accessed": False, "final_holdout_status": "UNTOUCHED", "r2b2_status": "NOT_STARTED"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(output), "readiness": str(readiness_path), "report": str(report_path), "index": str(index_path), "state": readiness["state"], "cycle_count": inventory["cycles"]["cycle_count"], "independent_utc_6h_blocks": inventory["calendar"]["independent_utc_6h_blocks"], "gap_records": readiness["gap_accounting"]["raw_gap_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InventoryError as exc:
        print(f"R3_INVENTORY_BLOCKED: {exc}")
        raise SystemExit(2)
