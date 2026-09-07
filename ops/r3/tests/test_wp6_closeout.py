"""Append-only integrity checks for the v8 closeout receipts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
OPS = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations"
CONTINUATION = OPS / "R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION_20260907_V2.json"
CONTINUATION_OLD = OPS / "R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION_20260907.json"
V3 = OPS / "R3_V8_OUTAGE_AND_RECOVERY_20260907_V3.json"
V7 = OPS / "R3_V8_WP5_FIREWALL_RECEIPT_20260907_V7.json"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body_sha(value: dict[str, object]) -> str:
    body = dict(value)
    body.pop("body_sha256", None)
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_continuation_v2_is_append_only_and_firewalled() -> None:
    value = json.loads(CONTINUATION.read_text(encoding="utf-8"))
    assert value["record_type"] == "R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION"
    assert value["body_sha256"] == _body_sha(value)
    assert value["supersedes"]["file_sha256"] == _file_sha(CONTINUATION_OLD)
    assert value["supersedes"]["status"] == "SUPERSEDED_BY_V2"
    assert value["prerequisite_state"] == "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED"
    assert value["migration_action_in_this_goal"] == "NONE"
    assert value["forceorder_v3_migration"] == "NOT_STARTED"
    assert value["outcomes_accessed"] is False
    assert value["final_holdout"] == "UNTOUCHED"
    assert value["r2b2"] == "NOT_ACCESSED"
    assert value["guardian_evidence"]["authority_count"] == 1
    assert value["guardian_evidence"]["collector_writer_count"] == 1
    assert value["accounting_evidence"]["v3_file_sha256"] == _file_sha(V3)
    assert value["accounting_evidence"]["v7_file_sha256"] == _file_sha(V7)
    assert value["qualification"]["cases"] == value["qualification"]["pass"] == 17


def test_startup_and_scheduler_contract_remains_guardian_only() -> None:
    startup = (REPO_ROOT / "ops" / "r3" / "install_r3_v8_startup.ps1").read_text(encoding="utf-8")
    task_xml = (REPO_ROOT / "ops" / "r3" / "R3-Prospective-Scientific-v8.xml").read_text(encoding="utf-8")
    wrapper = (REPO_ROOT / "ops" / "r3" / "run_r3_v8_guardian.ps1").read_text(encoding="utf-8")
    assert "run_r3_v8_guardian.ps1" in startup
    assert "launch_r3_v8_resume.ps1" not in startup
    assert "MultipleInstancesPolicy" in task_xml and "IgnoreNew" in task_xml
    assert "StandingPolicy" in wrapper
    assert "AuthorizationMode" in wrapper
