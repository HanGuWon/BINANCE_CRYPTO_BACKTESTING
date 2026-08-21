"""Acquire full censused UM funding and 15m premium-index anchor history."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from binance_research.data import ArchiveRequest, BinanceArchiveClient, load_kline_archive, normalize_archive_rows, validate_klines


def main() -> int:
    census_dir = Path("data/census/r1_full_history_v1")
    client = BinanceArchiveClient(Path("data/raw"), timeout=90, max_retries=3)
    requests: list[ArchiveRequest] = []
    for dataset, interval in (("fundingRate", None), ("premiumIndexKlines", "15m")):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            # The derivative archive index is probed directly because these
            # datasets use different object layouts than klines.
            _, listed, _ = client.list_objects_v2(
                f"data/futures/um/monthly/{dataset}/{symbol}/" + (f"{interval}/" if interval else "")
            )
            for obj in listed:
                if not obj.key.endswith(".zip"):
                    continue
                stem = Path(obj.key).stem
                year, month = stem[-7:].split("-")
                requests.append(ArchiveRequest("um", dataset, symbol, int(year), int(month), interval=interval))
    requests = sorted(set(requests), key=lambda r: (r.dataset, r.symbol, r.year, r.month))

    def acquire(request: ArchiveRequest) -> dict[str, object]:
        path, manifest = client.download(request)
        if request.dataset == "fundingRate":
            import zipfile
            with zipfile.ZipFile(path) as archive, archive.open(archive.namelist()[0]) as handle:
                raw = pd.read_csv(handle, header=None)
            normalized = normalize_archive_rows(raw, request.dataset, request.market)
            valid = set(normalized.columns) >= {"timestamp", "funding_interval_hours", "funding_rate"} and normalized["funding_rate"].notna().all() and normalized["timestamp"].notna().all()
            issue_codes = "" if valid else "FUNDING_SCHEMA_OR_TIMESTAMP"
        else:
            normalized = load_kline_archive(path)
            issues = validate_klines(normalized, "15m", allow_negative=True)
            issue_codes = ";".join(issue.code for issue in issues)
            valid = not any(issue.severity == "ERROR" for issue in issues)
        return {
            "dataset": request.dataset,
            "market": request.market,
            "symbol": request.symbol,
            "interval": request.interval or "event",
            "archive_month": f"{request.year:04d}-{request.month:02d}",
            "archive_url": manifest.archive_url,
            "row_count": len(normalized),
            "first_timestamp": normalized.timestamp.min().isoformat() if len(normalized) and "timestamp" in normalized else normalized.open_time.min().isoformat(),
            "last_timestamp": normalized.timestamp.max().isoformat() if len(normalized) and "timestamp" in normalized else normalized.open_time.max().isoformat(),
            "published_sha256": manifest.published_sha256,
            "computed_sha256": manifest.computed_sha256,
            "downloaded_at": manifest.downloaded_at,
            "integrity_status": "PASS" if valid and manifest.published_sha256 == manifest.computed_sha256 else "ISSUES",
            "issue_codes": issue_codes,
        }

    records: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(acquire, request) for request in requests]
        for number, future in enumerate(as_completed(futures), start=1):
            records.append(future.result())
            if number % 25 == 0:
                print(f"verified {number}/{len(requests)} derivative archives", flush=True)
    output = pd.DataFrame(records).sort_values(["dataset", "symbol", "archive_month"])
    output.to_csv(census_dir / "derivative_archive_manifest.csv", index=False)
    print(output.groupby(["dataset", "symbol"]).agg(first_archive_month=("archive_month", "min"), last_archive_month=("archive_month", "max"), objects=("archive_month", "count"), rows=("row_count", "sum")).to_string())
    print(f"integrity_failures={(output.integrity_status != 'PASS').sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
