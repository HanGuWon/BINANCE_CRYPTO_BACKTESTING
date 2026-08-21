"""Download and verify the censused full-history BTC/ETH 15m anchors."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from binance_research.data import ArchiveRequest, BinanceArchiveClient, load_kline_archive, sha256_bytes, validate_klines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census-dir", type=Path, default=Path("data/census/r1_full_history_v1"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    client = BinanceArchiveClient(args.raw_root, timeout=90, max_retries=3)
    requests: list[ArchiveRequest] = []
    anchors = {"BTCUSDT", "ETHUSDT"}
    for market in ("spot", "um"):
        census = pd.read_csv(args.census_dir / f"{market}_archive_object_census.csv")
        for _, row in census.iterrows():
            if str(row.symbol) not in anchors:
                continue
            if str(row.archive_month) == "nan":
                continue
            year, month = (int(part) for part in str(row.archive_month).split("-"))
            requests.append(ArchiveRequest(market, "klines", str(row.symbol), year, month, interval="15m"))
    requests = sorted({request for request in requests}, key=lambda request: (request.market, request.symbol, request.year, request.month))

    def acquire(request: ArchiveRequest) -> dict[str, object]:
        path, manifest = client.download(request)
        frame = load_kline_archive(path)
        issues = validate_klines(frame, "15m")
        return {
            "market": request.market,
            "symbol": request.symbol,
            "archive_month": f"{request.year:04d}-{request.month:02d}",
            "archive_url": manifest.archive_url,
            "row_count": len(frame),
            "first_timestamp": frame.open_time.min().isoformat() if len(frame) else None,
            "last_timestamp": frame.open_time.max().isoformat() if len(frame) else None,
            "published_sha256": manifest.published_sha256,
            "computed_sha256": sha256_bytes(path.read_bytes()),
            "downloaded_at": manifest.downloaded_at,
            "integrity_status": "PASS" if not issues else "ISSUES",
            "issue_codes": ";".join(issue.code for issue in issues),
        }

    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(acquire, request): request for request in requests}
        for number, future in enumerate(as_completed(futures), start=1):
            records.append(future.result())
            if number % 25 == 0:
                print(f"verified {number}/{len(requests)} anchor archives", flush=True)
    output = pd.DataFrame(records).sort_values(["market", "symbol", "archive_month"])
    output.to_csv(args.census_dir / "anchor_archive_manifest.csv", index=False)
    print(output.groupby(["market", "symbol"]).agg(first_archive_month=("archive_month", "min"), last_archive_month=("archive_month", "max"), objects=("archive_month", "count"), rows=("row_count", "sum")).to_string())
    print(f"integrity_failures={(output.integrity_status != 'PASS').sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
