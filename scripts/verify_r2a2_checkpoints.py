"""Verify a completed corrected R2A.2 checkpoint root without touching holdout data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from r2a_engine import HOLDOUT_BOUNDARY_BY_TF  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2a2_temporal_horizon_v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2/checkpoints_v9")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    root = Path(args.root)
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv")
    expected = {f"{t.trial_id}|{f.fold_id}" for t in registry.itertuples(index=False) for f in folds.itertuples(index=False)}
    manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    completed = set(manifest.get("completed_units", []))
    failed = manifest.get("failed_units", [])
    if manifest.get("registry_sha256") != sha256(CAMPAIGN / "trial_registry.csv"):
        raise RuntimeError("registry SHA mismatch")
    if manifest.get("full_registry_count") != len(registry):
        raise RuntimeError("registry count mismatch")
    if failed or completed != expected:
        raise RuntimeError(f"manifest incomplete: completed={len(completed)}/{len(expected)} failed={len(failed)}")

    files = sorted(root.glob("T*_F*_trades.parquet"))
    if {p.stem.removesuffix("_trades") for p in files} != expected:
        raise RuntimeError(f"parquet unit set mismatch: files={len(files)} expected={len(expected)}")
    rows = 0
    nonempty = 0
    holdout_violations = 0
    sign_violations = 0
    overlap_violations = 0
    required = {"decision_time", "symbol", "side", "signal_value", "entry_time", "exit_time", "gross_return", "funding_cashflow", "net_return"}
    for path in files:
        trial_id, fold_id = path.stem.removesuffix("_trades").split("_")
        trial = registry.loc[registry.trial_id == trial_id].iloc[0]
        df = pd.read_parquet(path)
        if not required.issubset(df.columns):
            raise RuntimeError(f"{path.name}: missing required fields")
        rows += len(df)
        if df.empty:
            continue
        nonempty += 1
        signal = pd.to_numeric(df.signal_value, errors="coerce")
        side = df.side.astype(str).str.upper()
        sign_violations += int(((side == "LONG") & (signal != 1)).sum() + ((side == "SHORT") & (signal != -1)).sum())
        boundary = HOLDOUT_BOUNDARY_BY_TF[str(trial.timeframe)]
        holdout_violations += int((pd.to_datetime(df.decision_time, utc=True) >= boundary).sum())
        entries = pd.to_datetime(df.entry_time, utc=True)
        exits = pd.to_datetime(df.exit_time, utc=True)
        work = pd.DataFrame({"symbol": df.symbol.astype(str), "entry": entries, "exit": exits}).sort_values(["symbol", "entry"])
        for _, grp in work.groupby("symbol", sort=False):
            overlap_violations += int((grp.entry.iloc[1:].to_numpy() < grp.exit.iloc[:-1].to_numpy()).sum())
    if sign_violations or holdout_violations or overlap_violations:
        raise RuntimeError(f"invariant failures sign={sign_violations} holdout={holdout_violations} overlap={overlap_violations}")
    report = {"status": "PASS", "checkpoint_root": str(root), "implementation_sha": manifest.get("implementation_sha"), "registry_sha256": manifest.get("registry_sha256"), "expected_units": len(expected), "verified_units": len(files), "rows": rows, "nonempty_units": nonempty, "sign_violations": 0, "holdout_violations": 0, "overlap_violations": 0, "holdout_boundaries": {k: v.isoformat() for k, v in HOLDOUT_BOUNDARY_BY_TF.items()}}
    out = Path(args.output) if args.output else root / "verification_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
