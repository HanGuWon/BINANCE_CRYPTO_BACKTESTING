"""Freeze monthly Top-N cohorts from an acquired native-1d manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from build_r16_1d_universe import build_monthly_cohorts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1"))
    args = parser.parse_args()
    manifest = pd.read_csv(args.campaign_dir / "volume_archive_manifest.csv")
    taxonomy = pd.read_csv(args.campaign_dir / "asset_taxonomy.csv")
    ranked = build_monthly_cohorts(manifest, taxonomy, args.campaign_dir)
    print(ranked.groupby(["market", "universe_month"], sort=True)[["selected_top20", "selected_top50", "selected_top100"]].sum().head(20).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
