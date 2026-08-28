"""Structural and directional guards for the dedicated R2B runner."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from r2b_historical_runner import load_registry  # noqa: E402
from r2b_signals import side_accepts_signal  # noqa: E402


def test_historical_registry_expands_to_576_units() -> None:
    trials, folds = load_registry()
    assert len(trials) == 72
    assert len({str(row["fold_id"]) for row in folds}) == 8
    units = {(str(f["fold_id"]), str(t["trial_id"])) for f in folds for t in trials if f["timeframe"] == t["timeframe"] and int(f["horizon_bars"]) == int(t["horizon_bars"])}
    assert len(units) == 576


def test_runner_side_gate_is_strict_and_nan_safe() -> None:
    assert side_accepts_signal(1.0, "LONG")
    assert not side_accepts_signal(-1.0, "LONG")
    assert side_accepts_signal(-1.0, "SHORT")
    assert not side_accepts_signal(1.0, "SHORT")
    assert not side_accepts_signal(0.0, "LONG")
    assert not side_accepts_signal(float("nan"), "SHORT")
