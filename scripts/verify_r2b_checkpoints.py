"""Fail-closed verifier for a completed R2B checkpoint root."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

EXPECTED_UNITS = 576


def verify(root: Path) -> dict[str, object]:
    manifest_path = root / "run_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing run_manifest.json: {root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    units = manifest.get("units", [])
    if len(units) != EXPECTED_UNITS or manifest.get("unit_count") != EXPECTED_UNITS:
        raise SystemExit(f"unit count {len(units)} != {EXPECTED_UNITS}")
    if manifest.get("final_holdout_status") != "UNTOUCHED":
        raise SystemExit("final holdout is not marked UNTOUCHED")
    seen = set()
    status_counts: dict[str, int] = {}
    for unit in units:
        uid = str(unit["unit_id"])
        if uid in seen:
            raise SystemExit(f"duplicate unit {uid}")
        seen.add(uid)
        status = str(unit.get("status"))
        if status not in {"VALID", "INSUFFICIENT_TRADES"}:
            raise SystemExit(f"non-terminal status {uid}: {status}")
        trade_path = root / "trades" / f"{uid}.parquet"
        if not trade_path.exists():
            raise SystemExit(f"missing trade checkpoint {uid}")
        digest = hashlib.sha256(trade_path.read_bytes()).hexdigest()
        if digest != unit.get("trade_file_sha256"):
            raise SystemExit(f"trade hash mismatch {uid}")
        trades = pd.read_parquet(trade_path)
        if len(trades) != int(unit.get("executed_trades", -1)):
            raise SystemExit(f"trade count mismatch {uid}")
        for column in ("decision_time", "entry_time", "exit_time"):
            if column in trades:
                stamps = pd.to_datetime(trades[column], utc=True)
                if stamps.ge(pd.Timestamp("2024-01-01T00:00:00Z")).any():
                    raise SystemExit(f"January 2024 or holdout row in {uid}")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {"status": "PASS", "unit_count": len(units), "status_counts": status_counts, "final_holdout_status": "UNTOUCHED"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
