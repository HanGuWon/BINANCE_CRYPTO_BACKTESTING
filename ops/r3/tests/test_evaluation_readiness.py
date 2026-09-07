from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.r3.check_r3_evaluation_readiness import (  # noqa: E402
    HORIZON_KEY,
    MINIMA,
    ReadinessInputError,
    _canonical_roster_hash,
    _verify_roster_artifact,
    evaluate_readiness,
    utc_6h_block_ids_for_gap,
)


def _blocks() -> list[str]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [(start + timedelta(hours=6 * index)).isoformat() for index in range(MINIMA["utc_6h_blocks"])]


def _inventory() -> dict:
    blocks = _blocks()
    return {
        "record_type": "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2",
        "calendar": {"observed_utc_days": MINIMA["calendar_days"], "independent_utc_6h_blocks": len(blocks), "eligible_by_utc_6h_block": {block: 1 for block in blocks}},
        "cycles": {"cycle_count": 200, "duplicate_cycle_ids": 0, "missing_cycle_count": 0},
        "availability_and_gaps": {"gap_records": [], "gap_accounting_complete": True, "health_gap_count": 0, "health_restart_count": 0, "source_unavailable_records": 0, "no_imputation": True, "strict_15m_boundary": {"rejected": 0}},
        "streams": {},
        "causal_input_presence": {
            "H01_execution_quality_context": {"usable_observations": MINIMA["R3_H01"]},
            "H02_price_oi_quadrant": {"usable_symbol_buckets": MINIMA["R3_H02"]},
            "H03_liquidation_continuation": {"observed_events": MINIMA["R3_H03"]},
            "H04_liquidation_reversion": {"observed_events": MINIMA["R3_H04"]},
            "H05_crowding_stress_modifier": {"usable_symbol_buckets": MINIMA["R3_H05"]},
            "H06_btc_breadth_concordance": {"usable_kline_symbol_buckets": MINIMA["R3_H06"]},
        },
        "integrity": {"payload_values_retained": False, "performance_fields_seen": False, "confirmatory_root_accessed": False, "secondary_campaign_accessed": False},
    }


def _spec() -> dict:
    return {"final_holdout_status": "UNTOUCHED", "r2b2_status": "NOT_STARTED", "outcome_analysis_status": "NOT_STARTED"}


def _contract(horizon: bool = True) -> dict:
    return {"evaluation_horizon_keys": [HORIZON_KEY] if horizon else [], "evaluation_horizon_sha256": "a" * 64 if horizon else "", "evaluation_horizon_interval": "15m", "evaluation_horizon_bars": 1, "evaluation_horizon_alternatives": []}


def _evaluate(inventory=None, contract=None, *, months=("2026-08", "2026-09"), human=True):
    return evaluate_readiness(contract or _contract(), inventory or _inventory(), _spec(), roster_months=list(months), human_authorized=human)


def test_synthetic_all_minima_is_eligible_but_never_starts() -> None:
    result = _evaluate()
    assert result["state"] == "R3_EVALUATION_ELIGIBLE_NOT_STARTED"
    assert result["auto_start"] is False
    assert result["reasons"] == []


def test_human_authorization_missing_does_not_auto_start_or_block_contract() -> None:
    result = _evaluate(human=False)
    assert result["state"] == "R3_EVALUATION_ELIGIBLE_NOT_STARTED"
    assert result["auto_start"] is False
    assert "HUMAN_AUTHORIZATION_MISSING" in result["reasons"]


def test_missing_or_multiple_horizons_are_blocked() -> None:
    result = _evaluate(contract=_contract(False))
    assert result["state"] == "R3_EVALUATION_PREREGISTRATION_BLOCKED"
    assert "HORIZON_NOT_FROZEN" in result["reasons"]
    multiple = _contract()
    multiple["evaluation_horizon_keys"] = [HORIZON_KEY, "OTHER"]
    assert _evaluate(contract=multiple)["state"] == "R3_EVALUATION_PREREGISTRATION_BLOCKED"


def test_gap_is_mapped_to_one_block_without_aggregate_subtraction() -> None:
    inventory = _inventory()
    inventory["availability_and_gaps"]["gap_records"] = [{"category": "RESTART_GAP", "start_time": "2026-01-01T01:00:00+00:00"}]
    result = _evaluate(inventory=inventory)
    assert result["gap_accounting"]["excluded_block_ids"] == ["2026-01-01T00:00:00+00:00"]
    assert result["gap_accounting"]["excluded_block_count"] == 1
    assert result["gap_attrition"]["raw_utc_6h_blocks"] == MINIMA["utc_6h_blocks"]
    assert result["gap_attrition"]["effective_utc_6h_blocks"] == MINIMA["utc_6h_blocks"] - 1
    assert result["gap_attrition"]["raw_hypothesis_counts"] == result["gap_attrition"]["effective_hypothesis_counts"]


def test_overlapping_gap_records_count_once_and_spanning_gap_hits_both_blocks() -> None:
    assert utc_6h_block_ids_for_gap("2026-01-01T05:59:00+00:00", "2026-01-01T06:00:00+00:00") == ("2026-01-01T00:00:00+00:00", "2026-01-01T06:00:00+00:00")
    inventory = _inventory()
    inventory["availability_and_gaps"]["gap_records"] = [
        {"category": "SOURCE_UNAVAILABLE", "start_time": "2026-01-01T01:00:00+00:00"},
        {"category": "RESTART_GAP", "start_time": "2026-01-01T02:00:00+00:00"},
        {"category": "MISSING_CYCLE", "start_time": "2026-01-01T05:59:00+00:00", "end_time": "2026-01-01T06:01:00+00:00"},
    ]
    result = _evaluate(inventory=inventory)
    assert result["gap_accounting"]["excluded_block_count"] == 2
    assert set(result["gap_accounting"]["block_reasons"]["2026-01-01T00:00:00+00:00"]) == {"MISSING_CYCLE", "RESTART_GAP", "SOURCE_UNAVAILABLE"}


def test_positive_aggregate_gap_without_explicit_record_fails_closed() -> None:
    inventory = _inventory()
    inventory["availability_and_gaps"]["health_gap_count"] = 1
    with pytest.raises(ReadinessInputError, match="aggregate gap"):
        _evaluate(inventory=inventory)


@pytest.mark.parametrize("record", [{"category": "UNKNOWN", "start_time": "2026-01-01T00:00:00+00:00"}, {"category": "RESTART_GAP"}, {"category": "RESTART_GAP", "start_time": "not-a-time"}, {"category": "RESTART_GAP", "start_time": "2026-01-01T06:00:00+00:00", "end_time": "2026-01-01T00:00:00+00:00"}])
def test_malformed_gap_records_fail_closed(record: dict) -> None:
    inventory = _inventory()
    inventory["availability_and_gaps"]["gap_records"] = [record]
    with pytest.raises(ReadinessInputError):
        _evaluate(inventory=inventory)


def test_missing_cycle_is_accounted_not_silently_discarded() -> None:
    inventory = _inventory()
    inventory["cycles"]["missing_cycle_count"] = 1
    inventory["availability_and_gaps"]["gap_records"] = [{"category": "MISSING_CYCLE", "start_time": "2026-01-02T00:00:00+00:00"}]
    result = _evaluate(inventory=inventory)
    assert result["gates"]["completeness"]["missing_cycle_count"] == 1
    assert result["gates"]["completeness"]["pass"] is True


def test_duplicate_cycles_and_strict_boundary_fail_completeness() -> None:
    inventory = _inventory()
    inventory["cycles"]["duplicate_cycle_ids"] = 1
    inventory["availability_and_gaps"]["strict_15m_boundary"]["rejected"] = 1
    result = _evaluate(inventory=inventory)
    assert result["gates"]["completeness"]["pass"] is False
    assert result["state"] == "R3_EVALUATION_PREREGISTRATION_BLOCKED"


def test_minima_shortfall_is_collection_continues_not_preregistration_block() -> None:
    inventory = _inventory()
    inventory["causal_input_presence"]["H03_liquidation_continuation"]["observed_events"] = 0
    result = _evaluate(inventory=inventory)
    assert result["state"] == "R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES"
    assert result["gates"]["hypotheses"]["R3_H03"]["pass"] is False


def test_roster_diversity_is_a_separate_gate() -> None:
    result = _evaluate(months=("2026-09",))
    assert result["gates"]["roster_months"]["pass"] is False
    assert result["state"] == "R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES"


def test_forbidden_result_field_and_path_fail_closed() -> None:
    inventory = _inventory()
    inventory["future_return"] = 0.0
    with pytest.raises(ReadinessInputError):
        _evaluate(inventory=inventory)


def test_outcome_values_accessed_true_is_an_integrity_block() -> None:
    inventory = _inventory()
    inventory["outcome_values_accessed"] = True
    with pytest.raises(ReadinessInputError, match="outcome_values_accessed"):
        _evaluate(inventory=inventory)
    inventory = _inventory()
    inventory["path"] = "D:/research/final_holdout/metadata.json"
    with pytest.raises(ReadinessInputError):
        _evaluate(inventory=inventory)


def test_outcome_values_accessed_false_is_preserved_as_metadata_only() -> None:
    inventory = _inventory()
    inventory["outcome_values_accessed"] = False
    result = _evaluate(inventory=inventory)
    assert result["firewall"]["metadata_only"] is True
    assert result["firewall"]["outcome_values_accessed"] is False


def _roster_fixture(tmp_path: Path, month: str = "2026-10") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / f"ranking_{month}.json"
    source.write_text("ranking metadata", encoding="utf-8")
    value = {"effective_end": f"{month}-28T23:59:59+00:00", "effective_month": month, "effective_start": f"{month}-01T00:00:00+00:00", "market": "um", "prior_ranking": [{"symbol": "AAAUSDT", "rank": 1}], "roster_sha256": "", "schema": "r3_roster_v1", "source_path": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "symbols": ["AAAUSDT"]}
    value["roster_sha256"] = _canonical_roster_hash(value)
    path = tmp_path / f"{month}.json"
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    (tmp_path / f"{month}_replay.json").write_text(json.dumps({"replayed": True, "roster_sha256": value["roster_sha256"], "status": "PASS"}), encoding="utf-8")
    return path


def test_roster_hash_and_replay_are_verified(tmp_path: Path) -> None:
    path = _roster_fixture(tmp_path)
    assert _verify_roster_artifact(path) == "2026-10"


def test_roster_source_or_replay_tampering_fails_closed(tmp_path: Path) -> None:
    path = _roster_fixture(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["roster_sha256"] = "0" * 64
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ReadinessInputError, match="roster hash"):
        _verify_roster_artifact(path)


def test_current_v1_inventory_is_not_accepted_as_v2_gap_input() -> None:
    inventory_path = ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    with pytest.raises(ReadinessInputError, match="gap_records"):
        _evaluate(inventory=inventory)
