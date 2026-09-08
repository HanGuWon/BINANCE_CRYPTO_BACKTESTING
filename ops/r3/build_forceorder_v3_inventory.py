"""Build a compact, outcome-blind inventory for a V3 derived root."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


FORBIDDEN = ("outcome", "holdout", "return", "pnl", "r2b2")


class InventoryError(RuntimeError):
    """Fail closed on an unauthorized or malformed derived root."""


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_sha(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "replay_manifest.json"):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _reject_row(value: Any, context: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if any(token in str(key).lower() for token in FORBIDDEN):
                raise InventoryError(f"forbidden field at {context}: {key}")
            _reject_row(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_row(child, f"{context}[{index}]")


def build_inventory(derived_root: Path) -> dict[str, Any]:
    root = derived_root.resolve()
    if root.drive.upper() != "D:" or not root.name.startswith("derived_forceorder_v3_v1"):
        raise InventoryError("derived root is not an authorized D-backed V3 root")
    manifest_path = root / "replay_manifest.json"
    metadata_path = root / "processed_v3" / "forceorder_v3_metadata.jsonl"
    if not manifest_path.is_file() or not metadata_path.is_file():
        raise InventoryError("derived root is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("record_type") != "R3_FORCEORDER_V3_REPLAY_MANIFEST" or manifest.get("status") != "REPLAYED_PREFIX_ONLY":
        raise InventoryError("replay manifest is not prefix-only")
    if manifest.get("raw_v8_mutated") is not False or manifest.get("outcomes_accessed") is not False or manifest.get("final_holdout") != "UNTOUCHED":
        raise InventoryError("unsafe replay policy flag")
    status = Counter()
    markets = Counter()
    sides = Counter()
    continuity = Counter()
    identity_hashes: set[str] = set()
    row_count = 0
    with metadata_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InventoryError(f"invalid metadata JSON at line {line_number}") from exc
            if not isinstance(row, dict):
                raise InventoryError(f"metadata row is not an object at line {line_number}")
            _reject_row(row, f"metadata:{line_number}")
            row_count += 1
            status[str(row.get("v3_status"))] += 1
            if row.get("v3_status") == "VALID":
                markets[str(row.get("market_type"))] += 1
                sides[str(row.get("forced_side"))] += 1
                continuity[str(row.get("continuity_state"))] += 1
                identity_hash = row.get("identity_tuple_sha256")
                if not isinstance(identity_hash, str) or len(identity_hash) != 64:
                    raise InventoryError(f"missing identity tuple hash at line {line_number}")
                identity_hashes.add(identity_hash)
    if row_count != int(manifest.get("liquidation_row_count", -1)):
        raise InventoryError("metadata row count does not match replay manifest")
    return {
        "record_type": "R3_FORCEORDER_V3_DERIVED_INVENTORY",
        "status": "PASS",
        "derived_root": str(root),
        "replay_manifest_sha256": _sha_file(manifest_path),
        "derived_tree_sha256_excluding_manifest": _tree_sha(root),
        "metadata_sha256": _sha_file(metadata_path),
        "row_count": row_count,
        "status_counts": dict(sorted(status.items())),
        "market_counts": dict(sorted(markets.items())),
        "forced_side_counts": dict(sorted(sides.items())),
        "continuity_counts": dict(sorted(continuity.items())),
        "distinct_valid_identity_tuple_count": len(identity_hashes),
        "outcome_blind": True,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derived-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_inventory(args.derived_root)
    if args.output:
        if any(token in args.output.as_posix().lower() for token in FORBIDDEN):
            raise InventoryError("forbidden inventory output path")
        if args.output.exists():
            raise InventoryError(f"refusing to overwrite inventory: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
