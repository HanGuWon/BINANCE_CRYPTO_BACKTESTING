"""Census, estimate, and optionally acquire native 1d ranking archives.

The script intentionally separates metadata estimation from downloading.  It
does not fetch intraday data and never reads a final holdout.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import hashlib
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from binance_research.census import asset_taxonomy_table
from binance_research.data import ArchiveRequest, BinanceArchiveClient, load_kline_archive, validate_klines
from binance_research.panel import select_verified_causal_liquidity_universe


MONTH_RE = re.compile(r"-(\d{4})-(\d{2})\.zip$")


def _month(key: str) -> str | None:
    match = MONTH_RE.search(Path(key).name)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _free_bytes(path: Path) -> int:
    return int(shutil.disk_usage(path).free)


def _summarize_1d_archive(path: Path) -> dict[str, object]:
    """Read only the native 1d fields needed for causal ranking and QA."""
    issues: list[str] = []
    frame = load_kline_archive(path)
    stamps = pd.to_datetime(frame["open_time"], utc=True)
    rows = int(len(frame))
    quote_volume = float(pd.to_numeric(frame["quote_volume"], errors="coerce").fillna(0).sum())
    timestamps = sorted(stamps.drop_duplicates())
    if stamps.duplicated().any():
        issues.append("DUPLICATE_TIMESTAMP")
    if len(timestamps) > 1:
        gaps = [right - left for left, right in zip(timestamps, timestamps[1:]) if right - left > pd.Timedelta(days=1)]
        if gaps:
            issues.append("MISSING_INTERVAL")
    impossible = ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1)) | (pd.to_numeric(frame["quote_volume"], errors="coerce") < 0))
    if impossible.any():
        issues.append("IMPOSSIBLE_OHLC")
    days = {timestamp.floor("D") for timestamp in timestamps}
    return {"row_count": rows, "observed_days": len(days), "quote_volume": quote_volume, "issue_codes": ";".join(sorted(set(issues))), "integrity_status": "PASS" if not issues else "ISSUES"}


def _funding_symbols(client: BinanceArchiveClient) -> set[str]:
    prefixes = client.discover_prefixes("data/futures/um/monthly/fundingRate/")
    return {prefix.rstrip("/").split("/")[-1].upper() for prefix in prefixes}


def _candidate_symbols(census_dir: Path, client: BinanceArchiveClient) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[tuple[str, str]] = []
    for market in ("spot", "um"):
        frame = pd.read_csv(census_dir / f"{market}_archive_symbol_census.csv")
        rows.extend((market, str(symbol)) for symbol in frame["symbol"])
    taxonomy = asset_taxonomy_table(rows, funding_verified_symbols=_funding_symbols(client))
    primary = taxonomy[taxonomy["primary_crypto_eligible"]].copy()
    return taxonomy, primary


def _list_symbol_1d(client: BinanceArchiveClient, market: str, symbol: str) -> list[dict[str, object]]:
    root = f"data/{'spot' if market == 'spot' else 'futures/um'}/monthly/klines/{symbol}/1d/"
    _, objects, pages = client.list_objects_v2(root)
    rows: list[dict[str, object]] = []
    for obj in objects:
        month = _month(obj.key)
        if month is None or not obj.key.endswith(".zip"):
            continue
        rows.append({"market": market, "symbol": symbol, "interval": "1d", "archive_month": month, "key": obj.key, "size": obj.size, "last_modified": obj.last_modified, "etag": obj.etag, "listing_pages": pages})
    return rows


def census_1d(census_dir: Path, output_dir: Path, *, workers: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    client = BinanceArchiveClient(Path("data/raw"), timeout=90, max_retries=3)
    taxonomy, primary = _candidate_symbols(census_dir, client)
    taxonomy.to_csv(output_dir / "asset_taxonomy.csv", index=False)
    candidates = [(str(row.market), str(row.symbol)) for row in primary.itertuples()]
    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_list_symbol_1d, client, market, symbol): (market, symbol) for market, symbol in candidates}
        for number, future in enumerate(as_completed(futures), start=1):
            records.extend(future.result())
            if number % 100 == 0:
                print(f"censused 1d prefixes {number}/{len(futures)}", flush=True)
    manifest = pd.DataFrame(records).sort_values(["market", "symbol", "archive_month"]).reset_index(drop=True)
    manifest.to_csv(output_dir / "volume_archive_manifest.csv", index=False)
    listed_bytes = int(pd.to_numeric(manifest.get("size", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    estimate = {
        "objects": int(len(manifest)),
        "compressed_bytes": listed_bytes,
        "estimated_extracted_bytes": int(listed_bytes * 4),
        "estimated_parquet_bytes": int(listed_bytes * 1.5),
        "estimated_temporary_peak_bytes": int(listed_bytes * 5),
        "free_disk_before_bytes": _free_bytes(Path.cwd()),
        "required_safety_margin_bytes": int(listed_bytes * 2),
        "primary_candidate_symbols": int(len(primary)),
        "status": "ESTIMATED_ONLY",
    }
    (output_dir / "volume_size_estimate.json").write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    print(json.dumps(estimate, indent=2))
    return taxonomy, manifest


def acquire_1d(manifest: pd.DataFrame, *, workers: int = 2) -> pd.DataFrame:
    client = BinanceArchiveClient(Path("data/raw"), timeout=90, max_retries=3)
    requests = []
    for row in manifest.itertuples():
        year, month = (int(part) for part in str(row.archive_month).split("-"))
        requests.append(ArchiveRequest(str(row.market), "klines", str(row.symbol), year, month, interval="1d"))
    requests = sorted(set(requests), key=lambda request: (request.market, request.symbol, request.year, request.month))

    def acquire(request: ArchiveRequest) -> dict[str, object]:
        relative = Path(request.market) / request.dataset / request.symbol / (request.interval or "")
        path = client.raw_root / relative / f"{request.symbol}-{request.interval}-{request.year:04d}-{request.month:02d}.zip"
        sidecar = path.with_suffix(path.suffix + ".manifest.json")
        if path.exists() and sidecar.exists():
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            computed = hashlib.sha256(path.read_bytes()).hexdigest()
            if computed != str(meta.get("computed_sha256", "")):
                raise RuntimeError(f"immutable cached archive checksum changed: {path}")
        else:
            path, manifest = client.download(request)
            meta = manifest.to_dict()
        frame = load_kline_archive(path)
        issues = validate_klines(frame, "1d")
        return {"market": request.market, "symbol": request.symbol, "archive_month": f"{request.year:04d}-{request.month:02d}", "raw_path": str(path), "row_count": len(frame), "first_timestamp": frame.open_time.min().isoformat() if len(frame) else None, "last_timestamp": frame.open_time.max().isoformat() if len(frame) else None, "published_sha256": meta.get("published_sha256"), "computed_sha256": meta.get("computed_sha256"), "integrity_status": "PASS" if not issues else "ISSUES", "issue_codes": ";".join(issue.code for issue in issues)}

    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(acquire, request): request for request in requests}
        for number, future in enumerate(as_completed(futures), start=1):
            request = futures[future]
            try:
                records.append(future.result())
            except Exception as exc:
                path = client.raw_root / request.market / request.dataset / request.symbol / (request.interval or "") / f"{request.symbol}-{request.interval}-{request.year:04d}-{request.month:02d}.zip"
                records.append({"market": request.market, "symbol": request.symbol, "archive_month": f"{request.year:04d}-{request.month:02d}", "raw_path": str(path) if path.exists() else None, "integrity_status": "ERROR", "issue_codes": f"{type(exc).__name__}:{exc}"})
            if number % 100 == 0:
                print(f"verified 1d archives {number}/{len(requests)}", flush=True)
    return pd.DataFrame(records).sort_values(["market", "symbol", "archive_month"])


def build_monthly_cohorts(manifest: pd.DataFrame, taxonomy: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    """Aggregate complete prior calendar months and freeze diagnostic cohorts."""
    census_rows = []
    for row in manifest.itertuples():
        integrity = getattr(row, "integrity_status", None)
        if integrity is None or (isinstance(integrity, float) and pd.isna(integrity)):
            raise RuntimeError("MISSING_INTEGRITY_PROVENANCE: row lacks integrity_status")
        if str(integrity) != "PASS":
            continue
        raw_path = Path(getattr(row, "raw_path", ""))
        if not raw_path.exists():
            continue
        month = pd.Period(str(row.archive_month), freq="M")
        expected_days = month.days_in_month
        summary = _summarize_1d_archive(raw_path)
        observed_days = int(summary["observed_days"])
        coverage = observed_days / expected_days
        census_rows.append({"market": row.market, "symbol": row.symbol, "volume_month": str(month), "prior_month_expected_days": expected_days, "prior_month_observed_days": observed_days, "coverage_ratio": coverage, "prior_month_quote_volume": float(summary["quote_volume"]), "volume_integrity_status": summary["integrity_status"], "issue_codes": summary["issue_codes"]})
    volumes = pd.DataFrame(census_rows)
    census_frames = []
    for market in ("spot", "um"):
        census = pd.read_csv(Path("data/census/r1_full_history_v1") / f"{market}_archive_symbol_census.csv")
        census_frames.append(census[["market", "symbol", "first_archive_month"]])
    census = pd.concat(census_frames, ignore_index=True).rename(columns={"first_archive_month": "first_archive_observed"})
    volumes = volumes.merge(census, on=["market", "symbol"], how="left")
    volumes["universe_month"] = (pd.PeriodIndex(volumes["volume_month"], freq="M") + 1).astype(str)
    volumes["first_observed"] = pd.to_datetime(volumes["first_archive_observed"].astype(str) + "-01", utc=True, errors="coerce")
    ranked = select_verified_causal_liquidity_universe(volumes, top_n=50, minimum_coverage_ratio=1.0)
    ranked.to_csv(output_dir / "universe_monthly.csv", index=False)
    summary = ranked.groupby(["market", "universe_month"], sort=True).agg(candidate_count=("symbol", "size"), eligible_count=("rank", lambda x: int(x.notna().sum())), top20=("selected_top20", "sum"), top50=("selected_top50", "sum"), top100=("selected_top100", "sum"), partial_prior_month=("eligibility_reason", lambda x: int(x.eq("PARTIAL_PRIOR_MONTH_EXCLUDED").sum())), membership_gap=("selected_top50", lambda x: int(x.sum() < 50))).reset_index()
    summary.to_csv(output_dir / "cohort_summary.csv", index=False)
    return ranked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-dir", type=Path, default=Path("data/census/r1_full_history_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--cohorts", action="store_true")
    args = parser.parse_args()
    taxonomy, listed = census_1d(args.census_dir, args.output_dir, workers=args.workers)
    if args.download:
        acquired = acquire_1d(listed, workers=args.workers)
        acquired.to_csv(args.output_dir / "volume_archive_acquisition.csv", index=False)
        estimate = json.loads((args.output_dir / "volume_size_estimate.json").read_text(encoding="utf-8"))
        estimate["status"] = "ACQUIRED"
        estimate["free_disk_after_bytes"] = _free_bytes(Path.cwd())
        (args.output_dir / "volume_size_estimate.json").write_text(json.dumps(estimate, indent=2), encoding="utf-8")
        acquisition_columns = [
            column
            for column in acquired.columns
            if column not in {"market", "symbol", "archive_month"}
        ]
        listed = listed.merge(
            acquired[["market", "symbol", "archive_month", *acquisition_columns]],
            on=["market", "symbol", "archive_month"],
            how="left",
        )
        listed.to_csv(args.output_dir / "volume_archive_manifest.csv", index=False)
    if args.cohorts:
        build_monthly_cohorts(listed, taxonomy, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
