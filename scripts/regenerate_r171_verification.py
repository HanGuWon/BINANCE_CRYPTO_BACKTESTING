'''R1.7.1 verification regeneration: feature audit + split metadata.

Regenerates the committed campaign CSVs from the materialized panel and the
authoritative global_calendar_split() implementation. Read-only with respect
to raw archives and Parquet partitions; writes only the two campaign CSVs.
'''
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from binance_research.audit import audit_feature_coverage  # noqa: E402
from binance_research.splits import HORIZON_PURGE_BARS_24H  # noqa: E402


TRAIN_BOUNDARY = pd.Timestamp("2024-01-20", tz="UTC")
VALIDATION_BOUNDARY = pd.Timestamp("2024-02-10", tz="UTC")
OPERATIONAL_EMBARGO_BARS = 1
STEP = {"15m": pd.Timedelta("15min"), "1h": pd.Timedelta("1h"), "4h": pd.Timedelta("4h")}


def split_metadata_frame() -> pd.DataFrame:
    """Derive exact split timestamps from global_calendar_split equations."""
    rows = []
    for timeframe, purge in HORIZON_PURGE_BARS_24H.items():
        step = STEP[timeframe]
        last_train = TRAIN_BOUNDARY - (purge + OPERATIONAL_EMBARGO_BARS) * step
        first_validation = TRAIN_BOUNDARY + OPERATIONAL_EMBARGO_BARS * step
        last_validation = VALIDATION_BOUNDARY - (purge + OPERATIONAL_EMBARGO_BARS) * step
        first_holdout = VALIDATION_BOUNDARY + OPERATIONAL_EMBARGO_BARS * step
        # Cross-check the derived values against a real global_calendar_split
        # call so the metadata can never drift from the implementation.
        frame = pd.DataFrame({
            "timestamp": pd.date_range(
                last_train - 10 * step,
                first_holdout + 10 * step,
                freq=step,
                tz="UTC",
            ),
        })
        split = __import__("binance_research.splits", fromlist=["global_calendar_split"]).global_calendar_split(
            frame,
            train_end=TRAIN_BOUNDARY.isoformat(),
            validation_end=VALIDATION_BOUNDARY.isoformat(),
            timeframe=timeframe,
            operational_embargo_bars=OPERATIONAL_EMBARGO_BARS,
        )
        assert split.train["timestamp"].max() == last_train
        assert split.validation["timestamp"].min() == first_validation
        assert split.validation["timestamp"].max() == last_validation
        assert split.test["timestamp"].min() == first_holdout
        rows.append({
            "timeframe": timeframe,
            "train_boundary_utc": TRAIN_BOUNDARY.isoformat(),
            "last_train_timestamp_utc": last_train.isoformat(),
            "first_validation_timestamp_utc": first_validation.isoformat(),
            "validation_boundary_utc": VALIDATION_BOUNDARY.isoformat(),
            "last_validation_timestamp_utc": last_validation.isoformat(),
            "first_test_holdout_timestamp_utc": first_holdout.isoformat(),
            "purge_bars_24h": purge,
            "operational_embargo_bars": OPERATIONAL_EMBARGO_BARS,
        })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-root", type=Path, default=Path("data/processed/r1_gap_safe_cohort"))
    parser.add_argument("--campaign-dir", type=Path, default=Path("campaigns/r1_final_panel_v1"))
    args = parser.parse_args()
    features = audit_feature_coverage(args.panel_root)
    features.to_csv(args.campaign_dir / "feature_availability_final.csv", index=False)
    splits = split_metadata_frame()
    splits.to_csv(args.campaign_dir / "split_metadata_final.csv", index=False)
    print(features.groupby(["market", "timeframe"])["coverage_fraction"].agg(["count", "min", "max"]).to_string())
    print(splits.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
