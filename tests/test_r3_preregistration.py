from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r3_prospective_context_v1"


def test_r3_registry_is_small_and_deterministic() -> None:
    path = CAMPAIGN / "trial_registry.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    assert len(rows) == 6
    assert digest == "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a"
    assert all(row["primary"] == "TRUE" for row in rows)


def test_launch_manifest_pins_required_contracts() -> None:
    manifest = json.loads((CAMPAIGN / "R3_LAUNCH_MANIFEST.json").read_text(encoding="utf-8"))
    required = {"implementation_commit", "source_tree_sha256", "registry_sha256", "universe_rule_sha256", "collection_contract_sha256", "feature_semantics_sha256", "statistics_contract_sha256", "final_holdout_status"}
    assert required <= manifest.keys()
    assert manifest["primary_hypothesis_count"] == 6
    assert manifest["final_holdout_status"] == "UNTOUCHED"
    assert manifest["outcome_analysis_status"] == "NOT_STARTED"


def test_launch_manifest_blocks_unverified_pilot_boundary() -> None:
    """The conformance erratum must remain the canonical launch disposition."""
    manifest = json.loads((CAMPAIGN / "R3_LAUNCH_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] in {"R3_BLOCKED_FINAL_LAUNCH_CONFORMANCE", "R3_BLOCKED_ROSTER_PROVENANCE"}
    assert manifest["pilot_status"] == "ENGINEERING_PILOT_ONLY"
    assert manifest["final_holdout_status"] == "UNTOUCHED"
    assert manifest["r2b2_status"] == "NOT_STARTED"


def test_temporal_gate_distinguishes_waiting_from_permanent_block() -> None:
    gate = json.loads((CAMPAIGN / "R3_TEMPORAL_GATE_RECEIPT.json").read_text(encoding="utf-8"))
    assert gate["stage"] == "A"
    assert gate["september_roster_status"] == "R3_WAITING_FOR_COMPLETED_AUGUST_RANKING"
    assert gate["required_boundary_utc"] == "2026-09-01T00:00:00Z"


def test_stage_a_shadow_state_cannot_authorize_scientific_collection() -> None:
    state = json.loads((CAMPAIGN / "R3_STAGE_A_STATE.json").read_text(encoding="utf-8"))
    assert state["state"] == "R3_ENGINEERING_SHADOW_VERIFIED_WAITING_FOR_AUGUST_CLOSE"
    assert state["scientific_collection"] == "NOT_ACTIVE"
    assert state["september_roster_state"] == "R3_WAITING_FOR_COMPLETED_AUGUST_RANKING"
    assert state["final_holdout"] == "UNTOUCHED"
