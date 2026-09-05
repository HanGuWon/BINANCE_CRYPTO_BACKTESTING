from __future__ import annotations

import json
import io
import os
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
    """Write machine artifacts into an immutable experiment directory."""

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
            buffer = io.StringIO()
            table.to_csv(buffer, index=True if "correlation" in name or "overlap" in name else False, lineterminator="\n")
            write_immutable_text(path, buffer.getvalue(), description=f"artifact {name}")
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
            f"- Origin Date: {metadata.get('origin_date') or metadata.get('timestamp') or metadata.get('created_at') or 'NOT_SPECIFIED'}",
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
            json.dumps(metadata, indent=2, sort_keys=True, default=str),
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
        write_immutable_text(path, "\n".join(lines) + "\n", description="research report")
        return path


def write_immutable_bytes(path: Path, payload: bytes, *, description: str = "artifact") -> Path:
    """Create *path* once, allowing only an exact-byte idempotent repeat.

    The exclusive create protects against concurrent writers. A symlink is
    never followed, including a dangling link, so an experiment artifact
    cannot be redirected outside its declared output directory.
    """
    destination = Path(path)
    if destination.is_symlink():
        raise ValueError(f"{description} destination must not be a symlink: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if destination.is_symlink():
            raise ValueError(f"{description} destination must not be a symlink: {destination}")
        if destination.read_bytes() != payload:
            raise ValueError(f"{description} immutable collision: {destination}")
    return destination


def write_immutable_text(path: Path, text: str, *, description: str = "artifact") -> Path:
    return write_immutable_bytes(path, text.encode("utf-8"), description=description)
