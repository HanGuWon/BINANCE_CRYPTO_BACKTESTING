"""Regression proof that the checkpoint verifier rejects the preserved v6 defect."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_r2b_checkpoints import verify  # noqa: E402
from evidence_paths import resolve_preserved_v6_root  # noqa: E402


def test_verifier_rejects_v6_execution_gap_with_exact_counts() -> None:
    V6 = resolve_preserved_v6_root()
    if V6 is None:
        pytest.skip("preserved v6 evidence root is unavailable or fails manifest lineage checks")
    with pytest.raises(SystemExit) as raised:
        verify(V6)
    result = json.loads(str(raised.value))
    assert result["status"] == "FAIL"
    assert result["exact_next_open_violations"] == 438
    assert result["exact_horizon_exit_violations"] == 4094
