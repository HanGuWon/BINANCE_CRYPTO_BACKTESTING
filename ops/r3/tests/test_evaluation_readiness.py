from __future__ import annotations

import copy
import json
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.r3.check_r3_evaluation_readiness import (  # noqa: E402
    MINIMA,
    ReadinessInputError,
    evaluate_readiness,
)


def _inventory() -> dict:
    return {
        "record_type": "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY",
        "calendar": {"observed_utc_days": MINIMA["calendar_days"], "independent_utc_6h_blocks": MINIMA["utc_6h_blocks"]},
        "cycles": {"cycle_count": 200, "duplicate_cycle_ids": 0, "missing_cycle_count": 0},
        "availability_and_gaps": {
            "gap_records": 0,
            "health_gap_count": 0,
            "health_restart_count": 0,
            "no_imputation": True,
            "strict_15m_boundary": {"rejected": 0},
        },
        "causal_input_presence": {
            "H01_execution_quality_context": {"usable_observations": MINIMA["R3_H01"]},
            "H02_price_oi_quadrant": {"usable_symbol_buckets": MINIMA["R3_H02"]},
            "H03_liquidation_continuation": {"observed_events": MINIMA["R3_H03"]},
            "H04_liquidation_reversion": {"observed_events": MINIMA["R3_H04"]},
            "H05_crowding_stress_modifier": {"usable_symbol_buckets": MINIMA["R3_H05"]},
            "H06_btc_breadth_concordance": {"usable_kline_symbol_buckets": MINIMA["R3_H06"]},
        },
        "integrity": {
            "payload_values_retained": False,
            "performance_fields_seen": False,
            "confirmatory_root_accessed": False,
            "secondary_campaign_accessed": False,
        },
    }


def _spec() -> dict:
    return {
        "final_holdout_status": "UNTOUCHED",
        "r2b2_status": "NOT_STARTED",
        "outcome_analysis_status": "NOT_STARTED",
    }


def _contract(horizon: bool = True) -> dict:
    return {
        "evaluation_horizon_keys": ["15m"] if horizon else [],
        "evaluation_horizon_sha256": "a" * 64 if horizon else "",
    }


def test_synthetic_all_minima_is_eligible_but_never_starts() -> None:
    result = evaluate_readiness(_contract(), _inventory(), _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)
    assert result["state"] == "R3_EVALUATION_ELIGIBLE_NOT_STARTED"
    assert result["auto_start"] is False
    assert result["reasons"] == []


def test_missing_horizon_is_a_hard_block_even_when_minima_are_met() -> None:
    result = evaluate_readiness(_contract(False), _inventory(), _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)
    assert result["state"] == "R3_EVALUATION_PREREGISTRATION_BLOCKED"
    assert "HORIZON_NOT_FROZEN" in result["reasons"]


def test_human_authorization_is_required_and_not_auto_started() -> None:
    result = evaluate_readiness(_contract(), _inventory(), _spec(), roster_months=["2026-08", "2026-09"], human_authorized=False)
    assert result["state"] == "R3_EVALUATION_PREREGISTRATION_BLOCKED"
    assert "HUMAN_AUTHORIZATION_MISSING" in result["reasons"]
    assert result["auto_start"] is False


def test_gap_attrition_reduces_effective_counts() -> None:
    inventory = _inventory()
    inventory["availability_and_gaps"]["health_gap_count"] = 3
    inventory["availability_and_gaps"]["health_restart_count"] = 3
    result = evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)
    assert result["gap_attrition"]["effective_hypothesis_counts"]["R3_H01"] == MINIMA["R3_H01"] - 3
    assert result["gap_attrition"]["effective_utc_6h_blocks"] == MINIMA["utc_6h_blocks"] - 1
    assert result["gates"]["hypotheses"]["R3_H01"]["pass"] is False


def test_duplicate_cycles_fail_completeness_before_eligibility() -> None:
    inventory = _inventory()
    inventory["cycles"]["duplicate_cycle_ids"] = 1
    result = evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)
    assert result["gates"]["completeness"]["pass"] is False
    assert "GLOBAL_METADATA_MINIMA_NOT_MET" in result["reasons"]


def test_strict_boundary_rejection_fails_completeness() -> None:
    inventory = _inventory()
    inventory["availability_and_gaps"]["strict_15m_boundary"]["rejected"] = 1
    result = evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)
    assert result["gates"]["completeness"]["pass"] is False


def test_absent_events_are_not_zero_imputed() -> None:
    inventory = _inventory()
    inventory["causal_input_presence"]["H03_liquidation_continuation"]["observed_events"] = 0
    result = evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)
    assert result["gates"]["hypotheses"]["R3_H03"]["observed"] == 0
    assert result["gates"]["hypotheses"]["R3_H03"]["pass"] is False


def test_roster_diversity_is_a_separate_gate() -> None:
    result = evaluate_readiness(_contract(), _inventory(), _spec(), roster_months=["2026-09"], human_authorized=True)
    assert result["gates"]["roster_months"]["pass"] is False
    assert "GLOBAL_METADATA_MINIMA_NOT_MET" in result["reasons"]


def test_forbidden_result_field_fails_closed() -> None:
    inventory = _inventory()
    inventory["future_return"] = 0.0
    with pytest.raises(ReadinessInputError):
        evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)


@pytest.mark.parametrize("token", ["outcome", "return", "pnl", "sharpe", "hit_rate", "future", "holdout", "r2b2"])
def test_broad_forbidden_tokens_fail_closed(token: str) -> None:
    inventory = _inventory()
    inventory[token + "_field"] = 1
    with pytest.raises(ReadinessInputError):
        evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)


@pytest.mark.parametrize("token", ["outcome", "return", "pnl", "sharpe", "hit_rate", "future", "holdout", "r2b2"])
def test_broad_forbidden_path_tokens_fail_closed(token: str) -> None:
    inventory = _inventory()
    inventory["path"] = "D:/metadata/" + token + "/snapshot.json"
    with pytest.raises(ReadinessInputError):
        evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)


def test_forbidden_holdout_path_fails_closed() -> None:
    inventory = _inventory()
    inventory["path"] = "D:/research/final_holdout/metadata.json"
    with pytest.raises(ReadinessInputError):
        evaluate_readiness(_contract(), inventory, _spec(), roster_months=["2026-08", "2026-09"], human_authorized=True)


def test_current_inventory_contract_is_horizon_blocked() -> None:
    inventory_path = ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903.json"
    spec_path = ROOT / "campaigns" / "r3_prospective_context_v1" / "campaign_spec.toml"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    spec = tomllib.loads(spec_path.read_text(encoding="utf-8"))
    contract = {"evaluation_horizon_keys": spec["evaluation_horizon_keys"]}
    result = evaluate_readiness(contract, inventory, spec, roster_months=[], human_authorized=False)
    assert result["state"] == "R3_EVALUATION_PREREGISTRATION_BLOCKED"
    assert "HORIZON_NOT_FROZEN" in result["reasons"]
