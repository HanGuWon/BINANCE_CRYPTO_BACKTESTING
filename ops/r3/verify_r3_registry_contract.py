"""Verify the frozen six-row R3 trial registry without market data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "campaigns" / "r3_prospective_context_v1" / "trial_registry.csv"
EXPECTED_SHA256 = "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a"
EXPECTED_IDS = ["R3_H01", "R3_H02", "R3_H03", "R3_H04", "R3_H05", "R3_H06"]


def verify() -> dict[str, object]:
    digest = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("R3 registry SHA256 mismatch")
    with REGISTRY.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [str(row.get("hypothesis_id")) for row in rows]
    if ids != EXPECTED_IDS or len(rows) != 6:
        raise ValueError("R3 registry must contain exactly ordered R3_H01-R3_H06 rows")
    if any(str(row.get("primary", "")).upper() != "TRUE" for row in rows):
        raise ValueError("every R3 registry row must be primary")
    field_names = {str(name).lower() for name in (rows[0].keys() if rows else [])}
    if field_names.intersection({"gross_return", "net_return", "future_return", "pnl", "sharpe", "hit_rate", "outcome"}):
        raise ValueError("registry contains forbidden outcome fields")
    return {"status": "PASS", "registry": str(REGISTRY), "registry_sha256": digest, "hypothesis_ids": ids, "primary_count": len(rows), "metadata_only": True}


def main() -> int:
    argparse.ArgumentParser().parse_args()
    print(json.dumps(verify(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
