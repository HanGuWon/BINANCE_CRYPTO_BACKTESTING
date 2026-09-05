"""R1.7 final-gate regressions: absolute phase, fail-closed provenance, causal joins."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from binance_research.data import DataIntegrityError, normalize_klines, validate_klines  # noqa: E402
from binance_research.panel import resample_contiguous_source  # noqa: E402


def _kline_rows(open_times_ms: list[int]) -> pd.DataFrame:
    rows = []
    for open_time in open_times_ms:
        rows.append([open_time, 10, 12, 9, 11, 5, open_time + 899_999, 55, 10, 3, 33, 0])
    return normalize_klines(rows)


@pytest.mark.parametrize("interval,offset_minutes", [("15m", -2), ("1h", 15), ("4h", 120)])
def test_absolute_off_grid_phase_fails_closed(interval: str, offset_minutes: int) -> None:
    base = 1_735_689_600_000 + offset_minutes * 60_000 - (1_735_689_600_000 % {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[interval])
    step_ms = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[interval]
    frame = _kline_rows([base + i * step_ms for i in range(5)])
    issues = {issue.code for issue in validate_klines(frame, interval)}
    assert "OFF_GRID_PHASE" in issues


@pytest.mark.parametrize("interval,hour_offset", [("15m", 0), ("1h", 0), ("4h", 0)])
def test_on_grid_phase_passes(interval: str, hour_offset: int) -> None:
    step_ms = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[interval]
    base = 1_735_689_600_000 + 10 * 3_600_000 if interval != "4h" else 1_735_689_600_000 + 12 * 3_600_000
    frame = _kline_rows([base + i * step_ms for i in range(6)])
    issues = [issue.code for issue in validate_klines(frame, interval)]
    assert not issues


def test_resample_contiguous_source_rejects_phase() -> None:
    base = 1_735_689_600_000 - (1_735_689_600_000 % 900_000) + 14 * 60_000 + 789
    frame = _kline_rows([base + i * 900_000 for i in range(4)])
    with pytest.raises(DataIntegrityError, match="OFF_GRID_PHASE"):
        resample_contiguous_source(frame, "1h", source_interval="15m")


def test_build_monthly_cohorts_missing_integrity_raises() -> None:
    from build_r16_1d_universe import build_monthly_cohorts

    manifest = pd.DataFrame([
        {"market": "spot", "symbol": "BTCUSDT", "archive_month": "2024-01"},
    ])
    taxonomy = pd.DataFrame()
    with pytest.raises(RuntimeError, match="MISSING_INTEGRITY_PROVENANCE"):
        build_monthly_cohorts(manifest, taxonomy, Path("build/_test_cohorts"))


def test_build_monthly_cohorts_checksum_mismatch_raises(tmp_path: Path) -> None:
    from build_r16_1d_universe import build_monthly_cohorts

    manifest = pd.DataFrame([
        {
            "market": "spot",
            "symbol": "BTCUSDT",
            "archive_month": "2024-01",
            "integrity_status": "PASS",
            "published_sha256": "a" * 64,
            "computed_sha256": "b" * 64,
            "raw_path": str(tmp_path / "missing.zip"),
        },
    ])
    with pytest.raises(RuntimeError, match="CHECKSUM_MISMATCH_OR_MISSING"):
        build_monthly_cohorts(manifest, pd.DataFrame(), tmp_path)
