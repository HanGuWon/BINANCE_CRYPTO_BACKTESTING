"""Fail-closed verifier for the causal R2B premium root."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

STEP = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}

def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).replace(chr(92), "/").encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()

def verify(root: Path, cutoff: pd.Timestamp) -> dict[str, object]:
    files = sorted(root.glob("market=um/symbol=*/timeframe=*/year=*/part-000.parquet"))
    if not files:
        raise SystemExit(f"no parquet partitions under {root}")
    rows = 0
    available = 0
    violations: list[str] = []
    timeframes: dict[str, int] = {}
    for path in files:
        frame = pd.read_parquet(path)
        required = {"timestamp", "premium", "premium_source_available_time", "premium_source_timestamp", "timeframe"}
        missing = required - set(frame.columns)
        if missing:
            violations.append(f"{path}: missing {sorted(missing)}")
            continue
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).astype("datetime64[ns, UTC]")
        frame["premium_source_available_time"] = pd.to_datetime(frame["premium_source_available_time"], utc=True).astype("datetime64[ns, UTC]")
        tf = str(frame["timeframe"].iloc[0])
        step = STEP[tf]
        matched = frame["premium"].notna()
        bad = matched & ((frame["premium_source_available_time"] >= (frame["timestamp"] + step)) | (frame["timestamp"] >= cutoff))
        if bad.any():
            violations.append(f"{path}: causal/cutoff violations={int(bad.sum())}")
        rows += len(frame)
        available += int(matched.sum())
        timeframes[tf] = timeframes.get(tf, 0) + len(frame)
    if violations:
        raise SystemExit(json.dumps({"violations": violations[:20], "violation_count": len(violations)}))
    return {"root": str(root.resolve()), "partition_files": len(files), "rows": rows, "available_premium_rows": available, "timeframe_rows": timeframes, "holdout_cutoff": cutoff.isoformat(), "tree_sha256": sha256_tree(root), "causal_guard": "PASS"}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--cutoff", default="2024-02-10T00:00:00Z")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = verify(args.root, pd.Timestamp(args.cutoff, tz="UTC"))
    if args.out:
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
