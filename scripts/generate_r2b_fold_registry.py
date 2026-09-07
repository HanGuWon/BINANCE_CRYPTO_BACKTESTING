"""Generate exact UTC fold/horizon execution boundaries for R2B."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "campaigns" / "r2b_restricted_derivatives_v1" / "fold_registry.csv"
HORIZONS = {"15m": (4, 16, 48, 96), "1h": (4, 12, 24), "4h": (3, 6)}
STEP = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4)}
FOLDS = (
    ("F01", "2020-H1", "2020-01-01T00:00:00Z", "2020-07-01T00:00:00Z"),
    ("F02", "2020-H2", "2020-07-01T00:00:00Z", "2021-01-01T00:00:00Z"),
    ("F03", "2021-H1", "2021-01-01T00:00:00Z", "2021-07-01T00:00:00Z"),
    ("F04", "2021-H2", "2021-07-01T00:00:00Z", "2022-01-01T00:00:00Z"),
    ("F05", "2022-H1", "2022-01-01T00:00:00Z", "2022-07-01T00:00:00Z"),
    ("F06", "2022-H2", "2022-07-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    ("F07", "2023-H1", "2023-01-01T00:00:00Z", "2023-07-01T00:00:00Z"),
    ("F08", "2023-H2", "2023-07-01T00:00:00Z", "2024-01-01T00:00:00Z"),
)


def rows() -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for fold_id, block, start_text, end_text in FOLDS:
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_text.replace("Z", "+00:00"))
        for timeframe, horizons in HORIZONS.items():
            step = STEP[timeframe]
            for horizon in horizons:
                validation_start = start + step
                history_end = validation_start - horizon * step
                output.append({
                    "fold_id": fold_id, "block": block,
                    "validation_start_utc": validation_start.isoformat().replace("+00:00", "Z"),
                    "validation_end_exclusive_utc": end.isoformat().replace("+00:00", "Z"),
                    "history_end_exclusive_utc": history_end.isoformat().replace("+00:00", "Z"),
                    "timeframe": timeframe, "horizon_bars": horizon,
                    "purge_bars": horizon, "embargo_bars": 1,
                    "minimum_trades": 30, "status": "PREREGISTERED",
                    "selection_basis": "calendar_block_and_time_structure_only",
                })
    return output


def main() -> None:
    fields = list(rows()[0])
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows())
    print(f"wrote {len(rows())} rows to {OUT}")


if __name__ == "__main__":
    main()
