"""Fail-closed verifier for a completed R2B checkpoint root."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

EXPECTED_UNITS = 576
ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r2b_restricted_derivatives_v1"
REQUIRED_TRADE_FIELDS = {"decision_time", "symbol", "side", "signal_variant", "signal_value", "source_open_time", "source_available_time", "entry_time", "exit_time", "gross_return", "funding_cashflow", "net_return"}


def verify(root: Path) -> dict[str, object]:
    manifest_path = root / "run_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing run_manifest.json: {root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_identity = {"implementation_commit", "source_tree_sha256", "registry_sha256", "fold_registry_sha256", "causal_root_tree_sha256", "head_commit"}
    if not required_identity <= set(manifest):
        raise SystemExit(f"run manifest missing identity fields: {sorted(required_identity - set(manifest))}")
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv")
    expected = {(str(f.fold_id), str(t.trial_id)): (str(t.timeframe), int(t.horizon_bars)) for _, f in folds.drop_duplicates(["fold_id", "timeframe", "horizon_bars"]).iterrows() for _, t in registry.iterrows() if str(f.timeframe) == str(t.timeframe) and int(f.horizon_bars) == int(t.horizon_bars)}
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
        key = (str(unit.get("fold_id")), str(unit.get("trial_id")))
        if key not in expected:
            raise SystemExit(f"unexpected fold/trial mapping {uid}")
        if (str(unit.get("timeframe")), int(unit.get("horizon_bars", -1))) != expected[key]:
            raise SystemExit(f"timeframe/horizon mismatch {uid}")
        if unit.get("implementation_commit") != manifest["implementation_commit"] or unit.get("source_tree_sha256") != manifest["source_tree_sha256"]:
            raise SystemExit(f"source identity mismatch {uid}")
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
        if set(trades.columns) != REQUIRED_TRADE_FIELDS:
            raise SystemExit(f"trade schema mismatch {uid}")
        for column in ("decision_time", "source_open_time", "source_available_time", "entry_time", "exit_time"):
            stamps = pd.to_datetime(trades[column], utc=True)
            if stamps.ge(pd.Timestamp("2024-01-01T00:00:00Z")).any():
                raise SystemExit(f"January 2024 or holdout row in {uid}")
        if (pd.to_datetime(trades["source_available_time"], utc=True) >= pd.to_datetime(trades["entry_time"], utc=True)).any():
            raise SystemExit(f"source availability is not before executable entry {uid}")
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
