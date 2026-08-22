from __future__ import annotations

from pathlib import Path
import inspect

import pandas as pd
import pytest

import binance_research.cli as cli
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


def test_cli_gap_safe_path_resets_state_after_source_gap(tmp_path: Path, bars, monkeypatch) -> None:
    gapped = bars.copy()
    gapped.loc[250:, "open_time"] += pd.Timedelta(hours=3)
    gapped.loc[250:, "close_time"] += pd.Timedelta(hours=3)
    captured = []
    original = cli.compute_gap_safe_features

    def wrapped(engine, frame, interval):
        result = original(engine, frame, interval)
        captured.append(result)
        return result

    monkeypatch.setattr(cli, "compute_gap_safe_features", wrapped)
    input_path = tmp_path / "gapped.csv"
    gapped.to_csv(input_path, index=False)
    assert main(["run", "--input", str(input_path), "--output", str(tmp_path / "artifacts"), "--timeframe", "1h", "--market", "spot"]) == 0
    assert captured
    features = captured[0]
    assert features.loc[250, "segment_id"] == 1
    assert pd.isna(features.loc[250, "rsi14"])
    assert features.loc[250, "cvd"] == pytest.approx(gapped.loc[250, "taker_buy_volume"] - (gapped.loc[250, "volume"] - gapped.loc[250, "taker_buy_volume"]))


def test_cli_explicit_final_holdout_branch_is_gap_safe_without_accessing_data() -> None:
    source = inspect.getsource(cli.run_research)
    assert source.count("compute_gap_safe_features") >= 2
    assert "if args.final_holdout" in source
