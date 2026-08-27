"""Materialize a pre-holdout, premium-only R2B context panel.

The existing R1 panel is immutable historical evidence.  This script writes a
separate D-backed R2B root, derives 1h/4h only from contiguous 15m source
segments, and aligns the latest source observation at or before each completed
bar decision timestamp.  The final-holdout month is excluded at input.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from binance_research.data import load_kline_archive


STEP = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}


def _zscore(values: pd.Series, period: int = 90) -> pd.Series:
    mean = values.rolling(period, min_periods=period).mean()
    std = values.rolling(period, min_periods=period).std(ddof=0)
    return (values - mean).div(std.replace(0, np.nan))


def load_source(raw_root: Path, symbol: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    frames = []
    for path in sorted((raw_root / "um" / "premiumIndexKlines" / symbol / "15m").glob("*.zip")):
        frame = load_kline_archive(path)[["open_time", "close"]].rename(columns={"open_time": "timestamp", "close": "premium"})
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["timestamp", "premium", "segment_id", "premium_zscore90"])
    raw = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True).astype("datetime64[ns, UTC]")
    raw = raw[raw["timestamp"] < cutoff].reset_index(drop=True)
    expected = STEP["15m"]
    raw["segment_id"] = raw["timestamp"].diff().fillna(expected).ne(expected).cumsum()
    raw["premium_zscore90"] = np.nan
    for _, positions in raw.groupby("segment_id", sort=False).groups.items():
        raw.loc[positions, "premium_zscore90"] = _zscore(raw.loc[positions, "premium"]).to_numpy()
    return raw


def resample_source(source: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "15m":
        return source.copy()
    ratio = int(STEP[timeframe] / STEP["15m"])
    pieces = []
    for segment_id, segment in source.groupby("segment_id", sort=False):
        indexed = segment.set_index("timestamp")
        grouped = indexed["premium"].resample(STEP[timeframe], label="left", closed="left")
        values = grouped.last()
        counts = grouped.count()
        values = values[counts == ratio].dropna().rename("premium").to_frame()
        if values.empty:
            continue
        values["segment_id"] = segment_id
        pieces.append(values.reset_index())
    if not pieces:
        return pd.DataFrame(columns=["timestamp", "premium", "segment_id", "premium_zscore90"])
    result = pd.concat(pieces, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    result["premium_zscore90"] = np.nan
    for _, positions in result.groupby("segment_id", sort=False).groups.items():
        result.loc[positions, "premium_zscore90"] = _zscore(result.loc[positions, "premium"]).to_numpy()
    return result


def align_source_to_decisions(decisions: pd.DataFrame, source: pd.DataFrame, step: pd.Timedelta) -> pd.DataFrame:
    """Backward-as-of align premium observations to completed-bar decisions.

    Keeping this operation as a small pure helper makes the point-in-time and
    no-forward-fill contract directly testable without reading the D-backed
    panel.
    """
    left = decisions[["timestamp"]].copy()
    left["decision_timestamp"] = pd.to_datetime(left["timestamp"], utc=True) + step
    right = source.rename(columns={"timestamp": "premium_source_timestamp"}).copy()
    right["premium_source_timestamp"] = pd.to_datetime(right["premium_source_timestamp"], utc=True)
    return pd.merge_asof(
        left.sort_values("decision_timestamp"),
        right.sort_values("premium_source_timestamp"),
        left_on="decision_timestamp",
        right_on="premium_source_timestamp",
        direction="backward",
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
                out["premium_source_timestamp"] = merged["premium_source_timestamp"]
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
