"""Fail-closed verifier for the causal R2B premium root."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

STEP = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}
EXPECTED_PARTITIONS = 1467
EXPECTED_ROWS = 8_357_398
EXPECTED_TREE_SHA256 = "6eef4e59225cb45c2833452a883249b11f03469298c1ecfb3837c5f4aaa27a7d"
CONSTITUENT_CLOSE_EPSILON = pd.Timedelta(milliseconds=1)

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
        required = {"timestamp", "premium", "premium_source_available_time", "premium_source_timestamp", "timeframe", "symbol", "segment_id", "gap_before", "premium_zscore90"}
        missing = required - set(frame.columns)
        if missing:
            violations.append(f"{path}: missing {sorted(missing)}")
            continue
        for column in ("timestamp", "premium_source_available_time", "premium_source_timestamp"):
            frame[column] = pd.to_datetime(frame[column], utc=True).astype("datetime64[ns, UTC]")
        tf = str(frame["timeframe"].iloc[0])
        if tf not in STEP:
            violations.append(f"{path}: unexpected timeframe={tf}")
            continue
        step = STEP[tf]
        if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
            violations.append(f"{path}: timestamps are duplicated or unsorted")
        if frame["symbol"].nunique() != 1 or frame["symbol"].iloc[0] not in str(path):
            violations.append(f"{path}: symbol/path mismatch")
        if frame["timeframe"].nunique() != 1 or f"timeframe={tf}" not in str(path):
            violations.append(f"{path}: timeframe/path mismatch")
        if frame["timestamp"].ge(cutoff).any():
            violations.append(f"{path}: holdout timestamps present")
        matched = frame["premium"].notna()
        source_available = frame["premium_source_available_time"]
        source_timestamp = frame["premium_source_timestamp"]
        bad = matched & (source_available.isna() | source_timestamp.isna() | (source_available >= (frame["timestamp"] + step)))
        if bad.any():
            violations.append(f"{path}: causal/cutoff violations={int(bad.sum())}")
        if (matched & source_timestamp.gt(frame["timestamp"])).any():
            violations.append(f"{path}: source timestamp is after the decision bar")
        expected_span = step - CONSTITUENT_CLOSE_EPSILON
        span_bad = matched & ((source_available - source_timestamp) != expected_span)
        if span_bad.any():
            violations.append(f"{path}: availability is not the native/max constituent close span={int(span_bad.sum())}")
        previous_timestamp = frame["timestamp"].shift()
        gap_rows = frame["gap_before"].fillna(False) & previous_timestamp.notna()
        if (gap_rows & ((frame["timestamp"] - previous_timestamp) <= step)).any():
            violations.append(f"{path}: gap_before is set without a preceding timeframe gap")
        if frame.loc[frame["premium_zscore90"].notna(), "premium"].isna().any():
            violations.append(f"{path}: z-score present without premium")
        rows += len(frame)
        available += int(matched.sum())
        timeframes[tf] = timeframes.get(tf, 0) + len(frame)
    if len(files) != EXPECTED_PARTITIONS:
        violations.append(f"partition count {len(files)} != expected {EXPECTED_PARTITIONS}")
    if rows != EXPECTED_ROWS:
        violations.append(f"row count {rows} != expected {EXPECTED_ROWS}")
    tree_sha256 = sha256_tree(root)
    if tree_sha256 != EXPECTED_TREE_SHA256:
        violations.append(f"tree sha {tree_sha256} != expected {EXPECTED_TREE_SHA256}")
    if violations:
        raise SystemExit(json.dumps({"violations": violations[:20], "violation_count": len(violations)}))
    return {"root": str(root.resolve()), "partition_files": len(files), "rows": rows, "available_premium_rows": available, "timeframe_rows": timeframes, "holdout_cutoff": cutoff.isoformat(), "tree_sha256": tree_sha256, "causal_guard": "PASS", "strict_availability_rule": "source_available_time < next_executable_open_time", "derived_availability_rule": "maximum constituent 15m close time"}

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
