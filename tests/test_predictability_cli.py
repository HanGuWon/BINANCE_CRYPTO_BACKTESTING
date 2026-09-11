from __future__ import annotations

from pathlib import Path

from binance_research.cli import main


def test_predictability_audit_and_development_outputs(tmp_path: Path, bars) -> None:
    input_path = tmp_path / "bars.csv"
    bars.to_csv(input_path, index=False)
    audit_path = tmp_path / "audit.json"
    assert main(["predictability", "audit", "--input", str(input_path), "--timeframe", "1h", "--output", str(audit_path)]) == 0
    assert "DEVELOPMENT_AUDIT_ONLY" in audit_path.read_text(encoding="utf-8")
    output = tmp_path / "development"
    assert main([
        "predictability",
        "run-development",
        "--input",
        str(input_path),
        "--output",
        str(output),
        "--timeframe",
        "1h",
        "--horizons",
        "1h",
        "--minimum-train",
        "80",
        "--validation-size",
        "40",
        "--step-size",
        "40",
    ]) == 0
    assert (output / "predictability_results.csv").exists()
    assert (output / "metadata.json").exists()
    assert "UNTOUCHED" in (output / "metadata.json").read_text(encoding="utf-8")
