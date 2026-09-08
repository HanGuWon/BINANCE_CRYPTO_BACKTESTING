"""Verify an outcome-blind ForceOrder V3 prefix replay and its accounting."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any


FORBIDDEN_PATH_TOKENS = ("holdout", "outcome", "return", "pnl", "r2b2")


class ReplayVerificationError(RuntimeError):
    """Raised on any prefix, schema, or accounting mismatch."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_sha(root: Path, *, exclude: set[str] | None = None) -> str:
    excluded = exclude or set()
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        data = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _reject_forbidden_row(value: Any, context: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in FORBIDDEN_PATH_TOKENS):
                raise ReplayVerificationError(f"forbidden derived-row field at {context}: {key}")
            _reject_forbidden_row(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_row(child, f"{context}[{index}]")


def verify_replay(cutoff_path: Path, derived_root: Path) -> dict[str, Any]:
    cutoff = json.loads(cutoff_path.read_text(encoding="utf-8"))
    if cutoff.get("record_type") != "R3_FORCEORDER_V3_CUTOFF_RECEIPT" or cutoff.get("status") != "FROZEN":
        raise ReplayVerificationError("cutoff is not frozen")
    derived_root = derived_root.resolve()
    if derived_root.drive.upper() != "D:" or not derived_root.name.startswith("derived_forceorder_v3_v1"):
        raise ReplayVerificationError("derived root is not the authorized D-backed name")
    manifest_path = derived_root / "replay_manifest.json"
    raw_root = derived_root / "raw_v3"
    processed_path = derived_root / "processed_v3" / "forceorder_v3_metadata.jsonl"
    if not manifest_path.is_file() or not raw_root.is_dir() or not processed_path.is_file():
        raise ReplayVerificationError("derived replay outputs are incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("record_type") != "R3_FORCEORDER_V3_REPLAY_MANIFEST" or manifest.get("status") != "REPLAYED_PREFIX_ONLY":
        raise ReplayVerificationError("replay manifest status mismatch")
    if manifest.get("raw_v8_mutated") is not False or manifest.get("outcomes_accessed") is not False or manifest.get("final_holdout") != "UNTOUCHED":
        raise ReplayVerificationError("replay policy flags are unsafe")
    entries = cutoff.get("files")
    if not isinstance(entries, list) or not entries:
        raise ReplayVerificationError("cutoff file list missing")
    expected_paths = {str(entry["path"]) for entry in entries}
    for entry in entries:
        relative = str(entry["path"])
        if any(token in relative.lower() for token in FORBIDDEN_PATH_TOKENS):
            raise ReplayVerificationError(f"forbidden source path: {relative}")
        expected_bytes = int(entry["bytes"])
        expected_sha = str(entry["sha256"]).lower()
        source = Path(cutoff["raw_root"]) / "raw_v1" / Path(*PurePosixPath(relative).parts)
        target = raw_root / Path(*PurePosixPath(relative).parts)
        if not source.is_file() or not target.is_file():
            raise ReplayVerificationError(f"prefix file missing: {relative}")
        with source.open("rb") as handle:
            source_prefix = handle.read(expected_bytes)
        target_bytes = target.read_bytes()
        if len(source_prefix) != expected_bytes or len(target_bytes) != expected_bytes:
            raise ReplayVerificationError(f"prefix byte count mismatch: {relative}")
        if _sha(source_prefix) != expected_sha or _sha(target_bytes) != expected_sha:
            raise ReplayVerificationError(f"prefix SHA mismatch: {relative}")
    actual_paths = {path.relative_to(raw_root).as_posix() for path in raw_root.rglob("*") if path.is_file()}
    if actual_paths != expected_paths:
        raise ReplayVerificationError(f"derived raw file set mismatch: extra={sorted(actual_paths - expected_paths)[:3]} missing={sorted(expected_paths - actual_paths)[:3]}")
    groups: defaultdict[str, list[tuple[str | None, str | None]]] = defaultdict(list)
    v2_counts: Counter[str] = Counter()
    v3_counts: Counter[str] = Counter()
    market_counts: Counter[str] = Counter()
    pressure_counts: Counter[str] = Counter()
    row_count = 0
    for line_number, line in enumerate(processed_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayVerificationError(f"invalid processed metadata JSON at line {line_number}") from exc
        if not isinstance(row, dict):
            raise ReplayVerificationError(f"processed row is not an object at line {line_number}")
        _reject_forbidden_row(row, f"processed:{line_number}")
        if "payload" in row or "return" in row or "entry" in row or "exit" in row:
            raise ReplayVerificationError(f"outcome-like field in processed row {line_number}")
        source_file = str(row.get("source_file") or "")
        if not source_file.endswith("/liquidation.jsonl") or source_file not in expected_paths:
            raise ReplayVerificationError(f"processed row has unauthorized source file at line {line_number}")
        row_count += 1
        v2_counts[str(row.get("v2_status"))] += 1
        v3_counts[str(row.get("v3_status"))] += 1
        if row.get("v3_status") == "VALID":
            key = str(row.get("identity_key"))
            tuple_sha = row.get("identity_tuple_sha256")
            if not isinstance(tuple_sha, str) or len(tuple_sha) != 64:
                raise ReplayVerificationError(f"missing identity tuple hash at line {line_number}")
            groups[key].append((tuple_sha, str(row.get("canonical_payload_sha256"))))
            market_counts[str(row.get("market_type"))] += 1
            side = str(row.get("forced_side"))
            pressure_counts[side] += 1
            if side not in {"BUY", "SELL"}:
                raise ReplayVerificationError(f"invalid pressure side at line {line_number}")
            amount = Decimal(str(row.get("signed_observed_notional")))
            if (side == "SELL" and amount < 0) or (side == "BUY" and amount > 0):
                raise ReplayVerificationError(f"signed pressure parity mismatch at line {line_number}")
            available = row.get("source_available_time")
            executable = row.get("executable_open")
            if available is None or executable is None:
                raise ReplayVerificationError(f"missing source availability at line {line_number}")
            from datetime import datetime
            left = datetime.fromisoformat(str(available).replace("Z", "+00:00"))
            right = datetime.fromisoformat(str(executable).replace("Z", "+00:00"))
            if not left < right:
                raise ReplayVerificationError(f"strict availability violation at line {line_number}")
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
    invalid = v3_counts["INVALID"]
    if row_count != sum(v3_counts.values()):
        raise ReplayVerificationError("processed row accounting mismatch")
    if row_count != unique + duplicate + collision + invalid:
        raise ReplayVerificationError("raw = unique + duplicate + collision + invalid invariant failed")
    expected_manifest_fields = {
        "file_count": len(entries),
        "total_rows": int(cutoff["total_rows"]),
        "liquidation_row_count": row_count,
        "unique_event_count": unique,
        "duplicate_envelope_count": duplicate,
        "collision_envelope_count": collision,
    }
    for field, expected in expected_manifest_fields.items():
        if manifest.get(field) != expected:
            raise ReplayVerificationError(f"replay manifest field mismatch: {field}")
    tree_sha = _tree_sha(derived_root, exclude={"replay_manifest.json"})
    if manifest.get("derived_tree_sha256_excluding_manifest") != tree_sha:
        raise ReplayVerificationError("derived tree SHA mismatch")
    result = {
        "status": "PASS",
        "cutoff_receipt_sha256": _sha_file(cutoff_path),
        "derived_tree_sha256_excluding_manifest": tree_sha,
        "file_count": len(entries),
        "total_rows": int(cutoff["total_rows"]),
        "liquidation_row_count": row_count,
        "v2_status_counts": dict(sorted(v2_counts.items())),
        "v3_status_counts": dict(sorted(v3_counts.items())),
        "v3_market_counts": dict(sorted(market_counts.items())),
        "pressure_side_counts": dict(sorted(pressure_counts.items())),
        "unique_event_count": unique,
        "duplicate_envelope_count": duplicate,
        "collision_envelope_count": collision,
        "collision_keys": collision_keys,
        "raw_v8_mutated": False,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", type=Path, required=True)
    parser.add_argument("--derived-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_replay(args.cutoff, args.derived_root)
    if args.output:
        if any(token in str(args.output).replace("\\", "/").lower() for token in FORBIDDEN_PATH_TOKENS):
            raise ReplayVerificationError("forbidden verifier output path")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise ReplayVerificationError(f"refusing to overwrite verifier receipt: {args.output}")
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
