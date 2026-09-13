"""Causal cross-sectional context primitives for Fast Discovery V2."""
from __future__ import annotations

import pandas as pd


def build_relative_strength(panel: pd.DataFrame, benchmark: pd.DataFrame, *, lookback_bars: int = 96) -> pd.DataFrame:
    """Add trailing symbol-vs-BTC relative strength and Top50 cross-sectional rank."""
    if lookback_bars < 1:
        raise ValueError("lookback_bars must be positive")
    required_panel = {"open_time", "symbol", "segment_id", "close", "selected_top50", "market"}
    if missing := required_panel - set(panel.columns):
        raise ValueError(f"panel missing relative-strength columns: {', '.join(sorted(missing))}")
    required_benchmark = {"open_time", "close"}
    if missing := required_benchmark - set(benchmark.columns):
        raise ValueError(f"benchmark missing relative-strength columns: {', '.join(sorted(missing))}")
    frame = panel.copy()
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True, errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["symbol"] = frame["symbol"].astype(str)
    frame["market"] = frame["market"].astype(str)
    frame["symbol_return_24h"] = frame.groupby(["symbol", "segment_id"], sort=False)["close"].pct_change(lookback_bars, fill_method=None)
    btc = benchmark.copy()
    btc["open_time"] = pd.to_datetime(btc["open_time"], utc=True, errors="raise")
    btc["close"] = pd.to_numeric(btc["close"], errors="coerce")
    if btc["open_time"].duplicated().any():
        raise ValueError("benchmark open_time must be unique")
    btc = btc.sort_values("open_time", kind="stable")
    btc["benchmark_return_24h"] = btc["close"].pct_change(lookback_bars, fill_method=None)
    source_time = "close_time" if "close_time" in btc.columns else "open_time"
    btc["source_available_time"] = pd.to_datetime(btc[source_time], utc=True, errors="raise")
    left_time = "close_time" if "close_time" in frame.columns else "open_time"
    frame[left_time] = pd.to_datetime(frame[left_time], utc=True, errors="raise")
    right = btc[["source_available_time", "benchmark_return_24h"]].dropna(subset=["source_available_time"]).sort_values("source_available_time", kind="stable")
    chunks: list[pd.DataFrame] = []
    for _, group in frame.groupby("symbol", sort=False):
        chunk = pd.merge_asof(group.sort_values(left_time, kind="stable"), right, left_on=left_time, right_on="source_available_time", direction="backward", allow_exact_matches=True)
        if "next_open_time" in chunk:
            chunk.loc[chunk["source_available_time"] >= pd.to_datetime(chunk["next_open_time"], utc=True), "benchmark_return_24h"] = pd.NA
        chunks.append(chunk)
    result = pd.concat(chunks, ignore_index=True).sort_values(["open_time", "symbol"], kind="stable").reset_index(drop=True)
    result["relative_strength_24h"] = result["symbol_return_24h"] - result["benchmark_return_24h"]
    selected = result["selected_top50"].astype(bool) & result["relative_strength_24h"].notna()
    result["relative_strength_rank"] = pd.NA
    for (_, timestamp), index in result.loc[selected].groupby(["market", "open_time"], sort=False).groups.items():
        values = result.loc[index, "relative_strength_24h"]
        result.loc[index, "relative_strength_rank"] = values.rank(method="average", pct=True)
    result.attrs["context"] = "BTC-relative trailing return and contemporaneous selected Top50 rank"
    result.attrs["holdout_status"] = "UNTOUCHED"
    return result
