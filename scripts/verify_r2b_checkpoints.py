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
STEP = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}
JANUARY_START = pd.Timestamp("2024-01-01T00:00:00Z")
HOLDOUT_START = pd.Timestamp("2024-02-10T00:00:00Z")


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
    counters = {"sign_violations": 0, "exact_next_open_violations": 0, "exact_horizon_exit_violations": 0, "source_availability_violations": 0, "per_symbol_overlap_violations": 0, "net_return_identity_violations": 0, "january_2024_violations": 0, "final_holdout_violations": 0, "schema_violations": 0, "trade_file_hash_violations": 0, "source_identity_violations": 0}
    expected_count_violations = int(len(units) != EXPECTED_UNITS or manifest.get("unit_count") != EXPECTED_UNITS)
    if manifest.get("final_holdout_status") != "UNTOUCHED":
        counters["final_holdout_violations"] += 1
    launch = json.loads((CAMPAIGN / "R2B_OUTCOME_LAUNCH_MANIFEST.json").read_text(encoding="utf-8"))
    for field in ("implementation_commit", "source_tree_sha256", "registry_sha256", "fold_registry_sha256", "causal_root_tree_sha256"):
        if manifest.get(field) != launch.get(field):
            counters["source_identity_violations"] += 1
    seen = set()
    status_counts: dict[str, int] = {}
    verified_units = 0
    total_trade_rows = 0
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
            counters["source_identity_violations"] += 1
        status = str(unit.get("status"))
        if status not in {"VALID", "INSUFFICIENT_TRADES"}:
            raise SystemExit(f"non-terminal status {uid}: {status}")
        trade_path = root / "trades" / f"{uid}.parquet"
        if not trade_path.exists():
            raise SystemExit(f"missing trade checkpoint {uid}")
        digest = hashlib.sha256(trade_path.read_bytes()).hexdigest()
        if digest != unit.get("trade_file_sha256"):
            counters["trade_file_hash_violations"] += 1
        trades = pd.read_parquet(trade_path)
        total_trade_rows += len(trades)
        verified_units += 1
        if len(trades) != int(unit.get("executed_trades", -1)):
            raise SystemExit(f"trade count mismatch {uid}")
        if set(trades.columns) != REQUIRED_TRADE_FIELDS:
            counters["schema_violations"] += 1
            continue
        step = STEP.get(str(unit.get("timeframe")))
        if step is None:
            counters["source_identity_violations"] += 1
            continue
        decision = pd.to_datetime(trades["decision_time"], utc=True)
        source = pd.to_datetime(trades["source_available_time"], utc=True)
        entry = pd.to_datetime(trades["entry_time"], utc=True)
        exit_ = pd.to_datetime(trades["exit_time"], utc=True)
        side = trades["side"].astype(str)
        signal = pd.to_numeric(trades["signal_value"], errors="coerce")
        counters["sign_violations"] += int((((side == "LONG") & (signal != 1)) | ((side == "SHORT") & (signal != -1)) | signal.isna()).sum())
        counters["exact_next_open_violations"] += int((entry - decision != step).sum())
        counters["exact_horizon_exit_violations"] += int((exit_ - entry != step * int(unit["horizon_bars"])).sum())
        counters["source_availability_violations"] += int((source >= entry).sum())
        counters["january_2024_violations"] += int((((decision >= JANUARY_START) & (decision < HOLDOUT_START)) | ((entry >= JANUARY_START) & (entry < HOLDOUT_START)) | ((exit_ >= JANUARY_START) & (exit_ < HOLDOUT_START))).sum())
        counters["final_holdout_violations"] += int(((decision >= HOLDOUT_START) | (entry >= HOLDOUT_START) | (exit_ >= HOLDOUT_START)).sum())
        calculated = pd.to_numeric(trades["gross_return"]) - 0.002 + pd.to_numeric(trades["funding_cashflow"])
        counters["net_return_identity_violations"] += int((abs(calculated - pd.to_numeric(trades["net_return"])) > 1e-12).sum())
        for _, group in trades.assign(_entry=entry, _exit=exit_).sort_values(["symbol", "_entry"]).groupby("symbol", sort=False):
            prior_exit = None
            for current_entry, current_exit in zip(group["_entry"], group["_exit"]):
                if prior_exit is not None and current_entry < prior_exit:
                    counters["per_symbol_overlap_violations"] += 1
                prior_exit = current_exit if prior_exit is None or current_exit > prior_exit else prior_exit
        status_counts[status] = status_counts.get(status, 0) + 1
    result = {"status": "PASS" if not any(counters.values()) and expected_count_violations == 0 else "FAIL", "expected_units": EXPECTED_UNITS, "verified_units": verified_units, "unit_count": len(units), "total_trade_rows": total_trade_rows, "status_counts": status_counts, "final_holdout_status": manifest.get("final_holdout_status"), "expected_count_violations": expected_count_violations, **counters}
    if result["status"] != "PASS":
        raise SystemExit(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
