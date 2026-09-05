"""Materialize a pre-holdout, premium-only R2B context panel.

The existing R1 panel is immutable historical evidence.  This script writes a
separate D-backed R2B root, derives 1h/4h only from contiguous 15m source
segments, and aligns the latest source observation at or before each completed
bar decision timestamp.  The final-holdout month is excluded at input.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from binance_research.data import load_kline_archive, normalize_klines


STEP = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}


def _zscore(values: pd.Series, period: int = 90) -> pd.Series:
    mean = values.rolling(period, min_periods=period).mean()
    std = values.rolling(period, min_periods=period).std(ddof=0)
    return (values - mean).div(std.replace(0, np.nan))


def load_source(raw_root: Path, symbol: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    frames = []
    for path in sorted((raw_root / "um" / "premiumIndexKlines" / symbol / "15m").glob("*.zip")):
        try:
            loaded = load_kline_archive(path)
        except (ValueError, TypeError):
            with zipfile.ZipFile(path) as archive:
                member = next(name for name in archive.namelist() if not name.endswith("/"))
                with archive.open(member) as handle:
                    rows = pd.read_csv(handle, header=None)
            rows = rows[pd.to_numeric(rows.iloc[:, 0], errors="coerce").notna()]
            loaded = normalize_klines(rows.itertuples(index=False, name=None))
        frame = loaded[["open_time", "close", "close_time"]].rename(
            columns={"open_time": "source_open_time", "close": "premium", "close_time": "source_close_time"}
        )
        frame["source_open_time"] = pd.to_datetime(frame["source_open_time"], utc=True)
        frame["source_close_time"] = pd.to_datetime(frame["source_close_time"], utc=True)
        frame["source_available_time"] = frame["source_close_time"]
        frame["source_max_constituent_close_time"] = frame["source_close_time"]
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["source_open_time", "source_close_time", "source_available_time", "source_max_constituent_close_time", "premium", "segment_id", "premium_zscore90"])
    raw = pd.concat(frames, ignore_index=True).drop_duplicates("source_open_time").sort_values("source_open_time")
    raw = raw[raw["source_open_time"] < cutoff].reset_index(drop=True)
    expected = STEP["15m"]
    raw["segment_id"] = raw["source_open_time"].diff().fillna(expected).ne(expected).cumsum()
    raw["premium_zscore90"] = np.nan
    for _, positions in raw.groupby("segment_id", sort=False).groups.items():
        raw.loc[positions, "premium_zscore90"] = _zscore(raw.loc[positions, "premium"]).to_numpy()
    return raw


def resample_source(source: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "15m":
        result = source.copy().sort_values("source_open_time").reset_index(drop=True)
        if "timestamp" not in result:
            result["timestamp"] = result["source_open_time"]
        if "premium_zscore90" not in result:
            result["premium_zscore90"] = np.nan
        for _, positions in result.groupby("segment_id", sort=False).groups.items():
            result.loc[positions, "premium_zscore90"] = _zscore(result.loc[positions, "premium"]).to_numpy()
        return result
    ratio = int(STEP[timeframe] / STEP["15m"])
    pieces = []
    for segment_id, segment in source.groupby("segment_id", sort=False):
        indexed = segment.set_index("source_open_time", drop=False).sort_index()
        grouped = indexed.resample(STEP[timeframe], label="left", closed="left")
        agg = grouped.agg(
            premium=("premium", "last"),
            _count=("premium", "count"),
            source_open_time=("source_open_time", "first"),
            source_close_time=("source_close_time", "last"),
            source_max_constituent_close_time=("source_close_time", "max"),
        )
        values = agg[(agg["_count"] == ratio) & agg["premium"].notna()].drop(columns="_count")
        if values.empty:
            continue
        values["source_available_time"] = values["source_max_constituent_close_time"]
        values["segment_id"] = segment_id
        values["timestamp"] = values.index
        pieces.append(values.reset_index(drop=True))
    if not pieces:
        return pd.DataFrame(columns=["source_open_time", "source_close_time", "source_available_time", "source_max_constituent_close_time", "premium", "segment_id", "premium_zscore90"])
    result = pd.concat(pieces, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    result["premium_zscore90"] = np.nan
    for _, positions in result.groupby("segment_id", sort=False).groups.items():
        result.loc[positions, "premium_zscore90"] = _zscore(result.loc[positions, "premium"]).to_numpy()
    return result.sort_values("timestamp").reset_index(drop=True)


def align_source_to_decisions(decisions: pd.DataFrame, source: pd.DataFrame, step: pd.Timedelta) -> pd.DataFrame:
    """Align only observations satisfying source_available_time < next_executable_open_time.

    source_available_time is the native 15m close or, for a derived bucket, the
    maximum constituent close. Exact-boundary observations are rejected by
    allow_exact_matches=False. Keeping this operation as a small pure helper
    makes the point-in-time and no-forward-fill contract directly testable.
    """
    left = decisions[["timestamp"]].copy()
    left["decision_timestamp"] = pd.to_datetime(left["timestamp"], utc=True).astype("datetime64[ns, UTC]")
    left["executable_open_time"] = left["decision_timestamp"] + step
    right = source.copy()
    if "source_open_time" not in right and "timestamp" in right:
        right["source_open_time"] = right["timestamp"]
    if "source_available_time" not in right:
        if "source_close_time" in right:
            right["source_available_time"] = right["source_close_time"]
        else:
            right["source_available_time"] = right["source_open_time"]
    for column in ("source_open_time", "source_close_time", "source_available_time", "source_max_constituent_close_time"):
        if column in right:
            right[column] = pd.to_datetime(right[column], utc=True).astype("datetime64[ns, UTC]")
    right = right.sort_values("source_available_time")
    return pd.merge_asof(
        left.sort_values("executable_open_time"),
        right,
        left_on="executable_open_time",
        right_on="source_available_time",
        direction="backward",
        allow_exact_matches=False,
    ).reset_index(drop=True)


def materialize(panel_root: Path, raw_root: Path, output_root: Path, symbols: list[str], selected_months: dict[str, set[str]], cutoff_by_timeframe: dict[str, pd.Timestamp]) -> dict[str, int]:
    counts = {timeframe: 0 for timeframe in STEP}
    for symbol in symbols:
        for timeframe, step in STEP.items():
            panel_paths = sorted((panel_root / "market=um" / f"symbol={symbol}" / f"timeframe={timeframe}").glob("year=*/part-000.parquet"))
            if not panel_paths:
                continue
            source = resample_source(load_source(raw_root, symbol, cutoff_by_timeframe[timeframe]), timeframe)
            for panel_path in panel_paths:
                bars = pd.read_parquet(panel_path, columns=["timestamp", "row_class", "symbol", "timeframe", "universe_month", "segment_id", "segment_start", "segment_end", "gap_before"])
                bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
                bars = bars[(bars["timestamp"] < cutoff_by_timeframe[timeframe]) & bars["universe_month"].astype(str).isin(selected_months.get(symbol, set()))].sort_values("timestamp")
                if bars.empty:
                    continue
                decisions = bars[["timestamp"]].copy()
                merged = align_source_to_decisions(decisions, source, step)
                out = bars.reset_index(drop=True).copy()
                merged = merged.reset_index(drop=True)
                out["premium_source_timestamp"] = merged.get("source_open_time")
                out["premium_source_available_time"] = merged.get("source_available_time")
                out["premium"] = merged["premium"]
                out["premium_zscore90"] = merged["premium_zscore90"]
                out["premium_coverage_status"] = np.where(out["premium"].notna(), "AVAILABLE", "NO_PRIOR_OBSERVATION")
                out["premium_zscore_coverage_status"] = np.where(out["premium_zscore90"].notna(), "AVAILABLE", np.where(out["premium"].notna(), "FEATURE_WARMUP_OR_ZERO_VARIANCE", "NO_PRIOR_OBSERVATION"))
                destination = output_root / f"market=um/symbol={symbol}/timeframe={timeframe}/year={panel_path.parent.name.split('=', 1)[1]}" / "part-000.parquet"
                destination.parent.mkdir(parents=True, exist_ok=True)
                out.to_parquet(destination, index=False)
                counts[timeframe] += len(out)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-root", type=Path, default=Path("data/processed/r1_gap_safe_cohort"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/r2b_restricted_derivatives_v1"))
    parser.add_argument("--universe", type=Path, default=Path("campaigns/r1_final_panel_v1/universe_monthly.csv"))
    parser.add_argument("--cutoff", default="2024-02-10T00:00:00Z")
    args = parser.parse_args()
    universe = pd.read_csv(args.universe)
    cutoff = pd.Timestamp(args.cutoff, tz="UTC")
    selected = universe.loc[(universe.market == "um") & universe.selected_top50.astype(bool) & (pd.to_datetime(universe.universe_month + "-01", utc=True) < cutoff)].copy()
    selected_months = {str(symbol): set(group.universe_month.astype(str)) for symbol, group in selected.groupby("symbol")}
    symbols = sorted(selected_months)
    cutoffs = {timeframe: cutoff for timeframe in STEP}
    counts = materialize(args.panel_root, args.raw_root, args.output_root, symbols, selected_months, cutoffs)
    print({"symbols": len(symbols), "rows": counts, "output_root": str(args.output_root.resolve()), "holdout_cutoff": cutoff.isoformat(), "no_holdout_input": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
