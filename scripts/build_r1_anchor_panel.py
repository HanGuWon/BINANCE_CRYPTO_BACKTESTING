"""Acquire and materialize the bounded R1A BTC/ETH anchor panel.

Raw archives and processed Parquet are intentionally ignored by git.  The
script prints exact row counts and SHA-256 values so a campaign run can be
audited without checking data into the repository.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from binance_research.data import ArchiveRequest, BinanceArchiveClient, load_kline_archive, resample_klines, sha256_bytes
from binance_research.panel import frame_sha256, write_partitioned_panel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--month", type=int, default=1)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed/r1"))
    args = parser.parse_args()

    client = BinanceArchiveClient(args.raw_root)
    for market in ("spot", "um"):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            request = ArchiveRequest(market, "klines", symbol, args.year, args.month, interval="15m")
            archive, manifest = client.download(request)
            source = load_kline_archive(archive)
            source["symbol"] = symbol
            for timeframe, frame in (("15m", source), ("1h", resample_klines(source.drop(columns="symbol"), "1h").assign(symbol=symbol)), ("4h", resample_klines(source.drop(columns="symbol"), "4h").assign(symbol=symbol))):
                panel = frame.rename(columns={"open_time": "timestamp"}).assign(market=market, timeframe=timeframe)
                write_partitioned_panel(panel, args.processed_root, provenance=manifest.archive_url or request.url())
                print(f"{market},{symbol},{timeframe},{len(panel)},{sha256_bytes(archive.read_bytes())},{frame_sha256(panel)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
