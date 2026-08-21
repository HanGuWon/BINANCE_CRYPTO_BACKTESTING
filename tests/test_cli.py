from __future__ import annotations

from pathlib import Path

from binance_research.cli import main
from binance_research.reporting import REQUIRED_ARTIFACTS


def test_end_to_end_validation_run_keeps_final_holdout_untouched(tmp_path: Path, bars) -> None:
    input_path = tmp_path / "bars.csv"
    output = tmp_path / "artifacts"
    bars.to_csv(input_path, index=False)
    assert main(["run", "--input", str(input_path), "--output", str(output), "--timeframe", "1h", "--market", "spot"]) == 0
    assert all((output / name).exists() for name in REQUIRED_ARTIFACTS)
    assert "UNTOUCHED" in (output / "final_holdout.csv").read_text()
    assert (output / "experiment_registry.jsonl").exists()
    assert (output / "research_report.md").exists()
    report = (output / "research_report.md").read_text(encoding="utf-8")
    assert "MISSING_INTERVAL" not in report
    assert "UNVERIFIED_BY_EXPERIMENT_RUN" in report
    assert "INSUFFICIENT EVIDENCE" in report
