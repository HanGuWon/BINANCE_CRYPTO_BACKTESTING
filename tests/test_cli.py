from __future__ import annotations

from pathlib import Path
import inspect
import os
import subprocess
import sys

import pandas as pd
import pytest

import binance_research.cli as cli
from binance_research.cli import _regime_table, main
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


def test_regime_attribution_uses_decision_time_not_future_entry_bar() -> None:
    times = pd.Series(pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC"))
    regimes = pd.DataFrame({"volatility_regime": ["low", "high", "panic"]})
    trades = [pd.DataFrame({"feature_id": ["sig"], "decision_time": [times.iloc[0] + pd.Timedelta(minutes=30)], "entry_bar": [2], "net_return": [0.1]})]
    result = _regime_table(trades, regimes, regime_times=times)
    assert result.loc[result["regime_type"] == "volatility_regime", "regime"].item() == "low"


def test_cli_defaults_are_repo_root_independent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli._load_config(None)["rule"]["holding_bars"] == 4
    args = cli.build_parser().parse_args(["collect", "--symbol", "BTCUSDT"])
    assert args.output == cli.REPO_ROOT / "data/raw/forward"
    download = cli.build_parser().parse_args(["download", "--market", "um", "--dataset", "klines", "--symbol", "BTCUSDT", "--year", "2024", "--month", "1"])
    assert download.raw_root == cli.REPO_ROOT / "data/raw"


def test_cli_help_subprocess_succeeds_from_unrelated_cwd(tmp_path: Path) -> None:
    env = os.environ.copy()
    src = str(cli.REPO_ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run([sys.executable, "-m", "binance_research.cli", "collect", "--symbol", "BTCUSDT", "--help"], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout


def test_reproducible_runtime_contract_documented() -> None:
    document = (cli.REPO_ROOT / "docs/REPRODUCIBLE_RUNTIME.md").read_text(encoding="utf-8")
    assert "Python 3.11" in document
    assert "python -m pytest -q tests ops/r3/tests -p no:cacheprovider" in document
    assert 'python -m pip install -e ".[dev]"' in document
