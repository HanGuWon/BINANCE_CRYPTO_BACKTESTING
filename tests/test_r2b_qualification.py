"""Pre-outcome R2B qualification contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from r2b_qualification import qualification_gate, validate_um_matrix  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2b_restricted_derivatives_v1"


def test_r2b_qualification_matrix_is_um_only_and_complete() -> None:
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    assert len(registry) == 72
    assert set(registry.market) == {"um"}
    assert set(registry.side) == {"LONG", "SHORT"}
    assert set(registry.signal_variant) == {"PRESSURE_CONTINUATION", "CROWDING_REVERSION"}
    assert validate_um_matrix()["valid"] is True


def test_r2b_qualification_gate_is_open_only_for_frozen_semantics() -> None:
    result = qualification_gate()
    assert result["status"] == "READY_FOR_QUALIFICATION"


def test_r2b_receipt_has_no_spot_scientific_matrix() -> None:
    receipt = json.loads((CAMPAIGN / "qualification_receipt.json").read_text(encoding="utf-8"))
    assert all(not item.startswith("spot_") for item in receipt["matrix_required_if_unblocked"])
    assert receipt["spot_control_status"] == "OUT_OF_SCOPE_ENGINE_CONTROL_ONLY"


def test_r2b_slow_reference_qualification_passes_without_outcomes() -> None:
    from r2b_qualification import run_qualification

    result = run_qualification()
    assert result["status"] == "PASS"
    assert result["mode"] == "SYNTHETIC_REFERENCE_ONLY"
    assert result["outcome_run_started"] is False
    assert result["final_holdout_status"] == "UNTOUCHED"
    assert set(result["required_fields"]) >= {
        "decision_time", "signal_value", "source_available_time", "entry_time",
        "exit_time", "gross_return", "funding_cashflow", "net_return",
    }
