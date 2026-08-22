"""Rebuild R1.7 monthly cohorts from fail-closed native-1d evidence only.

The canonical manifest must retain acquisition provenance, and every object
entering the ranking census must pass both the acquisition validator and an
independent second-pass summary.  Missing integrity metadata is fail-closed as
MISSING_INTEGRITY_PROVENANCE; it is never silently defaulted to PASS.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from build_r16_1d_universe import _summarize_1d_archive, build_monthly_cohorts


REQUIRED_INTEGRITY_COLUMNS = {
    "raw_path",
    "integrity_status",
    "published_sha256",
    "computed_sha256",
}


def strict_verified_manifest(manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "integrity_status" not in manifest.columns:
        raise RuntimeError("MISSING_INTEGRITY_PROVENANCE")
    """Reject missing provenance, non-PASS objects, checksum failures, and second-pass issues."""
    missing = REQUIRED_INTEGRITY_COLUMNS - set(manifest.columns)
    if missing:
        raise RuntimeError("MISSING_INTEGRITY_PROVENANCE: " + ", ".join(sorted(missing)))
    verified_indexes: list[int] = []
    exclusions: list[dict[str, object]] = []
    for index, row in manifest.iterrows():
        reason = ""
        status = str(row["integrity_status"])
        published = row["published_sha256"]
        computed = row["computed_sha256"]
        if status != "PASS":
            reason = f"ACQUISITION_{status or 'MISSING_STATUS'}"
        elif pd.isna(published) or pd.isna(computed) or not str(published) or str(published) != str(computed):
            reason = "CHECKSUM_MISMATCH_OR_MISSING"
        else:
            raw_value = row["raw_path"]
            raw_path = Path(str(raw_value)) if not pd.isna(raw_value) else Path("__MISSING_RAW__")
            if not raw_path.exists():
                reason = "MISSING_RAW"
            else:
                try:
                    summary = _summarize_1d_archive(raw_path)
                except Exception as exc:
                    reason = "SECOND_PASS_ERROR:" + type(exc).__name__
                    exclusions.append(
                        {
                            "market": row.get("market"),
                            "symbol": row.get("symbol"),
                            "archive_month": row.get("archive_month"),
                            "exclusion_reason": reason,
                        }
                    )
                    continue
                if str(summary["integrity_status"]) != "PASS":
                    reason = "SECOND_PASS_ISSUES:" + str(summary["issue_codes"])
        if reason:
            exclusions.append(
                {
                    "market": row.get("market"),
                    "symbol": row.get("symbol"),
                    "archive_month": row.get("archive_month"),
                    "exclusion_reason": reason,
                }
            )
        else:
            verified_indexes.append(index)
    columns = ["market", "symbol", "archive_month", "exclusion_reason"]
    return manifest.loc[verified_indexes].copy(), pd.DataFrame(exclusions, columns=columns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("campaigns/r1_final_panel_v1"))
    args = parser.parse_args()
    manifest = pd.read_csv(args.campaign_dir / "volume_archive_manifest.csv")
    taxonomy = pd.read_csv(args.campaign_dir / "asset_taxonomy.csv")
    verified, exclusions = strict_verified_manifest(manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    exclusions.to_csv(args.output_dir / "volume_ranking_exclusions.csv", index=False)
    ranked = build_monthly_cohorts(verified, taxonomy, args.output_dir)
    summary = ranked.groupby(["market", "universe_month"], sort=True).agg(
        candidate_count=("symbol", "size"),
        eligible_count=("rank", lambda x: int(x.notna().sum())),
        top20=("selected_top20", "sum"),
        top50=("selected_top50", "sum"),
        top100=("selected_top100", "sum"),
    ).reset_index()
    mature = summary[summary["universe_month"] >= "2024-01"]
    short = mature[mature["top50"] < 50]
    short = short.assign(requested_n=50, actual_n=short["top50"], shortfall_reason="INSUFFICIENT_ELIGIBLE_HISTORY")
    short[["market", "universe_month", "requested_n", "actual_n", "shortfall_reason"]].to_csv(args.output_dir / "top50_shortfalls.csv", index=False)
    print({"verified_objects": len(verified), "excluded_objects": len(exclusions), "cohort_rows": len(ranked)})
    print({"verified_objects": len(verified), "excluded_objects": len(exclusions), "cohort_rows": len(ranked)})
