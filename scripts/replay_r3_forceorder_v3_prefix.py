"""Replay only the byte prefix named by a frozen R3 v8 cutoff receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT / "src", REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ops.r3.r3_forceorder_identity import (  # noqa: E402
    ForceOrderIdentityError,
    validate_forceorder_envelope,
)
from ops.r3.r3_forceorder_identity_v3 import (  # noqa: E402
    ForceOrderIdentityV3Error,
    validate_forceorder_envelope_v3,
)


DERIVED_NAME_PREFIX = "derived_forceorder_v3_v1"
FORBIDDEN = ("outcome", "holdout", "return", "pnl", "r2b2")


class ReplayError(RuntimeError):
    """Fail-closed replay error."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_sha(root: Path, *, exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        data = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _strict_json(line: bytes, context: str) -> dict[str, Any]:
    def reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReplayError(f"duplicate JSON key at {context}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(line.decode("utf-8"), object_pairs_hook=reject)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayError(f"invalid JSON at {context}") from exc
    if not isinstance(value, dict):
        raise ReplayError(f"JSON object required at {context}")
    return value


def _as_iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _metadata_row(envelope: dict[str, Any], line_context: str) -> tuple[dict[str, Any], str | None, str | None, str | None]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ReplayError(f"liquidation payload is not an object at {line_context}")
    v2_status = "VALID"
    try:
        validate_forceorder_envelope({
            "market_type": envelope.get("market_type"),
            "symbol": envelope.get("symbol"),
            "stream": envelope.get("stream"),
            "endpoint": envelope.get("endpoint"),
            "collector_receipt_time": envelope.get("collector_receipt_time"),
            "corrected_response_receipt_time": envelope.get("corrected_response_receipt_time"),
            "continuity_state": envelope.get("continuity_state"),
            "payload": payload,
        })
    except ForceOrderIdentityError as exc:
        v2_status = f"INVALID:{exc.reason}"
    base = {
        "market_type": envelope.get("market_type"),
        "event_symbol": envelope.get("symbol"),
        "source_identity": None,
        "v2_status": v2_status,
        "v3_status": "INVALID",
        "v3_invalid_reason": None,
        "position_side": None,
        "raw_payload_sha256": _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
    }
    v3_envelope = {
        "market_type": envelope.get("market_type"),
        "symbol": envelope.get("symbol"),
        "stream": envelope.get("stream"),
        "endpoint": envelope.get("endpoint"),
        "collector_receipt_time": envelope.get("collector_receipt_time"),
        "corrected_response_receipt_time": envelope.get("corrected_response_receipt_time"),
        "continuity_state": envelope.get("continuity_state"),
        "payload": payload,
    }
    try:
        record = validate_forceorder_envelope_v3(v3_envelope)
    except ForceOrderIdentityV3Error as exc:
        base["v3_invalid_reason"] = exc.reason
        return base, v2_status, "INVALID", exc.reason
    identity = record.identity_tuple
    signed_base = Decimal(identity[14]) * Decimal(identity[12] or identity[11])
    signed = signed_base if identity[7] == "SELL" else -signed_base
    base.update({
        "identity_key": record.identity_key,
        "market_type": record.market_type,
        "event_symbol": record.event_symbol,
        "pair_symbol": record.pair_symbol,
        "subtype": record.subtype,
        "event_time_ms": identity[4],
        "order_trade_time_ms": identity[5],
        "trade_id": identity[6],
        "forced_side": identity[7],
        "source_available_time": _as_iso(record.source_available_time),
        "executable_open": _as_iso(record.executable_open),
        "continuity_state": record.continuity_state,
        "h03_status": record.h03_status,
        "h04_status": record.h04_status,
        "signed_observed_notional": format(signed, "f"),
        "canonical_payload_sha256": record.canonical_payload_sha256,
        "source_identity": record.identity_key,
        "identity_tuple_sha256": _sha256_bytes(record.identity_json.encode("utf-8")),
        "v3_status": "VALID",
        "v3_invalid_reason": None,
    })
    return base, v2_status, "VALID", record.identity_json


def replay_prefix(cutoff_path: Path, output_root: Path, *, implementation_commit: str | None = None) -> dict[str, Any]:
    cutoff = json.loads(cutoff_path.read_text(encoding="utf-8"))
    if cutoff.get("record_type") != "R3_FORCEORDER_V3_CUTOFF_RECEIPT" or cutoff.get("status") != "FROZEN" or cutoff.get("prefix_only") is not True:
        raise ReplayError("cutoff receipt is not a frozen prefix receipt")
    raw_root = Path(cutoff["raw_root"]).resolve()
    output_root = output_root.resolve()
    if output_root.drive.upper() != "D:" or not output_root.name.startswith(DERIVED_NAME_PREFIX):
        raise ReplayError(f"derived root must be D-backed and start with {DERIVED_NAME_PREFIX}")
    if output_root.exists() and any(output_root.iterdir()):
        raise ReplayError(f"refusing non-empty derived root: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    raw_out = output_root / "raw_v3"
    processed_out = output_root / "processed_v3"
    raw_out.mkdir()
    processed_out.mkdir()
    entries = cutoff.get("files")
    if not isinstance(entries, list) or not entries:
        raise ReplayError("cutoff has no files")

    liquidation_rows: list[dict[str, Any]] = []
    groups: defaultdict[str, list[tuple[str | None, str | None]]] = defaultdict(list)
    v2_counts: Counter[str] = Counter()
    v3_counts: Counter[str] = Counter()
    market_counts: Counter[str] = Counter()
    pressure_counts: Counter[str] = Counter()
    file_receipts: list[dict[str, Any]] = []
    total_rows = total_bytes = 0
    for entry in sorted(entries, key=lambda value: str(value.get("path"))):
        relative = str(entry["path"])
        source = raw_root / "raw_v1" / Path(*PurePosixPath(relative).parts)
        expected_bytes = int(entry["bytes"])
        expected_sha = str(entry["sha256"]).lower()
        with source.open("rb") as handle:
            data = handle.read(expected_bytes)
        if len(data) != expected_bytes or _sha256_bytes(data) != expected_sha:
            raise ReplayError(f"cutoff prefix changed: {relative}")
        destination = raw_out / Path(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        file_receipts.append({"path": relative, "bytes": expected_bytes, "rows": int(entry["rows"]), "sha256": expected_sha})
        total_bytes += expected_bytes
        total_rows += int(entry["rows"])
        if not relative.endswith("/liquidation.jsonl"):
            continue
        for line_number, line in enumerate(data.splitlines(), 1):
            if not line.strip():
                continue
            context = f"{relative}:{line_number}"
            envelope = _strict_json(line, context)
            metadata, v2_status, v3_status, identity_marker = _metadata_row(envelope, context)
            metadata["source_file"] = relative
            liquidation_rows.append(metadata)
            v2_counts[v2_status] += 1
            v3_counts[v3_status] += 1
            if v3_status == "VALID":
                market_counts[str(metadata["market_type"])] += 1
                pressure_counts[str(metadata["forced_side"])] += 1
                groups[str(metadata["identity_key"])].append((str(metadata["identity_tuple_sha256"]), str(metadata["canonical_payload_sha256"])))

    processed_path = processed_out / "forceorder_v3_metadata.jsonl"
    with processed_path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in liquidation_rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    unique = duplicate = collision = 0
    collision_keys: list[str] = []
    for key in sorted(groups):
        members = groups[key]
        if len({identity for identity, _ in members}) > 1 or len({canonical for _, canonical in members}) > 1:
            collision += len(members)
            collision_keys.append(key)
        else:
            unique += 1
            duplicate += len(members) - 1
    matrix = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_SOURCE_DEPENDENCY_MATRIX_V3_FORCEORDER.json"
    replay = {
        "record_type": "R3_FORCEORDER_V3_REPLAY_MANIFEST",
        "status": "REPLAYED_PREFIX_ONLY",
        "derived_root": str(output_root),
        "raw_v3_root": str(raw_out),
        "processed_v3_path": str(processed_path),
        "source_raw_root": str(raw_root),
        "cutoff_receipt": str(cutoff_path.resolve()),
        "cutoff_receipt_sha256": _sha256_file(cutoff_path),
        "implementation_commit": implementation_commit,
        "schema_matrix_sha256": _sha256_file(matrix) if matrix.is_file() else None,
        "file_count": len(file_receipts),
        "total_bytes": total_bytes,
        "total_rows": total_rows,
        "liquidation_row_count": len(liquidation_rows),
        "v2_status_counts": dict(sorted(v2_counts.items())),
        "v3_status_counts": dict(sorted(v3_counts.items())),
        "v3_market_counts": dict(sorted(market_counts.items())),
        "pressure_side_counts": dict(sorted(pressure_counts.items())),
        "unique_event_count": unique,
        "duplicate_envelope_count": duplicate,
        "collision_envelope_count": collision,
        "collision_keys": collision_keys,
        "raw_count_invariant": len(liquidation_rows) == unique + duplicate + collision + v3_counts["INVALID"],
        "derived_tree_sha256_excluding_manifest": _tree_sha(output_root, exclude={"replay_manifest.json"}),
        "raw_v8_mutated": False,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "files": file_receipts,
    }
    encoded = json.dumps(replay, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    (output_root / "replay_manifest.json").write_text(encoded, encoding="utf-8", newline="\n")
    return replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--implementation-commit")
    args = parser.parse_args()
    result = replay_prefix(args.cutoff, args.output_root, implementation_commit=args.implementation_commit)
    print(json.dumps({key: result[key] for key in ("status", "file_count", "total_rows", "liquidation_row_count", "v2_status_counts", "v3_status_counts", "unique_event_count", "duplicate_envelope_count", "collision_envelope_count", "derived_tree_sha256_excluding_manifest")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
