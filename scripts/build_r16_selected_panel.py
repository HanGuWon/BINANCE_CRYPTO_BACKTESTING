"""Estimate/acquire/materialize only frozen R1.6 Top-50 cohort context."""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from binance_research.data import ArchiveRequest, BinanceArchiveClient, DataIntegrityError, load_kline_archive
from binance_research.features import CoreFeatureEngine, compute_gap_safe_features
from binance_research.panel import resample_contiguous_source, write_partitioned_panel


def selected_manifest(cohorts: pd.DataFrame, census_dir: Path, *, top_column: str = "selected_top50") -> pd.DataFrame:
    selected = cohorts[cohorts[top_column].astype(bool)].copy()
    selected["universe_period"] = pd.PeriodIndex(selected["universe_month"], freq="M")
    selected["context_start"] = selected["universe_period"] - 2
    selected["context_end"] = selected["universe_period"]
    rows: list[pd.DataFrame] = []
    for market in ("spot", "um"):
        census = pd.read_csv(census_dir / f"{market}_archive_object_census.csv")
        census = census[(census["interval"] == "15m") & census["symbol"].isin(selected.loc[selected.market == market, "symbol"])]
        if census.empty:
            continue
        census["archive_period"] = pd.PeriodIndex(census["archive_month"], freq="M")
        wanted = selected.loc[selected.market == market, ["symbol", "context_start", "context_end"]].drop_duplicates()
        merged = census.merge(wanted, on="symbol", how="inner")
        merged = merged[(merged["archive_period"] >= merged["context_start"]) & (merged["archive_period"] <= merged["context_end"])].copy()
        rows.append(merged)
    if not rows:
        return pd.DataFrame()
    result = pd.concat(rows, ignore_index=True).drop_duplicates(["market", "symbol", "archive_month"])
    result["membership_month"] = result["archive_period"].astype(str)
    result["row_class"] = "WARMUP_CONTEXT_ONLY"
    selected_keys = set(zip(selected.market, selected.symbol, selected.universe_month))
    result.loc[[key in selected_keys for key in zip(result.market, result.symbol, result.membership_month)], "row_class"] = "RESEARCH_ELIGIBLE"
    return result.sort_values(["market", "symbol", "archive_month"]).reset_index(drop=True)


def estimate_selected(manifest: pd.DataFrame, output_dir: Path) -> dict[str, object]:
    bytes_ = int(pd.to_numeric(manifest["size"], errors="coerce").fillna(0).sum()) if len(manifest) else 0
    estimate = {"objects": int(len(manifest)), "compressed_bytes": bytes_, "estimated_extracted_bytes": bytes_ * 4, "estimated_parquet_bytes": int(bytes_ * 1.5), "estimated_temporary_peak_bytes": bytes_ * 5, "free_disk_before_bytes": int(shutil.disk_usage(Path.cwd()).free), "status": "ESTIMATED_ONLY"}
    (output_dir / "selected_panel_size_estimate.json").write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    return estimate


def acquire_selected(manifest: pd.DataFrame, *, workers: int = 2) -> pd.DataFrame:
    client = BinanceArchiveClient(Path("data/raw"), timeout=90, max_retries=3)
    requests = [ArchiveRequest(str(row.market), "klines", str(row.symbol), int(str(row.archive_month)[:4]), int(str(row.archive_month)[5:7]), interval="15m") for row in manifest.itertuples()]

    def acquire(request: ArchiveRequest) -> dict[str, object]:
        path, meta = client.download(request)
        return {"market": request.market, "symbol": request.symbol, "archive_month": f"{request.year:04d}-{request.month:02d}", "raw_path": str(path), "published_sha256": meta.published_sha256, "computed_sha256": meta.computed_sha256}

    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(acquire, request) for request in requests]
        for number, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if number % 50 == 0:
                print(f"acquired selected context {number}/{len(futures)}", flush=True)
    return pd.DataFrame(rows)


def materialize_selected(manifest: pd.DataFrame, output_root: Path) -> dict[str, object]:
    counts: dict[str, object] = {"objects": 0, "rows_15m": 0, "rows_1h": 0, "rows_4h": 0, "segments": 0, "gaps": 0, "research_eligible_rows": 0, "warmup_context_rows": 0, "failed_groups": []}
    for (market, symbol), group in manifest.groupby(["market", "symbol"], sort=True):
        frames = []
        for row in group.itertuples():
            path = Path(getattr(row, "raw_path", ""))
            if not path.exists():
                continue
            frame = load_kline_archive(path)
            frame["market"], frame["symbol"] = market, symbol
            frame["membership_month"] = row.membership_month
            frame["row_class"] = row.row_class
            frames.append(frame)
        if not frames:
            continue
        source = pd.concat(frames, ignore_index=True).drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        counts["objects"] += len(frames)
        try:
            bars_by_timeframe = (("15m", source), ("1h", resample_contiguous_source(source.drop(columns=["market", "symbol", "membership_month", "row_class"]), "1h", source_interval="15m")), ("4h", resample_contiguous_source(source.drop(columns=["market", "symbol", "membership_month", "row_class"]), "4h", source_interval="15m")))
            for timeframe, bars in bars_by_timeframe:
                bars = bars.rename(columns={"open_time": "timestamp"}).copy()
                bars["market"], bars["symbol"] = market, symbol
                bars["timeframe"] = timeframe
                bars["universe_month"] = bars["timestamp"].dt.to_period("M").astype(str)
                selected_months = set(group.loc[group["row_class"] == "RESEARCH_ELIGIBLE", "membership_month"].astype(str))
                bars["row_class"] = bars["universe_month"].map(lambda month: "RESEARCH_ELIGIBLE" if month in selected_months else "WARMUP_CONTEXT_ONLY")
                features = compute_gap_safe_features(CoreFeatureEngine(), bars.rename(columns={"timestamp": "open_time"}), timeframe)
                features = features.drop(columns=["open_time"], errors="ignore")
                panel = pd.concat([bars.reset_index(drop=True), features.reset_index(drop=True)], axis=1)
                panel = panel.loc[:, ~panel.columns.duplicated()]
                write_partitioned_panel(panel, output_root, provenance="r1.6-selected-cohort")
                counts[f"rows_{timeframe}"] += len(panel)
                counts["research_eligible_rows"] += int((panel.row_class == "RESEARCH_ELIGIBLE").sum())
                counts["warmup_context_rows"] += int((panel.row_class == "WARMUP_CONTEXT_ONLY").sum())
                if "segment_id" in panel:
                    counts["segments"] += int(panel.segment_id.nunique())
                    counts["gaps"] += int(panel.gap_before.sum())
        except DataIntegrityError as exc:
            counts["failed_groups"].append({"market": market, "symbol": symbol, "reason": str(exc)})
            continue
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1"))
    parser.add_argument("--census-dir", type=Path, default=Path("data/census/r1_full_history_v1"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    args = parser.parse_args()
    cohorts = pd.read_csv(args.campaign_dir / "universe_monthly.csv")
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.campaign_dir / "selected_intraday_manifest.csv"
    generated_manifest = selected_manifest(cohorts, args.census_dir)
    # Preserve an already-acquired manifest for materialization.  Rebuilding it
    # from the census would discard raw paths and checksums before the panel is
    # read, producing a misleading empty materialization.
    if args.acquire or not manifest_path.exists():
        manifest = generated_manifest
        manifest.to_csv(manifest_path, index=False)
    else:
        manifest = pd.read_csv(manifest_path)
        if len(manifest) != len(generated_manifest) or "raw_path" not in manifest.columns:
            manifest = generated_manifest
            manifest.to_csv(manifest_path, index=False)
    estimate = estimate_selected(manifest, args.campaign_dir)
    if args.acquire:
        acquired = acquire_selected(manifest, workers=args.workers)
        manifest = manifest.merge(acquired, on=["market", "symbol", "archive_month"], how="left")
        manifest.to_csv(args.campaign_dir / "selected_intraday_manifest.csv", index=False)
        estimate["status"] = "ACQUIRED"
        estimate["free_disk_after_bytes"] = int(shutil.disk_usage(Path.cwd()).free)
        (args.campaign_dir / "selected_panel_size_estimate.json").write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    if args.materialize:
        counts = materialize_selected(manifest, Path("data/processed/r1_gap_safe_cohort"))
        (args.campaign_dir / "selected_panel_summary.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
        print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
