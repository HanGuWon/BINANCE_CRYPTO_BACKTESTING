"""Materialize full-history anchor Parquet partitions from verified raw archives."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from binance_research.data import deduplicate_klines, load_kline_archive
from binance_research.panel import resample_contiguous_source


def _resample_contiguous(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample each regular run so known internal gaps drop only affected buckets."""
    ordered = deduplicate_klines(frame.sort_values("open_time"))
    if len(ordered) < 2:
        return ordered.iloc[0:0].copy()
    return resample_contiguous_source(ordered, rule, source_interval="15m")


def main() -> int:
    root = Path("data/census/r1_full_history_v1")
    output_root = Path("data/processed/r1_full_history")
    manifest = pd.read_csv(root / "anchor_archive_manifest.csv")
    for _, row in manifest.iterrows():
        month = str(row.archive_month)
        year = month[:4]
        archive = Path("data/raw") / row.market / "klines" / row.symbol / "15m" / f"{row.symbol}-15m-{month}.zip"
        source = load_kline_archive(archive)
        source["market"], source["symbol"] = row.market, row.symbol
        for timeframe, frame in (("15m", source), ("1h", _resample_contiguous(source.drop(columns=["market", "symbol"]), "1h")), ("4h", _resample_contiguous(source.drop(columns=["market", "symbol"]), "4h"))):
            frame = frame.copy()
            if timeframe != "15m":
                frame["market"], frame["symbol"] = row.market, row.symbol
            frame["timeframe"] = timeframe
            frame["provenance"] = row.archive_url
            frame = frame.rename(columns={"open_time": "timestamp"})
            destination = output_root / f"market={row.market}" / f"symbol={row.symbol}" / f"timeframe={timeframe}" / f"year={year}" / f"part-{month}.parquet"
            destination.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(destination, index=False)
    print(f"materialized {len(manifest) * 3} anchor partitions under {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
