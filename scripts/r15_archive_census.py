"""Run the metadata-only R1.5 Binance Vision archive census.

The census lists S3 metadata only.  It does not download market data.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from binance_research.census import eligibility_table, object_census_rows, symbol_census
from binance_research.data import BinanceArchiveClient

DATASET_PROBES = {
    "um_funding_monthly": "data/futures/um/monthly/fundingRate/",
    "um_funding_daily": "data/futures/um/daily/fundingRate/",
    "um_premium_index_monthly": "data/futures/um/monthly/premiumIndexKlines/",
    "um_premium_price_monthly": "data/futures/um/monthly/premiumPriceKlines/",
    "um_mark_price_monthly": "data/futures/um/monthly/markPriceKlines/",
    "um_index_price_monthly": "data/futures/um/monthly/indexPriceKlines/",
    "um_metrics_monthly": "data/futures/um/monthly/metrics/",
    "um_metrics_daily": "data/futures/um/daily/metrics/",
    "um_book_ticker_monthly": "data/futures/um/monthly/bookTicker/",
    "um_book_ticker_daily": "data/futures/um/daily/bookTicker/",
    "um_book_depth_monthly": "data/futures/um/monthly/bookDepth/",
    "um_book_depth_daily": "data/futures/um/daily/bookDepth/",
    "um_aggtrades_monthly": "data/futures/um/monthly/aggTrades/",
    "um_liquidation_snapshot_monthly": "data/futures/um/monthly/liquidationSnapshot/",
    "um_liquidation_snapshot_daily": "data/futures/um/daily/liquidationSnapshot/",
}


def _market_census(client: BinanceArchiveClient, market: str, interval: str, workers: int) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    root = f"data/{'spot' if market == 'spot' else 'futures/um'}/monthly/klines/"
    prefixes, _, root_pages = client.list_objects_v2(root, delimiter="/")
    rows: list[pd.DataFrame] = []
    page_count = root_pages

    def fetch(prefix: str) -> tuple[pd.DataFrame, int]:
        _, objects, pages = client.list_objects_v2(f"{prefix}{interval}/")
        return object_census_rows(objects, market=market, interval=interval), pages

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, prefix): prefix for prefix in prefixes}
        for number, future in enumerate(as_completed(futures), start=1):
            frame, pages = future.result()
            if not frame.empty:
                rows.append(frame)
            page_count += pages
            if number % 250 == 0:
                print(f"{market}: listed {number}/{len(prefixes)} symbol prefixes", flush=True)
    objects = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return objects, symbol_census(objects) if not objects.empty else pd.DataFrame(), len(prefixes), page_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("data/census/r1_full_history_v1"))
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = BinanceArchiveClient(Path("data/raw"), timeout=60)

    summaries: list[dict[str, object]] = []
    eligibility_frames: list[pd.DataFrame] = []
    for market in ("spot", "um"):
        objects, symbols, prefix_count, pages = _market_census(client, market, args.interval, args.workers)
        objects.to_csv(args.out_dir / f"{market}_archive_object_census.csv", index=False)
        symbols.to_csv(args.out_dir / f"{market}_archive_symbol_census.csv", index=False)
        eligibility = eligibility_table([(market, symbol) for symbol in symbols.get("symbol", [])])
        eligibility.to_csv(args.out_dir / f"{market}_instrument_eligibility.csv", index=False)
        eligibility_frames.append(eligibility)
        summaries.append({"market": market, "s3_symbol_prefixes": prefix_count, "s3_pages": pages, "object_rows": len(objects), "symbol_rows": len(symbols), "zip_bytes": int(pd.to_numeric(objects.get("size", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())})

    probes: list[dict[str, object]] = []
    for name, prefix in DATASET_PROBES.items():
        try:
            prefixes, objects, pages = client.list_objects_v2(prefix, delimiter="/")
            probes.append({"dataset": name, "prefix": prefix, "status": "PRESENT" if prefixes or objects else "EMPTY_OR_UNLISTED_AT_THE_PROBED_PATH", "pages": pages, "symbol_prefix_count": len(prefixes), "object_count": len(objects), "sample_prefix": prefixes[0] if prefixes else None, "sample_object": objects[0].key if objects else None})
        except Exception as exc:
            probes.append({"dataset": name, "prefix": prefix, "status": "LISTING_ERROR", "error": f"{type(exc).__name__}: {exc}"})

    pd.DataFrame(probes).to_csv(args.out_dir / "dataset_probe.csv", index=False)
    pd.DataFrame(summaries).to_csv(args.out_dir / "census_summary.csv", index=False)
    pd.concat(eligibility_frames, ignore_index=True).to_csv(args.out_dir / "instrument_eligibility.csv", index=False)
    (args.out_dir / "census_summary.json").write_text(json.dumps({"markets": summaries, "dataset_probes": probes}, indent=2), encoding="utf-8")
    print(json.dumps({"markets": summaries, "dataset_probes": probes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
