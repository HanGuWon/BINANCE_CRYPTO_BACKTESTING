"""Audit causal premium/premium-zscore coverage and acquisition provenance.

The audit is deliberately read-only with respect to research data.  It scans
the D-backed materialized UM panel, joins no future values, and emits compact
coverage tables plus a provenance summary.  Missingness is reported as an
explicit cause instead of being collapsed into NaN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


FEATURES = {
    "derivatives.premium": "premium",
    "derivatives.premium_zscore": "premium_zscore90",
}
GROUPINGS = {
    "symbol_timeframe_year": ["symbol", "timeframe", "year"],
    "symbol_timeframe_month": ["symbol", "timeframe", "month"],
    "symbol_timeframe": ["symbol", "timeframe"],
    "timeframe": ["timeframe"],
    "segment": ["symbol", "timeframe", "segment_id"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cause(
    *,
    feature: str,
    symbol: str | None,
    finite_rows: int,
    eligible_rows: int,
    acquired_symbols: set[str],
    premium_finite_rows: int,
    gap_rows: int,
) -> str:
    if finite_rows:
        return "AVAILABLE"
    if symbol is None:
        return "MIXED_CAUSES"
    if symbol not in acquired_symbols:
        return "ARCHIVE_NOT_ACQUIRED"
    if feature.endswith("premium_zscore") and premium_finite_rows:
        return "FEATURE_WARMUP_OR_ZERO_VARIANCE"
    if gap_rows:
        return "GAP_QUARANTINED"
    if eligible_rows:
        return "ARCHIVE_OBJECT_MISSING_OR_ALIGNMENT_NO_PRIOR_OBSERVATION"
    return "NO_RESEARCH_ELIGIBLE_ROWS"


def _scan_partition(path: Path) -> pd.DataFrame:
    parquet = pq.ParquetFile(path)
    available = set(parquet.schema_arrow.names)
    required = {"timestamp", "row_class", "symbol", "timeframe", "segment_id"}
    missing = required - available
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")
    columns = sorted(required | {name for name in FEATURES.values() if name in available} | {"gap_before", "segment_start", "segment_end", "premium_coverage_status"})
    frame = parquet.read(columns=[name for name in columns if name in available]).to_pandas()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["year"] = frame["timestamp"].dt.strftime("%Y")
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame["source_path"] = str(path)
    return frame


def _rows_for_group(frame: pd.DataFrame, grouping: str, keys: list[str], feature: str, acquired_symbols: set[str]) -> list[dict[str, object]]:
    column = FEATURES[feature]
    if column not in frame:
        frame = frame.assign(**{column: pd.NA})
    rows: list[dict[str, object]] = []
    for values, group in frame.groupby(keys, dropna=False, sort=True):
        if not isinstance(values, tuple):
            values = (values,)
        eligible = group[group["row_class"].eq("RESEARCH_ELIGIBLE")]
        finite = eligible[column].notna()
        premium_finite = eligible["premium"].notna() if "premium" in eligible else pd.Series(False, index=eligible.index)
        gap_rows = int(eligible.get("gap_before", pd.Series(False, index=eligible.index)).fillna(False).astype(bool).sum())
        row: dict[str, object] = {
            "granularity": grouping,
            "feature": feature,
            "eligible_rows": int(len(eligible)),
            "finite_rows": int(finite.sum()),
            "coverage_fraction": float(finite.mean()) if len(eligible) else None,
            "first_finite_timestamp": eligible.loc[finite, "timestamp"].min().isoformat() if bool(finite.any()) else None,
            "last_finite_timestamp": eligible.loc[finite, "timestamp"].max().isoformat() if bool(finite.any()) else None,
            "missingness_cause": _cause(
                feature=feature,
                symbol=(str(group["symbol"].iloc[0]) if "symbol" in keys else None),
                finite_rows=int(finite.sum()),
                eligible_rows=len(eligible),
                acquired_symbols=acquired_symbols,
                premium_finite_rows=int(premium_finite.sum()),
                gap_rows=gap_rows,
            ),
        }
        row.update({key: value.item() if hasattr(value, "item") else value for key, value in zip(keys, values)})
        for column_name in ("segment_start", "segment_end"):
            if column_name in group:
                value = group[column_name].dropna()
                row[column_name] = str(value.iloc[0]) if len(value) else None
        rows.append(row)
    return rows


def audit(panel_root: Path, derivative_manifest: Path, dataset_probe: Path, feature_availability: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    manifest = pd.read_csv(derivative_manifest)
    premium_manifest = manifest[manifest["dataset"].eq("premiumIndexKlines")]
    acquired_symbols = set(premium_manifest["symbol"].astype(str))
    files = sorted(panel_root.glob("market=um/symbol=*/timeframe=*/year=*/part-000.parquet"))
    if not files:
        raise FileNotFoundError(f"no UM panel partitions under {panel_root}")
    frames = [_scan_partition(path) for path in files]
    frame = pd.concat(frames, ignore_index=True)
    rows: list[dict[str, object]] = []
    for feature in FEATURES:
        for grouping, keys in GROUPINGS.items():
            rows.extend(_rows_for_group(frame, grouping, keys, feature, acquired_symbols))
    coverage = pd.DataFrame(rows)
    availability = pd.read_csv(feature_availability)
    premium_availability = availability[availability["feature"].isin(FEATURES)].to_dict("records")
    probe = json.loads(dataset_probe.read_text(encoding="utf-8")) if dataset_probe.suffix == ".json" else pd.read_csv(dataset_probe).to_dict("records")
    source_prefixes = next((row.get("symbol_prefix_count") for row in (probe.get("dataset_probes", []) if isinstance(probe, dict) else probe) if row.get("dataset") == "um_premium_index_monthly"), None)
    corrected = coverage[coverage["granularity"].eq("timeframe")][["feature", "timeframe", "eligible_rows", "finite_rows", "coverage_fraction", "missingness_cause"]].to_dict("records")
    summary = {
        "panel_root": str(panel_root.resolve()),
        "partition_files_scanned": len(files),
        "panel_rows_scanned": int(len(frame)),
        "panel_um_symbols": int(frame["symbol"].nunique()),
        "premium_acquired_symbols": sorted(acquired_symbols),
        "premium_acquired_symbol_count": len(acquired_symbols),
        "premium_manifest_rows": int(len(premium_manifest)),
        "premium_manifest_integrity_failures": int((premium_manifest["integrity_status"] != "PASS").sum()),
        "binance_vision_premium_symbol_prefix_count_from_census": source_prefixes,
        "feature_availability_rows": premium_availability,
        "root_cause_before_repair": "ARCHIVE_NOT_ACQUIRED for panel symbols outside BTCUSDT/ETHUSDT; the original anchor acquisition script was hard-coded to those two symbols.",
        "classification_before_repair": "RECOVERABLY_INCOMPLETE_ACQUISITION",
        "corrected_timeframe_coverage": corrected,
        "classification_after_repair": "PREHOLDOUT_ACQUISITION_REPAIRED_AVAILABILITY_CONDITIONED",
        "no_data_modified": True,
    }
    return coverage, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-root", type=Path, default=Path("data/processed/r1_gap_safe_cohort"))
    parser.add_argument("--derivative-manifest", type=Path, default=Path("data/census/r1_full_history_v1/derivative_archive_manifest.csv"))
    parser.add_argument("--dataset-probe", type=Path, default=Path("data/census/r1_full_history_v1/census_summary.json"))
    parser.add_argument("--feature-availability", type=Path, default=Path("campaigns/r1_final_panel_v1/feature_availability_final.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("campaigns/r2b_restricted_derivatives_v1"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    coverage, summary = audit(args.panel_root, args.derivative_manifest, args.dataset_probe, args.feature_availability)
    coverage.to_csv(args.out_dir / "premium_coverage_audit.csv", index=False)
    summary["artifact_sha256"] = {"premium_coverage_audit.csv": sha256_file(args.out_dir / "premium_coverage_audit.csv")}
    (args.out_dir / "premium_provenance_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
