"""Verify a compact V3 derived inventory against its immutable replay root."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class InventoryVerificationError(RuntimeError):
    """Raised on an inventory, manifest, or derived-tree mismatch."""


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


def _reject(value: Any, context: str) -> None:
    forbidden = ("outcome", "holdout", "return", "pnl", "r2b2")
    if isinstance(value, dict):
        for key, child in value.items():
            # These are receipt policy flags, not scientific outcome values.
            if str(key) not in {"outcome_blind", "outcomes_accessed", "final_holdout"} and any(token in str(key).lower() for token in forbidden):
                raise InventoryVerificationError(f"forbidden inventory field at {context}: {key}")
            _reject(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject(child, f"{context}[{index}]")


def verify_inventory(derived_root: Path, inventory_path: Path) -> dict[str, Any]:
    root = derived_root.resolve()
    if root.drive.upper() != "D:" or not root.name.startswith("derived_forceorder_v3_v1"):
        raise InventoryVerificationError("unauthorized derived root")
    manifest_path = root / "replay_manifest.json"
    metadata_path = root / "processed_v3" / "forceorder_v3_metadata.jsonl"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    _reject(inventory, "inventory")
    if inventory.get("record_type") != "R3_FORCEORDER_V3_DERIVED_INVENTORY" or inventory.get("status") != "PASS":
        raise InventoryVerificationError("inventory status mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "replay_manifest_sha256": _sha_file(manifest_path),
        "derived_tree_sha256_excluding_manifest": _tree_sha(root),
        "metadata_sha256": _sha_file(metadata_path),
        "row_count": int(manifest.get("liquidation_row_count", -1)),
    }
    for field, value in expected.items():
        if inventory.get(field) != value:
            raise InventoryVerificationError(f"inventory mismatch: {field}")
    status: Counter[str] = Counter()
    markets: Counter[str] = Counter()
    sides: Counter[str] = Counter()
    continuity: Counter[str] = Counter()
    identities: set[str] = set()
    rows = 0
    with metadata_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InventoryVerificationError(f"invalid metadata JSON at line {line_number}") from exc
            if not isinstance(row, dict):
                raise InventoryVerificationError(f"metadata object required at line {line_number}")
            rows += 1
            status[str(row.get("v3_status"))] += 1
            if row.get("v3_status") == "VALID":
                markets[str(row.get("market_type"))] += 1
                sides[str(row.get("forced_side"))] += 1
                continuity[str(row.get("continuity_state"))] += 1
                identity = row.get("identity_tuple_sha256")
                if not isinstance(identity, str) or len(identity) != 64:
                    raise InventoryVerificationError(f"identity tuple hash missing at line {line_number}")
                identities.add(identity)
    if rows != inventory.get("row_count"):
        raise InventoryVerificationError("recomputed row count mismatch")
    recomputed = {
        "status_counts": dict(sorted(status.items())),
        "market_counts": dict(sorted(markets.items())),
        "forced_side_counts": dict(sorted(sides.items())),
        "continuity_counts": dict(sorted(continuity.items())),
        "distinct_valid_identity_tuple_count": len(identities),
    }
    for field, value in recomputed.items():
        if inventory.get(field) != value:
            raise InventoryVerificationError(f"recomputed inventory mismatch: {field}")
    if inventory.get("outcome_blind") is not True or inventory.get("outcomes_accessed") is not False or inventory.get("final_holdout") != "UNTOUCHED":
        raise InventoryVerificationError("unsafe inventory policy flags")
    result = {"record_type": "R3_FORCEORDER_V3_DERIVED_INVENTORY_VERIFICATION", "status": "PASS", **expected, "outcomes_accessed": False, "final_holdout": "UNTOUCHED"}
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derived-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_inventory(args.derived_root, args.inventory)
    if args.output:
        if args.output.exists():
            raise InventoryVerificationError(f"refusing to overwrite verification receipt: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
