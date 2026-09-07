"""Verify one immutable, outcome-blind R3 v8 guardian receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ops.r3 import r3_ops
from ops.r3.r3_v8_guardian import GUARDIAN_RECORD_TYPE, RECEIPT_FIELDS, _canonical_json


def verify(path: Path) -> dict[str, Any]:
    value = r3_ops._load_json_object(Path(path))
    if set(value) != RECEIPT_FIELDS:
        raise r3_ops.OperationsAuditError(f"guardian receipt schema drift: {sorted(set(value) ^ RECEIPT_FIELDS)}")
    if value.get("record_type") != GUARDIAN_RECORD_TYPE:
        raise r3_ops.OperationsAuditError("guardian receipt record type is invalid")
    for field in ("guardian_lock_path", "collector_lock_path"):
        candidate = Path(str(value.get(field, "")))
        if not candidate.is_absolute():
            raise r3_ops.OperationsAuditError(f"{field} must be absolute")
    if value.get("outcomes_accessed") is not False:
        raise r3_ops.OperationsAuditError("outcome firewall is not false")
    if value.get("final_holdout") != "UNTOUCHED":
        raise r3_ops.OperationsAuditError("final holdout firewall is not UNTOUCHED")
    if value.get("r2b2") != "NOT_ACCESSED":
        raise r3_ops.OperationsAuditError("R2B2 firewall is not NOT_ACCESSED")
    if value.get("forceorder_v3_migration") != "NOT_STARTED":
        raise r3_ops.OperationsAuditError("ForceOrder V3 firewall is not NOT_STARTED")
    recorded_hash = str(value.get("receipt_body_sha256", ""))
    if len(recorded_hash) != 64 or any(char not in "0123456789abcdefABCDEF" for char in recorded_hash):
        raise r3_ops.OperationsAuditError("receipt_body_sha256 is not SHA256")
    body = dict(value)
    body.pop("receipt_body_sha256")
    computed = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    if computed != recorded_hash.lower():
        raise r3_ops.OperationsAuditError("receipt_body_sha256 mismatch")
    r3_ops._reject_forbidden(value, context="guardian receipt")
    return {"status": "PASS", "path": str(Path(path).resolve()), "receipt_body_sha256": recorded_hash.lower(), "decision": value["decision"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(_canonical_json(verify(args.path)))
        return 0
    except (OSError, ValueError, r3_ops.OperationsAuditError) as exc:
        print(f"R3_V8_GUARDIAN_RECEIPT_INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
