"""Estimate/acquire/materialize only frozen R1.6 Top-50 cohort context."""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import numpy as np

from binance_research.data import ArchiveRequest, BinanceArchiveClient, DataIntegrityError, load_kline_archive
from binance_research.features import CoreFeatureEngine, compute_gap_safe_features
from binance_research.panel import resample_contiguous_source, write_partitioned_panel


def selected_manifest(cohorts: pd.DataFrame, census_dir: Path, *, top_column: str = "selected_top50", interval: str = "15m") -> pd.DataFrame:
    selected = cohorts[cohorts[top_column].astype(bool)].copy()
    selected["universe_period"] = pd.PeriodIndex(selected["universe_month"], freq="M")
    selected["context_start"] = selected["universe_period"] - 2
    selected["context_end"] = selected["universe_period"]
    rows: list[pd.DataFrame] = []
    for market in ("spot", "um"):
        census = pd.read_csv(census_dir / f"{market}_archive_object_census.csv")
        census = census[(census["interval"] == interval) & census["symbol"].isin(selected.loc[selected.market == market, "symbol"])]
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


OFF_GRID_AUDIT_SYMBOLS = {("spot", symbol) for symbol in ("BCCUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LTCUSDT", "NEOUSDT")}


def quarantine_local_off_grid_rows(source: pd.DataFrame, market: str, symbol: str) -> tuple[pd.DataFrame, int]:
    """Remove every off-grid row (absolute UTC phase check), never snap.

    Only the six audited February-2018 spot series may contain off-grid rows;
    any other series fails closed. The normal return-to-grid row is preserved.
    """
    stamps = pd.to_datetime(source["open_time"], utc=True)
    step_ns = int(pd.Timedelta(minutes=15).value)
    off_grid = (stamps.astype("datetime64[ns, UTC]").astype("int64") % step_ns) != 0
    if not off_grid.any():
        return source, 0
    if (market, symbol) not in OFF_GRID_AUDIT_SYMBOLS:
        raise DataIntegrityError("unexpected off-grid rows for unaudited series " + market + "/" + symbol)
    mask = off_grid.to_numpy()
    return source.loc[~mask].copy(), int(mask.sum())


def estimate_selected(manifest: pd.DataFrame, output_dir: Path) -> dict[str, object]:
    bytes_ = int(pd.to_numeric(manifest["size"], errors="coerce").fillna(0).sum()) if len(manifest) else 0
    estimate = {"objects": int(len(manifest)), "compressed_bytes": bytes_, "estimated_extracted_bytes": bytes_ * 4, "estimated_parquet_bytes": int(bytes_ * 1.5), "estimated_temporary_peak_bytes": bytes_ * 5, "free_disk_before_bytes": int(shutil.disk_usage(Path.cwd()).free), "status": "ESTIMATED_ONLY"}
    estimate_file = output_dir / "selected_panel_size_estimate.json"
    if output_dir.is_dir():
        (estimate_file).write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    return estimate


def acquire_selected(manifest: pd.DataFrame, *, workers: int = 2, timeframe: str = "15m") -> pd.DataFrame:
    client = BinanceArchiveClient(Path("data/raw"), timeout=90, max_retries=3)
    requests = [ArchiveRequest(str(row.market), "klines", str(row.symbol), int(str(row.archive_month)[:4]), int(str(row.archive_month)[5:7]), interval=timeframe) for row in manifest.itertuples()]

    def acquire(request: ArchiveRequest) -> dict[str, object]:
        path, meta = client.download(request)
        return {"market": request.market, "symbol": request.symbol, "archive_month": f"{request.year:04d}-{request.month:02d}", "raw_path": str(path), "published_sha256": meta.published_sha256, "computed_sha256": meta.computed_sha256, "timeframe": request.interval}

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
        source, quarantined_rows = quarantine_local_off_grid_rows(source, market, symbol)
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


def materialize_native_selected(manifest: pd.DataFrame, *, timeframe: str, output_root: Path) -> dict[str, object]:
    """Materialize ONLY the native timeframe bars; never resample other grids."""
    counts: dict[str, object] = {"objects": 0, f"rows_{timeframe}": 0, "segments": 0, "gaps": 0, "research_eligible_rows": 0, "warmup_context_rows": 0, "failed_groups": [], "quarantined_off_grid_rows": 0}
    for (market, symbol), group in manifest.groupby(["market", "symbol"], sort=True):
        frames = []
        for row in group.itertuples():
            path = Path(getattr(row, "raw_path", ""))
            if not path.exists():
                continue
            published = getattr(row, "published_sha256", None)
            computed = getattr(row, "computed_sha256", None)
            if not published or not computed or str(published) != str(computed):
                raise DataIntegrityError(f"manifest checksum provenance invalid for {market}/{symbol}/{row.archive_month}")
            frame = load_kline_archive(path)
            frame["market"], frame["symbol"] = market, symbol
            frame["membership_month"] = row.membership_month
            frame["row_class"] = row.row_class
            frames.append(frame)
        if not frames:
            continue
        source = pd.concat(frames, ignore_index=True).drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        source, quarantined = quarantine_local_off_grid_rows(source, market, symbol)
        counts["quarantined_off_grid_rows"] = int(counts["quarantined_off_grid_rows"]) + quarantined
        counts["objects"] += len(frames)
        try:
            bars = resample_contiguous_source(source.drop(columns=["market", "symbol", "membership_month", "row_class"]), timeframe, source_interval=timeframe)
        except DataIntegrityError as exc:
            counts["failed_groups"].append({"market": market, "symbol": symbol, "reason": str(exc)})
            continue
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
        panel = attach_btc_context(panel, btc_source_market=market, timeframe=timeframe)
        if market == "um":
            panel = attach_um_funding(panel, symbol)
            panel = attach_um_premium(panel, timeframe)
        provenance = f"r1.7-selected-native-{timeframe}"
        write_partitioned_panel(panel, output_root, provenance=provenance)
        counts[f"rows_{timeframe}"] += len(panel)
        counts["research_eligible_rows"] += int((panel.row_class == "RESEARCH_ELIGIBLE").sum())
        counts["warmup_context_rows"] += int((panel.row_class == "WARMUP_CONTEXT_ONLY").sum())
        if "segment_id" in panel:
            counts["segments"] += int(panel.segment_id.nunique())
            counts["gaps"] += int(panel.gap_before.sum())
    return counts


def attach_btc_context(panel: pd.DataFrame, btc_source_market: str, timeframe: str) -> pd.DataFrame:
    """Causally backward-join same-timeframe BTCUSDT close from the given market."""
    source = panel[(panel["market"] == btc_source_market) & (panel["symbol"] == "BTCUSDT")][["timestamp", "close"]].rename(
        columns={"timestamp": "btc_source_timestamp", "close": "btc_close"}
    ).drop_duplicates("btc_source_timestamp").sort_values("btc_source_timestamp")
    frame = panel.copy()
    frame["_decision_ts"] = frame["timestamp"] - pd.Timedelta(milliseconds=1)
    merged = pd.merge_asof(
        frame.sort_values("_decision_ts"),
        source,
        left_on="_decision_ts",
        right_on="btc_source_timestamp",
        direction="backward",
    ).drop(columns=["_decision_ts"])
    merged["btc_source_market"] = btc_source_market
    merged["btc_source_symbol"] = "BTCUSDT"
    age_bars = (merged["_decision_ts"] - merged["btc_source_timestamp"]) if "_decision_ts" in merged else None
    merged["btc_source_age"] = None
    merged.loc[merged["btc_close"].notna(), "btc_source_age"] = (
        merged.loc[merged["btc_close"].notna(), "_decision_ts"] - merged.loc[merged["btc_close"].notna(), "btc_source_timestamp"]
    ) / pd.Timedelta(milliseconds={"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[timeframe])
    merged = merged.drop(columns=["_decision_ts"], errors="ignore")
    merged["btc_coverage_status"] = np.where(merged["btc_close"].notna(), "AVAILABLE", "NO_PRIOR_OBSERVATION")
    return merged


def attach_um_funding(panel: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Attach event-level 90-event funding z-score via backward-asof (causal)."""
    from binance_research.derivatives import backward_asof_event_feature, funding_event_zscore

    events = load_funding_events(symbol)
    if events is None or events.empty:
        frame = panel.copy()
        frame["funding_rate"] = np.nan
        frame["funding_zscore90"] = np.nan
        frame["funding_source_timestamp"] = pd.NaT
        frame["funding_coverage_status"] = "HISTORICAL_UNAVAILABLE"
        return frame
    scored = funding_event_zscore(events.rename(columns={"funding_rate": "funding_rate"}))
    scored = scored.rename(columns={"timestamp": "event_timestamp", "funding_zscore": "funding_zscore90"})
    frame = panel.rename(columns={"timestamp": "bar_timestamp"}).copy()
    frame["bar_timestamp"] = pd.to_datetime(frame["bar_timestamp"], utc=True)
    frame = backward_asof_event_feature(
        frame.sort_values("bar_timestamp"),
        scored[["event_timestamp", "funding_rate", "funding_zscore90"]],
        bar_timestamp="bar_timestamp",
        event_timestamp="event_timestamp",
        value_column="funding_rate",
    )
    zframe = backward_asof_event_feature(
        frame,
        scored[["event_timestamp", "funding_zscore90"]].rename(columns={"funding_zscore90": "_z"}),
        bar_timestamp="bar_timestamp",
        event_timestamp="event_timestamp",
        value_column="_z",
    ).rename(columns={"_z": "funding_zscore90", "event_timestamp": "funding_source_timestamp"})
    zframe["funding_coverage_status"] = np.where(zframe["funding_rate"].notna(), "AVAILABLE", "NO_PRIOR_EVENT")
    return zframe.rename(columns={"bar_timestamp": "timestamp"})


def load_funding_events(symbol: str) -> pd.DataFrame | None:
    """Load all cached UM fundingRate archives for one symbol."""
    root = Path("data/raw/um/fundingRate") / symbol
    if not root.is_dir():
        return None
    frames = []
    for path in sorted(root.glob(symbol + "-*.zip")):
        try:
            import io, zipfile as _zf
            with _zf.ZipFile(path) as archive:
                name = next(n for n in archive.namelist() if n.endswith(".csv"))
                with archive.open(name) as handle:
                    frame = pd.read_csv(io.TextIOWrapper(handle, encoding="utf-8"))
        except Exception:
            frame = None
        if frame is None:
            continue
        timestamp_column = "calc_time" if "calc_time" in frame.columns else "open_time" if "open_time" in frame.columns else "timestamp"
        rate_column = "last_funding_rate" if "last_funding_rate" in frame.columns else "funding_rate" if "funding_rate" in frame.columns else "close"
        if {timestamp_column, rate_column}.issubset(frame.columns):
            frame = frame.rename(columns={timestamp_column: "timestamp", rate_column: "funding_rate"})[["timestamp", "funding_rate"]]
        elif "open_time" in frame.columns and "close" in frame.columns:
            frame = frame.rename(columns={"open_time": "timestamp", "close": "funding_rate"})[["timestamp", "funding_rate"]]
        elif {"timestamp", "funding_rate"}.issubset(frame.columns):
            frame = frame[["timestamp", "funding_rate"]]
        else:
            continue
        frames.append(frame)
    if not frames:
        return None
    events = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp")
    events["timestamp"] = pd.to_datetime(pd.to_numeric(events["timestamp"], errors="coerce"), unit="ms", utc=True)
    events = events.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return events


def attach_um_premium(panel: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Attach UM premiumIndexKlines CLOSE and 90-bar gap-safe z-score."""
    root = Path("data/raw/um/premiumIndexKlines") / "BTCUSDT" / timeframe
    frames = []
    if root.is_dir():
        import io, zipfile as _zf
        for path in sorted(root.glob("BTCUSDT-*.zip")):
            try:
                with _zf.ZipFile(path) as archive:
                    name = next(n for n in archive.namelist() if n.endswith(".csv"))
                    with archive.open(name) as handle:
                        frame = pd.read_csv(io.TextIOWrapper(handle, encoding="utf-8"))
                frame = frame.rename(columns={frame.columns[0]: "open_time", frame.columns[4]: "premium"})
                frames.append(frame[["open_time", "premium"]])
            except Exception:
                continue
    out = panel.copy()
    if not frames:
        for column in ("premium", "premium_zscore90", "premium_source_timestamp"):
            out[column] = np.nan
        out["premium_coverage_status"] = "HISTORICAL_UNAVAILABLE"
        return out
    raw = pd.concat(frames, ignore_index=True).drop_duplicates("open_time")
    raw["timestamp"] = pd.to_datetime(pd.to_numeric(raw["open_time"], errors="coerce"), unit="ms", utc=True)
    raw = raw.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    step_ms = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[timeframe]
    stamps = raw["timestamp"]
    segment_id = stamps.diff().fillna(pd.Timedelta(milliseconds=step_ms)).ne(pd.Timedelta(milliseconds=step_ms)).cumsum()
    z = pd.Series(np.nan, index=raw.index, name="premium_zscore90")
    values = pd.to_numeric(raw["premium"], errors="coerce")
    for _, positions in raw.groupby(segment_id.to_numpy(), sort=False).groups.items():
        z.iloc[list(positions)] = _rolling_zscore(values.iloc[list(positions)], 90).to_numpy()
    raw = raw[["timestamp", "premium"]].assign(premium_zscore90=z)
    out["_decision_ts"] = out["timestamp"] - pd.Timedelta(milliseconds=1)
    merged = pd.merge_asof(
        out.sort_values("_decision_ts"),
        raw.rename(columns={"timestamp": "premium_source_timestamp"}),
        left_on="_decision_ts",
        right_on="premium_source_timestamp",
        direction="backward",
    ).drop(columns=["_decision_ts"])
    merged["premium_coverage_status"] = np.where(merged["premium"].notna(), "AVAILABLE", "NO_PRIOR_OBSERVATION")
    return merged


def _rolling_zscore(series: pd.Series, period: int) -> pd.Series:
    mean = series.rolling(period, min_periods=period).mean()
    std = series.rolling(period, min_periods=period).std(ddof=0)
    return (series - mean).div(std.replace(0, np.nan))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1"))
    parser.add_argument("--census-dir", type=Path, default=Path("data/census/r1_full_history_v1"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    parser.add_argument("--timeframe", default="15m")
    args = parser.parse_args()
    cohorts = pd.read_csv(args.campaign_dir / "universe_monthly.csv")
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    manifest_name = {
        "15m": "selected_intraday_manifest.csv",
        "1h": "selected_1h_manifest.csv",
        "4h": "selected_4h_manifest.csv",
    }[args.timeframe]
    output_root = Path("data/processed/r1_gap_safe_cohort")
    estimate_name = {
        "15m": "selected_panel_size_estimate.json",
        "1h": "selected_1h_size_estimate.json",
        "4h": "selected_4h_size_estimate.json",
    }[args.timeframe]
    summary_name = {
        "15m": "selected_panel_summary.json",
        "1h": "selected_1h_summary.json",
        "4h": "selected_4h_summary.json",
    }[args.timeframe]
    manifest_path = args.campaign_dir / manifest_name
    generated_manifest = selected_manifest(cohorts, args.census_dir, interval=args.timeframe)
    # Preserve an already-acquired manifest for materialization.  Rebuilding it
    # from the census would discard raw paths and checksums before the panel is
    # read, producing a misleading empty materialization.
    existing_manifest = pd.read_csv(manifest_path, low_memory=False) if manifest_path.exists() else None
    existing_has_paths = (
        existing_manifest is not None
        and "raw_path" in existing_manifest.columns
        and existing_manifest["raw_path"].notna().any()
        and existing_manifest["raw_path"].astype(str).str.contains("data", na=False).all()
    )
    needs_regenerate = (
        args.acquire
        or existing_manifest is None
        or not existing_has_paths
        or len(existing_manifest) != len(generated_manifest)
    )
    if needs_regenerate:
        manifest = generated_manifest
        manifest.to_csv(manifest_path, index=False)
    else:
        manifest = existing_manifest
        if "raw_path" not in manifest.columns and manifest_path.exists():
            raise RuntimeError("existing manifest is missing raw_path; refusing silent materialization")
    estimate = estimate_selected(manifest, args.campaign_dir)
    estimate_path = args.campaign_dir / estimate_name
    if args.acquire:
        acquired = acquire_selected(manifest, workers=args.workers, timeframe=args.timeframe)
        manifest = manifest.merge(acquired, on=["market", "symbol", "archive_month"], how="left")
        manifest.to_csv(manifest_path, index=False)
        estimate["status"] = "ACQUIRED"
        estimate["free_disk_after_bytes"] = int(shutil.disk_usage(Path.cwd()).free)
        (estimate_path).write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    if args.materialize:
        if "raw_path" not in manifest.columns:
            raise RuntimeError("selected manifest lost raw_path; refusing silent materialization")
        counts = materialize_native_selected(manifest, timeframe=args.timeframe, output_root=output_root)
        (args.campaign_dir / summary_name).write_text(json.dumps(counts, indent=2), encoding="utf-8")
        print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
