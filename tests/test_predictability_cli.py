from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

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


def test_record_forward_excludes_labels_maturing_at_prediction_cutoff(tmp_path: Path, bars, monkeypatch) -> None:
    input_path = tmp_path / "bars.csv"
    bars.to_csv(input_path, index=False)
    seen_training_rows: list[int] = []

    def fake_fit(frame, target, feature_names, regularization):
        seen_training_rows.append(len(frame))
        return SimpleNamespace(predict_proba=lambda future: np.full(len(future), 0.5))

    import binance_research.predictability_cli as predictability_cli

    monkeypatch.setattr(predictability_cli, "fit_logistic_model", fake_fit)
    output = tmp_path / "forward"
    assert main([
        "predictability",
        "record-forward",
        "--input",
        str(input_path),
        "--output",
        str(output),
        "--timeframe",
        "1h",
        "--horizons",
        "24h",
        "--train-rows",
        "120",
    ]) == 0
    assert seen_training_rows
    assert seen_training_rows[0] == 96