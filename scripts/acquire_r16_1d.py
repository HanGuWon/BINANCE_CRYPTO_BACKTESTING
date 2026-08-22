"""Acquire a previously estimated R1.6 native-1d manifest."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from build_r16_1d_universe import acquire_1d


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1"))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    manifest_path = args.campaign_dir / "volume_archive_manifest.csv"
    manifest = __import__("pandas").read_csv(manifest_path)
    acquired = acquire_1d(manifest, workers=args.workers)
    acquired.to_csv(args.campaign_dir / "volume_archive_acquisition.csv", index=False)
    acquisition_columns = [column for column in acquired.columns if column not in {"market", "symbol", "archive_month"}]
    merged = manifest.merge(acquired[["market", "symbol", "archive_month", *acquisition_columns]], on=["market", "symbol", "archive_month"], how="left")
    merged.to_csv(manifest_path, index=False)
    estimate_path = args.campaign_dir / "volume_size_estimate.json"
    estimate = json.loads(estimate_path.read_text(encoding="utf-8"))
    estimate["status"] = "ACQUIRED"
    estimate["free_disk_after_bytes"] = int(shutil.disk_usage(Path.cwd()).free)
    estimate_path.write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
