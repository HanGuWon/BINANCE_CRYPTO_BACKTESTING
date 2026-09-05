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
import os
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


FEATURES = {
    "derivatives.premium": "premium",
    "derivatives.premium_zscore": "premium_zscore90",
}
REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_R2B_MANIFEST = REPO_ROOT / "campaigns" / "r2b_restricted_derivatives_v1" / "premium_archive_manifest.csv"
ROOT_DECLARATION_COLUMNS = ("causal_root", "raw_root", "acquisition_root", "data_root")
ROOT_HASH_COLUMNS = ("causal_root_tree_sha256", "raw_root_tree_sha256", "acquisition_root_sha256", "data_root_tree_sha256")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
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


def _nonempty(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _declared_manifest_value(manifest: pd.DataFrame, columns: tuple[str, ...]) -> str | None:
    values: set[str] = set()
    for column in columns:
        if column not in manifest:
            continue
        values.update(value for value in (_nonempty(item) for item in manifest[column]) if value is not None)
    if len(values) > 1:
        raise ValueError(f"premium manifest contains conflicting root declarations: {sorted(values)}")
    return next(iter(values), None)


def _resolve_archive_path(local_path: object, *, raw_root: Path | None) -> Path:
    value = _nonempty(local_path)
    if value is None:
        raise ValueError("premium manifest contains a blank local_path")
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        normalized = value.replace("\\", "/")
        marker = "data/raw/um/premiumIndexKlines/"
        lower = normalized.casefold()
        marker_index = lower.find(marker)
        if raw_root is not None and marker_index >= 0:
            suffix = normalized[marker_index + len(marker) :]
            resolved = (raw_root / Path(suffix)).resolve()
        else:
            resolved = (REPO_ROOT / candidate).resolve()
    if raw_root is not None:
        root = raw_root.resolve()
        try:
            os.path.commonpath([str(root), str(resolved)])
            if os.path.commonpath([str(root), str(resolved)]) != str(root):
                raise ValueError(f"premium archive escapes declared raw root: {resolved}")
        except ValueError as exc:
            raise ValueError(f"premium archive escapes declared raw root: {resolved}") from exc
    return resolved


def _verify_archive_objects(manifest: pd.DataFrame, *, raw_root: Path | None) -> dict[str, int]:
    required = {"local_path", "published_sha256", "computed_sha256"}
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"premium manifest missing archive verification columns: {sorted(missing)}")
    seen: dict[Path, tuple[str, str]] = {}
    missing_count = checksum_failures = size_failures = 0
    for row in manifest.itertuples(index=False):
        path = _resolve_archive_path(getattr(row, "local_path"), raw_root=raw_root)
        expected = str(getattr(row, "computed_sha256")).strip().lower()
        published = str(getattr(row, "published_sha256")).strip().lower()
        if path in seen:
            if seen[path] != (expected, published):
                raise ValueError(f"premium manifest has conflicting checksums for one archive: {path}")
            continue
        seen[path] = (expected, published)
        if not path.is_file():
            missing_count += 1
            continue
        computed = sha256_file(path)
        if computed != expected or computed != published:
            checksum_failures += 1
        object_size = getattr(row, "object_size", None)
        if object_size is not None and not pd.isna(object_size):
            try:
                if path.stat().st_size != int(object_size):
                    size_failures += 1
            except (TypeError, ValueError):
                size_failures += 1
    if missing_count or checksum_failures or size_failures:
        raise ValueError(
            "premium archive verification failed: "
            f"missing={missing_count}, checksum_failures={checksum_failures}, size_failures={size_failures}"
        )
    return {"archive_objects_verified": len(seen), "archive_missing_count": 0, "archive_checksum_failures": 0, "archive_size_failures": 0}


def validate_premium_manifest(
    path: Path,
    *,
    expected_root: Path | None = None,
    expected_root_sha256: str | None = None,
    verify_archives: bool = False,
) -> pd.DataFrame:
    """Validate the authoritative R2B premium archive manifest.

    The historical R1 derivative manifest is intentionally rejected: accepting
    it silently recreates the BTC/ETH-only provenance bug this audit is meant
    to detect.
    """
    resolved = path.resolve()
    if resolved.name == "derivative_archive_manifest.csv" or "r1_full_history_v1" in {p.lower() for p in resolved.parts}:
        raise ValueError(f"historical R1 anchor manifest is not valid for R2B: {resolved}")
    manifest = pd.read_csv(resolved)
    required = {"dataset", "market", "interval", "symbol", "integrity_status", "published_sha256", "computed_sha256"}
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"premium manifest missing required columns: {sorted(missing)}")
    if set(manifest["dataset"].dropna().astype(str)) != {"premiumIndexKlines"}:
        raise ValueError("R2B premium manifest must contain only dataset=premiumIndexKlines")
    if set(manifest["market"].dropna().astype(str)) != {"um"}:
        raise ValueError("R2B premium manifest must contain only market=um")
    if set(manifest["interval"].dropna().astype(str)) != {"15m"}:
        raise ValueError("R2B premium manifest must contain only interval=15m")
    bad_status = manifest[~manifest["integrity_status"].astype(str).eq("PASS")]
    if not bad_status.empty:
        raise ValueError(f"premium manifest contains checksum/integrity failures: {len(bad_status)}")
    sha_mismatch = manifest["published_sha256"].astype(str).str.lower() != manifest["computed_sha256"].astype(str).str.lower()
    if sha_mismatch.any():
        raise ValueError(f"premium manifest contains checksum mismatches: {int(sha_mismatch.sum())}")
    malformed_sha = ~manifest["published_sha256"].astype(str).str.strip().map(lambda value: bool(SHA256_RE.fullmatch(value))) | ~manifest["computed_sha256"].astype(str).str.strip().map(lambda value: bool(SHA256_RE.fullmatch(value)))
    if malformed_sha.any():
        raise ValueError(f"premium manifest contains malformed SHA256 values: {int(malformed_sha.sum())}")
    if manifest.empty or manifest["symbol"].astype(str).nunique() < 3:
        raise ValueError("premium manifest resolves to an unexpectedly small symbol set; refusing R1-style anchor")
    declared_root = _declared_manifest_value(manifest, ROOT_DECLARATION_COLUMNS)
    declared_root_sha256 = _declared_manifest_value(manifest, ROOT_HASH_COLUMNS)
    if expected_root is not None:
        if declared_root is not None and Path(declared_root).resolve() != expected_root.resolve():
            raise ValueError(f"premium manifest root declaration conflicts with causal root: {declared_root}")
        if declared_root is not None and Path(declared_root).resolve() != expected_root.resolve():
            raise ValueError("premium manifest root declaration is not the expected causal root")
    if expected_root_sha256 is not None and declared_root_sha256 != expected_root_sha256.lower():
        raise ValueError("premium manifest root hash conflicts with causal root")
    if verify_archives:
        _verify_archive_objects(manifest, raw_root=expected_root)
    return manifest


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


def audit(
    panel_root: Path,
    derivative_manifest: Path,
    dataset_probe: Path,
    feature_availability: Path,
    *,
    expected_raw_root: Path | None = None,
    expected_raw_root_sha256: str | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    resolved_manifest = derivative_manifest.resolve()
    if resolved_manifest != AUTHORITATIVE_R2B_MANIFEST.resolve():
        raise ValueError(
            "R2B coverage audit requires the authoritative acquisition manifest: "
            f"{AUTHORITATIVE_R2B_MANIFEST.resolve()}"
        )
    premium_manifest = validate_premium_manifest(
        derivative_manifest,
        expected_root=expected_raw_root,
        expected_root_sha256=expected_raw_root_sha256,
        verify_archives=True,
    )
    acquired_symbols = set(premium_manifest["symbol"].astype(str))
    files = sorted(panel_root.glob("market=um/symbol=*/timeframe=*/year=*/part-000.parquet"))
    if not files:
        raise FileNotFoundError(f"no UM panel partitions under {panel_root}")
    frames = [_scan_partition(path) for path in files]
    frame = pd.concat(frames, ignore_index=True)
    panel_symbols = set(frame["symbol"].astype(str).unique())
    premium_symbols = set(frame.loc[frame["premium"].notna(), "symbol"].astype(str)) if "premium" in frame else set()
    # Four universe symbols have no premium archive and therefore legitimately
    # remain NO_PRIOR_OBSERVATION.  A manifest/root conflict is proven by finite
    # premium observations whose symbols are absent from the acquisition lineage.
    missing_archives = sorted(premium_symbols - acquired_symbols)
    if missing_archives:
        raise ValueError(f"premium manifest conflicts with causal panel root; missing symbols: {missing_archives[:10]}")
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
        "premium_manifest_sha256": sha256_file(derivative_manifest.resolve()),
        "premium_manifest_path": str(derivative_manifest.resolve()),
        "premium_manifest_declared_root": _declared_manifest_value(premium_manifest, ROOT_DECLARATION_COLUMNS),
        "premium_manifest_declared_root_sha256": _declared_manifest_value(premium_manifest, ROOT_HASH_COLUMNS),
        "premium_archive_objects_verified": True,
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
    parser.add_argument("--derivative-manifest", type=Path, default=Path("campaigns/r2b_restricted_derivatives_v1/premium_archive_manifest.csv"))
    parser.add_argument("--dataset-probe", type=Path, default=Path("data/census/r1_full_history_v1/census_summary.json"))
    parser.add_argument("--feature-availability", type=Path, default=Path("campaigns/r1_final_panel_v1/feature_availability_final.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("campaigns/r2b_restricted_derivatives_v1"))
    parser.add_argument("--expected-raw-root", type=Path, default=None, help="causal raw root used to resolve manifest local_path values")
    parser.add_argument("--expected-raw-root-sha256", default=None, help="declared causal raw-root tree hash")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    coverage, summary = audit(
        args.panel_root,
        args.derivative_manifest,
        args.dataset_probe,
        args.feature_availability,
        expected_raw_root=args.expected_raw_root,
        expected_raw_root_sha256=args.expected_raw_root_sha256,
    )
    coverage_path = args.out_dir / "premium_coverage_audit.csv"
    summary_path = args.out_dir / "premium_provenance_summary.json"
    coverage_bytes = coverage.to_csv(index=False).encode("utf-8")
    if coverage_path.exists() and coverage_path.read_bytes() != coverage_bytes:
        raise ValueError(f"immutable audit artifact already exists with different bytes: {coverage_path}")
    if not coverage_path.exists():
        coverage_path.write_bytes(coverage_bytes)
    summary["artifact_sha256"] = {"premium_coverage_audit.csv": hashlib.sha256(coverage_bytes).hexdigest()}
    summary_bytes = json.dumps(summary, indent=2, default=str).encode("utf-8")
    if summary_path.exists() and summary_path.read_bytes() != summary_bytes:
        raise ValueError(f"immutable provenance summary already exists with different bytes: {summary_path}")
    if not summary_path.exists():
        summary_path.write_bytes(summary_bytes)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
