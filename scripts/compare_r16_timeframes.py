"""Compare native Binance 1h/4h archives with 15m aggregation on anchors."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from binance_research.data import ArchiveRequest, BinanceArchiveClient, load_kline_archive
from binance_research.timeframes import compare_native_to_resampled, freeze_timeframe_source_policy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1/timeframe_comparison.csv"))
    parser.add_argument("--months", default="2024-01,2024-02")
    args = parser.parse_args()
    client = BinanceArchiveClient(Path("data/raw"), timeout=90, max_retries=3)
    rows: list[pd.DataFrame] = []
    for market in ("spot", "um"):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            for month in args.months.split(","):
                year, month_number = (int(value) for value in month.split("-"))
                source_path = Path("data/raw") / market / "klines" / symbol / "15m" / f"{symbol}-15m-{year:04d}-{month_number:02d}.zip"
                if not source_path.exists():
                    continue
                source = load_kline_archive(source_path)
                for timeframe in ("1h", "4h"):
                    native_path, _ = client.download(ArchiveRequest(market, "klines", symbol, year, month_number, interval=timeframe))
                    native = load_kline_archive(native_path)
                    comparison = compare_native_to_resampled(source, native, target=timeframe)
                    comparison.insert(0, "market", market)
                    comparison.insert(1, "symbol", symbol)
                    comparison.insert(2, "month", month)
                    rows.append(comparison)
    output = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(output.to_string(index=False))
    print(f"frozen_policy={freeze_timeframe_source_policy(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
