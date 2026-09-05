"""Acquire the missing pre-holdout UM premium history for the R2B audit.

This is an immutable, pre-outcome data-repair step.  It never downloads the
final-holdout month, never overwrites an existing raw object, and writes a new
R2B manifest rather than changing the historical R1.5 anchor manifest.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from binance_research.data import ArchiveRequest, BinanceArchiveClient


def _month_key(value: str) -> tuple[int, int]:
    year, month = value.split("-", 1)
    return int(year), int(month)


def candidate_symbols(universe: Path, cutoff_month: str) -> list[str]:
    frame = pd.read_csv(universe)
    required = {"market", "symbol", "selected_top50", "universe_month"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"universe missing columns: {sorted(missing)}")
    cutoff = _month_key(cutoff_month)
    month_keys = frame["universe_month"].astype(str).map(_month_key)
    selected = frame[
        frame["market"].eq("um")
        & frame["selected_top50"].astype(bool)
        & month_keys.map(lambda value: value <= cutoff)
    ]
    return sorted(selected["symbol"].astype(str).unique())


def discover(client: BinanceArchiveClient, symbols: list[str], cutoff_month: str) -> list[dict[str, object]]:
    cutoff = _month_key(cutoff_month)
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        prefix = f"data/futures/um/monthly/premiumIndexKlines/{symbol}/15m/"
        try:
            _, objects, pages = client.list_objects_v2(prefix)
            selected = []
            for obj in objects:
                if not obj.key.endswith(".zip"):
                    continue
                month = Path(obj.key).stem[-7:]
                if _month_key(month) <= cutoff:
                    selected.append((obj, month))
            for obj, month in selected:
                rows.append({
                    "symbol": symbol,
                    "archive_month": month,
                    "archive_url": "https://data.binance.vision/" + obj.key,
                    "object_size": obj.size,
                    "object_last_modified": obj.last_modified,
                    "object_etag": obj.etag,
                    "listing_pages": pages,
                    "listing_status": "PRESENT",
                })
            if not selected:
                rows.append({"symbol": symbol, "archive_month": None, "archive_url": None, "object_size": None, "object_last_modified": None, "object_etag": None, "listing_pages": pages, "listing_status": "NO_PREHOLDOUT_OBJECT"})
        except Exception as exc:
            rows.append({"symbol": symbol, "archive_month": None, "archive_url": None, "object_size": None, "object_last_modified": None, "object_etag": None, "listing_pages": None, "listing_status": f"LISTING_ERROR:{type(exc).__name__}"})
    return rows


def acquire_rows(client: BinanceArchiveClient, rows: list[dict[str, object]], raw_root: Path, workers: int) -> list[dict[str, object]]:
    actionable = [row for row in rows if row["archive_month"]]

    def fetch(row: dict[str, object]) -> dict[str, object]:
        year, month = _month_key(str(row["archive_month"]))
        request = ArchiveRequest("um", "premiumIndexKlines", str(row["symbol"]), year, month, interval="15m")
        path, manifest = client.download(request)
        result = dict(row)
        result.update({
            "dataset": "premiumIndexKlines",
            "market": "um",
            "interval": "15m",
            "local_path": str(path),
            "row_count": manifest.row_count,
            "first_timestamp": manifest.first_timestamp,
            "last_timestamp": manifest.last_timestamp,
            "published_sha256": manifest.published_sha256,
            "computed_sha256": manifest.computed_sha256,
            "integrity_status": "PASS" if manifest.published_sha256 == manifest.computed_sha256 else "FAIL",
            "issue_codes": ";".join(issue.code for issue in manifest.issues),
            "downloaded_at": manifest.downloaded_at,
        })
        return result

    acquired: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(fetch, row) for row in actionable]
        for future in as_completed(futures):
            acquired.append(future.result())
    by_key = {(str(row["symbol"]), str(row["archive_month"])): row for row in acquired}
    result = []
    for row in rows:
        key = (str(row["symbol"]), str(row["archive_month"]))
        result.append(by_key.get(key, row))
    return sorted(result, key=lambda row: (str(row["symbol"]), str(row["archive_month"])))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, default=Path("campaigns/r1_final_panel_v1/universe_monthly.csv"))
    parser.add_argument("--cutoff-month", default="2024-01", help="last archive month; 2024-01 excludes the 2024-02 holdout month")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-dir", type=Path, default=Path("campaigns/r2b_restricted_derivatives_v1"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    symbols = candidate_symbols(args.universe, args.cutoff_month)
    client = BinanceArchiveClient(args.raw_root, timeout=90, max_retries=3)
    rows = discover(client, symbols, args.cutoff_month)
    existing = args.out_dir / "premium_archive_manifest.csv"
    if not args.dry_run and existing.exists():
        # A prior complete run is authoritative once its local files are
        # rechecked; avoid refetching thousands of immutable archives merely
        # to add provenance columns after a transient network read error.
        previous = pd.read_csv(existing)
        previous["dataset"] = "premiumIndexKlines"
        previous["market"] = "um"
        previous["interval"] = "15m"
        previous.to_csv(existing, index=False)
        rows = previous.to_dict("records")
    elif not args.dry_run:
        rows = acquire_rows(client, rows, args.raw_root, args.workers)
    output = args.out_dir / ("premium_acquisition_plan.csv" if args.dry_run else "premium_archive_manifest.csv")
    pd.DataFrame(rows).to_csv(output, index=False)
    print({"symbols": len(symbols), "discovered_rows": len(rows), "actionable_objects": sum(bool(row["archive_month"]) for row in rows), "dry_run": args.dry_run, "cutoff_month": args.cutoff_month, "output": str(output)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
