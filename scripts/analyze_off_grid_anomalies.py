"""Audit exact off-grid anomalies inside cached 15m archives.

This is a read-only forensic pass over immutable raw objects.  It never snaps,
rounds, or rewrites timestamps; it only records evidence so downstream
materialization can quarantine the smallest defensible range.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from binance_research.data import INTERVAL_MS, load_kline_archive


def audit_symbol(manifest: pd.DataFrame, market: str, symbol: str) -> list[dict[str, object]]:
    expected_ms = int(INTERVAL_MS["15m"])
    group = manifest[(manifest["market"] == market) & (manifest["symbol"] == symbol)]
    anomalies: list[dict[str, object]] = []
    previous_timestamp: pd.Timestamp | None = None
    previous_month: str | None = None
    ordered = group.sort_values("archive_month")
    for row in ordered.itertuples():
        path = Path(str(row.raw_path))
        if not path.exists():
            continue
        frame = load_kline_archive(path)
        stamps = pd.to_datetime(frame["open_time"], utc=True).sort_values().reset_index(drop=True)
        for position, current in stamps.items():
            delta_ms: int | None = None
            anomaly_type = ""
            if previous_timestamp is not None:
                delta = (current - previous_timestamp).total_seconds() * 1000
                delta_ms = int(delta)
                if delta < 0:
                    anomaly_type = "TIME_REVERSAL"
                elif delta == 0:
                    anomaly_type = "DUPLICATE_TIMESTAMP"
                elif delta % expected_ms != 0:
                    anomaly_type = "OFF_GRID_TIMESTAMP"
            if anomaly_type:
                anomalies.append(
                    {
                        "market": market,
                        "symbol": symbol,
                        "archive_month": str(row.archive_month),
                        "archive_url": f"https://data.binance.vision/data/{'spot' if market == 'spot' else 'futures/um'}/monthly/klines/{symbol}/15m/{symbol}-15m-{row.archive_month}.zip",
                        "published_sha256": getattr(row, "published_sha256", ""),
                        "computed_sha256": getattr(row, "computed_sha256", ""),
                        "previous_timestamp": previous_timestamp.isoformat() if previous_timestamp is not None else "",
                        "previous_archive_month": previous_month or "",
                        "current_timestamp": current.isoformat(),
                        "current_row_position": int(position),
                        "delta_ms": delta_ms if delta_ms is not None else "",
                        "expected_delta_ms": expected_ms,
                        "anomaly_type": anomaly_type,
                        "source_evidence": f"raw archive row {int(position)} in {path}",
                        "resolution": "QUARANTINE_INVALID_ROW",
                    }
                )
            previous_timestamp = current
            previous_month = str(row.archive_month)
    return anomalies


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("campaigns/r1_final_panel_v1"))
    args = parser.parse_args()
    manifest = pd.read_csv(args.campaign_dir / "selected_intraday_manifest.csv")
    failed = [
        ("spot", "BCCUSDT"),
        ("spot", "BNBUSDT"),
        ("spot", "BTCUSDT"),
        ("spot", "ETHUSDT"),
        ("spot", "LTCUSDT"),
        ("spot", "NEOUSDT"),
    ]
    rows: list[dict[str, object]] = []
    for market, symbol in failed:
        rows.extend(audit_symbol(manifest, market, symbol))
        print(f"audited {market}/{symbol}: cumulative anomalies={len(rows)}", flush=True)
    output = pd.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output_dir / "off_grid_anomalies.csv", index=False)
    print(output[["market", "symbol", "archive_month", "current_timestamp", "anomaly_type"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
