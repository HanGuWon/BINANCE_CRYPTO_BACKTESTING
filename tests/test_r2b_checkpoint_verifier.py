"""Regression proof that the checkpoint verifier rejects the preserved v6 defect."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_r2b_checkpoints import verify  # noqa: E402


V6 = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r2b_restricted_derivatives_v1_checkpoints_v6")


def test_verifier_rejects_v6_execution_gap_with_exact_counts() -> None:
    if not (V6 / "run_manifest.json").exists():
        pytest.skip("D-backed v6 evidence root is unavailable")
    with pytest.raises(SystemExit) as raised:
        verify(V6)
    result = json.loads(str(raised.value))
    assert result["status"] == "FAIL"
    assert result["exact_next_open_violations"] == 438
    assert result["exact_horizon_exit_violations"] == 4094
