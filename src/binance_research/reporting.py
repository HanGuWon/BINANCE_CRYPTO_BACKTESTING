from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

import pandas as pd


REQUIRED_ARTIFACTS = (
    "indicator_summary.csv",
    "indicator_by_symbol.csv",
    "indicator_by_regime.csv",
    "indicator_by_year.csv",
    "indicator_by_month.csv",
    "predictive_horizons.csv",
    "parameter_robustness.csv",
    "feature_correlation.csv",
    "feature_clusters.csv",
    "signal_correlation.csv",
    "trade_overlap.csv",
    "return_series_correlation.csv",
    "cost_sensitivity.csv",
    "walk_forward.csv",
    "final_holdout.csv",
)


class ArtifactWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_tables(self, tables: Mapping[str, pd.DataFrame]) -> list[Path]:
        unexpected = set(tables) - set(REQUIRED_ARTIFACTS)
        if unexpected:
            raise ValueError(f"unknown artifact names: {', '.join(sorted(unexpected))}")
        paths: list[Path] = []
        for name in REQUIRED_ARTIFACTS:
            table = tables.get(name, pd.DataFrame([{"status": "INSUFFICIENT EVIDENCE"}]))
            path = self.output_dir / name
            table.to_csv(path, index=True if "correlation" in name or "overlap" in name else False)
            paths.append(path)
        return paths

    def write_report(self, metadata: dict[str, object], strongest: pd.DataFrame | None = None) -> Path:
        evidence = "INSUFFICIENT EVIDENCE"
        if strongest is not None and not strongest.empty:
            evidence = "CANDIDATES REQUIRE FORWARD SHADOW VALIDATION"
        lines = [
            "## Material Passport",
            "",
            "- Origin Skill: experiment-agent",
            "- Origin Mode: run",
            f"- Origin Date: {datetime.now(UTC).isoformat()}",
            f"- Verification Status: {metadata.get('verification_status', 'UNVERIFIED')}",
            f"- Harness Verification: {metadata.get('harness_verification_status', 'NOT_ASSERTED')}",
            f"- Experiment Evidence: {metadata.get('experiment_evidence_status', 'INSUFFICIENT EVIDENCE')}",
            f"- Campaign Readiness: {metadata.get('campaign_readiness', 'NOT_ASSERTED')}",
            "- Version Label: exp_result_v1",
            "",
            "# Research Report",
            "",
            f"**Evidence status:** `{evidence}`",
            "",
            "This report is research-only. Historical results do not establish future profitability.",
            "",
            "## Run metadata",
            "",
            "```json",
            json.dumps(metadata, indent=2, default=str),
            "```",
            "",
            "## Method and leakage protections",
            "",
            "Features use completed observations only; entries occur at the next executable open. "
            "Quantile and regime thresholds are fitted on training data, chronological partitions are "
            "embargoed, and the final test is untouched unless the run explicitly opts in.",
            "",
            "## Costs",
            "",
            "Gross and net results are separate. Net results include configured fees, bid/ask spread, "
            "slippage, latency, and aligned funding for futures.",
            "",
            "## Data availability and limitations",
            "",
            "Open-interest statistics and taker/top-trader ratios have short REST retention. Public "
            "book depth excludes RPI orders and is not guaranteed executable. Missing history is never "
            "backfilled from Alpaca or extrapolated. Negative and empty results remain in artifacts.",
        ]
        path = self.output_dir / "research_report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
